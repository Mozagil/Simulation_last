const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface GeometryUploadResponse {
  original_filename: string;
  stored_filename: string;
  path: string;
  size_bytes: string;
  tessellation_path: string;
  tessellation_url: string;
  triangle_count: number;
  face_count: number;
  triangle_to_face: number[];
  triangle_to_face_url: string;
  part_count: number;
  triangle_to_part: number[];
  triangle_to_part_url: string;
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

interface EdgesResponse {
  stored_filename: string;
  edge_count: number;
  edges: EdgeInfo[];
}

interface PointsResponse {
  stored_filename: string;
  point_count: number;
  points: PointInfo[];
}

export class GeometryUploadError extends Error {}

/** STEP/IGES dosyasını backend'e yükler, tessellation URL'ini içeren yanıtı döner. */
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
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new GeometryUploadError(body?.detail ?? `Yükleme başarısız oldu (HTTP ${response.status}).`);
  }

  return (await response.json()) as GeometryUploadResponse;
}

/** Tessellation URL'ini backend'in tam adresine çevirir (STLLoader fetch için). */
export function resolveTessellationUrl(tessellationUrl: string): string {
  return `${API_BASE_URL}${tessellationUrl}`;
}

/** Daha önce yüklenmiş bir dosyanın kenar listesini çeker. */
export async function fetchEdges(storedFilename: string): Promise<EdgeInfo[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/${storedFilename}/edges`);
  if (!response.ok) {
    throw new GeometryUploadError(`Kenar listesi alınamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as EdgesResponse;
  return body.edges;
}

/** Daha önce yüklenmiş bir dosyanın nokta (vertex) listesini çeker. */
export async function fetchPoints(storedFilename: string): Promise<PointInfo[]> {
  const response = await fetch(`${API_BASE_URL}/geometry/${storedFilename}/points`);
  if (!response.ok) {
    throw new GeometryUploadError(`Nokta listesi alınamadı (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as PointsResponse;
  return body.points;
}
