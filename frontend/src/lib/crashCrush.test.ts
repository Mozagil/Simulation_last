import { describe, expect, it } from "vitest";

import type { LoadCard } from "../components/CrashLoadCards";
import { crushRefFromRequest, crushRefPayload, forceVsCrush } from "./crashCrush";

const cards = [{ id: 11, kind: "inivel" }, { id: 12, kind: "rbody" }] as unknown as LoadCard[];

describe("1.23 C8b crashCrush", () => {
  it("payload: kızak kartı → rbody_<sıra>; bölge; eksik seçim null", () => {
    expect(crushRefPayload({ mode: "rbody", cardId: 12, region: "" }, cards)).toEqual({ rigid_body: "rbody_2" });
    expect(crushRefPayload({ mode: "region", cardId: null, region: "kutu_arka" }, cards)).toEqual({ region: "kutu_arka" });
    expect(crushRefPayload({ mode: "rbody", cardId: 11, region: "" }, cards)).toBeNull(); // kızak değil
    expect(crushRefPayload({ mode: "", cardId: null, region: "" }, cards)).toBeNull();
  });

  it("kayıtlı istekten: rbody_<sıra> → aynı kart; bölge; yok", () => {
    expect(crushRefFromRequest({ rigid_body: "rbody_2" }, cards)).toEqual({ mode: "rbody", cardId: 12, region: "" });
    expect(crushRefFromRequest({ region: "kutu_arka" }, cards)).toEqual({ mode: "region", cardId: null, region: "kutu_arka" });
    expect(crushRefFromRequest(null, cards).mode).toBe("");
  });

  it("F–δ: δ_maks'a kadar, |F|; ezilme yoksa null", () => {
    expect(forceVsCrush([0, 5, 10, 8], [0, -50, -60, 0])).toEqual({ x: [0, 5, 10], f: [0, 50, 60] });
    expect(forceVsCrush([0, -1], [1, 1])).toBeNull();
    expect(forceVsCrush(undefined, [1])).toBeNull();
  });
});
