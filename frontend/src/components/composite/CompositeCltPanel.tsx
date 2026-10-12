import { useEffect, useState } from "react";
import {
  computeClt,
  fetchCompositeMaterials,
  type CltResult,
  type CompositeMaterial,
} from "../../api/composite";

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

export function formatAbd(v: number): string {
  if (!Number.isFinite(v) || Math.abs(v) < 1e-8) return "0";
  const a = Math.abs(v);
  if (a >= 1e6 || a < 0.01) return v.toExponential(3);
  return v.toFixed(2);
}

export function AbdTable({
  title,
  unit,
  headers,
  values,
}: {
  title: string;
  unit: string;
  headers: string[];
  values: number[][];
}) {
  return (
    <div className="composite-abd-block">
      <p className="composite-expert-title">
        {title} · {unit}
      </p>
      <table className="doe-table composite-abd-table">
        <thead>
          <tr>
            <th />
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {values.map((row, i) => (
            <tr key={headers[i]}>
              <th scope="row">{headers[i]}</th>
              {row.map((cell, j) => (
                <td key={`${i}-${j}`}>{formatAbd(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CompositeCltPanel() {
  const [materials, setMaterials] = useState<CompositeMaterial[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rows, setRows] = useState<PlyRow[]>([]);
  const [nextKey, setNextKey] = useState(1);
  const [computing, setComputing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<CltResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCompositeMaterials()
      .then((list) => {
        if (cancelled) return;
        setMaterials(list);
        setLoadError(null);
        setLoaded(true);
        const first = list[0];
        if (first) {
          setRows([
            { key: 1, materialId: first.id, angle: "0", thickness: "0.125" },
            { key: 2, materialId: first.id, angle: "90", thickness: "0.125" },
            { key: 3, materialId: first.id, angle: "0", thickness: "0.125" },
          ]);
          setNextKey(4);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Ply listesi alınamadı.");
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  async function handleCompute() {
    setFormError(null);
    if (rows.length === 0) {
      setFormError("En az bir katman gerekli.");
      return;
    }
    const plies = [];
    for (const row of rows) {
      const mat = materials.find((m) => m.id === row.materialId);
      const angle = parseFinite(row.angle);
      const thickness = parsePositive(row.thickness);
      if (!mat || angle === null || thickness === null) {
        setFormError("Her katmanda malzeme, açı ve pozitif kalınlık olmalı.");
        return;
      }
      plies.push({
        e1: mat.e1,
        e2: mat.e2,
        g12: mat.g12,
        nu12: mat.nu12,
        thickness_mm: thickness,
        angle_deg: angle,
      });
    }
    setComputing(true);
    try {
      const abd = await computeClt(plies);
      setResult(abd);
    } catch (err: unknown) {
      setResult(null);
      setFormError(err instanceof Error ? err.message : "CLT hesaplanamadı.");
    } finally {
      setComputing(false);
    }
  }

  return (
    <div className="panel material-panel composite-clt" data-testid="composite-clt">
      <span className="eyebrow">Faz 3 · CLT</span>
      <h1>CLT önizleme</h1>
      <p className="lead material-lead">
        Katmanlar alt → üst. A N/mm, B N, D N·mm. Araç dizilim önermez — matrisler sayı.
      </p>
      {loadError && <p className="filename">{loadError}</p>}
      {!loaded && !loadError && <p className="filename">Ply listesi yükleniyor…</p>}
      {loaded && !loadError && materials.length === 0 && (
        <p className="filename">Kütüphane boş.</p>
      )}
      {materials.length > 0 && (
        <>
          <div className="doe-table-scroll composite-clt-scroll">
            <table className="doe-table composite-clt-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ply</th>
                  <th>θ °</th>
                  <th>t mm</th>
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
          <div className="material-action-row">
            <button type="button" className="material-secondary-button" onClick={addRow}>
              + Katman
            </button>
            <button
              type="button"
              className="material-secondary-button"
              disabled={computing}
              onClick={() => void handleCompute()}
            >
              {computing ? "Hesaplanıyor…" : "ABD hesapla"}
            </button>
          </div>
        </>
      )}
      {formError && <p className="filename">{formError}</p>}
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
