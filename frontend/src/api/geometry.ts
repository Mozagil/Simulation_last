const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

/** Tessellation/eşleme alanları — upload, copy gibi birden fazla endpoint'te ortak. */
export interface TessellationFields {
  tessellation_url: string;
  triangle_count: number;
  face_count: number;
  triangle_to_face: number[];
  triangle_to_face_url: string;
  part_count: number;
  triangle_to_part: number[];
  triangle_to_part_url: string;
  /** GERÇEK bir 3B katıya (volume) karşılık gelen part_id'ler — "Solid
   * gizle/göster" sadece bunları hedeflemeli, copy_surface/midsurface
   * çıktısı gibi düz (volume'süz) yüzey parçalarını değil. */
  volume_part_ids: number[];
}

export interface GeometryUploadResponse extends TessellationFields {
  geometry_id: number;
  original_filename: string;
  current_filename: string;
  size_bytes: string;
  tessellation_path: string;
}

export interface CopySurfaceResponse extends TessellationFields {
  geometry_id: number;
  original_face_id: number;
  new_face_id: number;
}

export interface CopySurfacesResponse extends TessellationFields {
  geometry_id: number;
  original_face_ids: number[];
  new_face_ids: number[];
}

export interface OffsetMidsurfacesResponse extends TessellationFields {
  geometry_id: number;
  original_face_ids: number[];
  new_face_ids: number[];
  thickness: number;
}

export interface EdgeInfo {
  id: number;
  length: number;
  part_id: number;
  start_point: number;
  end_point: number;
}

export interface PointInfo {
  id: number;
  coordinate: [number, number, number];
  part_id: number;
}

export interface PhysicalGroup {
  id: number;
  name: string;
  dim: number;
  entity_tags: number[];
  face_count: number;
}

interface EdgesResponse {
  geometry_id: number;
  edge_count: number;
  edges: EdgeInfo[];
}

interface PointsResponse {
  geometry_id: number;
  point_count: number;
  points: PointInfo[];
}

interface PhysicalGroupsResponse {
  geometry_id: number;
  group_count: number;
  groups: PhysicalGroup[];
}

export interface HealResponse extends TessellationFields {
  geometry_id: number;
  volumes_before: number;
  surfaces_before: number;
  volumes_after: number;
  surfaces_after: number;
}

export interface DefeatureCandidate {
  face_id: number;
  approx_radius: number;
  surface_type: string;
  part_id: number;
}

export interface DefeatureApplyResponse extends TessellationFields {
  geometry_id: number;
  max_radius: number;
  volumes_before: number;
  surfaces_before: number;
  volumes_after: number;
  surfaces_after: number;
}

export interface MidsurfaceResponse extends TessellationFields {
  geometry_id: number;
  face_id_a: number;
  face_id_b: number;
  new_face_id: number;
}

export interface MidsurfacePairResult {
  face_id_a: number;
  face_id_b: number;
  new_face_id: number;
}

export interface MidsurfaceForPartResponse extends TessellationFields {
  geometry_id: number;
  part_id: number;
  midsurface_count: number;
  midsurfaces: MidsurfacePairResult[];
  new_face_ids: number[];
  /** Geriye dönük: ilk çift (tek cidarlı plaka mesajları için). */
  chosen_face_id_a: number;
  chosen_face_id_b: number;
  new_face_id: number;
}

interface DefeatureCandidatesResponse {
  geometry_id: number;
  max_radius: number;
  candidate_count: number;
  candidates: DefeatureCandidate[];
}

export class GeometryUploadError extends Error {}

async function parseErrorDetail(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: string } | null;
  return body?.detail ?? fallback;
}

/** STEP/IGES dosyasını backend'e yükler, kalıcı bir geometry_id ile birlikte döner. */
export async function uploadGeometry(file: File): Promise<GeometryUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/geometry/upload`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new GeometryUploadError(
      "Backend'e ulaşılamadı. Sunucunun çalıştığından emin olun (uvicorn app.main:app --reload).",
    );
  }

  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Yükleme başarısız oldu (HTTP ${response.status}).`),
    );
  }

  return (await response.json()) as GeometryUploadResponse;
}

/** Tessellation URL'ini backend'in tam adresine çevirir. `cacheBust` verilirse
 * (örn. bir mutasyon sonrası), aynı dosya adı olsa bile tarayıcının eski STL'i
 * cache'ten kullanmasını önlemek için query param eklenir.
 */
