/** Crash (OpenRadioss) API — Faz 1.7–1.9. CalculiX `/solve` kullanmaz. */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class CrashApiError extends Error {}

export interface CrashBarrierPayload {
  speed_m_s: number;
  angle_deg: number;
  wall: {
    point: [number, number, number];
    normal: [number, number, number];
  };
}

export interface CrashModelPayload {
  law: "elastic" | "plastic";
  isolid: number;
  ismstr: number;
  nip: number;
  sigma_y_pa?: number | null;
  harden_b_mpa: number;
  harden_n: number;
}

export interface CrashSolveRequest {
  geometry_id: number;
  barrier: CrashBarrierPayload;
  dimension?: number;
  run_solver?: boolean;
  wait?: boolean;
  t_end_ms?: number;
  name?: string;
  model?: CrashModelPayload;
  scenario?: "rigid_wall" | "plate_ball";
}

export interface CrashSolveResponse {
  job_id: string;
  geometry_id: number;
  status: string;
  message: string;
  starter_url: string;
  engine_url: string;
  progress_url: string;
  ws_url: string;
  cards: Record<string, boolean>;
  openradioss_available: boolean;
  solver_ran: boolean;
  scalars: Record<string, number>;
}

export interface CrashJobSnapshot {
  job_id: string;
  geometry_id?: number;
  status?: string;
  message?: string;
  percent?: number;
  cycle?: number | null;
  time_ms?: number | null;
  hub_state?: string;
  scalars?: Record<string, number>;
  starter_url?: string;
  solver_ran?: boolean;
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : JSON.stringify(item),
        )
        .join("; ");
    }
  }
  return `HTTP ${status}`;
}

export async function postCrashSolve(
  body: CrashSolveRequest,
): Promise<CrashSolveResponse> {
  const response = await fetch(`${API_BASE_URL}/crash/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new CrashApiError(detailMessage(payload, response.status));
  }
  return payload as CrashSolveResponse;
}

export async function fetchCrashJob(jobId: string): Promise<CrashJobSnapshot> {
  const response = await fetch(`${API_BASE_URL}/crash/jobs/${jobId}`);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new CrashApiError(detailMessage(payload, response.status));
  }
  return payload as CrashJobSnapshot;
}

export function crashJobWsUrl(jobId: string): string {
  const base = API_BASE_URL.replace(/\/$/, "");
  return `${base.replace(/^http/, "ws")}/crash/jobs/${jobId}/ws`;
}
