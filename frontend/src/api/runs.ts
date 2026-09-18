/** Analiz geçmişi (AnalysisRun) API — ROADMAP.md "7. Veritabanına kayıt +
 * geçmiş". Backend'deki `analysis_runs` tablosuyla birebir eşleşir: her
 * /solve çağrısı kalıcı bir satır üretir. Kullanıcı geçmişten silebilir.
 */

import type { AnalyticComparison } from "../templates/analyticCompare";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class RunFetchError extends Error {}

export interface RunSummary {
  id: number;
  geometry_id: number;
  geometry_filename: string | null;
  /** Şablondan üretilen geometrilerde şablon kimliği; yüklenen STEP'te null. */
  template_id: string | null;
  /** Şablon parametreleri (L, T, W …) — DOE'de hangi kombinasyonun hangi
   * sonucu verdiğini okumak için. */
  template_params: Record<string, number | string> | null;
  name: string | null;
  created_at: string;
  dimension: number;
  status: "pending" | "inp_only" | "solved" | "failed";
  message: string | null;
  scalars: Record<string, number>;
  /** Hangi DOE/kalite setinden geldi; elle çözümlerde null. */
  doe_study_id?: number | null;
  /** Elle dışlanmış mı — deneme, mükerrer, kalitesiz koşular. Dışlanan
   * run silinmez, sadece eğitim setinden ve (istenirse) listeden çıkar. */
  excluded?: boolean;
  exclude_reason?: string | null;
}

export interface RunDetail extends RunSummary {
  element_size: number | null;
  element_scheme: "tet" | "quad" | "mix" | null;
  shell_thickness: number | null;
  bcs: unknown[];
  materials_snapshot: unknown[];
  tessellation_url: string | null;
  mesh_preview_url: string | null;
  results_preview_url: string | null;
  inp_url: string | null;
  analytic_comparison?: AnalyticComparison | null;
}

export interface RunFilter {
  /** Yalnız bu şablonun run'ları — kiriş ve delikli plaka karışmasın. */
  templateId?: string | null;
  /** Yalnız bu DOE setinin run'ları. */
  doeStudyId?: number | null;
  /** Dışlanmışları gizle. */
  includeExcluded?: boolean;
  /** YALNIZ dışlanmışları göster (gözden geçirmek için). */
  onlyExcluded?: boolean;
}

function filterQuery(f?: RunFilter): string {
  if (!f) return "";
  const q = new URLSearchParams();
  if (f.templateId) q.set("template_id", f.templateId);
  if (f.doeStudyId != null) q.set("doe_study_id", String(f.doeStudyId));
  if (f.includeExcluded === false) q.set("include_excluded", "false");
  if (f.onlyExcluded) q.set("only_excluded", "true");
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function setRunExcluded(
  runId: number,
  excluded: boolean,
  reason?: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs/${runId}/exclude`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ excluded, reason: reason ?? null }),
  });
  if (!response.ok) {
    throw new RunFetchError(`İşaretlenemedi (HTTP ${response.status}).`);
  }
}

export async function setRunsExcludedBulk(
  runIds: number[],
  excluded: boolean,
  reason?: string,
): Promise<number> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs/exclude-bulk`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: runIds, excluded, reason: reason ?? null }),
  });
  if (!response.ok) {
    throw new RunFetchError(`Toplu işaretleme başarısız (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as { updated: number };
  return body.updated;
}

export async function fetchRuns(filter?: RunFilter): Promise<RunSummary[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs${filterQuery(filter)}`);
  if (!response.ok) {
    throw new RunFetchError(`Geçmiş alınamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as { runs: RunSummary[] };
  return body.runs;
}

export async function fetchRunDetail(runId: number): Promise<RunDetail> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs/${runId}`);
  if (!response.ok) {
    throw new RunFetchError(`Run detayı alınamadı (HTTP ${response.status}).`);
  }
  return (await response.json()) as RunDetail;
}

export async function deleteRun(runId: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs/${runId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new RunFetchError(`Run silinemedi (HTTP ${response.status}).`);
  }
}
