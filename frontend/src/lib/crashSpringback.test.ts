import { describe, expect, it } from "vitest";

import type { CrashAnimation } from "../api/crash";
import { springbackCurves, springbackRows } from "./crashSpringback";

/** Parça 0: düğüm 0–3 (dörtgen), parça 1: düğüm 4–7. Düğüm 8 yüze ait değil (rijit ana düğüm gibi). */
function anim(frames: { t: number; shift: number; dent: number; p1: number; free: number }[]): CrashAnimation {
  const base = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 5, 0, 0, 6, 0, 0, 6, 1, 0, 5, 1, 0, 9, 9, 9];
  return {
    faces: [
      [0, 1, 2, 3],
      [4, 5, 6, 7],
    ],
    face_part: [0, 1],
    scalars: {},
    frames: frames.map((f) => {
      const p = [...base];
      for (let v = 0; v < 4; v++) p[3 * v] += f.shift + (v === 0 ? f.dent : 0);
      for (let v = 4; v < 8; v++) p[3 * v + 1] += f.p1;
      p[24] += f.free;
      return { time: f.t, positions: p };
    }),
  };
}

describe("1.24c3 crashSpringback", () => {
  it("eğri: mutlak ötelemeyi, öteleme çıkarılmış çökmeyi izler (backend testiyle aynı sayılar)", () => {
    const c = springbackCurves(
      anim([
        { t: 0, shift: 0, dent: 0, p1: 0, free: 0 },
        { t: 1, shift: 50, dent: 2, p1: 3, free: 500 },
        { t: 2, shift: 100, dent: 1, p1: 3, free: 900 },
      ]),
    )!;
    expect(c.time).toEqual([0, 1, 2]);
    const p0 = c.series.get(0)!;
    expect(p0.disp).toEqual([0, 52, 101]); // öteleme + çökme (düğüm 0)
    expect(p0.def[1]).toBeCloseTo(1.5);
    expect(p0.def[2]).toBeCloseTo(0.75);
    // parça 1 rijit kayıyor → def 0; model = parçaların en büyüğü; yüze ait olmayan düğüm sayılmaz
    expect(c.series.get(1)!.def).toEqual([0, 0, 0]);
    expect(c.series.get("model")!.disp).toEqual([0, 52, 101]);
    expect(c.series.get("model")!.def[1]).toBeCloseTo(1.5);
  });

  it("tek kare → eğri yok", () => {
    expect(springbackCurves(anim([{ t: 0, shift: 0, dent: 0, p1: 0, free: 0 }]))).toBeNull();
  });

  it("satırlar: model + parça, iki tanım; olmayan tanım satırı yok", () => {
    const rows = springbackRows({
      model_disp_peak_mm: 181.7, model_disp_peak_t_ms: 20, model_disp_final_mm: 181.7, springback_mm: 0, springback_ratio: 0,
      model_def_peak_mm: 4.73, model_def_peak_t_ms: 1, model_def_final_mm: 1.34, springback_def_mm: 3.39, springback_def_ratio: 0.716,
      part_0_def_peak_mm: 4.73, part_0_springback_def_mm: 3.39,
      rwall_force_max: 1756,
    });
    expect(rows.map((r) => `${r.scope}:${r.def}`)).toEqual(["model:disp", "model:def", "0:def"]);
    expect(rows[1]).toMatchObject({ peak: 4.73, tPeak: 1, final: 1.34, springback: 3.39, ratio: 0.716 });
    expect(springbackRows({ rwall_force_max: 1 })).toEqual([]);
  });
});
