/**
 * Mesh düğüm bulutu (THREE.Points) yardımcıları.
 *
 * Gizlenen Tet10/Tri6 ara düğümlerinin konumu NaN yapılır; three.js sınır
 * küresini bu konumlardan hesaplarsa yarıçap NaN olur ve raycast bütün bulutu
 * ıskalar (hiçbir düğüm seçilemez). Küre/kutu bozulmamış konum kopyasından
 * (tüm düğümler — gizlilerin üst kümesi) kurulur.
 */
import * as THREE from "three";

export function setNodeCloudBounds(geometry: THREE.BufferGeometry, basePositions: Float32Array) {
  const box = new THREE.Box3().setFromArray(basePositions);
  geometry.boundingBox = box;
  geometry.boundingSphere = box.getBoundingSphere(new THREE.Sphere());
}
