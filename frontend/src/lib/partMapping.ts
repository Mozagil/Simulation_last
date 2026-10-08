/**
 * Mesh parça no ↔ CAD parça no eşlemesi (yüzey etiketi üzerinden).
 *
 * 2D mesh'te parça numarası bağlı kabuk bileşenlerinden gelir; CAD
 * tessellation'ında ise solid + orta yüzey birlikte numaralanır (ör. mesh
 * "Parça #0" = CAD parça 1). İki önizleme de aynı CAD yüzey etiketini taşır,
 * eşleme bunun üzerinden kurulur.
 */
export type PartMap = Map<number, number[]>;

function facesByPart(triToPart: number[], triToFace: number[]): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>();
  const n = Math.min(triToPart.length, triToFace.length);
  for (let i = 0; i < n; i++) {
    const p = triToPart[i];
    if (p < 0) continue;
    let s = out.get(p);
    if (!s) out.set(p, (s = new Set()));
    s.add(triToFace[i]);
  }
  return out;
}

/** mesh parça → o parçanın yüzeylerini içeren CAD parçaları. */
export function buildMeshToCadParts(
  meshTriToPart: number[],
  meshTriToFace: number[],
  cadTriToPart: number[],
  cadTriToFace: number[],
): PartMap {
  const faceToCad = new Map<number, Set<number>>();
  const n = Math.min(cadTriToPart.length, cadTriToFace.length);
  for (let i = 0; i < n; i++) {
    const p = cadTriToPart[i];
    if (p < 0) continue;
    let s = faceToCad.get(cadTriToFace[i]);
    if (!s) faceToCad.set(cadTriToFace[i], (s = new Set()));
    s.add(p);
  }
  const map: PartMap = new Map();
  for (const [mp, faces] of facesByPart(meshTriToPart, meshTriToFace)) {
    const cad = new Set<number>();
    for (const f of faces) for (const c of faceToCad.get(f) ?? []) cad.add(c);
    map.set(mp, [...cad].sort((a, b) => a - b));
  }
  return map;
}

/** CAD parça seçimi → seçili sayılacak mesh parçaları. */
export function meshPartsForCadSelection(map: PartMap, cadIds: number[]): number[] {
  const sel = new Set(cadIds);
  const out: number[] = [];
  for (const [mp, cad] of map) if (cad.some((c) => sel.has(c))) out.push(mp);
  return out.sort((a, b) => a - b);
}

/** Bir mesh parçasının CAD yüzey etiketleri (vurgulama için). */
export function meshPartFaces(meshTriToPart: number[], meshTriToFace: number[], partId: number): number[] {
  return [...(facesByPart(meshTriToPart, meshTriToFace).get(partId) ?? [])];
}
