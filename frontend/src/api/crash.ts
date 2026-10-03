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
  law: "elastic" | "plastic" | "tabulated";
  isolid: number;
  ismstr: number;
  nip: number;
  sigma_y_pa?: number | null;
  harden_b_mpa: number;
  harden_n: number;
  // 1.14a — LAW2 Johnson-Cook; 0 = terim kapalı / Radioss varsayılanı
  eps_p_max?: number;
  sig_max0_mpa?: number;
  jc_c?: number;
  jc_eps_dot0_per_s?: number;
  jc_icc?: number;
  jc_fsmooth?: number;
  jc_fcut_hz?: number;
  jc_chard?: number;
  jc_m?: number;
  jc_t_melt_k?: number;
  jc_rho_cp?: number;
  jc_t_r_k?: number;
  // 1.14c — LAW36 tablo
  tab_curves?: { eps_dot_per_s: number; points: [number, number][] }[];
  tab_eps_t?: number;
  tab_eps_m?: number;
  tab_eps_f?: number;
  tab_vp?: number;
  /** 1.14d — kopma kriterleri; yoksa kopma yok */
  fail?: CrashFailPayload;
  /** Kabuk parçalar (2D mesh) için /PROP/TYPE1; 0 = Radioss /DEF_SHELL varsayılanı. */
  shell?: CrashShellPayload;
}

export interface CrashFailPayload {
  johnson?: {
    d1: number;
    d2: number;
    d3: number;
    d4: number;
    d5: number;
    eps_dot0_per_s: number;
    ifail_sh: number;
    ifail_so: number;
    dadv: number;
  };
  tensstrain?: { eps_t1: number; eps_t2: number; eps_f1: number; eps_f2: number; s_flag: number };
}

export interface CrashShellPayload {
  /** Ortak kalınlık (mm); parça satırındaki t bunu ezer. */
  thickness_mm?: number | null;
  ishell: number;
  ish3n: number;
  ismstr: number;
  /** N: kalınlık boyunca integrasyon noktası (0, 1, 3…10) */
  nip: number;
}

/** Parça rolü: hareketli (ilk hız alır) ya da sabit (/BCS). Verilmeyen parça hareketli. */
export interface CrashPartSpec {
  part_id: number;
  role: "moving" | "fixed";
  /** Kabuk parça kalınlığı (mm); boşsa model.shell.thickness_mm. */
  thickness_mm?: number | null;
  /** 1.14b — parça başına kart; yoksa istekteki global model */
  model?: CrashModelPayload;
}

/** Temas (1.12): /INTER/TYPE7 (slave düğüm → master yüzey) | TYPE24 (yüzey ↔ yüzey).
 * Parça kimlikleri mesh part_id'si; master = slave → self-contact. Bayraklar Radioss
 * değerleri (0 = Radioss varsayılanı); öneri yok, mühendis doldurur. */
export interface CrashContactSpec {
  type: 7 | 24;
  master_part: number;
  slave_part: number;
  fric: number;
  stfac: number;
  /** mm — yalnız TYPE7 */
  gapmin: number;
  istf: number;
  inacti: number;
  /** yalnız TYPE24 */
  iedge: number;
}

/** 1.15a — engine çıktı aralıkları + zaman adımı kartı; null/"" = varsayılan. */
export interface CrashEnginePayload {
  th_dt_ms: number | null;
  anim_dt_ms: number | null;
  dt_kind: string;
  dt_scale: number;
  dt_min_ms: number;
}

/** 1.15b — /TH grupları; değişkenler backend'de Radioss sırasına dizilir. */
export interface CrashThPayload {
  rwall: { enabled: boolean; vars: string[] };
  inter: { enabled: boolean; vars: string[] };
  part: { enabled: boolean; vars: string[] };
  sect: { enabled: boolean; vars: string[] };
  node_ids: number[];
  node_vars: string[];
}

