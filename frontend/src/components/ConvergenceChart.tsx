/** Yakınsama eğrisi: düğüm sayısı (log) → hedef değer.
 *
 * Log-x bilinçli: mesh incelttikçe düğüm sayısı katlanarak artar, lineer
 * eksende son iki basamak grafiğin tamamını yiyor ve "yakınsadı mı" sorusu
 * görünmez oluyor.
 *
 * Analitik referans kesikli çizgi olarak çizilir — sapmanın yönü (FEA üstte mi
 * altta mı) yakınsamanın kendisi kadar bilgi taşır. Grafik yorum yazmaz.
 */

export interface ConvergencePoint {
  nodeCount: number;
  value: number;
  elementSize: number;
}

interface Props {
  title: string;
  unit: string;
  points: ConvergencePoint[];
  analytic?: number | null;
}

const W = 300;
const H = 150;
const PAD_L = 46;
const PAD_R = 10;
const PAD_T = 14;
const PAD_B = 26;

/** Düğüm sayısı binlik ayracı İNCE BOŞLUK.
 *
 * tr-TR nokta kullanıyor ("3.578") ve aynı tabloda hedef değerler ondalık
 * nokta taşıyor ("23.964") — yan yana okunduğunda 3578 düğüm 3.578 sanılıyor.
 * Panel de bunu kullanır (tek tanım, tek görünüm).
 */
export function fmtCount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("en-US").replace(/,/g, " ");
}

function niceValue(v: number): string {
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}

export default function ConvergenceChart({ title, unit, points, analytic }: Props) {
  const usable = points.filter(
    (p) => Number.isFinite(p.value) && Number.isFinite(p.nodeCount) && p.nodeCount > 0,
  );
  if (usable.length < 2) {
    return (
      <figure className="convergence-chart">
        <figcaption>
          {title} <span className="convergence-chart-unit">({unit})</span>
        </figcaption>
        <p className="filename">Grafik için en az 2 çözülmüş basamak gerekir.</p>
      </figure>
    );
  }

  const xs = usable.map((p) => Math.log10(p.nodeCount));
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const xSpan = xMax - xMin || 1;

  const values = usable.map((p) => p.value);
  const candidates = analytic != null && Number.isFinite(analytic) ? [...values, analytic] : values;
  let yMin = Math.min(...candidates);
  let yMax = Math.max(...candidates);
  const ySpanRaw = yMax - yMin;
  // Tamamen düz bir seri (yakınsamış deplasman) sıfır yükseklikte kutu verir;
  // değerin kendisinin %2'si kadar pay bırakıp çizgiyi ortaya alıyoruz.
  const pad = ySpanRaw > 0 ? ySpanRaw * 0.15 : Math.max(Math.abs(yMax) * 0.02, 1e-9);
  yMin -= pad;
  yMax += pad;
  const ySpan = yMax - yMin || 1;

  const px = (nodeCount: number) =>
    PAD_L + ((Math.log10(nodeCount) - xMin) / xSpan) * (W - PAD_L - PAD_R);
  const py = (value: number) => PAD_T + (1 - (value - yMin) / ySpan) * (H - PAD_T - PAD_B);

  const path = usable.map((p) => `${px(p.nodeCount)},${py(p.value)}`).join(" ");
  const first = usable[0];
  const last = usable[usable.length - 1];

  return (
    <figure className="convergence-chart">
      <figcaption>
        {title} <span className="convergence-chart-unit">({unit})</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${title} yakınsama eğrisi`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* eksenler */}
        <line
          x1={PAD_L}
          y1={PAD_T}
          x2={PAD_L}
          y2={H - PAD_B}
          stroke="var(--border)"
          strokeWidth={1}
        />
        <line
          x1={PAD_L}
          y1={H - PAD_B}
          x2={W - PAD_R}
          y2={H - PAD_B}
          stroke="var(--border)"
          strokeWidth={1}
        />

        {/* analitik referans */}
        {analytic != null && Number.isFinite(analytic) && (
          <>
            <line
              x1={PAD_L}
              y1={py(analytic)}
              x2={W - PAD_R}
              y2={py(analytic)}
              stroke="var(--muted)"
              strokeWidth={1}
              strokeDasharray="4 3"
            />
            <text
              x={W - PAD_R}
              y={py(analytic) - 4}
              textAnchor="end"
              fontSize={8}
              fill="var(--muted)"
            >
              analitik {niceValue(analytic)}
            </text>
          </>
        )}

        <polyline points={path} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
        {usable.map((p) => (
          <circle
            key={p.elementSize}
            cx={px(p.nodeCount)}
            cy={py(p.value)}
            r={2.5}
            fill="var(--accent)"
          >
            <title>
              {`es=${p.elementSize} mm · ${fmtCount(p.nodeCount)} düğüm · ${niceValue(p.value)} ${unit}`}
            </title>
          </circle>
        ))}

        {/* y ucu etiketleri */}
        <text x={PAD_L - 5} y={PAD_T + 4} textAnchor="end" fontSize={8} fill="var(--muted)">
          {niceValue(yMax)}
        </text>
        <text x={PAD_L - 5} y={H - PAD_B} textAnchor="end" fontSize={8} fill="var(--muted)">
          {niceValue(yMin)}
        </text>

        {/* x ucu etiketleri: kaba → ince */}
        <text x={PAD_L} y={H - PAD_B + 11} textAnchor="start" fontSize={8} fill="var(--muted)">
          {fmtCount(first.nodeCount)}
        </text>
        <text x={W - PAD_R} y={H - PAD_B + 11} textAnchor="end" fontSize={8} fill="var(--muted)">
          {fmtCount(last.nodeCount)}
        </text>
        <text
          x={(PAD_L + W - PAD_R) / 2}
          y={H - 3}
          textAnchor="middle"
          fontSize={8}
          fill="var(--muted)"
        >
          düğüm sayısı (log)
        </text>
      </svg>
    </figure>
  );
}
