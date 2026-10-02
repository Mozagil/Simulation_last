/** Crash kuvvet–zaman grafiği (1.12b): temas (|FN|, arayüz başına) ve duvar.
 *
 * Eksenler: zaman ms (deck birimi kg–mm–ms), kuvvet kN. Her seri kendi
 * çizgisi; altta seri başına tepe değer ve zamanı. Grafik yorum yapmaz,
 * eşik/bant çizmez.
 */

import { niceValue } from "./ConvergenceChart";

export interface ForceSeries {
  key: string;
  label: string;
  values: number[];
}

const W = 400;
const H = 170;

/** `curves` sözlüğünden çizilecek kuvvet serileri: contact_k_force (k sırasıyla), rwall_force. */
export function forceSeriesFromCurves(curves: Record<string, number[]> | undefined): ForceSeries[] {
  if (!curves) return [];
  const contacts = Object.keys(curves)
    .map((k) => /^contact_(\d+)_force$/.exec(k))
    .filter((m): m is RegExpExecArray => m != null)
    .sort((a, b) => Number(a[1]) - Number(b[1]))
    .map((m) => ({ key: m[0], label: `Temas ${m[1]}`, values: curves[m[0]] }));
  const wall = curves.rwall_force ? [{ key: "rwall_force", label: "Rijit duvar", values: curves.rwall_force }] : [];
  return [...contacts, ...wall].filter((s) => s.values.length > 1);
}

export default function CrashForceChart({ time, series }: { time: number[]; series: ForceSeries[] }) {
  if (time.length < 2 || series.length === 0) return null;
  const tMin = time[0];
  const tMax = time[time.length - 1];
  const tSpan = tMax - tMin || 1;
  const fMax = Math.max(...series.flatMap((s) => s.values.map((v) => Math.abs(v))), 1e-9) * 1.1;

  const px = (t: number) => 8 + ((t - tMin) / tSpan) * (W - 16);
  const py = (f: number) => 8 + (1 - f / fMax) * (H - 16);
  const path = (values: number[]) =>
    values
      .slice(0, time.length)
      .map((v, i) => `${px(time[i]).toFixed(1)},${py(Math.abs(v)).toFixed(1)}`)
      .join(" ");

  const peaks = series.map((s) => {
    let i = 0;
    s.values.forEach((v, j) => {
      if (Math.abs(v) > Math.abs(s.values[i])) i = j;
    });
    return { ...s, peak: Math.abs(s.values[i]), at: time[i] };
  });

  return (
    <figure className="cv-card crash-force-card">
      <span className="cv-card-head">
        <strong>Kuvvet · kN</strong>
        <span className="crash-force-legend">
          {series.map((s, i) => (
            <span key={s.key} className="ds-sb crash-force-legend-item">
              <span className={`crash-force-swatch crash-series-${i % 4}`} />
              {s.label}
            </span>
          ))}
        </span>
      </span>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Kuvvet–zaman grafiği"
        preserveAspectRatio="none"
        className="cv-svg"
      >
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} className="cv-frame" />
        {series.map((s, i) => (
          <polyline key={s.key} points={path(s.values)} className={`crash-force-line crash-series-${i % 4}`} />
        ))}
      </svg>
      <span className="cv-axis ds-sb">
        <span>{niceValue(tMin)} ms</span>
        <span>zaman (ms)</span>
        <span>{niceValue(tMax)} ms</span>
      </span>
      <span className="cv-stats">
        {peaks.map((p) => (
          <span key={p.key}>
            <span className="ml-k">{p.label} tepe</span>
            <strong>{`${niceValue(p.peak)} kN`}</strong>
            <span className="ds-sb">{`t = ${niceValue(p.at)} ms`}</span>
          </span>
        ))}
      </span>
    </figure>
  );
}
