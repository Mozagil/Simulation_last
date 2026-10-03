import { useEffect, useState } from "react";
import { setMaterialCrashCurves, type Material } from "../api/materials";
import { parseCurvePoints } from "./CrashMaterialCard";

/** Malzeme kütüphanesinde LAW36 akma eğrileri (1.17g-3, backend 1.14c2).
 * Crash'te LAW36 seçili ve "eğriler malzemeden" işaretliyse bu eğriler
 * kullanılır. Kütüphane malzemesi (is_editable = false) yalnız okunur. */

interface Row {
  id: number;
  rate: string;
  points: string;
}

let seq = 0;

function rowsFrom(m: Material): Row[] {
  const curves = m.crash_curves ?? [];
  return curves.map((c) => {
    seq += 1;
    return { id: seq, rate: String(c.eps_dot_per_s), points: c.points.map(([x, y]) => `${x} ${y}`).join("\n") };
  });
}

export default function MaterialCrashCurves({
  material,
  onSaved,
}: {
  material: Material;
  onSaved: (m: Material) => void;
}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>(() => rowsFrom(material));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setRows(rowsFrom(material));
    setMsg(null);
  }, [material]);

  const n = material.crash_curves?.length ?? 0;

  async function save(clear = false) {
    setBusy(true);
    setMsg(null);
    try {
      const curves = clear
        ? null
        : rows.map((r, i) => ({
            eps_dot_per_s: Number(r.rate.replace(",", ".")),
            points: parseCurvePoints(r.points, `Eğri ${i + 1}`),
          }));
      if (curves && curves.some((c) => !Number.isFinite(c.eps_dot_per_s))) {
        throw new Error("Eğri hızı (ε̇) sayı olmalı.");
      }
      const m = await setMaterialCrashCurves(material.id, curves && curves.length ? curves : null);
      onSaved(m);
      setMsg(clear ? "Eğriler silindi." : `${m.crash_curves?.length ?? 0} eğri kaydedildi.`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="material-crash-curves" data-testid="material-crash-curves">
      <button type="button" className="material-advanced-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} Crash LAW36 eğrileri · {n > 0 ? `${n} eğri` : "yok"}
      </button>
      {open && (
        <>
          {!material.is_editable && (
            <p className="material-assign-hint">
              Kütüphane malzemesi değiştirilemez — eğri için "+ ÖZEL" ile kullanıcı malzemesi oluşturun.
            </p>
          )}
          {rows.map((r, i) => (
            <div key={r.id} className="crash-mat-curve">
              <div className="crash-contact-head">
                <strong>Eğri {i + 1}</strong>
                <label className="crash-mat-rate">
                  <span>ε̇ (1/s)</span>
                  <input
                    aria-label={`Malzeme eğri ${i + 1} ε̇`}
                    value={r.rate}
                    disabled={!material.is_editable || busy}
                    onChange={(e) => setRows((rs) => rs.map((x) => (x.id === r.id ? { ...x, rate: e.target.value } : x)))}
                  />
                </label>
                {material.is_editable && (
                  <button
                    type="button"
                    className="crash-contact-remove"
                    aria-label={`Malzeme eğri ${i + 1} sil`}
                    disabled={busy}
                    onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}
                  >
                    ×
                  </button>
                )}
              </div>
              <textarea
                aria-label={`Malzeme eğri ${i + 1} noktaları`}
                className="crash-mat-points"
                rows={4}
                placeholder={"ε_p  σ (MPa)\n0     235\n0.2   320"}
                value={r.points}
                disabled={!material.is_editable || busy}
                onChange={(e) => setRows((rs) => rs.map((x) => (x.id === r.id ? { ...x, points: e.target.value } : x)))}
              />
            </div>
          ))}
          {material.is_editable && (
            <div className="material-action-row">
              <button
                type="button"
                className="material-secondary-button"
                disabled={busy}
                onClick={() => {
                  seq += 1;
                  setRows((rs) => [...rs, { id: seq, rate: "0", points: "" }]);
                }}
              >
                + Eğri
              </button>
              <button type="button" className="material-assign-button" disabled={busy || rows.length === 0} onClick={() => void save()}>
                Kaydet
              </button>
              {n > 0 && (
                <button type="button" className="material-secondary-button" disabled={busy} onClick={() => void save(true)}>
                  Sil
                </button>
              )}
            </div>
          )}
          {msg && <p className="material-assign-hint">{msg}</p>}
          <p className="material-assign-hint">
            Satır başına ε_p ve gerçek gerilme σ (MPa); ε_p kesin artan, eğriler ε̇ artan. Crash kartında
            LAW36 + "eğriler malzemeden" seçilince bu eğriler kullanılır.
          </p>
        </>
      )}
    </div>
  );
}
