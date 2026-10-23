/** MBD (Project Chrono) API — Faz 5.2b. */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class MbdApiError extends Error {}

function detailMessage(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join("; ");
  }
  return `HTTP ${status}`;
}

export interface MbdSolveRequest {
  sprung_mass_kg: number;
  unsprung_mass_kg: number;
  suspension_k_n_per_m: number;
  suspension_c_n_s_per_m: number;
  tire_k_n_per_m: number;
  speed_m_s: number;
  road: { kind: "cosine_bump" | "step"; height_mm: number; length_m: number; start_m: number };
  t_end_s: number;
  dt_s: number;
}

export interface MbdResult {
  job_id: string;
  state: string;
  scalars: Record<string, number>;
  curves: Record<string, number[]>;
  diagnostics: {
    n_rows?: number;
    columns?: string[];
    summary?: { wall_s?: number; steps?: number; dt_s?: number; t_end_s?: number };
  };
}

export async function postMbdSolve(body: MbdSolveRequest): Promise<MbdResult> {
  const response = await fetch(`${API_BASE_URL}/mbd/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new MbdApiError(detailMessage(payload, response.status));
  return payload as MbdResult;
}
