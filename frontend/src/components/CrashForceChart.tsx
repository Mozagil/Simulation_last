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

/** 1.23 C8 — y ekseni ölçeği: 0'dan başlayan 1·2·5×10ⁿ adımlı ~4 aralık; üst = son tik. */
export function niceTicks(maxAbs: number): number[] {
  if (!(maxAbs > 0) || !Number.isFinite(maxAbs)) return [0, 1];
  const raw = maxAbs / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const n = Math.ceil(maxAbs / step - 1e-9);
  return Array.from({ length: n + 1 }, (_, i) => Number((i * step).toPrecision(12)));
}

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

/** 1.23 C8 — kuvvet grafiği açıklaması (veri kaynağı; yorum yok). */
export const FORCE_CHART_NOTE =
  "Kuvvet = TH'deki birikimli impulsun zamana türevi (|F|, global bileşke): rijit duvar /TH/RWALL, " +
  "temas /TH/INTER, kesit /TH/SECTIO (FN + FT). Ham = süzülmemiş; CFC = SAE J211 süzülmüş (kalın çizgi). " +
  "Nokta = serinin tepe değeri.";

/** 1.23 C6 — enerji serileri (J): global TH sütunları; toplam = IE + KE (+ dönme + HG − dış iş). */
export const ENERGY_CURVES: [string, string][] = [
  ["internal_energy", "İç enerji"],
  ["kinetic_energy", "Kinetik enerji"],
  ["hourglass_energy", "Hourglass enerjisi"],
  ["contact_energy", "Temas enerjisi"],
  ["external_work", "Dış iş"],
  ["total_energy", "Toplam enerji"],
];

export function energySeriesFromCurves(curves: Record<string, number[]> | undefined): ForceSeries[] {
  if (!curves) return [];
  return ENERGY_CURVES.filter(([k]) => (curves[k]?.length ?? 0) > 1).map(([k, label]) => ({
    key: k,
    label,
    values: curves[k],
  }));
}

export default function CrashForceChart({
  time,
  series,
  title = "Kuvvet · kN",
  unit = "kN",
  ariaLabel = "Kuvvet–zaman grafiği",
  yLabel = "kuvvet",
  note,
}: {
  time: number[];
  series: ForceSeries[];
  title?: string;
  /** 1.17e2 — tepe değer birimi (kN, g, J …) */
  unit?: string;
  ariaLabel?: string;
  /** 1.23 C8 — y ekseni adı (birim `unit`'ten) */
  yLabel?: string;
  /** 1.23 C8 — grafiğin altında kısa açıklama (veri kaynağı; yorum yok) */
  note?: string;
}) {
  const tOf = (s: ForceSeries) => s.time ?? time;
  if (series.length === 0 || series.some((s) => tOf(s).length < 2)) return null;
  const tMin = Math.min(...series.map((s) => tOf(s)[0]));
  const tMax = Math.max(...series.map((s) => tOf(s)[tOf(s).length - 1]));
  const tSpan = tMax - tMin || 1;
  const ticks = niceTicks(Math.max(...series.flatMap((s) => s.values.map((v) => Math.abs(v))), 0));
  const fMax = ticks[ticks.length - 1];

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
  const colorOf = (k: string) => bases.indexOf(baseKey(k)) % 6;
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
              <span
                className={`crash-force-swatch crash-series-${colorOf(s.key)}${isCfc(s.key) ? " crash-force-swatch-cfc" : ""}`}
              />
              {s.label}
            </span>
          ))}
        </span>
      </span>
      <div className="crash-chart-plot">
        <div className="crash-chart-yaxis ds-sb" aria-hidden="true">
          <span className="crash-chart-ylabel">{`${yLabel} (${unit})`}</span>
          {ticks.map((v) => (
            <span key={v} className="crash-chart-ytick" style={{ top: `${(py(v) / H) * 100}%` }}>
              {String(v)}
            </span>
          ))}
        </div>
        <div className="crash-chart-area">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={ariaLabel}
            preserveAspectRatio="none"
            className="cv-svg"
          >
            <rect x="0.5" y="0.5" width={W - 1} height={H - 1} className="cv-frame" />
            {ticks.slice(1, -1).map((v) => (
              <line key={v} x1={1} x2={W - 1} y1={py(v)} y2={py(v)} className="crash-chart-grid" />
            ))}
            {series.map((s) => (
              <polyline key={s.key} points={path(s)} className={lineClass(s.key)} />
            ))}
          </svg>
          {/* SVG oransız ölçeklenir (preserveAspectRatio=none): nokta / etiket HTML, % konum */}
          {peaks
            .filter((p) => !hasTwin(p.key))
            .map((p) => (
              <span
                key={p.key}
                className={`crash-chart-peak crash-series-${colorOf(p.key)}${px(p.at) / W > 0.8 ? " crash-chart-peak-left" : ""}`}
                style={{
                  left: `${(px(p.at) / W) * 100}%`,
                  top: `${(py(p.peak) / H) * 100}%`,
                }}
                title={`${p.label} tepe ${niceValue(p.peak)} ${unit} · t = ${niceValue(p.at)} ms`}
                data-testid="crash-chart-peak"
              >
                <span className="crash-chart-peak-label">{niceValue(p.peak)}</span>
              </span>
            ))}
        </div>
      </div>
      <span className="cv-axis ds-sb crash-chart-xaxis">
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
      {note && <p className="crash-chart-note ds-sb">{note}</p>}
    </figure>
  );
}
