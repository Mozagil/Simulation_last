/** Crash (OpenRadioss) API — Faz 1.7–1.9. CalculiX `/solve` kullanmaz. */

import type { MeshGenerateResponse } from "./geometry";

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
  /** 1.17h — /PROP/TYPE14 hourglass katsayısı h (0 = varsayılan; hm_cfg 0…0.15) */
  solid_hourglass_h?: number;
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
  /** 1.17h — hourglass Hm / Hf / Hr (0 = varsayılan; hm_cfg 0…0.05) */
  hm?: number;
  hf?: number;
  hr?: number;
}

/** Parça rolü: hareketli (ilk hız alır) ya da sabit (/BCS). Verilmeyen parça hareketli. */
export interface CrashPartSpec {
  part_id: number;
  /** free (1.18b): ilk hız yok, /BCS yok */
  role: "moving" | "fixed" | "free";
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

/** 1.17e — SAE J211 CFC sınıfları; null = süzme yok (ham korunur). */
export interface CrashFilterPayload {
  force_cfc: number | null;
  acc_cfc: number | null;
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
  filters?: CrashFilterPayload;
  /** TODO 11.9 — kart tabanlı yükleme / tutma (bölge ya da parça hedefli). */
  initial_velocities?: Record<string, unknown>[];
  boundary_conditions?: Record<string, unknown>[];
  imposed_velocities?: Record<string, unknown>[];
  rigid_bodies?: Record<string, unknown>[];
  /** 11.2 — Yükleme: Yerçekimi */
  gravity?: { accel_m_s2: number; direction: "X" | "Y" | "Z" };
  /** 1.22 — OpenRadioss ham kartları; starter deck'ine /END'den önce aynen. */
  raw_cards?: string;
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
  /** 1.22f: koşu ham kartla üretildi. Eski sunucuda yok. */
  has_raw_cards?: boolean;
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

/** 1.17a — POST /crash/scenario (şablon → mesh → malzeme → çözüm). */
export interface CrashScenarioRequest {
  template_id?: string;
  name?: string;
  geometry?: Record<string, number>;
  element_size_mm?: number;
  material_id?: number;
  material_name?: string;
  thickness_mm?: number | null;
  speed_m_s?: number;
  angle_deg?: number;
  t_end_ms?: number;
  rigid_bodies?: { name: string; region?: string; part_id?: number; mass_kg?: number }[];
  filters?: CrashFilterPayload;
  /** 1.18b — plaka–küre: küre malzemesi (boş = plaka), kabuk kalınlığı, ana düğüm ek kütlesi */
  ball_material_id?: number;
  ball_thickness_mm?: number;
  ball_mass_kg?: number;
  /** K5 — küre toplam kütlesi; ek kütle = toplam − kabuk */
  ball_total_mass_kg?: number;
  template_defaults?: boolean;
  /** K2 — düşme yüksekliği (mm); verilirse çarpma hızı √(2·g·H), speed_m_s yerine */
  drop_height_mm?: number;
  /** K2 — /GRAV; boşsa düşme şablonunda −9.81 m/s² Z */
  gravity?: { accel_m_s2: number; direction: "X" | "Y" | "Z" };
  /** 1.22 — OpenRadioss ham kartları; starter deck'ine /END'den önce aynen. */
  raw_cards?: string;
  /** K3 — direk çapı (mm, /RWALL/CYL) ve uç rijit gövde ek kütlesi (kg) */
  pole_diameter_mm?: number;
  end_mass_kg?: number;
  /** K4 — ROPS yanal itme hızı (m/s) */
  push_speed_m_s?: number;
  /** K10 — Friedlander patlama darbesi: Ps (MPa), td (ms), b */
  blast_peak_mpa?: number;
  blast_duration_ms?: number;
  blast_decay?: number;
  /** K12 — SPH kuş: kütle ve boy / çap */
  bird_mass_kg?: number;
  bird_ld?: number;
  /** K13 — mayın: TNT eşdeğeri (kg), plaka altındaki mesafe (mm) */
  mine_tnt_kg?: number;
  mine_standoff_mm?: number;
  run_solver?: boolean;
  wait?: boolean;
  /** Malzeme modeli + kabuk kartı; boşsa sunucu varsayılanı (LAW2, Ishell 0). */
  model?: { law: "elastic" | "plastic" | "tabulated"; shell?: Partial<CrashShellPayload> };
}

/** Senaryonun kurulumu (yanıttaki "scenario" alanının arayüzün okuduğu kısmı). */
export interface CrashScenarioSetup {
  template_id?: string;
  wall?: { point: number[]; normal: number[] };
  use_rigid_wall?: boolean;
  /** parça id → rol (JSON anahtarı string). */
  part_roles?: Record<string, "moving" | "fixed" | "free">;
  direction?: number[] | null;
  speed_m_s?: number;
  t_end_ms?: number;
  [key: string]: unknown;
}

export interface CrashScenarioResponse {
  geometry_id: number;
  scenario: CrashScenarioSetup;
  /** Sunucuda üretilen mesh (geometry generate_mesh yanıtı). */
  mesh?: MeshGenerateResponse;
  crash: CrashSolveResponse;
}

export async function postCrashScenario(body: CrashScenarioRequest): Promise<CrashScenarioResponse> {
  const response = await fetch(`${API_BASE_URL}/crash/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new CrashApiError(detailMessage(payload, response.status));
  return payload as CrashScenarioResponse;
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

/** Koşu sonrası yeniden süzme (post-process): yalnız *_cfcN eğri / skalerleri. */
export async function fetchCrashRefilter(
  jobId: string,
  forceCfc: number | null,
  accCfc: number | null,
): Promise<{ curves: Record<string, number[]>; scalars: Record<string, number> }> {
  const q = new URLSearchParams();
  if (forceCfc) q.set("force_cfc", String(forceCfc));
  if (accCfc) q.set("acc_cfc", String(accCfc));
  const response = await fetch(`${API_BASE_URL}/crash/jobs/${jobId}/cfc?${q.toString()}`);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new CrashApiError(detailMessage(payload, response.status));
  return payload as { curves: Record<string, number[]>; scalars: Record<string, number> };
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

/** 1.17e2 — koşu detayı: girdi + skaler + tüm eğriler (job.json). */
export interface CrashRunDetail extends CrashRunSummary {
  request: Record<string, unknown>;
  materials_snapshot: unknown[];
  diagnostics: CrashDiagnostics;
  curves: Record<string, number[]>;
}

export async function fetchCrashRun(runId: number): Promise<CrashRunDetail> {
  return getJson<CrashRunDetail>(`${API_BASE_URL}/crash/runs/${runId}`);
}

/** 1.17f — validasyon raporu (oranlar veri; kabul kriteri yok). */
export interface CrashValidationRow {
  quantity: string;
  sim: number | null;
  ref: number | null;
  ref_label: string;
  ratio: number | null;
  alt_ref?: number | null;
  alt_label?: string;
}

export interface CrashValidationMeshRow {
  element_mm: number;
  run_id: number;
  wall_s: number;
  crush_mm: number;
  t_stop_ms: number;
  ie_stop_j: number;
  pm_energy_kn: number;
  f_mean_kn: number;
  f_peak_kn: number | null;
  ratio_wa: number;
  ratio_aj: number;
  energy_balance_rel: number | null;
  hourglass_ratio: number | null;
}

/** Çok koşulu vakalarda (mesh / yönelim / kontrol) koşu başına kalite verisi. */
export interface CrashValidationRun {
  run_id: number;
  element_mm?: number;
  orientation?: string;
  v0_m_s?: number;
  control?: boolean;
  wall_s?: number | null;
  energy_balance_rel?: number | null;
  hourglass_ratio?: number | null;
  force_max_kn?: number | null;
  f_peak_kn?: number | null;
  f_max_kn?: number | null;
}

export interface CrashValidationCase {
  id: string;
  title: string;
  run_id?: number;
  rows?: CrashValidationRow[];
  runs?: CrashValidationRun[];
  energy_balance_rel?: number | null;
  hourglass_ratio?: number | null;
  references?: {
    wierzbicki_abramowicz_1983_kn?: number;
    abramowicz_jones_1984_kn?: number;
    formula: string;
    k_n_per_mm?: number;
    ball_mass_kg?: number;
  };
  mesh?: CrashValidationMeshRow[];
  /** 1.18e V5 — Recht–Ipson uydurması (tutarlılık verisi) */
  fit?: {
    a: number;
    v_bl_m_s: number;
    r2: number;
    bracket_low_m_s: number | null;
    bracket_high_m_s: number | null;
    v_bl_in_bracket: boolean;
  };
}

export interface CrashValidationReport {
  generated_at: string;
  updated_at?: string;
  setup: {
    template: string;
    L_mm: number;
    h_mm: number;
    b_mm: number;
    t_mm: number;
    material: string;
    v0_m_s: number;
    note: string;
  };
  cases: CrashValidationCase[];
}

export async function fetchCrashValidation(): Promise<CrashValidationReport> {
  return getJson<CrashValidationReport>(`${API_BASE_URL}/crash/validation`);
}

/** Mühendisin kabul eşikleri; null = kontrol yok. Oranlar ve dengeler kesir. */
export interface CrashValidationThreshold {
  ratio_min: number | null;
  ratio_max: number | null;
  energy_balance_max: number | null;
  hourglass_max: number | null;
}

export interface CrashValidationThresholds {
  default: CrashValidationThreshold;
  cases: Record<string, CrashValidationThreshold>;
  updated_at?: string | null;
}

export async function fetchValidationThresholds(): Promise<CrashValidationThresholds> {
  return getJson<CrashValidationThresholds>(`${API_BASE_URL}/crash/validation/thresholds`);
}

export async function putValidationThresholds(t: CrashValidationThresholds): Promise<CrashValidationThresholds> {
  return getJson<CrashValidationThresholds>(`${API_BASE_URL}/crash/validation/thresholds`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(t),
  });
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

/** K0 — explicit şablon kataloğu (GET /crash/catalog). */
export interface CrashCatalogEntry {
  id: string;
  sector: "otomotiv" | "savunma" | "is_makineleri" | string;
  title: string;
  /** ready: /crash/scenario ile koşulur · planned: küçük ek altyapı · major: ayrı faz */
  status: "ready" | "planned" | "major";
  template_id: string | null;
  mesh_dim: number | null;
  reference: string;
  validation: string;
  infrastructure: string;
  step: string;
  /** Kart başlangıç değerleri (aynı şablonu paylaşan örnekler; K5) */
  defaults?: {
    geometry?: Record<string, number>;
    extras?: Record<string, string>;
    common?: Partial<Record<"elem" | "speed" | "tEnd" | "forceCfc", string>>;
    acc_cfc?: number | null;
  };
}

export interface CrashCatalog {
  entries: CrashCatalogEntry[];
  scenario_templates: Record<string, number>;
}

export async function fetchCrashCatalog(): Promise<CrashCatalog> {
  return getJson<CrashCatalog>(`${API_BASE_URL}/crash/catalog`);
}

/** 1.22b/c — ham kart ID satırı (satır no ham metin içinde, 1 tabanlı). */
export interface RawCardIdRow {
  line: number;
  keyword: string;
  namespace: string;
  id: number;
  /** Yalnız `duplicates`: aynı ID'nin ham metindeki ilk satırı. */
  first_line?: number;
}

export interface RawCardsInventoryResponse {
  user_id_min: number;
  nodes: { count: number; min: number | null; max: number | null };
  elements: { count: number; min: number | null; max: number | null };
  /** Üretilen deck'te ad alanı başına kullanılan ID'ler. */
  ids: Record<string, number[]>;
  collisions: RawCardIdRow[];
  duplicates: RawCardIdRow[];
  below_user_range: RawCardIdRow[];
}

export interface StarterMessageBlock {
  kind: "error" | "warning";
  id: number;
  lines: string[];
}

export interface RawCardsCheckResponse {
  exit_code: number;
  errors: StarterMessageBlock[];
  warnings: StarterMessageBlock[];
  raw_cards_deck_line: number | null;
  console_tail: string;
}

async function postRawCards<T>(path: string, body: CrashSolveRequest): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/crash/raw-cards/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new CrashApiError(detailMessage(payload, response.status));
  return payload as T;
}

/** Üretilen deck'in ID envanteri + ham kart çakışmaları (solver koşmaz). */
export function postRawCardsInventory(body: CrashSolveRequest): Promise<RawCardsInventoryResponse> {
  return postRawCards("inventory", body);
}

/** Ham kartlı deck'le yalnız starter: ERROR/WARNING blokları aynen. Starter yoksa 503. */
export function postRawCardsCheck(body: CrashSolveRequest): Promise<RawCardsCheckResponse> {
  return postRawCards("check", body);
}

/** Backend `/files/crash/...` yolunu tam adrese çevirir (1.23 A7). */
export function crashFileUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
}

/**
 * Dosyayı indirir (1.23 A7). Farklı kökenli adreste `<a download>` yok
 * sayıldığı için içerik blob olarak çekilip kaydedilir; ad = yolun son parçası.
 */
export async function downloadCrashFile(path: string, filename?: string): Promise<void> {
  const response = await fetch(crashFileUrl(path));
  if (!response.ok) throw new CrashApiError(`İndirilemedi (${response.status}).`);
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename ?? path.split("/").pop() ?? "crash.rad";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