export function resolveTessellationUrl(tessellationUrl: string, cacheBust?: number): string {
  const base = `${API_BASE_URL}${tessellationUrl}`;
  return cacheBust !== undefined ? `${base}?t=${cacheBust}` : base;
}

/** Bir geometrinin kenar listesini çeker. */
export async function fetchEdges(geometryId: number): Promise<EdgeInfo[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/edges`);
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Kenar listesi alınamadı (HTTP ${response.status}).`),
    );
  }
  const body = (await response.json()) as EdgesResponse;
  return body.edges;
}

/** Bir geometrinin nokta (vertex) listesini çeker. */
export async function fetchPoints(geometryId: number): Promise<PointInfo[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/points`);
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Nokta listesi alınamadı (HTTP ${response.status}).`),
    );
  }
  const body = (await response.json()) as PointsResponse;
  return body.points;
}

/** Verilen yüzeyi kalıcı olarak çoğaltır (STEP dosyasına geri yazılır). */
export async function copySurface(geometryId: number, faceId: number): Promise<CopySurfaceResponse> {
  const response = await fetch(
    `${API_BASE_URL}/geometry/${geometryId}/surfaces/${faceId}/copy`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Yüzey kopyalanamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as CopySurfaceResponse;
}

/** Verilen TÜM yüzeyleri tek bir mutasyonda çoğaltır (çoklu seçim desteği). */
export async function copySurfaces(
  geometryId: number,
  faceIds: number[],
): Promise<CopySurfacesResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/surfaces/copy-multiple`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ face_ids: faceIds }),
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Yüzeyler kopyalanamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as CopySurfacesResponse;
}

/** Verilen her (düzlemsel) yüzeyi kendi normali boyunca, kalınlığın yarısı
 * kadar İÇE doğru kaydırarak orta yüzeyini üretir — iki yüzey eşleştirmeye
 * gerek yok, sadece dış yüzey(ler) + kalınlık.
 */
export async function createOffsetMidsurfaces(
  geometryId: number,
  faceIds: number[],
  thickness: number,
): Promise<OffsetMidsurfacesResponse> {
  const response = await fetch(
    `${API_BASE_URL}/geometry/${geometryId}/surfaces/offset-midsurface`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ face_ids: faceIds, thickness }),
    },
  );
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Offset midsurface oluşturulamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as OffsetMidsurfacesResponse;
}

/** Verilen yüzeyleri isimli bir Physical Group'a atar (kalıcı, DB'de). */
export async function createPhysicalGroup(
  geometryId: number,
  name: string,
  faceIds: number[],
): Promise<PhysicalGroup> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/physical-groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, face_ids: faceIds }),
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Grup oluşturulamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as PhysicalGroup;
}

/** Bir geometriye atanmış tüm Physical Group'ları çeker. */
export async function fetchPhysicalGroups(geometryId: number): Promise<PhysicalGroup[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/physical-groups`);
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Grup listesi alınamadı (HTTP ${response.status}).`),
    );
  }
  const body = (await response.json()) as PhysicalGroupsResponse;
  return body.groups;
}

/** Küçük boşluk/tolerans hatalarını düzeltir (`occ.healShapes`). Kalıcıdır.
 * DİKKAT: yüzey ID'lerini yeniden numaralandırabilir (backend'de doğrulandı).
 */
export async function healGeometry(geometryId: number): Promise<HealResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/heal`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Geometry healing başarısız (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as HealResponse;
}

/** Son mutasyon işlemini (copy/heal/midsurface) geri alır. Tek seviyeli —
 * sadece en son işlem geri alınabilir. Geri alınacak bir şey yoksa 400 döner.
 */
export async function undoLastMutation(geometryId: number): Promise<TessellationFields> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/undo`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Geri alma başarısız (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as TessellationFields;
}

/** Yarıçapı eşik altındaki fillet yüzeylerini tespit eder (kaldırmadan). */
export async function findDefeatureCandidates(
  geometryId: number,
  maxRadius: number,
): Promise<DefeatureCandidate[]> {
  const response = await fetch(
    `${API_BASE_URL}/geometry/${geometryId}/defeature-candidates?max_radius=${maxRadius}`,
  );
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Defeature adayları alınamadı (HTTP ${response.status}).`),
    );
  }
  const body = (await response.json()) as DefeatureCandidatesResponse;
  return body.candidates;
}

/** Seçilen fillet/radyus yüzeylerini kaldırır; yüzeysizse mid kabuktaki
 * tüm radyusları otomatik kaldırır (max_radius). */
