const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface Material {
  id: number;
  name: string;
  category: string;
  standard: string | null;
  density: number;
  youngs_modulus: number;
  poisson_ratio: number;
  yield_strength: number;
  ultimate_strength: number;
  elongation: number | null;
  sn_curve: Record<string, unknown> | null;
  source: string;
  is_editable: boolean;
}

export interface MaterialsListResponse {
  count: number;
  materials: Material[];
}

export interface MaterialAssignment {
  id: number;
  geometry_id: number;
  part_id: number;
  material_id: number;
  material_name: string | null;
  material_category: string | null;
}

/** Kütüphane malzemelerini listeler. */
export async function fetchMaterials(): Promise<Material[]> {
  const response = await fetch(`${API_BASE_URL}/materials`);
  if (!response.ok) {
    throw new Error(`Malzeme listesi alınamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as MaterialsListResponse;
  return body.materials;
}

/** Parçaya malzeme atar (aynı parça için günceller). */
export async function assignMaterial(
  geometryId: number,
  partId: number,
  materialId: number,
): Promise<MaterialAssignment> {
  const response = await fetch(`${API_BASE_URL}/materials/assignments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geometry_id: geometryId,
      part_id: partId,
      material_id: materialId,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      detail || `Malzeme ataması başarısız (HTTP ${response.status}).`,
    );
  }
  const body = (await response.json()) as { assignment: MaterialAssignment };
  return body.assignment;
}

/** Bir geometrinin malzeme atamalarını listeler. */
export async function fetchMaterialAssignments(
  geometryId: number,
): Promise<MaterialAssignment[]> {
  const response = await fetch(
    `${API_BASE_URL}/materials/assignments?geometry_id=${geometryId}`,
  );
  if (!response.ok) {
    throw new Error(`Atamalar alınamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as {
    assignments: MaterialAssignment[];
  };
  return body.assignments;
}

/** Kullanıcı tanımlı malzeme oluşturur. */
export async function createMaterial(input: {
  name: string;
  category?: string;
  density: number;
  youngs_modulus: number;
  poisson_ratio: number;
  yield_strength: number;
  ultimate_strength: number;
  elongation?: number | null;
  sn_mode?: "none" | "estimated" | "tested";
}): Promise<Material> {
  const response = await fetch(`${API_BASE_URL}/materials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      category: input.category ?? "custom",
      density: input.density,
      youngs_modulus: input.youngs_modulus,
      poisson_ratio: input.poisson_ratio,
      yield_strength: input.yield_strength,
      ultimate_strength: input.ultimate_strength,
      elongation: input.elongation ?? null,
      sn_mode: input.sn_mode ?? "none",
    }),
  });
  if (!response.ok) {
    throw new Error(`Malzeme oluşturulamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as { material: Material };
  return body.material;
}

/** S-N eğrisi ayarla (estimated | tested). */
export async function setMaterialSnCurve(
  materialId: number,
  source: "estimated" | "tested",
  points?: { N: number; sigma: number }[],
): Promise<Material> {
  const response = await fetch(`${API_BASE_URL}/materials/${materialId}/sn-curve`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, points }),
  });
  if (!response.ok) {
    throw new Error(`S-N güncellenemedi (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as { material: Material };
  return body.material;
}

export interface SolveResponse {
  geometry_id: number;
  run_id: number;
  dimension: number;
  inp_path: string;
  inp_url: string;
  ccx_available: boolean;
  cards: Record<string, boolean>;
  solver_ran: boolean;
  job_id: string | null;
  frd_path: string | null;
  message: string;
  scalars?: Record<string, number>;
  fatigue_note?: string | null;
  fatigue_runout?: boolean;
  results_preview_url?: string | null;
  analysis_type?: "static" | "modal";
  n_modes?: number | null;
  frequencies?: number[];
  status?: "pending" | "inp_only" | "solved" | "failed";
}

export type SolveBC = {
  type: string;
  face_ids?: number[];
  edge_ids?: number[];
  /** CAD vertex (köşe) id'leri — backend POINT_ nset'i üzerinden mesh
   * düğümüne çevirir. Remesh'i atlatır. */
  node_ids?: number[];
  /** Ham CalculiX mesh düğüm numaraları — kullanıcı mesh üzerinde düğüm
   * seçtiğinde. Mesh yeniden üretilirse ANLAMINI YİTİRİR. */
  mesh_node_ids?: number[];
  fx?: number;
  fy?: number;
  fz?: number;
  magnitude?: number;
  gx?: number;
  gy?: number;
  gz?: number;
  dx?: number;
  dy?: number;
  dz?: number;
  dofs?: Record<string, number>;
  axis?: number[];
  normal?: number[];
  ref_node_id?: number;
};

/** CalculiX .inp üret (+ isteğe bağlı ccx). */
export async function solveGeometry(
  geometryId: number,
  opts: {
    dimension: 2 | 3;
    shell_thickness?: number;
    run_solver?: boolean;
    bcs: SolveBC[];
    name?: string;
    element_size?: number;
    element_scheme?: string;
    analysis_type?: "static" | "modal";
    n_modes?: number;
    freq_min?: number;
    freq_max?: number;
    wait?: boolean;
  },
): Promise<SolveResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dimension: opts.dimension,
      shell_thickness: opts.shell_thickness ?? 3,
      run_solver: opts.run_solver ?? false,
      bcs: opts.bcs,
      ...(opts.name ? { name: opts.name } : {}),
      ...(opts.element_size != null ? { element_size: opts.element_size } : {}),
      ...(opts.element_scheme ? { element_scheme: opts.element_scheme } : {}),
      ...(opts.analysis_type ? { analysis_type: opts.analysis_type } : {}),
      ...(opts.n_modes != null ? { n_modes: opts.n_modes } : {}),
      ...(opts.freq_min != null ? { freq_min: opts.freq_min } : {}),
      ...(opts.freq_max != null ? { freq_max: opts.freq_max } : {}),
      ...(opts.wait === false ? { wait: false } : {}),
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Solve başarısız (HTTP ${response.status}).`);
  }
  return (await response.json()) as SolveResponse;
}

/** Pa → GPa, MPa gösterimi için. */
export function formatGPa(pa: number): string {
  return `${(pa / 1e9).toFixed(1)} GPa`;
}

export function formatMPa(pa: number): string {
  return `${(pa / 1e6).toFixed(0)} MPa`;
}
