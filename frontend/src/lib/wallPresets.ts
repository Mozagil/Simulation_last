/**
 * 1.23 B2 — kayıtlı rijit duvar konumları (düğmeyle kaydet, sonraki vakada listeden seç).
 *
 * Duvar = nokta (mm) + normal (paneldeki yön düğmesi). Tarayıcıda (localStorage)
 * tutulur — sunucu / DB şeması değişmez. Aynı adla kaydetmek üzerine yazar.
 * Depolama yoksa / bozuksa boş liste.
 */

export interface WallPreset {
  name: string;
  point: [number, number, number];
  normal: [number, number, number];
}

const KEY = "crashWallPresets";

const isTriple = (v: unknown): v is [number, number, number] =>
  Array.isArray(v) && v.length === 3 && v.every((c) => typeof c === "number" && Number.isFinite(c));

export function readWallPresets(): WallPreset[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const list = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(list)) return [];
    return list.filter(
      (p): p is WallPreset =>
        !!p && typeof p.name === "string" && p.name.trim() !== "" && isTriple(p.point) && isTriple(p.normal),
    );
  } catch {
    return [];
  }
}

function write(list: WallPreset[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* depolama yoksa yalnız bu oturum */
  }
}

/** Ekle; aynı ad varsa üzerine yazar (sıra korunur). Güncel listeyi döner. */
export function saveWallPreset(p: WallPreset): WallPreset[] {
  const list = readWallPresets();
  const i = list.findIndex((q) => q.name === p.name);
  const next = i >= 0 ? list.map((q, k) => (k === i ? p : q)) : [...list, p];
  write(next);
  return next;
}

export function removeWallPreset(name: string): WallPreset[] {
  const next = readWallPresets().filter((q) => q.name !== name);
  write(next);
  return next;
}

const fmt = (v: number) => String(Number(v.toFixed(3)));

/** Ad verilmezse: "nokta (0, 0, 0) · normal +X" (eksen değilse vektör). */
export function defaultWallName(point: [number, number, number], normal: [number, number, number]): string {
  const axis = ["X", "Y", "Z"].find((_, i) => normal.every((c, k) => (k === i ? Math.abs(c) === 1 : c === 0)));
  const i = ["X", "Y", "Z"].indexOf(axis ?? "");
  const n = axis ? `${normal[i] > 0 ? "+" : "−"}${axis}` : `(${normal.map(fmt).join(", ")})`;
  return `nokta (${point.map(fmt).join(", ")}) · normal ${n}`;
}
