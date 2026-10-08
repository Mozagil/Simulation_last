import { describe, expect, it } from "vitest";
import { buildMeshToCadParts, meshPartFaces, meshPartsForCadSelection } from "./partMapping";

describe("partMapping", () => {
  // CAD: parça 0 = solid (yüzey 1-3), parça 1 = orta yüzey (yüzey 7)
  const cadPart = [0, 0, 0, 1, 1];
  const cadFace = [1, 2, 3, 7, 7];
  // Mesh (2D, yalnız orta yüzey): parça 0 → yüzey 7
  const meshPart = [0, 0, 0];
  const meshFace = [7, 7, 7];

  it("solid + orta yüzey: mesh #0 → CAD 1", () => {
    const m = buildMeshToCadParts(meshPart, meshFace, cadPart, cadFace);
    expect(m.get(0)).toEqual([1]);
    expect(meshPartsForCadSelection(m, [1])).toEqual([0]);
    expect(meshPartsForCadSelection(m, [0])).toEqual([]);
  });

  it("aynı numaralı modelde kimlik eşlemesi", () => {
    const m = buildMeshToCadParts([0, 1], [5, 9], [0, 1, 1], [5, 9, 9]);
    expect([...m.entries()]).toEqual([[0, [0]], [1, [1]]]);
    expect(meshPartFaces([0, 1, 1], [5, 9, 9], 1)).toEqual([9]);
  });
});
