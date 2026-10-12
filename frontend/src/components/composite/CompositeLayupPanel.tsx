import { useEffect, useState } from "react";
import {
  computeClt,
  fetchCompositeLayups,
  fetchCompositeMaterials,
  putCompositeLayup,
  type CltResult,
  type CompositeMaterial,
} from "../../api/composite";
import { AbdTable } from "./CompositeCltPanel";

type PlyRow = {
  key: number;
  materialId: number;
  angle: string;
  thickness: string;
};

const VOIGT_A = ["Nx", "Ny", "Nxy"];
const VOIGT_D = ["Mx", "My", "Mxy"];

function parseFinite(raw: string): number | null {
  const n = Number(raw.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function parsePositive(raw: string): number | null {
  const n = parseFinite(raw);
  return n !== null && n > 0 ? n : null;
}

function toCltPlies(rows: PlyRow[], materials: CompositeMaterial[]) {
  const plies = [];
  for (const row of rows) {
    const mat = materials.find((m) => m.id === row.materialId);
    const angle = parseFinite(row.angle);
    const thickness = parsePositive(row.thickness);
    if (!mat || angle === null || thickness === null) return null;
    plies.push({
      e1: mat.e1,
      e2: mat.e2,
      g12: mat.g12,
      nu12: mat.nu12,
      thickness_mm: thickness,
      angle_deg: angle,
    });
  }
  return plies.length ? plies : null;
}

export default function CompositeLayupPanel({
  geometryId,
  partIds,
  selectedPartId,
}: {
  geometryId: number | null;
  partIds: number[];
  selectedPartId: number | null;
}) {
  const [materials, setMaterials] = useState<CompositeMaterial[]>([]);
  const [partId, setPartId] = useState(partIds[0] ?? 0);
  const [rows, setRows] = useState<PlyRow[]>([]);
  const [nextKey, setNextKey] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<CltResult | null>(null);

  useEffect(() => {
    if (selectedPartId != null && partIds.includes(selectedPartId)) {
      setPartId(selectedPartId);
      return;
    }
    if (!partIds.includes(partId)) {
      setPartId(partIds[0] ?? 0);
    }
  }, [selectedPartId, partIds, partId]);

  useEffect(() => {
    let cancelled = false;
    fetchCompositeMaterials()
      .then((list) => {
        if (!cancelled) setMaterials(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Ply listesi alınamadı.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (geometryId == null) {
      setRows([]);
      setResult(null);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    fetchCompositeLayups(geometryId, partId)
      .then((layups) => {
        if (cancelled) return;
        const layup = layups[0];
        setLoadError(null);
        if (!layup) {
          setRows([]);
          return;
        }
        setRows(
          layup.plies.map((p, i) => ({
            key: i + 1,
            materialId: p.material_id,
            angle: String(p.angle_deg),
            thickness: String(p.thickness_mm),
          })),
        );
        setNextKey(layup.plies.length + 1);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setRows([]);
        setLoadError(err instanceof Error ? err.message : "Dizilim alınamadı.");
      });
    return () => {
      cancelled = true;
    };
  }, [geometryId, partId]);

  useEffect(() => {
    const plies = toCltPlies(rows, materials);
    if (!plies) {
      setResult(null);
      return;
    }
    const timer = window.setTimeout(() => {
      computeClt(plies)
        .then(setResult)
        .catch(() => setResult(null));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [rows, materials]);

  function setRow(key: number, patch: Partial<PlyRow>) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function addRow() {
    const materialId = rows[rows.length - 1]?.materialId ?? materials[0]?.id;
    if (materialId == null) return;
    setRows((prev) => [
      ...prev,
      { key: nextKey, materialId, angle: "0", thickness: "0.125" },
    ]);
    setNextKey((k) => k + 1);
  }

  function removeRow(key: number) {
    setRows((prev) => prev.filter((r) => r.key !== key));
  }

  function moveRow(key: number, dir: -1 | 1) {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.key === key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      const tmp = next[i];
      next[i] = next[j];
      next[j] = tmp;
      return next;
    });
  }

  async function handleSave() {
    setSaveError(null);
    if (geometryId == null) {
      setSaveError("Geometri yok.");
      return;
    }
    const stored = [];
    for (const row of rows) {
      const angle = parseFinite(row.angle);
      const thickness = parsePositive(row.thickness);
      if (angle === null || thickness === null) {
        setSaveError("Her katmanda malzeme, açı ve pozitif kalınlık olmalı.");
        return;
      }
      stored.push({
        material_id: row.materialId,
        thickness_mm: thickness,
        angle_deg: angle,
      });
    }
    if (stored.length === 0) {
      setSaveError("En az bir katman gerekli.");
      return;
    }
    setSaving(true);
    try {
      await putCompositeLayup({
        geometry_id: geometryId,
        part_id: partId,
        plies: stored,
      });
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Dizilim kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel material-panel composite-layup" data-testid="composite-layup">
      <span className="eyebrow">Faz 3 · Dizilim</span>
      <h1>Dizilim</h1>
      <p className="lead material-lead">
        Katmanlar alt → üst. θ °, t mm. ABD canlı (A N/mm, B N, D N·mm). Araç dizilim önermez.
      </p>
      {geometryId == null && <p className="filename">Geometri yükle (1 · GEOMETRY).</p>}
      {geometryId != null && (
        <label className="mesh-field material-field">
          <span>Parça</span>
          <select
            aria-label="Parça"
            value={partId}
            onChange={(e) => setPartId(Number(e.target.value))}
          >
            {(partIds.length ? partIds : [partId]).map((id) => (
              <option key={id} value={id}>
                #{id}
              </option>
            ))}
          </select>
        </label>
      )}
      {loadError && <p className="filename">{loadError}</p>}
      {geometryId != null && materials.length > 0 && (
        <>
          <div className="doe-table-scroll composite-clt-scroll">
            <table className="doe-table composite-clt-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ply</th>
                  <th>θ °</th>
                  <th>t mm</th>
                  <th>Sıra</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.key}>
                    <td>{i + 1}</td>
                    <td>
                      <select
                        aria-label={`Katman ${i + 1} ply`}
                        value={row.materialId}
                        onChange={(e) => setRow(row.key, { materialId: Number(e.target.value) })}
                      >
                        {materials.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        aria-label={`Katman ${i + 1} açı`}
                        value={row.angle}
                        onChange={(e) => setRow(row.key, { angle: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`Katman ${i + 1} kalınlık`}
                        value={row.thickness}
                        onChange={(e) => setRow(row.key, { thickness: e.target.value })}
                      />
                    </td>
                    <td className="composite-order-cell">
                      <button
                        type="button"
                        className="material-secondary-button"
                        aria-label={`Katman ${i + 1} yukarı`}
                        disabled={i === 0}
                        onClick={() => moveRow(row.key, -1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="material-secondary-button"
                        aria-label={`Katman ${i + 1} aşağı`}
                        disabled={i === rows.length - 1}
                        onClick={() => moveRow(row.key, 1)}
                      >
                        ↓
                      </button>
                    </td>
                    <td>
                      <button type="button" className="material-secondary-button" onClick={() => removeRow(row.key)}>
                        Sil
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length === 0 && <p className="filename">Katman yok.</p>}
          <div className="material-action-row">
            <button type="button" className="material-secondary-button" onClick={addRow} disabled={materials.length === 0}>
              + Katman
            </button>
            <button
              type="button"
              className="material-secondary-button"
              disabled={saving}
              onClick={() => void handleSave()}
            >
              {saving ? "Kaydediliyor…" : "Kaydet"}
            </button>
          </div>
        </>
      )}
      {saveError && <p className="filename">{saveError}</p>}
      {result && (
        <div className="composite-abd" data-testid="composite-abd">
          <p className="filename">
            n = {result.n_plies} · h = {result.h_mm} mm
          </p>
          <div className="composite-abd-grid">
            <AbdTable title="A" unit="N/mm" headers={VOIGT_A} values={result.A_N_per_mm} />
            <AbdTable title="B" unit="N" headers={VOIGT_A} values={result.B_N} />
            <AbdTable title="D" unit="N·mm" headers={VOIGT_D} values={result.D_N_mm} />
          </div>
        </div>
      )}
    </div>
  );
}
