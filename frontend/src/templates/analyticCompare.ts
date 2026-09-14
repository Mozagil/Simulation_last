export interface AnalyticMetric {
  key: string;
  label: string;
  unit: string;
  analytic: number;
  fea: number;
  rel_error: number;
  threshold: number;
  warn: boolean;
}

export interface AnalyticComparison {
  template_id: string;
  skipped: boolean;
  reason: string | null;
  warned: boolean;
  metrics: AnalyticMetric[];
}

export function isAnalyticComparison(value: unknown): value is AnalyticComparison {
  if (value == null || typeof value !== "object") return false;
  const v = value as AnalyticComparison;
  return typeof v.template_id === "string" && Array.isArray(v.metrics);
}

export function comparisonFromScalars(
  scalars: Record<string, unknown> | undefined | null,
): AnalyticComparison | null {
  if (!scalars) return null;
  const raw = scalars._analytic_comparison;
  return isAnalyticComparison(raw) ? raw : null;
}

export function pickAnalyticComparison(
  primary?: AnalyticComparison | null,
  scalars?: Record<string, unknown> | null,
): AnalyticComparison | null {
  if (isAnalyticComparison(primary)) return primary;
  return comparisonFromScalars(scalars);
}

export function formatRelPercent(rel: number): string {
  return `${(rel * 100).toFixed(1)}%`;
}
