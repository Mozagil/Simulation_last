/** 1.23 C5 — iki koşunun deforme şekli yan yana, ortak fiziksel zamanla.
 *
 * Zaman ekseni iki koşunun birleşimi (0 … en uzun t_end); kısa koşu kendi son
 * karesinde kalır ("koşu sonu"). Her pencerenin renk skaleri, ölçeği ve görünümü
 * ayrı seçilir. 1.23 C5b: isteğe bağlı ortak renk ölçeği (aynı skalerde iki koşunun
 * min–max birleşimi) ve kamera eşleme. Yorum yok, veri gösterir.
 */

import { useEffect, useMemo, useState } from "react";

import CrashAnimationViewer, { CameraLink, PLAY_SPEEDS } from "./CrashAnimationViewer";

export interface AnimRef {
  id: number;
  title: string;
}

/** 1× hızda tüm aralık ~3 sn (tek pencereli oynatmayla aynı). */
const PLAY_SECONDS = 3;

type ScalarState = { scalar: string; meta?: { min: number; max: number } } | null;

/** 1.23 C5b — ortak ölçek: iki pencere aynı skalerdeyse min–max birleşimi, yoksa null. */
export function commonRange(a: ScalarState, b: ScalarState): [number, number] | null {
  if (!a?.meta || !b?.meta || a.scalar !== b.scalar) return null;
  return [Math.min(a.meta.min, b.meta.min), Math.max(a.meta.max, b.meta.max)];
}

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
  const [scalarA, setScalarA] = useState<ScalarState>(null);
  const [scalarB, setScalarB] = useState<ScalarState>(null);
  const [shareScale, setShareScale] = useState(false);
  const [linkCam, setLinkCam] = useState(false);
  const cameraLink = useMemo(() => new CameraLink(), []);
  const shared = commonRange(scalarA, scalarB);
  const colorRange = shareScale ? shared : null;
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
      <div className="crash-var-chips" role="group" aria-label="Karşılaştırma görünümü">
        <button
          type="button"
          className={shareScale ? "crash-var-chip active" : "crash-var-chip"}
          aria-pressed={shareScale}
          onClick={() => setShareScale((v) => !v)}
          title="İki pencerede aynı renk ölçeği: aynı skalerde iki koşunun min–max birleşimi"
        >
          Ortak renk ölçeği
        </button>
        <button
          type="button"
          className={linkCam ? "crash-var-chip active" : "crash-var-chip"}
          aria-pressed={linkCam}
          onClick={() => setLinkCam((v) => !v)}
          title="Birinde döndür / yakınlaştır / hazır görünüm → diğeri aynı kamerada"
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
      <div className="crash-compare-anim-grid">
        <CrashAnimationViewer
          runId={a.id}
          title={a.title}
          docked
          syncTime={t}
          onTimes={setTimesA}
          colorRange={colorRange}
          onScalar={(scalar, meta) => setScalarA({ scalar, meta })}
          cameraLink={cameraLink}
          linkCamera={linkCam}
        />
        <CrashAnimationViewer
          runId={b.id}
          title={b.title}
          docked
          syncTime={t}
          onTimes={setTimesB}
          colorRange={colorRange}
          onScalar={(scalar, meta) => setScalarB({ scalar, meta })}
          cameraLink={cameraLink}
          linkCamera={linkCam}
        />
      </div>
    </div>
  );
}
