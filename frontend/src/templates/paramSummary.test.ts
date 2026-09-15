import { describe, expect, it } from "vitest";
import { summarizeTemplateParams, symbolMapFromTemplates } from "./paramSummary";

const TEMPLATES = [
  {
    id: "cantilever_beam",
    name: "Ankastre kiriş",
    description: "",
    tags: [],
    params_schema: {
      properties: {
        length: { type: "number", default: 500, symbol: "L" },
        thickness: { type: "number", default: 10, symbol: "T" },
        width: { type: "number", default: 50, symbol: "W" },
      },
    },
    regions: [],
    has_analytic: true,
  },
] as never;

describe("summarizeTemplateParams", () => {
  const symbols = symbolMapFromTemplates(TEMPLATES);

  it("harfleri kullanır ve gereksiz basamakları kırpar", () => {
    const out = summarizeTemplateParams(
      "cantilever_beam",
      { length: 512.4999, thickness: 9.4, width: 48 },
      symbols,
    );
    expect(out).toBe("L 512.5 · T 9.4 · W 48");
  });

  it("bilinmeyen şablonda parametre adını gösterir", () => {
    expect(summarizeTemplateParams("yok", { length: 400 }, symbols)).toBe("length 400");
  });

  it("enum/metin değerleri olduğu gibi yazar", () => {
    expect(summarizeTemplateParams("cantilever_beam", { notch_kind: "v" }, symbols)).toBe(
      "notch_kind v",
    );
  });

  it("parametre yoksa boş döner", () => {
    expect(summarizeTemplateParams("cantilever_beam", null, symbols)).toBe("");
    expect(summarizeTemplateParams("cantilever_beam", {}, symbols)).toBe("");
  });
});
