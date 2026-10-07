/**
 * Yerel eleman boyutu / remesh (kullanıcı 2026-10-07). Viewport'ta YÜZEY
 * modunda seçilen yüzeylere ayrı eleman boyutu verilir; liste bir sonraki
 * mesh üretiminde de kullanılır (bölgesel sıklaştırma / seyreltme kalıcı).
 */
import { useState } from "react";

export default function MeshRemeshPanel({
  selectedFaceIds,
  faceSizes,
  onChange,
  onRemesh,
  globalSize,
  disabled = false,
  hasMesh,
}: {
  selectedFaceIds: number[];
  faceSizes: Record<number, number>;
  onChange: (next: Record<number, number>) => void;
  /** Verilen yerel boyutlarla mesh'i yeniden üret. */
  onRemesh: (sizes: Record<number, number>) => void;
  globalSize: string;
  disabled?: boolean;
  hasMesh: boolean;
}) {
  const [size, setSize] = useState("");
  const value = Number(size);
  const sizeOk = size.trim() !== "" && Number.isFinite(value) && value > 0;
  const entries = Object.entries(faceSizes).map(([k, v]) => [Number(k), v] as const);

  function applySelected() {
    if (!sizeOk || selectedFaceIds.length === 0) return;
    const next = { ...faceSizes };
    for (const f of selectedFaceIds) next[f] = value;
    onChange(next);
    onRemesh(next);
  }

  function remove(face: number) {
    const next = { ...faceSizes };
    delete next[face];
    onChange(next);
  }

  return (
    <section className="remesh-panel" aria-label="Yerel boyut / remesh" data-testid="remesh-panel">
      <p className="material-assignments-title">Yerel boyut / remesh</p>
      <p className="crash-behavior-hint">
        Viewport'ta YÜZEY modunda yüzey(ler) seç, boyutu yaz, uygula: yalnız o yüzeyler bu boyutla
        yeniden mesh'lenir, diğerleri {globalSize || "global"} mm kalır. Liste sonraki mesh'lerde de geçerli.
        Yüzey seçmek için mesh görünümünü kapat (viewport solundaki ızgara düğmesi).
      </p>
      <div className="remesh-row">
        <span className="remesh-sel">
          {selectedFaceIds.length ? `${selectedFaceIds.length} yüzey seçili` : "yüzey seçilmedi"}
        </span>
        <label className="crash-unit-field">
          <span className="crash-unit-box">
            <input
              aria-label="Yerel eleman boyutu"
              placeholder="ör. 3"
              value={size}
              disabled={disabled}
              onChange={(e) => setSize(e.target.value)}
            />
            <em>mm</em>
          </span>
        </label>
        <button
          type="button"
          className="material-secondary-button"
          disabled={disabled || !sizeOk || selectedFaceIds.length === 0}
          onClick={applySelected}
        >
          Seçili yüzeylere uygula + remesh
        </button>
      </div>
      {entries.length > 0 && (
        <div className="remesh-chips" aria-label="Yerel boyutlar">
          {entries.map(([face, s]) => (
            <span key={face} className="remesh-chip">
              yüzey {face} · {s} mm
              <button type="button" aria-label={`Yüzey ${face} yerel boyutunu kaldır`} disabled={disabled} onClick={() => remove(face)}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <button
        type="button"
        className="material-secondary-button"
        disabled={disabled || !hasMesh}
        onClick={() => onRemesh(faceSizes)}
      >
        Tümünü yeniden mesh'le
      </button>
    </section>
  );
}
