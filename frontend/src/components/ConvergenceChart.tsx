/** Yakınsama eğrisi: düğüm sayısı (log) → hedef değer (ML Studio 1a kartı).
 *
 * Log-x bilinçli: mesh incelttikçe düğüm sayısı katlanarak artar, lineer
 * eksende son iki basamak grafiğin tamamını yiyor ve "yakınsadı mı" sorusu
 * görünmez oluyor.
 *
 * Analitik referans kesikli çizgi olarak çizilir — sapmanın yönü (FEA üstte mi
 * altta mı) yakınsamanın kendisi kadar bilgi taşır. Kartın altında üç sayı:
 * en ince, son iki basamak, analitiğe göre. Grafik yorum yazmaz; "kararlı
 * bant" gibi bir eşik çizmez — hangi mesh'in yeterli olduğuna mühendis bakar.
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
  /** Son iki basamak arası yüzde değişim (backend özeti). */
  lastStepDeltaPct?: number | null;
}

const W = 400;
const H = 170;

/** Düğüm sayısı binlik ayracı İNCE BOŞLUK.
 *
 * tr-TR nokta kullanıyor ("3.578") ve aynı tabloda hedef değerler ondalık
 * nokta taşıyor ("23.964") — yan yana okunduğunda 3578 düğüm 3.578 sanılıyor.
 * Panel de bunu kullanır (tek tanım, tek görünüm).
 */
export function fmtCount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("en-US").replace(/,/g, " ");
}

/** "2.1 k", "186 k", "930" — kart altı kısa düğüm sayısı. */
export function fmtCountShort(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} M`;
  if (value >= 1e4) return `${Math.round(value / 1e3)} k`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)} k`;
  return String(Math.round(value));
}

export function niceValue(v: number): string {
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}

export function fmtSignedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export default function ConvergenceChart({ title, unit, points, analytic, lastStepDeltaPct }: Props) {
  const usable = points.filter(
    (p) => Number.isFinite(p.value) && Number.isFinite(p.nodeCount) && p.nodeCount > 0,
  );
  const hasRef = analytic != null && Number.isFinite(analytic);
  const head = (
    <span className="cv-card-head">
      <strong>
        {title} · {unit}
      </strong>
      {hasRef ? (
        <span className="ds-sb cv-ref-legend">
          <span className="cv-ref-swatch" />
          analitik {niceValue(analytic as number)}
        </span>
      ) : null}
    </span>
  );
  if (usable.length < 2) {
    return (
      <figure className="cv-card">
        {head}
        <p className="ds-sb">Grafik için en az 2 çözülmüş basamak gerekir.</p>
      </figure>
    );
  }

  const xs = usable.map((p) => Math.log10(p.nodeCount));
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const xSpan = xMax - xMin || 1;

  const values = usable.map((p) => p.value);
  const candidates = hasRef ? [...values, analytic as number] : values;
  let yMin = Math.min(...candidates);
  let yMax = Math.max(...candidates);
  const ySpanRaw = yMax - yMin;
  // Tamamen düz bir seri (yakınsamış deplasman) sıfır yükseklikte kutu verir;
  // değerin kendisinin %2'si kadar pay bırakıp çizgiyi ortaya alıyoruz.
  const pad = ySpanRaw > 0 ? ySpanRaw * 0.15 : Math.max(Math.abs(yMax) * 0.02, 1e-9);
  yMin -= pad;
  yMax += pad;
  const ySpan = yMax - yMin || 1;

  const px = (nodeCount: number) => 22 + ((Math.log10(nodeCount) - xMin) / xSpan) * (W - 44);
  const py = (value: number) => 12 + (1 - (value - yMin) / ySpan) * (H - 24);

  const path = usable.map((p) => `${px(p.nodeCount).toFixed(1)},${py(p.value).toFixed(1)}`).join(" ");
  const first = usable[0];
  const last = usable[usable.length - 1];
  const vsRef = hasRef ? ((last.value - (analytic as number)) / (analytic as number)) * 100 : null;

  return (
    <figure className="cv-card">
      {head}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${title} yakınsama eğrisi`}
        preserveAspectRatio="none"
        className="cv-svg"
      >
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} className="cv-frame" />
        {hasRef && (
          <line x1="0" y1={py(analytic as number)} x2={W} y2={py(analytic as number)} className="cv-ref" />
        )}
        <polyline points={path} className="cv-line" />
        {usable.map((p) => (
          <rect
            key={p.elementSize}
            x={px(p.nodeCount) - 3.5}
            y={py(p.value) - 3.5}
            width="7"
            height="7"
            className="cv-dot"
          >
            <title>
              {`es=${p.elementSize} mm · ${fmtCount(p.nodeCount)} düğüm · ${niceValue(p.value)} ${unit}`}
            </title>
          </rect>
        ))}
      </svg>
      <span className="cv-axis ds-sb">
        <span>{fmtCountShort(first.nodeCount)} düğüm</span>
        <span>düğüm sayısı (log)</span>
        <span>{fmtCountShort(last.nodeCount)}</span>
      </span>
      <span className="cv-stats">
        <span>
          <span className="ml-k">En ince</span>
          <strong>{`${niceValue(last.value)} ${unit}`}</strong>
        </span>
        <span>
          <span className="ml-k">Son iki basamak</span>
          <strong>{fmtSignedPct(lastStepDeltaPct)}</strong>
        </span>
        <span>
          <span className="ml-k">Analitiğe göre</span>
          <strong>{vsRef == null ? "—" : fmtSignedPct(vsRef)}</strong>
        </span>
      </span>
    </figure>
  );
}
