import { describe, expect, it } from "vitest";
import { CRASH_DOC, CRASH_MATERIAL_EXAMPLES } from "./crashDoc";

describe("1.23 A3 — belgede malzeme örnekleri", () => {
  it("dört örnek (LAW1, LAW2 εp,max, TENSSTRAIN, JOHNSON) ayrı bölümde, kartlı ve ölçülmüş sonuçlu", () => {
    expect(CRASH_MATERIAL_EXAMPLES.map((e) => e.card)).toEqual(["/MAT/LAW1", "/MAT/LAW2", "/FAIL/TENSSTRAIN", "/FAIL/JOHNSON"]);
    const sec = CRASH_DOC.find((s) => s.id === "malzeme-ornek");
    expect(sec?.items).toHaveLength(4);
    for (const it of sec!.items!) {
      expect(it.what).toMatch(/Sonuç: .*(kN|J)/);
      expect(it.card).toBeTruthy();
    }
  });
});
