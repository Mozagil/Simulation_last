/** 1.23 C5 — iki koşunun deforme şekli yan yana, ortak fiziksel zamanla.
 *
 * Zaman ekseni iki koşunun birleşimi (0 … en uzun t_end); kısa koşu kendi son
 * karesinde kalır ("koşu sonu"). Her pencerenin renk skaleri, ölçeği ve görünümü
 * ayrı seçilir. Yorum yok, veri gösterir.
 */

import { useEffect, useState } from "react";

import CrashAnimationViewer, { PLAY_SPEEDS } from "./CrashAnimationViewer";

export interface AnimRef {
  id: number;
  title: string;
}

/** 1× hızda tüm aralık ~3 sn (tek pencereli oynatmayla aynı). */
const PLAY_SECONDS = 3;

export function timeSpan(a: number[] | null, b: number[] | null): [number, number] | null {
  const all = [...(a ?? []), ...(b ?? [])];
  if (all.length < 2) return null;
  return [Math.min(...all), Math.max(...all)];
}

export default function CrashCompareAnim({ a, b, onClose }: { a: AnimRef; b: AnimRef; onClose: () => void }) {
  const [timesA, setTimesA] = useState<number[] | null>(null);
  const [timesB, setTimesB] = useState<number[] | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const span = timeSpan(timesA, timesB);
  const t0 = span?.[0];
  const t1 = span?.[1];

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

  return (
    <div className="cv-card crash-compare-anim" data-testid="crash-compare-anim">
      <span className="cv-card-head">
        <strong>Karşılaştır · deforme şekil</strong>
        <span className="ds-sb" data-testid="crash-compare-anim-time">
          t = {t.toFixed(3)} ms{span ? ` / ${span[1].toFixed(3)} ms` : ""}
        </span>
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
      <div className="crash-compare-anim-grid">
        <CrashAnimationViewer runId={a.id} title={a.title} docked syncTime={t} onTimes={setTimesA} />
        <CrashAnimationViewer runId={b.id} title={b.title} docked syncTime={t} onTimes={setTimesB} />
      </div>
    </div>
  );
}