/** 1.15c — /SECT/PARAL paralelkenar kesit (mm). */
export interface CrashSectionPayload {
  name: string;
  origin: [number, number, number];
  corner1: [number, number, number];
  corner2: [number, number, number];
  parts: number[];
  iframe: number;
}

export interface CrashSolveRequest {
  geometry_id: number;
  barrier: CrashBarrierPayload;
  parts?: CrashPartSpec[];
  contacts?: CrashContactSpec[];
  /** false → /RWALL yazılmaz; ilk hız yine bariyerden. */
  use_rigid_wall?: boolean;
  dimension?: number;
  run_solver?: boolean;
  wait?: boolean;
  t_end_ms?: number;
  name?: string;
  model?: CrashModelPayload;
  scenario?: "rigid_wall" | "plate_ball";
  engine?: CrashEnginePayload;
  th?: CrashThPayload;
  sections?: CrashSectionPayload[];
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
  diagnostics?: CrashDiagnostics;
  /** 1.16a — crash_runs kaydı (geometri yoksa null) */
  run_id?: number | null;
}

/** 1.14f — solver listing'inden okunan veri (yorum yok). */
export interface CrashDiagnostics {
  starter_errors?: Record<string, number>;
  starter_warnings?: Record<string, number>;
  deleted_elements?: { criterion: string; kind: string; element: number; time: number | null }[];
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
  /** time (ms), rwall_force / contact_k_force (kN) … */
  curves?: Record<string, number[]>;
  starter_url?: string;
  solver_ran?: boolean;
  diagnostics?: CrashDiagnostics;
}

/** 1.16 — crash koşu kaydı (crash_runs). */
export interface CrashRunSummary {
  id: number;
  job_id: string;
  geometry_id: number;
  name: string | null;
  created_at: string | null;
  dimension: number | null;
  t_end_ms: number | null;
  status: string;
  message: string | null;
  solver_ran: boolean;
  scalars: Record<string, number>;
  excluded: boolean;
  exclude_reason: string | null;
}

export interface CrashRunCompared extends CrashRunSummary {
  curves: Record<string, number[]>;
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

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new CrashApiError(detailMessage(payload, response.status));
  return payload as T;
}

/** geometryId null → tüm geometrilerin koşuları. */
export async function fetchCrashRuns(geometryId: number | null): Promise<CrashRunSummary[]> {
  const q = geometryId != null ? `?geometry_id=${geometryId}` : "";
  return (await getJson<{ runs: CrashRunSummary[] }>(`${API_BASE_URL}/crash/runs${q}`)).runs;
}

export async function patchCrashRun(
  id: number,
  body: { name?: string | null; excluded?: boolean; exclude_reason?: string | null },
): Promise<CrashRunSummary> {
  return getJson<CrashRunSummary>(`${API_BASE_URL}/crash/runs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** 1.17d — deforme şekil (anim_to_vtk → yüzey + kare başına konum / skaler). */
export interface CrashAnimation {
  faces: number[][];
  face_part: number[];
  scalars: Record<string, { location: "node" | "face"; min: number; max: number }>;
  frames: {
    time: number | null;
    positions: number[];
    node?: Record<string, number[]>;
    face_alive?: number[];
    face?: Record<string, number[]>;
  }[];
}

export async function fetchCrashAnimation(runId: number): Promise<CrashAnimation> {
  return getJson<CrashAnimation>(`${API_BASE_URL}/crash/runs/${runId}/animation`);
}

export async function compareCrashRuns(ids: number[]): Promise<CrashRunCompared[]> {
  return (
    await getJson<{ runs: CrashRunCompared[] }>(`${API_BASE_URL}/crash/runs/compare?ids=${ids.join(",")}`)
  ).runs;
}

export function crashJobWsUrl(jobId: string): string {
  const base = API_BASE_URL.replace(/\/$/, "");
  return `${base.replace(/^http/, "ws")}/crash/jobs/${jobId}/ws`;
}
