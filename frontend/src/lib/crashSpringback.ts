/** 1.24c3 — geri sekme: skaler satırları (backend 1.24c1) + |u|max–t eğrisi (animasyon karelerinden).
 *
 * Tanımlar backend `crash_springback.py` ile aynı (kullanıcı kararı D):
 * - mutlak: |u|max, u = konum − ilk kare konumu (rijit öteleme dahil)
 * - öteleme çıkarılmış: |u − ū(parça)|max, ū = o karede parçanın düğümlerinin ortalaması
 * Eğri yalnız yüzey düğümlerinden (animasyon yüzleri; kabukta tüm düğümler). Katı parçada iç
 * düğümler yok → öteleme çıkarılmış eğri backend skalerinden biraz farklı olabilir. Veri, yorum yok.
 */

import type { CrashAnimation } from "../api/crash";

export type SbDef = "disp" | "def";

export interface SpringbackRow {
  scope: "model" | number;
  def: SbDef;
  peak?: number;
  tPeak?: number;
  final?: number;
  springback?: number;
  ratio?: number;
}

/** Skalerlerden tablo satırları: model + backend'in yazdığı her parça, iki tanım. */
export function springbackRows(sc: Record<string, number> | undefined): SpringbackRow[] {
  if (!sc) return [];
  const parts = [
    ...new Set(
      Object.keys(sc)
        .map((k) => /^part_(\d+)_(disp|def)_peak_mm$/.exec(k)?.[1])
        .filter((p): p is string => p != null)
        .map(Number),
    ),
  ].sort((a, b) => a - b);
  const rows: SpringbackRow[] = [];
  for (const scope of ["model", ...parts] as const) {
    for (const def of ["disp", "def"] as const) {
      const pre = scope === "model" ? "model_" : `part_${scope}_`;
      const sb = def === "disp" ? "springback" : "springback_def";
      const sbPre = scope === "model" ? "" : `part_${scope}_`;
      const row: SpringbackRow = {
        scope,
        def,
        peak: sc[`${pre}${def}_peak_mm`],
        tPeak: sc[`${pre}${def}_peak_t_ms`],
        final: sc[`${pre}${def}_final_mm`],
        springback: sc[`${sbPre}${sb}_mm`],
        ratio: sc[`${sbPre}${sb}_ratio`],
      };
      if (row.peak != null || row.springback != null) rows.push(row);
    }
  }
  return rows;
}

export interface SpringbackCurves {
  time: number[];
  /** kapsam ("model" ya da parça no) → tanım → kare başına değer */
  series: Map<"model" | number, Record<SbDef, number[]>>;
}

/** Animasyon kareleri → kare başına |u|max (mutlak + öteleme çıkarılmış), model ve parça. */
/** Deck yazıcının kuralı (openradioss `_rid`): mesh parçası #p → /PART/p+1; animasyon kart kimliği verir. */
export const cardToMeshPart = (card: number) => card - 1;

export function springbackCurves(anim: CrashAnimation): SpringbackCurves | null {
  const frames = anim.frames.filter((f) => f.positions.length > 0);
  if (frames.length < 2) return null;
  const members = new Map<number, number[]>();
  anim.faces.forEach((face, fi) => {
    const p = cardToMeshPart(anim.face_part[fi] ?? 1);
    const set = members.get(p) ?? [];
    for (const v of face) set.push(v);
    members.set(p, set);
  });
  for (const [p, nodes] of members) members.set(p, [...new Set(nodes)]);
  const p0 = frames[0].positions;
  const time = frames.map((f, k) => f.time ?? k);
  const series = new Map<"model" | number, Record<SbDef, number[]>>();
  const push = (scope: "model" | number, def: SbDef, v: number) => {
    const s = series.get(scope) ?? { disp: [], def: [] };
    s[def].push(v);
    series.set(scope, s);
  };
  for (const f of frames) {
    let modelAbs = -Infinity;
    let modelDef = -Infinity;
    for (const [p, nodes] of members) {
      const us: [number, number, number][] = [];
      for (const v of nodes) {
        const x = f.positions[3 * v];
        const y = f.positions[3 * v + 1];
        const z = f.positions[3 * v + 2];
        const x0 = p0[3 * v];
        const y0 = p0[3 * v + 1];
        const z0 = p0[3 * v + 2];
        if (x == null || y == null || z == null || x0 == null || y0 == null || z0 == null) continue;
        us.push([x - x0, y - y0, z - z0]);
      }
      let abs = NaN;
      let def = NaN;
      if (us.length) {
        const m = [0, 1, 2].map((i) => us.reduce((s, u) => s + u[i], 0) / us.length);
        abs = Math.max(...us.map((u) => Math.hypot(u[0], u[1], u[2])));
        def = Math.max(...us.map((u) => Math.hypot(u[0] - m[0], u[1] - m[1], u[2] - m[2])));
        modelAbs = Math.max(modelAbs, abs);
        modelDef = Math.max(modelDef, def);
      }
      push(p, "disp", abs);
      push(p, "def", def);
    }
    push("model", "disp", Number.isFinite(modelAbs) ? modelAbs : NaN);
    push("model", "def", Number.isFinite(modelDef) ? modelDef : NaN);
  }
  return { time, series };
}
