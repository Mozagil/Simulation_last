/** DOE sağ pano — "Sonuç dağılımı" (Claude Design ML Studio 1a).
 *
 * Bir çalışmanın örneklerini tabloya bakmadan özetler:
 *   - kalite şeridi: ok / analytic_warn / diğer etiketlerin oranı
 *   - 4 strip grafik: maks deplasman, maks von Mises, Δ deplasman, Δ VM
 *     (her nokta bir örnek; kutu = çeyrekler arası, çizgi = ortalama;
 *     uyarılı örnek kahverengi)
 *   - en çok sapan 4 örnek (analitik referansa göre), tıklayınca run açılır
 * Veri `fetchDoeResults` çıktısıdır; burada hiçbir şey yeniden hesaplanmaz,
 * yalnız sıralanıp çizilir. Öneri/karar yok — mühendis bakar.
 */

import type { DoeQualityInfo, DoeResultRow, DoeResults, DoeStudyInfo } from "../api/doe";
import DoeResultsTable from "./DoeResultsTable";

const OK_LABEL = "ok";
const WARN_LABELS = new Set(["analytic_warn"]);

/** Etiket → renk sınıfı: ok yeşil, analitik uyarı kahverengi, gerisi gri. */
export function qualityTone(label: string): "ok" | "warn" | "other" {
  if (label === OK_LABEL) return "ok";
  if (WARN_LABELS.has(label)) return "warn";
  return "other";
}

function fmtVal(v: number, digits: number): string {
  return String(Number(v.toFixed(digits)));
}

function fmtSigned(v: number): string {
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
}

interface StripSpec {
  key: string;
  label: string;
  unit: string;
  pick: (r: DoeResultRow) => number | null;
  fmt: (v: number) => string;
}

const STRIPS: StripSpec[] = [
  { key: "u", label: "Maks deplasman", unit: "mm", pick: (r) => r.scalars.max_displacement ?? null, fmt: (v) => fmtVal(v, 2) },
  { key: "vm", label: "Maks von Mises", unit: "MPa", pick: (r) => r.scalars.max_von_mises ?? null, fmt: (v) => fmtVal(v, 0) },
  { key: "du", label: "Δ deplasman", unit: "% analitiğe göre", pick: (r) => r.dev_displacement_pct, fmt: fmtSigned },
  { key: "dvm", label: "Δ von Mises", unit: "% analitiğe göre", pick: (r) => r.dev_von_mises_pct, fmt: fmtSigned },
];

const W = 600;

