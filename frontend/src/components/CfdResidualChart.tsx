/** İterasyon geçmişi grafiği — AKIŞ 2.7. Residual'lar log₁₀ ölçek, katsayılar
 * (Cd, Cl …) doğrusal ölçek. Alan başına çizgi, yalnız veri. */

const COLORS = ["#2b6cb0", "#c05621", "#2f855a", "#9b2c2c", "#6b46c1", "#b7791f", "#2c7a7b"];

export default function CfdResidualChart({
  iterations,
  residuals,
  height = 180,
  log = true,
  label = "Residual geçmişi (log ölçek)",
  testId = "cfd-residual-chart",
}: {
  iterations: number[];
  residuals: Record<string, number[]>;
  height?: number;
  log?: boolean;
  label?: string;
  testId?: string;
}) {
  const names = Object.keys(residuals).filter((k) => residuals[k]?.length);
  if (!iterations.length || !names.length) return <p className="crash-behavior-hint">Henüz veri yok.</p>;
  const w = 320;
  const pad = { l: 38, r: 8, t: 8, b: 20 };
  const all = names.flatMap((k) => residuals[k]).filter((v) => Number.isFinite(v) && (!log || v > 0));
  let lo: number;
  let hi: number;
  let ticks: number[];
  if (log) {
    lo = Math.floor(Math.log10(Math.min(...all)));
    hi = Math.ceil(Math.log10(Math.max(...all)));
    if (hi === lo) hi = lo + 1;
    ticks = Array.from({ length: hi - lo + 1 }, (_, i) => hi - i);
  } else {
    const mn = Math.min(...all);
    const mx = Math.max(...all);
    const m = (mx - mn || Math.abs(mx) || 1) * 0.08;
    lo = mn - m;
    hi = mx + m;
    ticks = Array.from({ length: 5 }, (_, i) => hi - ((hi - lo) * i) / 4);
  }
  const xMax = iterations[iterations.length - 1] || 1;
  const x = (it: number) => pad.l + ((w - pad.l - pad.r) * it) / xMax;
  const yv = (v: number) => (log ? Math.log10(Math.max(v, 1e-30)) : v);
  const y = (v: number) => pad.t + ((height - pad.t - pad.b) * (hi - yv(v))) / (hi - lo);
  const tickY = (t: number) => pad.t + ((height - pad.t - pad.b) * (hi - t)) / (hi - lo);
  return (
    <figure className="cfd-chart" data-testid={testId}>
      <svg viewBox={`0 0 ${w} ${height}`} role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={w - pad.r} y1={tickY(t)} y2={tickY(t)} className="cfd-chart-grid" />
            <text x={pad.l - 4} y={tickY(t) + 3} textAnchor="end" className="cfd-chart-tick">
              {log ? `1e${t}` : t.toPrecision(3)}
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
        {names.map((k, i) => {
          const last = residuals[k][residuals[k].length - 1];
          return (
            <span key={k}>
              <i style={{ background: COLORS[i % COLORS.length] }} /> {k} {log ? last.toExponential(1) : last.toPrecision(4)}
            </span>
          );
        })}
      </figcaption>
    </figure>
  );
}
