export type SelectionMode = "part" | "surface" | "edge" | "point";

export type MeshGrowMode = "element" | "face" | "attached";

export interface MeshPickInfo {
  elementId: number;
  faceId: number;
  partId: number;
}

export const SELECTION_MODES: { mode: SelectionMode; label: string }[] = [
  { mode: "part", label: "Parça" },
  { mode: "surface", label: "Yüzey" },
  { mode: "edge", label: "Kenar" },
  { mode: "point", label: "Nokta" },
];

/** Aktif moddaki seçili öğelerin id listesi (Ctrl+tık ile çoklu seçim
 * desteklenir — düz tıklama seçimi TEK öğeye indirger, Ctrl+tık mevcut
 * seçime ekler/çıkarır). Boş dizi = hiçbir şey seçili değil.
 */
export interface MultiSelectionInfo {
  mode: SelectionMode;
  ids: number[];
}

/** Mesh üzerinde neyin seçildiği. CAD seçim modlarından (SelectionMode)
 * BAĞIMSIZ ikinci bir eksen: CAD geometrisi ile mesh ayrı varlıklardır.
 * null = mesh seçimi kapalı, CAD modu aktif.
 */
export type MeshSelectMode = "element" | "node" | null;

export const MESH_SELECT_MODES: { mode: Exclude<MeshSelectMode, null>; label: string }[] = [
  { mode: "element", label: "Mesh eleman" },
  { mode: "node", label: "Mesh düğüm" },
];