export async function applyDefeature(
  geometryId: number,
  options: { faceIds?: number[]; maxRadius?: number },
): Promise<DefeatureApplyResponse> {
  const body: { face_ids?: number[]; max_radius?: number } = {};
  if (options.faceIds && options.faceIds.length > 0) {
    body.face_ids = options.faceIds;
  }
  if (options.maxRadius != null) {
    body.max_radius = options.maxRadius;
  }
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/defeature`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Defeature başarısız (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as DefeatureApplyResponse;
}

export interface MeshGenerateResponse {
  geometry_id: number;
  element_size: number;
  dimension: number;
  element_scheme: "tet" | "quad" | "mix";
  node_count: number;
  element_count: number;
  element_type_counts: Record<string, number>;
  mesh_path: string;
  mesh_url: string;
  preview_url: string | null;
}

export type MeshElementScheme = "tet" | "quad" | "mix";

/** Mesh önizleme: nodes + yüzey üçgenleri + kenar çiftleri (CAD koordinatı). */
export interface MeshPreviewData {
  nodes: number[][];
  /** Üçgen indeksleri [i0,i1,i2, ...] — shaded yüzey. */
  faces: number[];
  /** Kenar uç çiftleri [a,b, ...] — wireframe overlay. */
  lines: number[];
  /** Her önizleme üçgeninin CalculiX ELSET PART_{n} indeksi. Yoksa tümü 0. */
  triangle_to_part?: number[];
  /** Gmsh yüzey tag'i — Face grow. */
  triangle_to_face?: number[];
  /** FE eleman id (quad = iki üçgen aynı id) — eleman picking. */
  triangle_to_element?: number[];
}

/** FEA mesh üretir: dimension 2 = shell, 3 = solid; scheme tet|quad|mix. */
export async function generateMesh(
  geometryId: number,
  elementSize: number,
  dimension: 2 | 3,
  elementScheme: MeshElementScheme = "tet",
  curveNodes: Record<number, number> = {},
): Promise<MeshGenerateResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/mesh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      element_size: elementSize,
      dimension,
      element_scheme: elementScheme,
      curve_nodes: curveNodes,
    }),
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Mesh üretimi başarısız (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as MeshGenerateResponse;
}

export interface MeshQualityMetricSummary {
  name: string;
  min: number;
  max: number;
  mean: number;
  values: number[];
}

export interface MeshQualityResponse {
  geometry_id: number;
  dimension: number;
  element_count: number;
  mesh_path: string;
  jacobian: MeshQualityMetricSummary;
  aspect_ratio: MeshQualityMetricSummary;
}

/** Kayıtlı mesh için Jacobian (minSJ) + aspect ratio özeti. */
export async function fetchMeshQuality(
  geometryId: number,
  dimension: 2 | 3,
): Promise<MeshQualityResponse> {
  const response = await fetch(
    `${API_BASE_URL}/geometry/${geometryId}/mesh/quality?dimension=${dimension}`,
  );
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Mesh kalite alınamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as MeshQualityResponse;
}

/** Mesh wireframe JSON'unu çeker (`/files/meshes/...preview.json`). */
export async function fetchMeshPreview(previewUrl: string): Promise<MeshPreviewData> {
  const response = await fetch(`${API_BASE_URL}${previewUrl}?t=${Date.now()}`);
  if (!response.ok) {
    throw new GeometryUploadError(
      `Mesh önizleme alınamadı (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as MeshPreviewData;
}

/** İki paralel, düzlemsel yüzey arasında orta yüzeyi hesaplar. Kalıcıdır. */
export async function createMidsurface(
  geometryId: number,
  faceIdA: number,
  faceIdB: number,
): Promise<MidsurfaceResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/midsurface`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ face_id_a: faceIdA, face_id_b: faceIdB }),
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Midsurface oluşturulamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as MidsurfaceResponse;
}

/** Verilen parçanın en uygun paralel/düzlemsel yüzey çiftini OTOMATİK tespit
 * edip midsurface hesaplar — kullanıcının manuel iki yüzey seçmesi gerekmez.
 */
export async function createMidsurfaceForPart(
  geometryId: number,
  partId: number,
): Promise<MidsurfaceForPartResponse> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/parts/${partId}/midsurface`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new GeometryUploadError(
      await parseErrorDetail(response, `Midsurface oluşturulamadı (HTTP ${response.status}).`),
    );
  }
  return (await response.json()) as MidsurfaceForPartResponse;
}
