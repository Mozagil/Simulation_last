const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export type ComponentSource = "mesh" | "cad";
export type PropertyKind = "shell" | "solid";

export interface ComponentRecord {
  id: number;
  geometry_id: number;
  part_id: number;
  name: string;
  source: ComponentSource;
  material_id: number | null;
  material_name: string | null;
  material_category: string | null;
  property_kind: PropertyKind;
  thickness: number | null;
}

export interface ProductTreeItem {
  part_id: number;
  label: string;
  component: ComponentRecord | null;
  material_name: string | null;
  property_kind: PropertyKind | null;
  thickness: number | null;
}

export interface ProductTree {
  geometry_id: number;
  original_filename: string;
  item_count: number;
  items: ProductTreeItem[];
}

export async function upsertComponent(
  geometryId: number,
  body: {
    part_id: number;
    name?: string;
    source?: ComponentSource;
    material_id?: number | null;
    property_kind?: PropertyKind;
    thickness?: number | null;
  },
): Promise<ComponentRecord> {
  const response = await fetch(`${API_BASE_URL}/geometry/${geometryId}/components`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Component kaydı başarısız (HTTP ${response.status}).`);
  }
  const payload = (await response.json()) as { component: ComponentRecord };
  return payload.component;
}

export async function patchComponent(
  componentId: number,
  body: {
    name?: string;
    material_id?: number | null;
    property_kind?: PropertyKind;
    thickness?: number;
  },
): Promise<ComponentRecord> {
  const response = await fetch(`${API_BASE_URL}/components/${componentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Component güncellenemedi (HTTP ${response.status}).`);
  }
  const payload = (await response.json()) as { component: ComponentRecord };
  return payload.component;
}

export async function fetchProductTree(
  geometryId: number,
  partCount: number,
): Promise<ProductTree> {
  const response = await fetch(
    `${API_BASE_URL}/geometry/${geometryId}/product-tree?part_count=${partCount}`,
  );
  if (!response.ok) {
    throw new Error(`Ürün ağacı alınamadı (HTTP ${response.status}).`);
  }
  return (await response.json()) as ProductTree;
}
