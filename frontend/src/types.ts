export type SelectionMode = "part" | "surface" | "edge" | "point";

export const SELECTION_MODES: { mode: SelectionMode; label: string }[] = [
  { mode: "part", label: "Parça" },
  { mode: "surface", label: "Yüzey" },
  { mode: "edge", label: "Kenar" },
  { mode: "point", label: "Nokta" },
];

export type SelectionInfo =
  | { mode: "part"; id: number; triangleCount: number }
  | { mode: "surface"; id: number; triangleCount: number }
  | { mode: "edge"; id: number; length: number }
  | { mode: "point"; id: number; coordinate: [number, number, number] };
