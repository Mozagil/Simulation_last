import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fetchCfdFields, type CfdFields } from "../api/cfd";
import { jet } from "./CrashAnimationViewer";

/** Faz 2.8 alan görselleştirme: gövde yüzeyinde Cp (nokta bulutu), kesit
 * düzleminde |U| ve akım çizgileri (|U| renkli). Renk ölçeği katman başına
 * verinin min–max'ı. Yorum yok, veri gösterir. */

export type FieldLayer = "cp" | "slice" | "lines";

export function range(vals: number[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of vals) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return Number.isFinite(lo) ? [lo, hi] : [0, 1];
}

function colors(vals: number[], [lo, hi]: [number, number]): Float32Array {
  const span = hi - lo || 1;
  const out = new Float32Array(vals.length * 3);
  vals.forEach((v, i) => out.set(jet((v - lo) / span), i * 3));
  return out;
}

function fmt(v: number): string {
  return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3);
}

export default function CfdFieldViewer({ jobId }: { jobId: string }) {
  const [data, setData] = useState<CfdFields | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<Record<FieldLayer, boolean>>({ cp: true, slice: true, lines: true });
  const holderRef = useRef<HTMLDivElement>(null);
  const objsRef = useRef<Partial<Record<FieldLayer, THREE.Object3D>>>({});
  const renderRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    fetchCfdFields(jobId)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  useEffect(() => {
    const holder = holderRef.current;
    if (!data || !holder) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      return; // WebGL yok (test ortamı)
    }
    const width = holder.clientWidth || 640;
    const height = holder.clientHeight || 380;
    renderer.setSize(width, height);
    renderer.setClearColor(0xf4f6f8);
    holder.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const box = new THREE.Box3();
    const disposables: { dispose: () => void }[] = [];
    const addPoints = (key: FieldLayer, pts: [number, number, number][], vals: number[], size: number) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(pts.flat()), 3));
      g.setAttribute("color", new THREE.BufferAttribute(colors(vals, range(vals)), 3));
      const m = new THREE.PointsMaterial({ size, vertexColors: true, sizeAttenuation: false });
      scene.add((objsRef.current[key] = new THREE.Points(g, m)));
      disposables.push(g, m);
      g.computeBoundingBox();
      if (key === "cp" && g.boundingBox) box.union(g.boundingBox);
    };
    if (data.body) addPoints("cp", data.body.points, data.body.cp, 6);
    if (data.slice) addPoints("slice", data.slice.points, data.slice.speed, 3);
    if (data.streamlines?.length) {
      const group = new THREE.Group();
      const rg = range(data.streamlines.flatMap((s) => s.speed));
      for (const s of data.streamlines) {
        if (s.points.length < 2) continue;
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(s.points.flat()), 3));
        g.setAttribute("color", new THREE.BufferAttribute(colors(s.speed, rg), 3));
        const m = new THREE.LineBasicMaterial({ vertexColors: true });
        group.add(new THREE.Line(g, m));
        disposables.push(g, m);
      }
      scene.add((objsRef.current.lines = group));
    }
    if (box.isEmpty()) box.setFromObject(scene);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const camera = new THREE.PerspectiveCamera(35, width / height, size / 200, size * 50);
    camera.position.set(center.x + size * 0.4, center.y - size * 1.1, center.z + size * 0.5);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render);
    renderRef.current = render;
    render();
    const ro = new ResizeObserver(() => {
      const w = holder.clientWidth;
      const h = holder.clientHeight;
      if (w < 2 || h < 2) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    });
    ro.observe(holder);
    return () => {
      ro.disconnect();
      controls.dispose();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      holder.removeChild(renderer.domElement);
      objsRef.current = {};
      renderRef.current = null;
    };
  }, [data]);

  useEffect(() => {
    (Object.keys(layers) as FieldLayer[]).forEach((k) => {
      const o = objsRef.current[k];
      if (o) o.visible = layers[k];
    });
    renderRef.current?.();
  }, [layers, data]);

  if (error) return <p className="crash-behavior-hint" data-testid="cfd-fields-missing">Alan görselleştirme: {error}</p>;
  if (!data) return <p className="crash-behavior-hint">Alan verisi yükleniyor…</p>;

  const legends: { key: FieldLayer; label: string; vals?: number[] }[] = [
    { key: "cp", label: "Cp (gövde)", vals: data.body?.cp },
    { key: "slice", label: "|U| kesit (m/s)", vals: data.slice?.speed },
    { key: "lines", label: "|U| akım çizgisi (m/s)", vals: data.streamlines?.flatMap((s) => s.speed) },
  ];
  return (
    <div className="cfd-fields" data-testid="cfd-fields">
      <h4>Alan görselleştirme</h4>
      <div className="cfd-fields-toolbar">
        {legends.map((l) => {
          if (!l.vals?.length) return null;
          const [lo, hi] = range(l.vals);
          return (
            <label key={l.key} className="material-check">
              <input type="checkbox" checked={layers[l.key]} onChange={(e) => setLayers((s) => ({ ...s, [l.key]: e.target.checked }))} />
              <span>
                {l.label}: {fmt(lo)} … {fmt(hi)}
              </span>
            </label>
          );
        })}
      </div>
      <div className="cfd-fields-view" ref={holderRef} />
      <div className="cfd-fields-scale" aria-hidden="true" />
      <p className="crash-behavior-hint">
        Renk: mavi = en düşük, kırmızı = en yüksek (katman başına min–max) · {data.body?.points.length ?? 0} yüzey noktası ·{" "}
        {data.slice?.points.length ?? 0} kesit noktası · {data.streamlines?.length ?? 0} akım çizgisi · U∞ {fmt(data.u_ref_m_s)} m/s
      </p>
    </div>
  );
}
