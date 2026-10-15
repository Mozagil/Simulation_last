/** 1.21e-2d — içe aktarılan modelin dış yüzeyi (önizleme): parça (PID) renkli, döndürülebilir.
 * Veri `/crash/import/dyna/{id}/preview` (mm). Yalnız görüntü; seçim / düzenleme yok. */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { DynaImportPreview } from "../api/crash";

const PALETTE = [0x3b6ea8, 0xc0703a, 0x4f8a5b, 0x8a5aa8, 0xa8a03b, 0x3ba89e, 0xa83b5a, 0x6b6b6b];

export const partColor = (i: number) => `#${PALETTE[i % PALETTE.length].toString(16).padStart(6, "0")}`;

/** Yüzleri üçgenler (dörtgen → 2), yüz başına renk; parça sırası `pids` dizisinden. */
export function previewTriangles(p: DynaImportPreview): { positions: number[]; colors: number[]; pids: number[] } {
  const pids = [...new Set(p.face_part)].sort((a, b) => a - b);
  const positions: number[] = [];
  const colors: number[] = [];
  p.faces.forEach((f, fi) => {
    const c = new THREE.Color(PALETTE[pids.indexOf(p.face_part[fi]) % PALETTE.length]);
    for (let k = 1; k + 1 < f.length; k++) {
      for (const v of [f[0], f[k], f[k + 1]]) {
        positions.push(...p.nodes[v]);
        colors.push(c.r, c.g, c.b);
      }
    }
  });
  return { positions, colors, pids };
}

export default function CrashImportPreview({ preview }: { preview: DynaImportPreview }) {
  const host = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el || typeof WebGLRenderingContext === "undefined") return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      return; // WebGL yok (test ortamı)
    }
    const w = el.clientWidth || 400;
    const h = el.clientHeight || 300;
    renderer.setSize(w, h);
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f3f0);
    const { positions, colors } = previewTriangles(preview);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, flatShading: true }));
    scene.add(mesh);
    scene.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0x222222 })));
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const sun = new THREE.DirectionalLight(0xffffff, 0.8);
    sun.position.set(1, 1.5, 2);
    scene.add(sun);
    const { min, max } = preview.bbox_mm;
    const centre = new THREE.Vector3((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2);
    const size = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1);
    const camera = new THREE.PerspectiveCamera(40, w / h, size / 100, size * 50);
    camera.up.set(0, 0, 1);
    camera.position.copy(centre).add(new THREE.Vector3(size * 1.2, -size * 1.4, size * 0.9));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(centre);
    controls.update();
    let raf = 0;
    const loop = () => {
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelAnimationFrame(raf);
      controls.dispose();
      geo.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [preview]);

  const pids = [...new Set(preview.face_part)].sort((a, b) => a - b);
  return (
    <figure className="crash-import-preview" aria-label="İçe aktarılan model önizlemesi">
      <div ref={host} className="crash-import-preview-canvas" />
      <figcaption className="crash-import-legend">
        {pids.map((pid, i) => (
          <span key={pid}>
            <i style={{ background: partColor(i) }} /> PID {pid} · {preview.part_faces[String(pid)] ?? 0} yüz
          </span>
        ))}
        <span className="ds-sb">
          {" "}
          · kutu {preview.bbox_mm.min.map((v) => v.toFixed(0)).join(", ")} … {preview.bbox_mm.max.map((v) => v.toFixed(0)).join(", ")} mm
        </span>
      </figcaption>
    </figure>
  );
}
