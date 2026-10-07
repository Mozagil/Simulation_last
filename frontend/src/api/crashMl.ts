/** Crash DOE + vekil model API (1.19c / 1.19e): /crash/doe, /crash/ml. */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class CrashMlApiError extends Error {}

export interface CrashDoeCaseInfo {
  id: number;
  index: number;
  status: string;
  /** Taranan değerler: noktalı yol → değer */
  values: Record<string, number>;
  geometry_id: number | null;
  run_id: number | null;
  message: string | null;
}

export interface CrashDoeStudyInfo {
  id: number;
  name: string | null;
  template_id: string;
  seed: number;
  status: string;
  message: string | null;
  created_at: string | null;
  vary: Record<string, [number, number]> | null;
  n_cases: number;
  counts: Record<string, number>;
  cases?: CrashDoeCaseInfo[];
}

export interface CrashDoeSpecPayload {
  name?: string;
  /** Sabit kısım: CrashScenarioRequest gövdesi (template_id dahil) */
  base: Record<string, unknown>;
  /** Taranan alanlar: noktalı yol → [alt, üst] */
  vary: Record<string, [number, number]>;
  n_samples: number;
  seed: number;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* gövde yok */
    }
    throw new CrashMlApiError(detail);
  }
  return (await res.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function fetchCrashDoeStudies(): Promise<CrashDoeStudyInfo[]> {
  return (await request<{ studies: CrashDoeStudyInfo[] }>(`${API_BASE_URL}/crash/doe/studies`)).studies;
}

export function fetchCrashDoeStudy(id: number): Promise<CrashDoeStudyInfo> {
  return request<CrashDoeStudyInfo>(`${API_BASE_URL}/crash/doe/studies/${id}`);
}

export function createCrashDoeStudy(spec: CrashDoeSpecPayload): Promise<CrashDoeStudyInfo> {
  return request<CrashDoeStudyInfo>(`${API_BASE_URL}/crash/doe/studies`, post(spec));
}

export function resumeCrashDoeStudy(id: number): Promise<CrashDoeStudyInfo> {
  return request<CrashDoeStudyInfo>(`${API_BASE_URL}/crash/doe/studies/${id}/run`, { method: "POST" });
}
