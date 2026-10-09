/** Residual geçmişi (log₁₀ ölçek) — AKIŞ 2.7b. Alan başına çizgi, yalnız veri. */

const COLORS = ["#2b6cb0", "#c05621", "#2f855a", "#9b2c2c", "#6b46c1", "#b7791f", "#2c7a7b"];

export default function CfdResidualChart({
  iterations,
  residuals,
  height = 180,
}: {
  iterations: number[];
  residuals: Record<string, number[]>;
  height?: number;
}) {
  const names = Object.keys(residuals).filter((k) => residuals[k]?.length);
  if (!iterations.length || !names.length) return <p className="crash-behavior-hint">Henüz residual verisi yok.</p>;
  const w = 320;
  const pad = { l: 34, r: 8, t: 8, b: 20 };
  const all = names.flatMap((k) => residuals[k]).filter((v) => v > 0);
  const lo = Math.floor(Math.log10(Math.min(...all)));
  const hi = Math.ceil(Math.log10(Math.max(...all)));
  const span = Math.max(hi - lo, 1);
  const xMax = iterations[iterations.length - 1] || 1;
  const x = (it: number) => pad.l + ((w - pad.l - pad.r) * it) / xMax;
  const y = (v: number) => pad.t + ((height - pad.t - pad.b) * (hi - Math.log10(Math.max(v, 1e-30)))) / span;
  const decades = Array.from({ length: span + 1 }, (_, i) => hi - i);
  return (
    <figure className="cfd-chart" data-testid="cfd-residual-chart">
      <svg viewBox={`0 0 ${w} ${height}`} role="img" aria-label="Residual geçmişi (log ölçek)">
        {decades.map((d) => (
          <g key={d}>
            <line x1={pad.l} x2={w - pad.r} y1={y(10 ** d)} y2={y(10 ** d)} className="cfd-chart-grid" />
            <text x={pad.l - 4} y={y(10 ** d) + 3} textAnchor="end" className="cfd-chart-tick">
              1e{d}
            </text>
          </g>
        ))}
        <text x={w - pad.r} y={height - 4} textAnchor="end" className="cfd-chart-tick">
          iterasyon {xMax}
        </text>
        {names.map((k, i) => {
          const vals = residuals[k];
          const its = iterations.slice(0, vals.length);
          const d = vals.map((v, j) => `${j ? "L" : "M"}${x(its[j]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
          return <path key={k} d={d} fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth="1.3" />;
        })}
      </svg>
      <figcaption className="cfd-chart-legend">
        {names.map((k, i) => (
          <span key={k}>
            <i style={{ background: COLORS[i % COLORS.length] }} /> {k} {residuals[k][residuals[k].length - 1].toExponential(1)}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
