/** DOE / batch runner API (0.5.4). */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class DoeApiError extends Error {}

export interface DoeCaseInfo {
  id: number;
  index: number;
  status: string;
  scenario: string;
  element_size: number;
  geometry_params: Record<string, number>;
  geometry_id: number | null;
  run_id: number | null;
  message: string | null;
}

export interface DoeStudyInfo {
  id: number;
  name: string | null;
  template_id: string;
  seed: number;
  status: string;
  message: string | null;
  n_cases: number;
  counts: Record<string, number>;
  cases: DoeCaseInfo[];
}

export interface DoeSpecPayload {
  name?: string;
  template_id: string;
  seed: number;
  n_samples: number;
  /** Taranacak parametreler: ad -> [min, max] */
  geometry: Record<string, [number, number]>;
  /** Taranmayan, sabit verilen parametreler (sayı ya da enum). */
  fixed_params?: Record<string, number | string>;
  element_size: [number, number];
  load_fy?: [number, number];
  /** Senaryodaki tüm yük BC'lerini bu katsayı aralığıyla ölçekler. */
  load_scale?: [number, number];
  material_ids: number[];
  bc_scenarios: { name: string; bcs: Record<string, unknown>[] }[];
  dimension?: number;
  element_scheme?: string;
  run_solver?: boolean;
}

async function parseError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) return String(body.detail);
  } catch {
    /* ignore */
  }
  return `${fallback} (HTTP ${res.status}).`;
}

export async function fetchDoeStudies(): Promise<DoeStudyInfo[]> {
  const res = await fetch(`${API_BASE_URL}/doe/studies`);
  if (!res.ok) throw new DoeApiError(await parseError(res, "DOE listesi alınamadı"));
  const body = (await res.json()) as { studies: DoeStudyInfo[] };
  return body.studies;
}

export async function createDoeStudy(
  spec: DoeSpecPayload,
  wait: boolean,
): Promise<DoeStudyInfo> {
  const res = await fetch(`${API_BASE_URL}/doe/studies?wait=${wait ? "true" : "false"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new DoeApiError(await parseError(res, "DOE başlatılamadı"));
  return (await res.json()) as DoeStudyInfo;
}

export interface DoeQualityInfo {
  study_id: number;
  n_cases: number;
  n_ok: number;
  counts: Record<string, number>;
  flagged: Record<string, number[]>;
}

export async function startQualitySet(opts: {
  material_ids?: number[];
  run_solver?: boolean;
  wait?: boolean;
}): Promise<DoeStudyInfo> {
  const res = await fetch(`${API_BASE_URL}/doe/quality-set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      material_ids: opts.material_ids,
      run_solver: opts.run_solver ?? false,
      wait: opts.wait ?? false,
    }),
  });
  if (!res.ok) throw new DoeApiError(await parseError(res, "Kalite seti başlatılamadı"));
  return (await res.json()) as DoeStudyInfo;
}

export async function fetchDoeQuality(studyId: number): Promise<DoeQualityInfo> {
  const res = await fetch(`${API_BASE_URL}/doe/studies/${studyId}/quality`);
  if (!res.ok) throw new DoeApiError(await parseError(res, "Kalite taraması alınamadı"));
  return (await res.json()) as DoeQualityInfo;
}
