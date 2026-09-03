/** Analiz geçmişi (AnalysisRun) API — ROADMAP.md "7. Veritabanına kayıt +
 * geçmiş". Backend'deki `analysis_runs` tablosuyla birebir eşleşir: her
 * /solve çağrısı kalıcı bir satır üretir, hiçbiri silinmez.
 */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class RunFetchError extends Error {}

export interface RunSummary {
  id: number;
  geometry_id: number;
  geometry_filename: string | null;
  name: string | null;
  created_at: string;
  dimension: number;
  status: "pending" | "inp_only" | "solved" | "failed";
  message: string | null;
  scalars: Record<string, number>;
}

export interface RunDetail extends RunSummary {
  shell_thickness: number | null;
  bcs: unknown[];
  materials_snapshot: unknown[];
  tessellation_url: string | null;
  mesh_preview_url: string | null;
  results_preview_url: string | null;
  inp_url: string | null;
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/runs`);
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
