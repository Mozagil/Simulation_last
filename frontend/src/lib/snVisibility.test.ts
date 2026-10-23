import { describe, expect, it } from "vitest";
import { customMaterialSnMode, snControlsVisible } from "./snVisibility";

describe("snControlsVisible", () => {
  it("crash ve MBD sekmelerinde S-N öğeleri gizli", () => {
    expect(snControlsVisible("crash")).toBe(false);
    expect(snControlsVisible("mbd")).toBe(false);
    expect(customMaterialSnMode(true, "mbd")).toBe("none");
  });

  it("durability ve modal sekmelerinde değişmedi", () => {
    expect(snControlsVisible("durability")).toBe(true);
    expect(snControlsVisible("modal")).toBe(true);
  });
});

describe("customMaterialSnMode", () => {
  it("durability'de kutu işaretliyse tahmini S-N", () => {
    expect(customMaterialSnMode(true, "durability")).toBe("estimated");
    expect(customMaterialSnMode(false, "durability")).toBe("none");
  });

  it("crash'te gizli kutu işaretli kalsa da S-N eklenmez", () => {
    expect(customMaterialSnMode(true, "crash")).toBe("none");
  });
});