/** Deterministik dikey saçılım: aynı örnek her render'da aynı yerde. */
function jitter(index: number): number {
  const x = Math.sin(index * 12.9898) * 43758.5453;
  return 12 + (x - Math.floor(x)) * 20;
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function Strip({ spec, rows }: { spec: StripSpec; rows: DoeResultRow[] }) {
  const pts = rows
    .map((r) => ({ v: spec.pick(r), q: r.quality, i: r.index }))
    .filter((p): p is { v: number; q: string; i: number } => p.v != null && Number.isFinite(p.v));
  if (pts.length === 0) {
    return (
      <div className="doe-strip" data-testid={`strip-${spec.key}`}>
        <span className="doe-strip-label">
          <span className="doe-strip-name">{spec.label}</span>
          <span className="doe-strip-unit">{spec.unit}</span>
        </span>
        <span className="doe-strip-empty">veri yok</span>
        <span />
      </div>
    );
  }
  const vals = pts.map((p) => p.v).sort((a, b) => a - b);
  const lo = vals[0];
  const hi = vals[vals.length - 1];
  const span = hi - lo || 1;
  const x = (v: number) => ((v - lo) / span) * W;
  const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
  const q1 = quantile(vals, 0.25);
  const q3 = quantile(vals, 0.75);
  return (
    <div className="doe-strip" data-testid={`strip-${spec.key}`}>
      <span className="doe-strip-label">
        <span className="doe-strip-name">{spec.label}</span>
        <span className="doe-strip-unit">{spec.unit}</span>
      </span>
      <svg viewBox={`0 0 ${W} 44`} preserveAspectRatio="none" className="doe-strip-svg" aria-hidden="true">
        <line x1="0" y1="22" x2={W} y2="22" className="doe-strip-axis" />
        <rect x={x(q1)} y="10" width={Math.max(2, x(q3) - x(q1))} height="24" className="doe-strip-iqr" />
        {pts.map((p) => (
          <circle
            key={p.i}
            cx={x(p.v)}
            cy={jitter(p.i)}
            r="2.6"
            className={`doe-strip-dot doe-strip-dot-${qualityTone(p.q)}`}
          />
        ))}
        <line x1={x(mean)} y1="4" x2={x(mean)} y2="40" className="doe-strip-mean" />
      </svg>
      <span className="doe-strip-stats">
        <span>
          <span className="doe-strip-unit">ort </span>
          <strong>{spec.fmt(mean)}</strong>
        </span>
        <span className="doe-strip-unit">
          {spec.fmt(lo)} – {spec.fmt(hi)}
        </span>
      </span>
    </div>
  );
}

/** |Δ| en büyük 4 örnek — VM sapması, yoksa deplasman sapması. */
export function topOutliers(rows: DoeResultRow[], n = 4): { row: DoeResultRow; dev: number }[] {
  return rows
    .map((row) => ({ row, dev: row.dev_von_mises_pct ?? row.dev_displacement_pct ?? null }))
    .filter((o): o is { row: DoeResultRow; dev: number } => o.dev != null && Number.isFinite(o.dev))
    .sort((a, b) => Math.abs(b.dev) - Math.abs(a.dev))
    .slice(0, n);
}

function paramSummary(row: DoeResultRow, columns: string[]): string {
  return columns
    .slice(0, 3)
    .map((c) => {
      const v = row.params[c];
      return `${c} ${typeof v === "number" ? Number(v.toPrecision(3)) : v ?? "—"}`;
    })
    .join(" · ");
}

function statusTone(status: string): "ok" | "warn" | "other" {
  if (status === "completed") return "ok";
  if (status === "running" || status === "pending") return "warn";
  return "other";
}

const STATUS_TR: Record<string, string> = {
  completed: "tamamlandı",
  running: "çalışıyor",
  pending: "bekliyor",
  failed: "hata",
};

interface DoeDistributionProps {
  study: DoeStudyInfo;
  quality: DoeQualityInfo | null;
  results: DoeResults | null;
  loading: boolean;
  tableOpen: boolean;
  onToggleTable: () => void;
  onOpenRun?: (runId: number) => void;
}

export default function DoeDistribution({
  study,
  quality,
  results,
  loading,
  tableOpen,
  onToggleTable,
  onOpenRun,
}: DoeDistributionProps) {
  const counts = quality?.counts ?? {};
  const total = quality?.n_cases ?? study.n_cases;
  const legend = Object.entries(counts).sort(([a], [b]) => {
    const order = (k: string) => (k === OK_LABEL ? 0 : qualityTone(k) === "warn" ? 1 : 2);
    return order(a) - order(b) || a.localeCompare(b);
  });
  const rows = results?.rows ?? [];
  const outliers = topOutliers(rows);

  return (
    <div className="doe-dist" data-testid="doe-distribution">
      <div className="doe-phead-r">
        <span className="doe-phead-title">
          <span className="ml-k">
            Çalışma #{study.id}
            {study.name ? ` · ${study.name}` : ""} · {study.n_cases} örnek
          </span>
          <span className="ml-h">Sonuç dağılımı</span>
        </span>
        <span className={`doe-st doe-st-${statusTone(study.status)}`}>
          {STATUS_TR[study.status] ?? study.status}
        </span>
        <button
          type="button"
          className="doe-btn doe-btn-ghost"
          disabled={!results}
          onClick={onToggleTable}
        >
          {tableOpen ? "Tabloyu kapat" : "Tabloyu aç"}
        </button>
      </div>

      {study.message ? <p className="doe-dist-msg">{study.message}</p> : null}

      {legend.length > 0 && (
        <div className="doe-qbar-wrap" data-testid="quality-strip">
          <span className="doe-qbar">
            {legend.map(([k, v]) => (
              <span
                key={k}
                className={`doe-qbar-seg doe-qbar-${qualityTone(k)}`}
                style={{ width: `${(v / Math.max(1, total)) * 100}%` }}
                title={`${k} ${v}`}
              />
            ))}
          </span>
          <span className="doe-qbar-legend">
            {legend.map(([k, v]) => (
              <span key={k}>
                <span className={`doe-qbar-swatch doe-qbar-${qualityTone(k)}`} />
                {k} {v}
              </span>
            ))}
          </span>
        </div>
      )}

      {loading && !results ? <p className="doe-empty">Sonuçlar yükleniyor…</p> : null}

      {results && (
        <>
          {STRIPS.map((s) => (
            <Strip key={s.key} spec={s} rows={rows} />
          ))}

          {outliers.length > 0 && (
            <div className="doe-outliers">
              <span className="ml-k">En çok sapan {outliers.length} örnek · analitik referansa göre</span>
              <div className="doe-outlier-grid">
                {outliers.map(({ row, dev }) => (
                  <button
                    key={row.index}
                    type="button"
                    className="doe-outlier"
                    disabled={row.run_id == null || !onOpenRun}
                    onClick={() => row.run_id != null && onOpenRun?.(row.run_id)}
                  >
                    <span className="doe-outlier-head">
                      <strong>#{row.index}</strong>
                      <span className={`doe-st doe-st-${qualityTone(row.quality)}`}>{row.quality}</span>
                    </span>
                    <span className={`doe-outlier-dev doe-outlier-dev-${qualityTone(row.quality)}`}>
                      {fmtSigned(dev)}
                    </span>
                    <span className="doe-outlier-params">{paramSummary(row, results.param_columns)}</span>
                    <span className="doe-outlier-link">{row.run_id != null ? "Run'ı aç →" : "run yok"}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {tableOpen && <DoeResultsTable results={results} onOpenRun={onOpenRun} />}
        </>
      )}
    </div>
  );
}
