/** Crash kuvvet–zaman grafiği (1.12b): temas (|FN|, arayüz başına) ve duvar.
 *
 * Eksenler: zaman ms (deck birimi kg–mm–ms), kuvvet kN. Her seri kendi
 * çizgisi; altta seri başına tepe değer ve zamanı. Grafik yorum yapmaz;
 * 1.23 C8 ortalama kuvvet aralığı (gölge) yalnız veriden, sabit eşikle.
 */

import { useRef } from "react";

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

/** 1.23 C8 — temas aralığı eşiği: |F| > tepe × MEAN_THRESHOLD. */
export const MEAN_THRESHOLD = 0.01;

/** 1.23 C8 — ortalama kuvvet (B): temas aralığında ∫|F|dt / Δt (yamuk).
 *  Aralık = |F| > eşik×tepe olan ilk ve son örnek arası; Δt = 0 ise null. */
export function contactMean(
  time: number[],
  values: number[],
  frac = MEAN_THRESHOLD,
): { mean: number; t0: number; t1: number } | null {
  const n = Math.min(time.length, values.length);
  const abs = values.slice(0, n).map((v) => Math.abs(v));
  const peak = Math.max(0, ...abs);
  if (!(peak > 0)) return null;
  const on = abs.map((v) => v > frac * peak);
  const i0 = on.indexOf(true);
  const i1 = on.lastIndexOf(true);
  const dt = time[i1] - time[i0];
  if (i0 < 0 || !(dt > 0)) return null;
  let area = 0;
  for (let i = i0; i < i1; i++) area += ((abs[i] + abs[i + 1]) / 2) * (time[i + 1] - time[i]);
  return { mean: area / dt, t0: time[i0], t1: time[i1] };
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
  "Nokta = serinin tepe değeri. Kesikli çizgi = ortalama kuvvet: temas aralığında (gölgeli; " +
  `|F| > tepenin %${MEAN_THRESHOLD * 100}'i) impuls / süre.`;

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

/** 1.23 C1b — dosya adı: başlıktan (Türkçe harf → ASCII), ör. "Kuvvet · kN" → "kuvvet_kN". */
export function chartFileBase(title: string): string {
  const tr: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u", Ç: "C", Ğ: "G", İ: "I", Ö: "O", Ş: "S", Ü: "U" };
  const ascii = title.replace(/[çğıöşüÇĞİÖŞÜ]/g, (c) => tr[c] ?? c);
  const [head, ...rest] = ascii.split(/[^A-Za-z0-9]+/).filter(Boolean);
  return [head?.toLowerCase(), ...rest].filter(Boolean).join("_") || "grafik";
}

const csvCell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

/** 1.23 C1b — CSV (virgül ayraç, nokta ondalık): ortak zaman ekseninde geniş tablo
 *  (t, seri1, seri2 …); seriler ayrı zaman eksenliyse (karşılaştırma) seri başına t + değer.
 *  Değerler kayıtlı veri (işaretli); grafik |F| çizer. */
export function chartCsv(time: number[], series: ForceSeries[], unit: string): string {
  const shared = series.every((s) => !s.time);
  const cols: { head: string; vals: number[] }[] = shared
    ? [{ head: "t (ms)", vals: time }, ...series.map((s) => ({ head: `${s.label} (${unit})`, vals: s.values }))]
    : series.flatMap((s) => [
        { head: `${s.label} t (ms)`, vals: s.time ?? time },
        { head: `${s.label} (${unit})`, vals: s.values },
      ]);
  const n = shared ? time.length : Math.max(...cols.map((c) => c.vals.length));
  const lines = [cols.map((c) => csvCell(c.head)).join(",")];
  for (let i = 0; i < n; i++) lines.push(cols.map((c) => (c.vals[i] == null ? "" : String(c.vals[i]))).join(","));
  return lines.join("\n") + "\n";
}

export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function CrashForceChart({
  time,
  series,
  title = "Kuvvet · kN",
  unit = "kN",
  ariaLabel = "Kuvvet–zaman grafiği",
  yLabel = "kuvvet",
  note,
  showMean = false,
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
  /** 1.23 C8 — temas aralığı ortalaması (yalnız kuvvet grafiği) */
  showMean?: boolean;
}) {
  const figRef = useRef<HTMLElement | null>(null);
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
  // CFC eşi olan ham seriye ortalama çizilmez (tepe noktası gibi)
  const means = showMean
    ? series
        .filter((s) => !hasTwin(s.key))
        .map((s) => ({ ...s, m: contactMean(tOf(s), s.values) }))
        .filter((s): s is ForceSeries & { m: NonNullable<ReturnType<typeof contactMean>> } => s.m != null)
    : [];

  const exportCsv = () =>
    downloadBlob(new Blob([chartCsv(time, series, unit)], { type: "text/csv;charset=utf-8" }), `${chartFileBase(title)}.csv`);

  // 1.23 C1b — PNG: grafik veriden 2B tuvale yeniden çizilir (SVG + HTML katmanı tek
  // resme dönmüyor); renkler ekrandaki lejanttan, tema ile aynı.
  const exportPng = () => {
    const fig = figRef.current;
    if (!fig) return;
    const css = getComputedStyle(fig);
    const swatches = [...fig.querySelectorAll<HTMLElement>(".crash-force-swatch")];
    const colors = series.map((_, i) => (swatches[i] ? getComputedStyle(swatches[i]).color : "#333"));
    const bg = css.backgroundColor && css.backgroundColor !== "rgba(0, 0, 0, 0)" ? css.backgroundColor : "#ffffff";
    const fg = css.color || "#111";
    const colorFor = (k: string) => colors[series.findIndex((s) => s.key === k)] ?? fg;
    const marked = peaks.filter((p) => !hasTwin(p.key));
    const stats = [
      ...peaks.map((p) => `${p.label} tepe ${niceValue(p.peak)} ${unit} · t = ${niceValue(p.at)} ms`),
      ...means.map((s) => `${s.label} ortalama ${niceValue(s.m.mean)} ${unit} · ${niceValue(s.m.t0)}–${niceValue(s.m.t1)} ms`),
    ];
    const CW = 1400;
    const L = 100;
    const R = 40;
    const T = 90;
    const ph = 520;
    const pw = CW - L - R;
    const CH = T + ph + 60 + 26 * Math.ceil(stats.length / 2) + 20;
    const c = document.createElement("canvas");
    c.width = CW;
    c.height = CH;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const X = (t: number) => L + ((t - tMin) / tSpan) * pw;
    const Y = (f: number) => T + (1 - f / fMax) * ph;
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CW, CH);
    ctx.fillStyle = fg;
    ctx.font = "600 24px system-ui, sans-serif";
    ctx.fillText(title, L, 38);
    // lejant
    ctx.font = "16px system-ui, sans-serif";
    let lx = L;
    series.forEach((s, i) => {
      ctx.fillStyle = colors[i];
      ctx.fillRect(lx, 58, 20, isCfc(s.key) ? 5 : 3);
      ctx.fillStyle = fg;
      ctx.fillText(s.label, lx + 26, 66);
      lx += 26 + ctx.measureText(s.label).width + 26;
    });
    // kılavuz, çerçeve, eksen yazıları
    ctx.strokeStyle = fg;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.15;
    for (const v of ticks.slice(1, -1)) {
      ctx.beginPath();
      ctx.moveTo(L, Y(v));
      ctx.lineTo(L + pw, Y(v));
      ctx.stroke();
    }
    ctx.globalAlpha = 0.6;
    ctx.strokeRect(L, T, pw, ph);
    ctx.globalAlpha = 1;
    ctx.fillStyle = fg;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const v of ticks) ctx.fillText(String(v), L - 10, Y(v));
    ctx.save();
    ctx.translate(30, T + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(`${yLabel} (${unit})`, 0, 0);
    ctx.restore();
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.fillText(`${niceValue(tMin)} ms`, L, T + ph + 10);
    ctx.textAlign = "center";
    ctx.fillText("zaman (ms)", L + pw / 2, T + ph + 10);
    ctx.textAlign = "right";
    ctx.fillText(`${niceValue(tMax)} ms`, L + pw, T + ph + 10);
    // ortalama aralığı (gölge)
    for (const s of means) {
      ctx.fillStyle = colorFor(s.key);
      ctx.globalAlpha = 0.08;
      ctx.fillRect(X(s.m.t0), T, X(s.m.t1) - X(s.m.t0), ph);
    }
    ctx.globalAlpha = 1;
    // eğriler: CFC kalın, eşi olan ham ince + soluk
    series.forEach((s, i) => {
      const t = tOf(s);
      ctx.strokeStyle = colors[i];
      ctx.lineWidth = isCfc(s.key) ? 3 : hasTwin(s.key) ? 1 : 2;
      ctx.globalAlpha = hasTwin(s.key) ? 0.45 : 1;
      ctx.beginPath();
      s.values.slice(0, t.length).forEach((v, j) => {
        if (j === 0) ctx.moveTo(X(t[j]), Y(Math.abs(v)));
        else ctx.lineTo(X(t[j]), Y(Math.abs(v)));
      });
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
    // ortalama (kesikli)
    ctx.lineWidth = 2;
    ctx.setLineDash([10, 6]);
    for (const s of means) {
      ctx.strokeStyle = colorFor(s.key);
      ctx.beginPath();
      ctx.moveTo(X(s.m.t0), Y(s.m.mean));
      ctx.lineTo(X(s.m.t1), Y(s.m.mean));
      ctx.stroke();
    }
    ctx.setLineDash([]);
    // tepe noktaları
    ctx.font = "600 15px system-ui, sans-serif";
    ctx.textBaseline = "bottom";
    for (const p of marked) {
      const x = X(p.at);
      const y = Y(p.peak);
      ctx.fillStyle = colorFor(p.key);
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fill();
      const left = (x - L) / pw > 0.8;
      ctx.textAlign = left ? "right" : "left";
      ctx.fillStyle = fg;
      ctx.fillText(niceValue(p.peak), x + (left ? -10 : 10), y - 6);
    }
    // ekrandaki istatistik satırları
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.font = "15px system-ui, sans-serif";
    ctx.fillStyle = fg;
    stats.forEach((txt, i) => ctx.fillText(txt, L + (i % 2) * (pw / 2), T + ph + 44 + 26 * Math.floor(i / 2)));
    c.toBlob((b) => b && downloadBlob(b, `${chartFileBase(title)}.png`), "image/png");
  };

  return (
    <figure className="cv-card crash-force-card" ref={figRef}>
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
        <span className="crash-chart-export">
          <button type="button" className="crash-var-chip" onClick={exportPng} title="Grafiği PNG olarak indir (1400×800)">
            PNG
          </button>
          <button type="button" className="crash-var-chip" onClick={exportCsv} title="Eğri verisini CSV olarak indir">
            CSV
          </button>
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
            {means.map((s) => (
              <rect
                key={`band-${s.key}`}
                x={px(s.m.t0)}
                y={1}
                width={px(s.m.t1) - px(s.m.t0)}
                height={H - 2}
                className={`crash-chart-mean-band crash-series-${colorOf(s.key)}`}
              />
            ))}
            {series.map((s) => (
              <polyline key={s.key} points={path(s)} className={lineClass(s.key)} />
            ))}
            {means.map((s) => (
              <line
                key={`mean-${s.key}`}
                x1={px(s.m.t0)}
                x2={px(s.m.t1)}
                y1={py(s.m.mean)}
                y2={py(s.m.mean)}
                className={`crash-chart-mean crash-series-${colorOf(s.key)}`}
                data-testid="crash-chart-mean"
              />
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
        {means.map((s) => (
          <span key={`mean-${s.key}`}>
            <span className="ml-k">{s.label} ortalama</span>
            <strong>{`${niceValue(s.m.mean)} ${unit}`}</strong>
            <span className="ds-sb">{`${niceValue(s.m.t0)}–${niceValue(s.m.t1)} ms`}</span>
          </span>
        ))}
      </span>
      {note && <p className="crash-chart-note ds-sb">{note}</p>}
    </figure>
  );
}
