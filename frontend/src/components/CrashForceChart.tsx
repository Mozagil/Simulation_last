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
  /** 1.16b — karşılaştırmada her koşunun kendi zaman ekseni; yoksa ortak `time`. */
  time?: number[];
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
  // 1.15c — kesit kuvveti (FN + FT, global; bileşen dI/dt)
  const sections = Object.keys(curves)
    .map((k) => /^section_(\d+)_force$/.exec(k))
    .filter((m): m is RegExpExecArray => m != null)
    .sort((a, b) => Number(a[1]) - Number(b[1]))
    .map((m) => ({ key: m[0], label: `Kesit ${m[1]}`, values: curves[m[0]] }));
  // 1.17e — CFC süzülmüş kopyalar (ham eğrinin hemen yanında)
  const filtered = Object.keys(curves)
    .map((k) => /^(rwall|contact_(\d+)|section_(\d+))_force_cfc(\d+)$/.exec(k))
    .filter((m): m is RegExpExecArray => m != null)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map((m) => ({
      key: m[0],
      label: `${m[2] ? `Temas ${m[2]}` : m[3] ? `Kesit ${m[3]}` : "Rijit duvar"} CFC${m[4]}`,
      values: curves[m[0]],
    }));
  return [...contacts, ...wall, ...sections, ...filtered].filter((s) => s.values.length > 1);
}

export default function CrashForceChart({
  time,
  series,
  title = "Kuvvet · kN",
  unit = "kN",
  ariaLabel = "Kuvvet–zaman grafiği",
}: {
  time: number[];
  series: ForceSeries[];
  title?: string;
  /** 1.17e2 — tepe değer birimi (kN, g, J …) */
  unit?: string;
  ariaLabel?: string;
}) {
  const tOf = (s: ForceSeries) => s.time ?? time;
  if (series.length === 0 || series.some((s) => tOf(s).length < 2)) return null;
  const tMin = Math.min(...series.map((s) => tOf(s)[0]));
  const tMax = Math.max(...series.map((s) => tOf(s)[tOf(s).length - 1]));
  const tSpan = tMax - tMin || 1;
  const fMax = Math.max(...series.flatMap((s) => s.values.map((v) => Math.abs(v))), 1e-9) * 1.1;

  const px = (t: number) => 8 + ((t - tMin) / tSpan) * (W - 16);
  const py = (f: number) => 8 + (1 - f / fMax) * (H - 16);
  const path = (s: ForceSeries) =>
    s.values
      .slice(0, tOf(s).length)
      .map((v, i) => `${px(tOf(s)[i]).toFixed(1)},${py(Math.abs(v)).toFixed(1)}`)
      .join(" ");

  // 1.17e2 — CFC süzülmüş seri ham eşiyle aynı renk, kalın; eşi olan ham seri
  // ince ve soluk. Renk sırası taban anahtara (…_cfcN eki atılmış) göre.
  const baseKey = (k: string) => k.replace(/_cfc\d+$/, "");
  const bases = [...new Set(series.map((s) => baseKey(s.key)))];
  const colorOf = (k: string) => bases.indexOf(baseKey(k)) % 4;
  const isCfc = (k: string) => /_cfc\d+$/.test(k);
  const hasTwin = (k: string) => !isCfc(k) && series.some((o) => isCfc(o.key) && baseKey(o.key) === k);
  const lineClass = (k: string) =>
    `crash-force-line crash-series-${colorOf(k)}${isCfc(k) ? " crash-force-line-cfc" : hasTwin(k) ? " crash-force-line-raw" : ""}`;

  const peaks = series.map((s) => {
    let i = 0;
    s.values.forEach((v, j) => {
      if (Math.abs(v) > Math.abs(s.values[i])) i = j;
    });
    return { ...s, peak: Math.abs(s.values[i]), at: tOf(s)[i] };
  });

  return (
    <figure className="cv-card crash-force-card">
      <span className="cv-card-head">
        <strong>{title}</strong>
        <span className="crash-force-legend">
          {series.map((s) => (
            <span key={s.key} className="ds-sb crash-force-legend-item">
              <span className={`crash-force-swatch crash-series-${colorOf(s.key)}${isCfc(s.key) ? " crash-force-swatch-cfc" : ""}`} />
              {s.label}
            </span>
          ))}
        </span>
      </span>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={ariaLabel}
        preserveAspectRatio="none"
        className="cv-svg"
      >
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} className="cv-frame" />
        {series.map((s) => (
          <polyline key={s.key} points={path(s)} className={lineClass(s.key)} />
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
            <strong>{`${niceValue(p.peak)} ${unit}`}</strong>
            <span className="ds-sb">{`t = ${niceValue(p.at)} ms`}</span>
          </span>
        ))}
      </span>
    </figure>
  );
}
