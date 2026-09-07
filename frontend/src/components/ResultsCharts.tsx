// ResultsCharts.tsx — istatistik tablosu + sürekli dağılım eğrisi (bar değil)
// + modal mod şekli küçük resmi. Harici chart kütüphanesi yok.

function computeStats(values: number[]) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const sum = sorted.reduce((a, b) => a + b, 0);
  const mean = sum / sorted.length;
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  return { min, max, mean, median };
}

function fmt(v: number): string {
  if (Math.abs(v) >= 1000 || (Math.abs(v) < 0.01 && v !== 0)) return v.toExponential(2);
  return v.toFixed(2);
}

export function ResultsStatsTable({ label, values }: { label: string; values: number[] }) {
  const stats = computeStats(values);
  if (!stats) return null;
  return (
    <div className="results-stats-table">
      <p className="results-stats-title">{label}</p>
      <div className="results-stats-row">
        <span>min</span>
        <span>{fmt(stats.min)}</span>
      </div>
      <div className="results-stats-row">
        <span>max</span>
        <span>{fmt(stats.max)}</span>
      </div>
      <div className="results-stats-row">
        <span>ortalama</span>
        <span>{fmt(stats.mean)}</span>
      </div>
      <div className="results-stats-row">
        <span>medyan</span>
        <span>{fmt(stats.median)}</span>
      </div>
    </div>
  );
}

const HIST_WIDTH = 320;
const HIST_HEIGHT = 96;
const KDE_POINTS = 64;

/** Gaussian KDE — sürekli yoğunluk eğrisi (histogram çubuğu değil). */
function kdeCurve(values: number[], n = KDE_POINTS): { xs: number[]; ys: number[]; min: number; max: number } {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  if (range < 1e-30) {
    return { xs: [min, min], ys: [1, 1], min, max };
  }
  const sample =
    values.length > 4000
      ? values.filter((_, i) => i % Math.ceil(values.length / 4000) === 0)
      : values;
  const mean = sample.reduce((a, b) => a + b, 0) / sample.length;
  const variance = sample.reduce((a, v) => a + (v - mean) ** 2, 0) / sample.length;
  const sigma = Math.sqrt(variance) || range / 6;
  const h = Math.max(1.06 * sigma * sample.length ** (-0.2), range / 40);
  const xs: number[] = [];
  const ys: number[] = [];
  const inv = 1 / (Math.sqrt(2 * Math.PI) * h * sample.length);
  for (let i = 0; i < n; i++) {
    const x = min + (i / (n - 1)) * range;
    let s = 0;
    for (const v of sample) {
      const z = (x - v) / h;
      s += Math.exp(-0.5 * z * z);
    }
    xs.push(x);
    ys.push(s * inv);
  }
  return { xs, ys, min, max };
}

