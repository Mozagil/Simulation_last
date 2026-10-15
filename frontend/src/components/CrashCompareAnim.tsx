/** 1.23 C5 — koşuların deforme şekli yan yana, ortak fiziksel zamanla.
 *
 * Zaman ekseni koşuların birleşimi (0 … en uzun t_end); kısa koşu kendi son
 * karesinde kalır ("koşu sonu"). Her pencerenin renk skaleri, ölçeği ve görünümü
 * ayrı seçilir. 1.23 C5b: isteğe bağlı ortak renk ölçeği (aynı skalerde koşuların
 * min–max birleşimi) ve kamera eşleme. 1.25b: N koşu ızgarada (Sol/Sağ yerine) +
 * "Büyük pencere" (tam ekran). Yorum yok, veri gösterir.
 */

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import CrashAnimationViewer, { CameraLink, PLAY_SPEEDS } from "./CrashAnimationViewer";

export interface AnimRef {
  id: number;
  title: string;
}

/** 1× hızda tüm aralık ~3 sn (tek pencereli oynatmayla aynı). */
const PLAY_SECONDS = 3;

type ScalarState = { scalar: string; meta?: { min: number; max: number } } | null;

/** 1.23 C5b / 1.25b — ortak ölçek: tüm pencereler aynı skalerdeyse min–max birleşimi, yoksa null. */
export function commonRange(states: ScalarState[]): [number, number] | null {
  if (states.length < 2) return null;
  const first = states[0]?.scalar;
  if (states.some((s) => !s?.meta || s.scalar !== first)) return null;
  return [Math.min(...states.map((s) => s!.meta!.min)), Math.max(...states.map((s) => s!.meta!.max))];
}

export function timeSpan(...lists: (number[] | null | undefined)[]): [number, number] | null {
  const all = lists.flatMap((l) => l ?? []);
  if (all.length < 2) return null;
  return [Math.min(...all), Math.max(...all)];
}

/** 1.25b — ızgara sütun sayısı: 2 → 2, 3 → 3, 4 → 2×2, 5–6 → 3. */
export function gridColumns(n: number): number {
  if (n <= 2) return Math.max(1, n);
  if (n === 4) return 2;
  return 3;
}

export default function CrashCompareAnim({ runs, onClose }: { runs: AnimRef[]; onClose?: () => void }) {
  const [times, setTimes] = useState<Record<number, number[]>>({});
  const [scalars, setScalars] = useState<Record<number, ScalarState>>({});
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [shareScale, setShareScale] = useState(false);
  const [linkCam, setLinkCam] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const cameraLink = useMemo(() => new CameraLink(), []);
  const shared = commonRange(runs.map((r) => scalars[r.id] ?? null));
  const colorRange = shareScale ? shared : null;
  const span = timeSpan(...runs.map((r) => times[r.id]));
  const t0 = span?.[0];
  const t1 = span?.[1];
  const cols = gridColumns(runs.length);
  const rows = Math.ceil(runs.length / cols);

  useEffect(() => {
    if (!playing || t0 === undefined || t1 === undefined) return;
    let raf = 0;
    let prev = performance.now();
    const step = (now: number) => {
      const dt = (now - prev) / 1000;
      prev = now;
      setT((v) => {
        const next = v + (dt * speed * (t1 - t0)) / PLAY_SECONDS;
        return next > t1 ? t0 : next;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, t0, t1]);

  // Büyük pencerede ESC yalnız büyük pencereyi kapatır (karşılaştırma sayfası açık kalır):
  // yakalama evresinde dinlenir, sayfanın (önce bağlanan) window dinleyicisine ulaşmaz.
  useEffect(() => {
    if (!maximized) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setMaximized(false);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [maximized]);

  return (
    <div
      className={maximized ? "cv-card crash-compare-anim crash-compare-anim-max" : "cv-card crash-compare-anim"}
      data-testid="crash-compare-anim"
    >
      <span className="cv-card-head">
        <strong>Karşılaştır · deforme şekil · {runs.length} koşu</strong>
        <span className="ds-sb" data-testid="crash-compare-anim-time">
          t = {t.toFixed(3)} ms{span ? ` / ${span[1].toFixed(3)} ms` : ""}
        </span>
        <button
          type="button"
          className="doe-btn doe-btn-ghost crash-compare-anim-max-btn"
          aria-pressed={maximized}
          onClick={() => setMaximized((v) => !v)}
          title={maximized ? "Sayfaya dön (ESC)" : "Izgarayı tam ekranda aç"}
        >
          {maximized ? "Küçült" : "Büyük pencere"}
        </button>
        {onClose && (
          <button
            type="button"
            className="crash-anim-expand"
            data-testid="crash-compare-anim-close"
            onClick={onClose}
            title="Geometriye dön"
            aria-label="Karşılaştırmayı kapat"
          >
            ×
          </button>
        )}
      </span>
      <div className="crash-anim-controls crash-compare-anim-controls">
        <button
          type="button"
          className="doe-btn doe-btn-ghost"
          aria-label={playing ? "Durdur" : "Oynat"}
          disabled={!span}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          aria-label="Ortak zaman (ms)"
          min={span?.[0] ?? 0}
          max={span?.[1] ?? 1}
          step={span ? (span[1] - span[0]) / 1000 : 0.001}
          value={t}
          disabled={!span}
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
        />
        <select aria-label="Oynatma hızı" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
          {PLAY_SPEEDS.map((v) => (
            <option key={v} value={v}>
              {v}× hız
            </option>
          ))}
        </select>
      </div>
      <div className="crash-var-chips" role="group" aria-label="Karşılaştırma görünümü">
        <button
          type="button"
          className={shareScale ? "crash-var-chip active" : "crash-var-chip"}
          aria-pressed={shareScale}
          onClick={() => setShareScale((v) => !v)}
          title="Tüm pencerelerde aynı renk ölçeği: aynı skalerde koşuların min–max birleşimi"
        >
          Ortak renk ölçeği
        </button>
        <button
          type="button"
          className={linkCam ? "crash-var-chip active" : "crash-var-chip"}
          aria-pressed={linkCam}
          onClick={() => setLinkCam((v) => !v)}
          title="Birinde döndür / yakınlaştır / hazır görünüm → diğerleri aynı kamerada"
        >
          Kamera eşle
        </button>
        {shareScale && (
          <span className="crash-behavior-hint" data-testid="crash-compare-scale-note">
            {shared
              ? `Ortak ölçek ${Number(shared[0].toPrecision(3))} … ${Number(shared[1].toPrecision(3))}`
              : "Pencerelerde farklı skaler seçili — ortak ölçek uygulanmadı"}
          </span>
        )}
      </div>
      <div
        className="crash-compare-anim-grid"
        data-testid="crash-compare-anim-grid"
        style={{ "--cmp-cols": cols, "--cmp-rows": rows } as CSSProperties}
      >
        {runs.map((r) => (
          <CrashAnimationViewer
            key={r.id}
            runId={r.id}
            title={r.title}
            docked
            syncTime={t}
            onTimes={(ts) => setTimes((m) => ({ ...m, [r.id]: ts }))}
            colorRange={colorRange}
            onScalar={(scalar, meta) => setScalars((m) => ({ ...m, [r.id]: { scalar, meta } }))}
            cameraLink={cameraLink}
            linkCamera={linkCam}
          />
        ))}
      </div>
    </div>
  );
}
