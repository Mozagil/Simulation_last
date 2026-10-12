import { useEffect, useState } from "react";
import {
  fetchCompositeOrientations,
  putCompositeOrientation,
} from "../../api/composite";

export type FiberZero = {
  origin: [number, number, number];
  dir: [number, number, number];
};

function parseFinite(raw: string): number | null {
  const n = Number(raw.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function triple(x: string, y: string, z: string): [number, number, number] | null {
  const a = parseFinite(x);
  const b = parseFinite(y);
  const c = parseFinite(z);
  if (a === null || b === null || c === null) return null;
  return [a, b, c];
}

export default function CompositeRosettePanel({
  geometryId,
  partIds,
  selectedPartId,
  selectedFaceIds,
  onFiberZero,
}: {
  geometryId: number | null;
  partIds: number[];
  selectedPartId: number | null;
  selectedFaceIds: number[];
  onFiberZero?: (marker: FiberZero | null) => void;
}) {
  const [partId, setPartId] = useState(partIds[0] ?? 0);
  const [dx, setDx] = useState("1");
  const [dy, setDy] = useState("0");
  const [dz, setDz] = useState("0");
  const [ox, setOx] = useState("0");
  const [oy, setOy] = useState("0");
  const [oz, setOz] = useState("0");
  const [target, setTarget] = useState<"part" | "faces">("part");
  const [faceIds, setFaceIds] = useState<number[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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
    if (geometryId == null) {
      setLoadError(null);
      onFiberZero?.(null);
      return;
    }
    let cancelled = false;
    fetchCompositeOrientations(geometryId, partId)
      .then((rows) => {
        if (cancelled) return;
        setLoadError(null);
        const row = rows[0];
        if (!row) {
          setDx("1");
          setDy("0");
          setDz("0");
          setOx("0");
          setOy("0");
          setOz("0");
          setTarget("part");
          setFaceIds([]);
          return;
        }
        setDx(String(row.dir0[0] ?? 1));
        setDy(String(row.dir0[1] ?? 0));
        setDz(String(row.dir0[2] ?? 0));
        setOx(String(row.origin[0] ?? 0));
        setOy(String(row.origin[1] ?? 0));
        setOz(String(row.origin[2] ?? 0));
        setTarget(row.target === "faces" ? "faces" : "part");
        setFaceIds(row.face_ids ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Rozet alınamadı.");
      });
    return () => {
      cancelled = true;
    };
    // onFiberZero App setState — sabit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometryId, partId]);

  useEffect(() => {
    const dir = triple(dx, dy, dz);
    const origin = triple(ox, oy, oz);
    if (!dir || !origin || (dir[0] === 0 && dir[1] === 0 && dir[2] === 0)) {
      onFiberZero?.(null);
      return;
    }
    onFiberZero?.({ origin, dir });
  }, [dx, dy, dz, ox, oy, oz, onFiberZero]);

  async function handleSave() {
    setSaveError(null);
    if (geometryId == null) {
      setSaveError("Geometri yok.");
      return;
    }
    const dir = triple(dx, dy, dz);
    const origin = triple(ox, oy, oz);
    if (!dir || !origin) {
      setSaveError("dir0 ve origin sayı olmalı.");
      return;
    }
    if (target === "faces" && faceIds.length === 0) {
      setSaveError("Yüzey seçimi boş.");
      return;
    }
    setSaving(true);
    try {
      await putCompositeOrientation({
        geometry_id: geometryId,
        part_id: partId,
        kind: "parallel",
        dir0: dir,
        origin,
        target,
        face_ids: target === "faces" ? faceIds : [],
      });
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Rozet kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel material-panel composite-rosette" data-testid="composite-rosette">
      <span className="eyebrow">Faz 3 · Rozet</span>
      <h1>Rozet + OSS</h1>
      <p className="lead material-lead">
        Paralel rozet. 0° = dir0 (varsayılan global X). Atama: parça veya seçili yüzey. Araç yön
        önermez.
      </p>
      {geometryId == null && <p className="filename">Geometri yükle (1 · GEOMETRY).</p>}
      {geometryId != null && (
        <>
          <label className="mesh-field material-field">
            <span>Parça</span>
            <select
              aria-label="Rozet parça"
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
          <p className="filename">tür · paralel</p>
          <p className="composite-expert-title">0° yön (dir0)</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>dx</span>
              <input aria-label="dir0 x" value={dx} onChange={(e) => setDx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>dy</span>
              <input aria-label="dir0 y" value={dy} onChange={(e) => setDy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>dz</span>
              <input aria-label="dir0 z" value={dz} onChange={(e) => setDz(e.target.value)} />
            </label>
          </div>
          <p className="composite-expert-title">Orijin (mm)</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>x</span>
              <input aria-label="origin x" value={ox} onChange={(e) => setOx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>y</span>
              <input aria-label="origin y" value={oy} onChange={(e) => setOy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>z</span>
              <input aria-label="origin z" value={oz} onChange={(e) => setOz(e.target.value)} />
            </label>
          </div>
          <label className="mesh-field material-field">
            <span>OSS</span>
            <select
              aria-label="OSS hedef"
              value={target}
              onChange={(e) => setTarget(e.target.value === "faces" ? "faces" : "part")}
            >
              <option value="part">parça</option>
              <option value="faces">seçili yüzeyler</option>
            </select>
          </label>
          {target === "faces" && (
            <>
              <p className="filename">
                yüzey: {faceIds.length ? faceIds.join(", ") : "yok"}
              </p>
              <button
                type="button"
                className="material-secondary-button"
                disabled={selectedFaceIds.length === 0}
                onClick={() => setFaceIds([...selectedFaceIds])}
              >
                Seçimi al
              </button>
            </>
          )}
          {loadError && <p className="filename">{loadError}</p>}
          {saveError && <p className="filename">{saveError}</p>}
          <div className="material-action-row">
            <button
              type="button"
              className="material-secondary-button"
              disabled={saving}
              onClick={() => void handleSave()}
            >
              {saving ? "Kaydediliyor…" : "Rozet kaydet"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
