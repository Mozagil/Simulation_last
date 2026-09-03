// ResultsCharts.tsx — "sonuç ekranı çok boş" şikayetine karşı: sayısal
// istatistikler (min/max/ortalama/medyan) + basit bir dağılım histogramı.
// Harici bir chart kütüphanesi kullanmadan (proje bunu içermiyor), saf SVG
// ile çiziliyor.

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

const HIST_BINS = 16;
const HIST_WIDTH = 320;
const HIST_HEIGHT = 90;

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
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const counts = new Array(HIST_BINS).fill(0);
  for (const v of values) {
    const idx = Math.min(HIST_BINS - 1, Math.floor(((v - min) / range) * HIST_BINS));
    counts[idx]++;
  }
  const maxCount = Math.max(...counts) || 1;
  const barWidth = HIST_WIDTH / HIST_BINS;

  return (
    <div className="results-histogram">
      <p className="results-stats-title">{label}</p>
      <svg width={HIST_WIDTH} height={HIST_HEIGHT} viewBox={`0 0 ${HIST_WIDTH} ${HIST_HEIGHT}`}>
        {counts.map((c, i) => {
          const h = (c / maxCount) * (HIST_HEIGHT - 14);
          return (
            <rect
              key={i}
              x={i * barWidth + 1}
              y={HIST_HEIGHT - 14 - h}
              width={barWidth - 2}
              height={h}
              fill={color}
              opacity={0.75}
            />
          );
        })}
        <text x={0} y={HIST_HEIGHT - 2} fontSize="9" fill="var(--muted)">
          {fmt(min)}
        </text>
        <text x={HIST_WIDTH - 30} y={HIST_HEIGHT - 2} fontSize="9" fill="var(--muted)">
          {fmt(max)}
        </text>
      </svg>
    </div>
  );
}