/** Dağılım: sürekli yoğunluk eğrisi (mühendislik plot). */
export function ResultsHistogram({
  label,
  values,
  color,
}: {
  label: string;
  values: number[];
  color: string;
}) {
  if (values.length === 0) return null;
  const { xs, ys, min, max } = kdeCurve(values);
  const maxY = Math.max(...ys) || 1;
  const plotH = HIST_HEIGHT - 16;
  const degenerate = max - min < 1e-30;
  const pts = xs.map((x, i) => {
    const t = degenerate ? i / Math.max(xs.length - 1, 1) : (x - min) / (max - min || 1);
    const px = t * HIST_WIDTH;
    const py = plotH - (ys[i] / maxY) * (plotH - 4);
    return [px, py] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${HIST_WIDTH},${plotH} L0,${plotH} Z`;

  return (
    <div className="results-histogram">
      <p className="results-stats-title">{label}</p>
      <svg width={HIST_WIDTH} height={HIST_HEIGHT} viewBox={`0 0 ${HIST_WIDTH} ${HIST_HEIGHT}`}>
        <path d={area} fill={color} opacity={0.16} />
        <path d={line} fill="none" stroke={color} strokeWidth={1.7} strokeLinejoin="round" />
        <line x1={0} y1={plotH} x2={HIST_WIDTH} y2={plotH} stroke="var(--border)" strokeWidth={1} />
        <text x={0} y={HIST_HEIGHT - 2} fontSize="9" fill="var(--muted)">
          {fmt(min)}
        </text>
        <text x={HIST_WIDTH - 36} y={HIST_HEIGHT - 2} fontSize="9" fill="var(--muted)">
          {fmt(max)}
        </text>
      </svg>
    </div>
  );
}

export function FrequencyLinePlot({ frequencies }: { frequencies: number[] }) {
  if (frequencies.length === 0) return null;
  const w = 320;
  const h = 80;
  const maxF = Math.max(...frequencies) || 1;
  const pts = frequencies.map((f, i) => {
    const x = frequencies.length === 1 ? w / 2 : (i / (frequencies.length - 1)) * (w - 8) + 4;
    const y = (h - 16) - (f / maxF) * (h - 24);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <div className="results-histogram">
      <p className="results-stats-title">f (Hz) · mode</p>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <path d={line} fill="none" stroke="var(--accent, #2a6f97)" strokeWidth={1.6} />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={2.4} fill="var(--accent, #2a6f97)" />
        ))}
        <text x={0} y={h - 2} fontSize="9" fill="var(--muted)">
          1
        </text>
        <text x={w - 16} y={h - 2} fontSize="9" fill="var(--muted)">
          {frequencies.length}
        </text>
      </svg>
    </div>
  );
}

function jetHex(t: number): string {
  const x = Math.min(1, Math.max(0, t));
  const r = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3))));
  const g = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2))));
  const b = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1))));
  return `rgb(${r},${g},${b})`;
}

/** 2D izdüşüm: deforme düğümler — her mod için küçük görsel. */
export function ModeShapeThumb({
  nodes,
  vectors,
}: {
  nodes: number[][];
  vectors: number[][];
}) {
  const w = 148;
  const h = 96;
  if (nodes.length === 0) {
    return <svg className="mode-thumb" width={w} height={h} />;
  }
  let maxU = 0;
  const mags = nodes.map((_, i) => {
    const d = vectors[i] ?? [0, 0, 0];
    const u = Math.hypot(d[0], d[1], d[2]);
    if (u > maxU) maxU = u;
    return u;
  });
  const spans = [0, 1, 2].map((ax) => {
    const vs = nodes.map((n) => n[ax]);
    return Math.max(...vs) - Math.min(...vs);
  });
  const axA = spans[0] >= spans[1] && spans[0] >= spans[2] ? 0 : spans[1] >= spans[2] ? 1 : 2;
  const axB = [0, 1, 2].filter((a) => a !== axA).sort((a, b) => spans[b] - spans[a])[0];
  const bbox = Math.max(spans[axA], spans[axB], 1e-9);
  const scaleU = maxU > 1e-30 ? (0.32 * bbox) / maxU : 0;
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const d = vectors[i] ?? [0, 0, 0];
    xs.push(nodes[i][axA] + d[axA] * scaleU);
    ys.push(nodes[i][axB] + d[axB] * scaleU);
  }
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const rx = maxX - minX || 1;
  const ry = maxY - minY || 1;
  const pad = 6;
  const s = Math.min((w - pad * 2) / rx, (h - pad * 2) / ry);
  const step = Math.max(1, Math.floor(nodes.length / 280));
  const dots = [];
  for (let i = 0; i < nodes.length; i += step) {
    const px = pad + (xs[i] - minX) * s;
    const py = h - pad - (ys[i] - minY) * s;
    const t = maxU > 1e-30 ? mags[i] / maxU : 0;
    dots.push(<circle key={i} cx={px} cy={py} r={1.35} fill={jetHex(t)} />);
  }
  return (
    <svg className="mode-thumb" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <rect
        x={0.5}
        y={0.5}
        width={w - 1}
        height={h - 1}
        fill="var(--surface-2, #f4f4f1)"
        stroke="var(--border)"
      />
      {dots}
    </svg>
  );
}
