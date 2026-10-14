import { describe, expect, it } from "vitest";
import { meshPreviewUrl, meshResultFromPreview, meshSizeText } from "./crashRunLoad";

const preview = (triToElem: number[], elemTags?: number[]) => ({
  nodes: [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
  faces: [],
  lines: [],
  triangle_to_element: triToElem,
  element_tags: elemTags,
});

describe("1.23 B3a — geçmişten koşu yükle: mesh özeti önizlemeden", () => {
  it("meshPreviewUrl: geometri + boyut", () => {
    expect(meshPreviewUrl(4277, 2)).toBe("/files/meshes/4277_d2.preview.json");
  });

  it("eleman başına 2 üçgen → quad; sayılar önizlemeden; boyut bilinmez (NaN)", () => {
    const m = meshResultFromPreview(7, 2, preview([0, 0, 1, 1], [11, 12]));
    expect(m).toMatchObject({ geometry_id: 7, dimension: 2, element_scheme: "quad", node_count: 4, element_count: 2 });
    expect(m.preview_url).toBe("/files/meshes/7_d2.preview.json");
    expect(Number.isNaN(m.element_size)).toBe(true);
  });

  it("hepsi 1 üçgen → tet (üçgen); karışık → mix; element_tags yoksa eleman sayısı üçgen eşlemesinden", () => {
    expect(meshResultFromPreview(1, 2, preview([0, 1, 2])).element_scheme).toBe("tet");
    expect(meshResultFromPreview(1, 2, preview([0, 1, 2])).element_count).toBe(3);
    expect(meshResultFromPreview(1, 2, preview([0, 0, 1])).element_scheme).toBe("mix");
  });

  it("meshSizeText: bilinmeyen boyut '—'", () => {
    expect(meshSizeText(Number.NaN)).toBe("—");
    expect(meshSizeText(5)).toBe("5");
  });
});
