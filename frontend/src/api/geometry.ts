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
