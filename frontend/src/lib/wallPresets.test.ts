import { beforeEach, describe, expect, it } from "vitest";
import { defaultWallName, readWallPresets, removeWallPreset, saveWallPreset } from "./wallPresets";

describe("1.23 B2 — kayıtlı duvarlar", () => {
  beforeEach(() => window.localStorage.removeItem("crashWallPresets"));

  it("kaydet / oku / aynı adla üzerine yaz / sil", () => {
    expect(readWallPresets()).toEqual([]);
    saveWallPreset({ name: "a", point: [0, 0, 0], normal: [1, 0, 0] });
    saveWallPreset({ name: "b", point: [1, 2, 3], normal: [0, 0, -1] });
    saveWallPreset({ name: "a", point: [5, 0, 0], normal: [1, 0, 0] });
    expect(readWallPresets().map((p) => [p.name, p.point[0]])).toEqual([
      ["a", 5],
      ["b", 1],
    ]);
    expect(removeWallPreset("a").map((p) => p.name)).toEqual(["b"]);
  });

  it("bozuk kayıt ve geçersiz girdiler atlanır", () => {
    window.localStorage.setItem("crashWallPresets", "{bozuk");
    expect(readWallPresets()).toEqual([]);
    window.localStorage.setItem(
      "crashWallPresets",
      JSON.stringify([{ name: "ok", point: [0, 0, 0], normal: [0, 1, 0] }, { name: "", point: [0, 0, 0], normal: [0, 1, 0] }, { name: "x", point: [0, 0] }]),
    );
    expect(readWallPresets().map((p) => p.name)).toEqual(["ok"]);
  });

  it("otomatik ad: eksen normali ± eksen, değilse vektör", () => {
    expect(defaultWallName([0, 0, 0], [-1, 0, 0])).toBe("nokta (0, 0, 0) · normal −X");
    expect(defaultWallName([12.5, 0, 40], [0, 0, 1])).toBe("nokta (12.5, 0, 40) · normal +Z");
    expect(defaultWallName([0, 0, 0], [0.7071, 0.7071, 0])).toBe("nokta (0, 0, 0) · normal (0.707, 0.707, 0)");
  });
});
