/**
 * 1.23 B3a — geçmişten crash koşusu yükle: geometri + sunucudaki mesh + kurulum.
 *
 * Crash koşusu mesh bilgisini (eleman boyutu, şema) kaydetmiyor; mesh dosyası ve
 * önizlemesi geometri başına sunucuda duruyor (`/files/meshes/{id}_d{2|3}.preview.json`).
 * Mesh özeti önizlemeden çıkarılır: düğüm / eleman sayısı ve şema (önizlemede eleman
 * başına üçgen: hepsi 2 → quad, hepsi 1 → tet (üçgen), karışık → mix). Eleman boyutu
 * bilinmez → NaN (arayüz "—" yazar); paneldeki eleman boyutu alanına dokunulmaz.
 */

import type { MeshGenerateResponse, MeshPreviewData } from "../api/geometry";

export function meshPreviewUrl(geometryId: number, dimension: 2 | 3): string {
  return `/files/meshes/${geometryId}_d${dimension}.preview.json`;
}

export function meshResultFromPreview(
  geometryId: number,
  dimension: 2 | 3,
  preview: MeshPreviewData,
): MeshGenerateResponse {
  const triPerElem = new Map<number, number>();
  for (const e of preview.triangle_to_element ?? []) triPerElem.set(e, (triPerElem.get(e) ?? 0) + 1);
  const counts = new Set(triPerElem.values());
  const scheme: MeshGenerateResponse["element_scheme"] =
    counts.size === 1 && counts.has(2) ? "quad" : counts.size === 1 && counts.has(1) ? "tet" : counts.size ? "mix" : "tet";
  const url = meshPreviewUrl(geometryId, dimension);
  return {
    geometry_id: geometryId,
    element_size: Number.NaN,
    dimension,
    element_scheme: scheme,
    node_count: preview.nodes.length,
    element_count: preview.element_tags?.length ?? triPerElem.size,
    element_type_counts: {},
    mesh_path: "",
    mesh_url: url.replace(".preview.json", ".msh"),
    preview_url: url,
  };
}

/** Eleman boyutu metni: bilinmiyorsa (geçmişten yüklenen mesh) "—". */
export function meshSizeText(size: number): string {
  return Number.isFinite(size) ? String(size) : "—";
}
