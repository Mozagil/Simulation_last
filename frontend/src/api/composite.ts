const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface CompositeMaterial {
  id: number;
  name: string;
  ply_kind: string;
  category: string;
  standard: string | null;
  density: number;
  e1: number;
  e2: number;
  e3: number;
  nu12: number;
  nu13: number;
  nu23: number;
  g12: number;
  g13: number;
  g23: number;
  xt: number;
  xc: number;
  yt: number;
  yc: number;
  s12: number;
  s13: number | null;
  s23: number | null;
  source: string;
  is_editable: boolean;
}

export interface CreateCompositeMaterialInput {
  name: string;
  ply_kind?: string;
  category?: string;
  density: number;
  e1: number;
  e2: number;
  e3: number;
  nu12: number;
  nu13: number;
  nu23: number;
  g12: number;
  g13: number;
  g23: number;
  xt: number;
  xc: number;
  yt: number;
  yc: number;
  s12: number;
  s13?: number | null;
  s23?: number | null;
}

async function _detail(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  return typeof body?.detail === "string" ? body.detail : fallback;
}

export async function fetchCompositeMaterials(): Promise<CompositeMaterial[]> {
  const response = await fetch(`${API_BASE_URL}/composite/materials`);
  if (!response.ok) {
    throw new Error(await _detail(response, `Ply listesi alınamadı (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { materials: CompositeMaterial[] };
  return body.materials;
}

export interface CltPlyInput {
  e1: number;
  e2: number;
  g12: number;
  nu12: number;
  thickness_mm: number;
  angle_deg: number;
}

export interface CltResult {
  n_plies: number;
  h_mm: number;
  A_N_per_mm: number[][];
  B_N: number[][];
  D_N_mm: number[][];
}

export interface CompositeLayupPly {
  material_id: number;
  material_name: string | null;
  thickness_mm: number;
  angle_deg: number;
}

export interface CompositeLayup {
  id: number;
  geometry_id: number;
  part_id: number;
  n_plies: number;
  plies: CompositeLayupPly[];
}

export async function fetchCompositeLayups(
  geometryId: number,
  partId?: number,
): Promise<CompositeLayup[]> {
  const params = new URLSearchParams({ geometry_id: String(geometryId) });
  if (partId != null) params.set("part_id", String(partId));
  const response = await fetch(`${API_BASE_URL}/composite/layups?${params}`);
  if (!response.ok) {
    throw new Error(await _detail(response, `Dizilim alınamadı (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { layups: CompositeLayup[] };
  return body.layups;
}

export async function putCompositeLayup(input: {
  geometry_id: number;
  part_id: number;
  plies: { material_id: number; thickness_mm: number; angle_deg: number }[];
}): Promise<CompositeLayup> {
  const response = await fetch(`${API_BASE_URL}/composite/layups`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await _detail(response, `Dizilim kaydedilemedi (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { layup: CompositeLayup };
  return body.layup;
}

export interface CompositeOrientation {
  id: number;
  geometry_id: number;
  part_id: number;
  kind: string;
  dir0: number[];
  origin: number[];
  target: string;
  face_ids: number[];
}

export async function fetchCompositeOrientations(
  geometryId: number,
  partId?: number,
): Promise<CompositeOrientation[]> {
  const params = new URLSearchParams({ geometry_id: String(geometryId) });
  if (partId != null) params.set("part_id", String(partId));
  const response = await fetch(`${API_BASE_URL}/composite/orientations?${params}`);
  if (!response.ok) {
    throw new Error(await _detail(response, `Rozet alınamadı (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { orientations: CompositeOrientation[] };
  return body.orientations;
}

export async function putCompositeOrientation(input: {
  geometry_id: number;
  part_id: number;
  kind?: string;
  dir0: number[];
  origin: number[];
  target: string;
  face_ids: number[];
}): Promise<CompositeOrientation> {
  const response = await fetch(`${API_BASE_URL}/composite/orientations`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geometry_id: input.geometry_id,
      part_id: input.part_id,
      kind: input.kind ?? "parallel",
      dir0: input.dir0,
      origin: input.origin,
      target: input.target,
      face_ids: input.face_ids,
    }),
  });
  if (!response.ok) {
    throw new Error(await _detail(response, `Rozet kaydedilemedi (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { orientation: CompositeOrientation };
  return body.orientation;
}

export async function computeClt(plies: CltPlyInput[]): Promise<CltResult> {
  const response = await fetch(`${API_BASE_URL}/composite/clt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plies }),
  });
  if (!response.ok) {
    throw new Error(await _detail(response, `CLT hesaplanamadı (HTTP ${response.status}).`));
  }
  return (await response.json()) as CltResult;
}

export async function createCompositeMaterial(
  input: CreateCompositeMaterialInput,
): Promise<CompositeMaterial> {
  const response = await fetch(`${API_BASE_URL}/composite/materials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      ply_kind: input.ply_kind ?? "ud",
      category: input.category ?? "custom",
      density: input.density,
      e1: input.e1,
      e2: input.e2,
      e3: input.e3,
      nu12: input.nu12,
      nu13: input.nu13,
      nu23: input.nu23,
      g12: input.g12,
      g13: input.g13,
      g23: input.g23,
      xt: input.xt,
      xc: input.xc,
      yt: input.yt,
      yc: input.yc,
      s12: input.s12,
      s13: input.s13 ?? null,
      s23: input.s23 ?? null,
    }),
  });
  if (!response.ok) {
    throw new Error(await _detail(response, `Ply oluşturulamadı (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { material: CompositeMaterial };
  return body.material;
}

export interface CompositeRun {
  id: number;
  job_id: string;
  geometry_id: number;
  part_id: number;
  name: string | null;
  dimension: number;
  status: string;
  message: string | null;
  solver_ran: boolean;
  inp_url: string | null;
  scalars: Record<string, number | boolean>;
  has_ply_field: boolean;
}

export async function fetchCompositeRuns(geometryId: number): Promise<CompositeRun[]> {
  const response = await fetch(`${API_BASE_URL}/composite/runs?geometry_id=${geometryId}`);
  if (!response.ok) {
    throw new Error(await _detail(response, `Koşular alınamadı (HTTP ${response.status}).`));
  }
  const body = (await response.json()) as { runs: CompositeRun[] };
  return body.runs;
}

/** 3.13: eleman × katman dizileri (gerilme MPa, ply ekseni; IRF dayanım yoksa null). */
export interface CompositePlySet {
  element_ids: number[];
  plies: { material: string; angle_deg: number }[];
  s11: number[][];
  s22: number[][];
  s12: number[][];
  tsai_wu_irf: (number | null)[][];
  hashin_irf: (number | null)[][];
  hashin_mode: number[][];
  nodes: number[][];
  faces: number[][];
}

export interface CompositePlyField {
  run_id: number;
  name: string | null;
  scalars: Record<string, number | boolean>;
  f12_star: number;
  hashin_modes: string[];
  sets: Record<string, CompositePlySet>;
}

export async function fetchCompositePlyField(runId: number): Promise<CompositePlyField> {
  const response = await fetch(`${API_BASE_URL}/composite/runs/${runId}/plies`);
  if (!response.ok) {
    throw new Error(await _detail(response, `Katman alanı alınamadı (HTTP ${response.status}).`));
  }
  return (await response.json()) as CompositePlyField;
}
