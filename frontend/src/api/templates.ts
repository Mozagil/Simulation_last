/** Şablon kütüphanesi API (0.4.3 / 0.4.4). */

import type { SolveBC } from "./materials";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class TemplateApiError extends Error {}

export interface TemplateRegionInfo {
  name: string;
  description: string;
  dim: number;
}

export interface GeometryTemplateInfo {
  id: string;
  name: string;
  description: string;
  tags: string[];
  params_schema: {
    properties?: Record<string, unknown>;
    required?: string[];
  };
  regions: TemplateRegionInfo[];
  has_analytic: boolean;
  /** Bölge adıyla bağlı (id'siz) referans BC'ler. */
  default_bcs?: SolveBC[];
}

export interface CreateFromTemplateResponse {
  geometry_id: number;
  /** Şablonun referans sınır koşulları, bu geometrinin yüzey/kenar id'leriyle
   * bağlı. Arayüz bunları BC listesine hazır koyar; kullanıcı düzenler. */
  default_bcs?: SolveBC[];
  original_filename: string;
  current_filename: string;
  template_id: string;
  template_params: Record<string, number>;
  regions: Record<string, number[]>;
  tessellation_url: string;
  triangle_count: number;
  face_count: number;
  triangle_to_face: number[];
  triangle_to_face_url: string;
  part_count: number;
  triangle_to_part: number[];
  triangle_to_part_url: string;
  volume_part_ids: number[];
}

export async function fetchTemplates(): Promise<GeometryTemplateInfo[]> {
  const res = await fetch(`${API_BASE_URL}/templates`);
  if (!res.ok) {
    throw new TemplateApiError(`Şablon listesi alınamadı (HTTP ${res.status}).`);
  }
  const body = (await res.json()) as { templates: GeometryTemplateInfo[] };
  return body.templates;
}

export async function createGeometryFromTemplate(
  templateId: string,
  params: Record<string, number | string>,
): Promise<CreateFromTemplateResponse> {
  const res = await fetch(`${API_BASE_URL}/templates/${encodeURIComponent(templateId)}/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new TemplateApiError(text || `Şablon üretilemedi (HTTP ${res.status}).`);
  }
  return (await res.json()) as CreateFromTemplateResponse;
}

export async function downloadGeometryStep(geometryId: number, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/geometry/${geometryId}/step`);
  if (!res.ok) {
    throw new TemplateApiError(`STEP indirilemedi (HTTP ${res.status}).`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".step") || filename.endsWith(".stp") ? filename : `${filename}.step`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
