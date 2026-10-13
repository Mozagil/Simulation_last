import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { setNodeCloudBounds } from "./nodeCloud";

function cloud() {
  const base = new Float32Array([0, 0, 0, 10, 0, 0, 5, 0, 0]); // 3. düğüm = ara düğüm
  const pos = base.slice();
  pos[6] = pos[7] = pos[8] = NaN; // gizli
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const pts = new THREE.Points(geom, new THREE.PointsMaterial());
  pts.updateMatrixWorld();
  return { base, geom, pts };
}

function pick(pts: THREE.Points, x: number) {
  const ray = new THREE.Raycaster(new THREE.Vector3(x, 0, 5), new THREE.Vector3(0, 0, -1));
  ray.params.Points = { threshold: 0.5 };
  return ray.intersectObject(pts).map((h) => h.index);
}

describe("setNodeCloudBounds", () => {
  it("NaN'lı konumlardan hesaplanan küre bozuk, raycast ıskalar (hatanın kendisi)", () => {
    const { pts } = cloud();
    expect(pick(pts, 0)).toEqual([]);
  });

  it("küre bozulmamış kopyadan kurulunca görünür düğüm seçilir, gizli düğüm seçilmez", () => {
    const { base, geom, pts } = cloud();
    setNodeCloudBounds(geom, base);
    expect(geom.boundingSphere?.radius).toBeCloseTo(5);
    expect(pick(pts, 0)).toEqual([0]);
    expect(pick(pts, 10)).toEqual([1]);
    expect(pick(pts, 5)).toEqual([]);
  });
});
