/** Mesh yakınsama taraması API (0.6.1). */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class ConvergenceApiError extends Error {}

export interface ConvergenceTarget {
  value: number | null;
  /** Bir önceki (daha kaba) çözülen basamağa göre yüzde değişim. */
  delta_prev_pct: number | null;
  /** En ince çözülen mesh'e göre yüzde sapma. */
  delta_finest_pct: number | null;
}

export interface ConvergenceAnalyticMetric {
  key: string;
  label: string;
  unit: string;
  analytic: number;
  fea: number;
  rel_error: number;
  warn: boolean;
}

export interface ConvergenceRow {
  index: number;
  element_size: number;
  ratio: number | null;
  run_id: number | null;
  status: string;
  message: string | null;
  node_count: number | null;
  element_count: number | null;
  targets: Record<string, ConvergenceTarget>;
  analytic: {
    skipped: boolean;
    reason: string | null;
    warned: boolean;
    metrics: ConvergenceAnalyticMetric[];
  } | null;
}

export interface ConvergenceSummary {
  finest: number | null;
  finest_element_size: number | null;
  finest_node_count: number | null;
  last_step_delta_pct: number | null;
}

export interface ConvergenceReport {
  n_steps: number;
  n_solved: number;
  targets: string[];
  summary: Record<string, ConvergenceSummary>;
  rows: ConvergenceRow[];
  geometry_id: number;
  template_id: string;
  template_params: Record<string, number | string>;
  material: { id: number; name: string; youngs_modulus: number };
  name: string | null;
}

export interface ConvergenceRequest {
  template_id: string;
  params: Record<string, number | string>;
  material_id: number;
  element_ratios?: number[];
  element_sizes?: number[];
  dimension?: number;
  element_scheme?: string;
  name?: string;
}

async function parseError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length && d[0]?.msg) return String(d[0].msg);
    if (d != null) return String(d);
  } catch {
    /* ignore */
  }
  return `${fallback} (HTTP ${res.status}).`;
}

export async function runConvergence(
  body: ConvergenceRequest,
): Promise<ConvergenceReport> {
  const res = await fetch(`${API_BASE_URL}/doe/convergence`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ConvergenceApiError(await parseError(res, "Yakınsama taraması başarısız"));
  return (await res.json()) as ConvergenceReport;
}

/** "1.5, 1.2, 0.8" → [1.5, 1.2, 0.8]. Geçersiz/boş parça atlanır. */
export function parseNumberList(raw: string): number[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => Number(s))
    .filter((v) => Number.isFinite(v) && v > 0);
}
