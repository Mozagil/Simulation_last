/** CFD (OpenFOAM) API — Faz 2.2–2.6 uçları; arayüz 2.7. */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class CfdApiError extends Error {}

function detailMessage(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
  }
  return `HTTP ${status}`;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new CfdApiError(detailMessage(payload, response.status));
  return payload as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return getJson<T>(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ------------------------------------------------------------------ mesh (2.5)

export type CfdMesher = "snappy" | "cfmesh";

export interface CfdTunnelParams {
  upstream: number;
  downstream: number;
  lateral: number;
  ground: boolean;
  ground_clearance_m: number;
  base_cell_m: number;
}

export interface CfdSnappyParams {
  surface_level_min: number;
  surface_level_max: number;
  feature_level: number;
  wake_level: number;
  wake_length: number;
  n_layers: number;
  expansion_ratio: number;
  final_layer_thickness: number;
  stl_size_mm: number | null;
}

export interface CfdMeshRequest {
  geometry_id: number;
  mesher: CfdMesher;
  tunnel: CfdTunnelParams;
  snappy: CfdSnappyParams;
  regions?: string[] | null;
}

export interface CfdCheckMesh {
  cells?: number;
  points?: number;
  faces?: number;
  hexahedra?: number;
  polyhedra?: number;
  non_orthogonality_max?: number;
  non_orthogonality_avg?: number;
  skewness_max?: number;
  aspect_ratio_max?: number;
  min_volume?: number;
  failed_checks?: number;
  mesh_ok?: boolean;
  patch_faces?: Record<string, number>;
}

export interface CfdLayerCoverage {
  faces: number;
  target_layers: number;
  layers: number;
  thickness_m: number;
  thickness_percent: number;
}

export interface CfdMeshMeta {
  mesh_id: string;
  geometry_id: number;
  mesher: CfdMesher;
  status: "pending" | "meshed" | "failed";
  message: string;
  patches: string[];
  surface: { regions: string[]; triangles: number; triangles_per_region: Record<string, number>; open_edges: number; bbox_m: number[] };
  domain: { min_m: number[]; max_m: number[]; background_cells: number[]; body_length_m: number };
  check: CfdCheckMesh;
  snappy?: { background_cells?: number; snapped_cells?: number; layer_cells?: number; cells_per_level?: Record<string, number>; layers?: Record<string, CfdLayerCoverage>; seconds?: number };
  cfmesh?: { finished: boolean; layer_cells_added: number };
  hub_state?: string;
}

export function postCfdMesh(body: CfdMeshRequest): Promise<CfdMeshMeta> {
  return postJson<CfdMeshMeta>("/cfd/mesh", { ...body, wait: false });
}

export function fetchCfdMesh(meshId: string): Promise<CfdMeshMeta> {
  return getJson<CfdMeshMeta>(`${API_BASE_URL}/cfd/mesh/${meshId}`);
}

// ------------------------------------------------------------- çözüm (2.2–2.4)

/** R4: üç çözücü, NLGEOM gibi seçilir (otomatik değil). */
export type CfdSolver = "simpleFoam" | "rhoSimpleFoam" | "rhoCentralFoam";

export type CfdPatchKind = "inlet" | "outlet" | "wall" | "slip" | "farfield" | "symmetry" | "empty";

export interface CfdPatchSpec {
  name: string;
  kind: CfdPatchKind;
  velocity_m_s?: [number, number, number];
  pressure?: number;
}

export interface CfdCase {
  nu_m2_s: number;
  rho_kg_m3: number;
  patches: CfdPatchSpec[];
  turbulence: { model: "laminar" | "kOmegaSST"; intensity: number; length_scale_m: number };
  control: {
    iterations: number;
    write_interval: number;
    residual_p: number;
    residual_u: number;
    relax_u: number;
    relax_other: number;
    n_procs?: number;
  };
  initial_velocity_m_s?: [number, number, number];
  solver?: CfdSolver;
  compressible?: { p_inf_pa: number; t_inf_k: number; transonic: boolean; max_co: number };
  forces?: {
    patches: string[];
    cofr_m: [number, number, number];
    u_ref_m_s: number;
    l_ref_m: number;
    a_ref_m2: number;
    average_last: number;
  } | null;
}

export interface CfdSolveResponse {
  job_id: string;
  run_id?: number;
  status: string;
  message: string;
}

export interface CfdJobSnapshot {
  job_id: string;
  status: "case_only" | "pending" | "solved" | "failed";
  message: string;
  hub_state?: string;
  percent?: number;
  iteration?: number;
  end_iterations?: number;
  scalars?: Record<string, number>;
  curves?: { iteration?: number[]; residuals?: Record<string, number[]>; force_coeffs?: Record<string, number[]> };
  rocket_aero?: Record<string, unknown> | null;
}

export function postCfdSolve(body: { case: CfdCase; mesh_id: string; name?: string | null; geometry_id?: number | null }): Promise<CfdSolveResponse> {
  return postJson<CfdSolveResponse>("/cfd/solve", { ...body, wait: false });
}

export function fetchCfdJob(jobId: string): Promise<CfdJobSnapshot> {
  return getJson<CfdJobSnapshot>(`${API_BASE_URL}/cfd/jobs/${jobId}`);
}

// ------------------------------------------------------------- roket (R2, R3)

export interface BarrowmanComponent {
  name: string;
  cn_alpha: number;
  x_mm: number;
}

export interface BarrowmanResult {
  cn_alpha: number;
  x_cp_mm: number;
  x_cp_calibers: number;
  stability_calibers?: number;
  reference_diameter_mm: number;
  components: BarrowmanComponent[];
  notes: string[];
}

export function postBarrowman(body: { geometry_id: number; cg_mm?: number | null }): Promise<BarrowmanResult> {
  return postJson<BarrowmanResult>("/cfd/rocket/barrowman", body);
}

export interface RocketSolveBody {
  mesh_id: string;
  speed_m_s: number;
  alpha_deg: number;
  cg_mm?: number | null;
  rho_kg_m3: number;
  nu_m2_s: number;
  temperature_k: number;
  turbulence_model: "laminar" | "kOmegaSST";
  iterations: number;
  relax_u: number;
  relax_other: number;
  name?: string | null;
  solver?: CfdSolver;
  p_inf_pa?: number;
  transonic?: boolean;
  max_co?: number;
  n_procs?: number;
}

export function postRocketSolve(body: RocketSolveBody): Promise<CfdSolveResponse & { mach: number; barrowman: BarrowmanResult }> {
  return postJson("/cfd/rocket/solve", { ...body, wait: false });
}

// ------------------------------------------------------------- koşu geçmişi (2.4)

export interface CfdRunSummary {
  id: number;
  job_id: string;
  geometry_id: number | null;
  name: string | null;
  created_at: string | null;
  application: string | null;
  turbulence: string | null;
  mesh_kind: string | null;
  status: string;
  message: string | null;
  scalars: Record<string, number>;
  reference: Record<string, unknown> | null;
  excluded: boolean;
}

export function fetchCfdRuns(geometryId?: number | null): Promise<{ count: number; runs: CfdRunSummary[] }> {
  const q = geometryId != null ? `?geometry_id=${geometryId}` : "";
  return getJson(`${API_BASE_URL}/cfd/runs${q}`);
}

export function patchCfdRun(id: number, body: { name?: string; excluded?: boolean }): Promise<CfdRunSummary> {
  return getJson(`${API_BASE_URL}/cfd/runs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ------------------------------------------------------------- 2.8 alan görselleştirme

export interface CfdFields {
  u_ref_m_s: number;
  p_ref: number;
  compressible: boolean;
  body?: { points: [number, number, number][]; p: number[]; cp: number[] };
  slice?: { points: [number, number, number][]; speed: number[] };
  streamlines?: { points: [number, number, number][]; speed: number[] }[];
}

export function fetchCfdFields(jobId: string): Promise<CfdFields> {
  return getJson<CfdFields>(`${API_BASE_URL}/cfd/jobs/${jobId}/fields`);
}

// ------------------------------------------------------------- R5 Mach × α taraması

export interface RocketSweepPoint {
  mach: number;
  alpha_deg: number;
  speed_m_s: number;
  status: string;
  message?: string;
  job_id?: string;
  CA?: number | null;
  CN?: number | null;
  CD?: number | null;
  CL?: number | null;
  Cm?: number | null;
  x_cp_m?: number | null;
}

export interface RocketTableRow {
  mach: number;
  n_points: number;
  CD_alpha_min: number;
  alpha_min_deg: number;
  CN_alpha_per_rad: number | null;
  x_cp_m_mean: number | null;
}

export interface RocketSweep {
  sweep_id: string;
  status: "pending" | "running" | "done";
  message?: string;
  solver: CfdSolver;
  points: RocketSweepPoint[];
  table: RocketTableRow[];
}

export function postRocketSweep(body: Omit<RocketSolveBody, "speed_m_s" | "alpha_deg"> & { machs: number[]; alphas_deg: number[] }): Promise<RocketSweep> {
  return postJson<RocketSweep>("/cfd/rocket/sweep", { ...body, wait: false });
}

export function fetchRocketSweep(id: string): Promise<RocketSweep> {
  return getJson<RocketSweep>(`${API_BASE_URL}/cfd/rocket/sweep/${id}`);
}

export function rocketSweepCsvUrl(id: string, kind: "table" | "points"): string {
  return `${API_BASE_URL}/cfd/rocket/sweep/${id}/csv?kind=${kind}`;
}

// ------------------------------------------------------------- R6 OpenRocket içe aktarma

export interface OrkImport {
  name: string;
  params: Record<string, number | string>;
  notes: string[];
  valid: boolean;
}

export async function postRocketOrk(file: File): Promise<OrkImport> {
  const fd = new FormData();
  fd.append("file", file);
  return getJson<OrkImport>(`${API_BASE_URL}/cfd/rocket/ork`, { method: "POST", body: fd });
}

/** CFD koşusu PDF raporu (kurulum, katsayılar, roket / Barrowman, grafikler). */
export function cfdRunReportUrl(runId: number): string {
  return `${API_BASE_URL}/cfd/runs/${runId}/report.pdf`;
}
