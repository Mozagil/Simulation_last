import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fetchCrashAnimation, type CrashAnimation } from "../api/crash";

/** Crash deforme şekli (1.17d): yüzey üçgenleri, kare kaydırıcı, oynat, skaler
 * renk (yer değiştirme büyüklüğü düğümde; eleman skalerleri yüzde). Renk
 * ölçeği tüm karelerin min–max'ı (sabit). Silinen eleman (EROSION_STATUS 0)
 * görünmez. Yorum yok, veri gösterir. */

const SCALAR_LABELS: Record<string, string> = {
  disp_mag: "Yer değiştirme |u| (mm)",
  "2DELEM_Plastic_Strain": "Plastik şekil değiştirme (kabuk)",
  "3DELEM_Plastic_Strain": "Plastik şekil değiştirme (solid)",
  "2DELEM_Specific_Energy": "Özgül enerji (kabuk)",
  "3DELEM_Specific_Energy": "Özgül enerji (solid)",
};

/** GeometryViewer / ModalModeGrid jetColor() ile aynı formül. */
export function jet(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  return [
    Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3))),
    Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2))),
    Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1))),
  ];
}

function fmt(v: number): string {
  if (v === 0) return "0";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(2);
}

/** Yüzleri üçgenlere aç: her üçgen köşesi için düğüm indeksi + kaynak yüz. */
export function triangulate(faces: number[][]): { vtx: Int32Array; tri_face: Int32Array } {
  const vtx: number[] = [];
  const tf: number[] = [];
  faces.forEach((f, fi) => {
    for (let k = 1; k + 1 < f.length; k += 1) {
      vtx.push(f[0], f[k], f[k + 1]);
      tf.push(fi);
    }
  });
  return { vtx: Int32Array.from(vtx), tri_face: Int32Array.from(tf) };
}

export default function CrashAnimationViewer({ runId, title }: { runId: number; title?: string }) {
  const [data, setData] = useState<CrashAnimation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [scalar, setScalar] = useState("disp_mag");
  const holderRef = useRef<HTMLDivElement | null>(null);
  const meshRef = useRef<{ geom: THREE.BufferGeometry; render: () => void } | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    setFrame(0);
    fetchCrashAnimation(runId)
      .then((d) => {
        if (!alive) return;
        setData(d);
        const names = Object.keys(d.scalars);
        setScalar(names.find((k) => k.endsWith("Plastic_Strain")) ?? names[0] ?? "disp_mag");
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Animasyon okunamadı."));
    return () => {
      alive = false;
    };
  }, [runId]);

  const tri = useMemo(() => (data ? triangulate(data.faces) : null), [data]);

  // Sahne: veri gelince bir kez kurulur.
  useEffect(() => {
    const holder = holderRef.current;
    if (!data || !tri || !holder) return;
    const width = holder.clientWidth || 320;
    const height = holder.clientHeight || 260;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    holder.appendChild(renderer.domElement);
    const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(dark ? "#101312" : "#f4f6f2");
    scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const dl = new THREE.DirectionalLight(0xffffff, 0.6);
    dl.position.set(1, 1.5, 2);
    scene.add(dl);

    const n = tri.vtx.length;
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    geom.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    const mesh = new THREE.Mesh(
      geom,
      new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.8, flatShading: true }),
    );
    scene.add(mesh);

    // Kamera: ilk kare sınır kutusu
    const p0 = data.frames[0].positions;
    const box = new THREE.Box3();
    // yalnız yüzeylerde kullanılan düğümler (rijit duvar / ana düğüm noktaları hariç)
    for (const v of tri.vtx) box.expandByPoint(new THREE.Vector3(p0[v * 3], p0[v * 3 + 1], p0[v * 3 + 2]));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const camera = new THREE.PerspectiveCamera(35, width / height, size / 100, size * 20);
    camera.position.set(center.x + size * 0.6, center.y + size * 0.5, center.z + size * 0.9);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render);
    meshRef.current = { geom, render };
    render();
    return () => {
      controls.dispose();
      geom.dispose();
      (mesh.material as THREE.Material).dispose();
      renderer.dispose();
      holder.removeChild(renderer.domElement);
      meshRef.current = null;
    };
  }, [data, tri]);

  // Kare / skaler değişince konum + renk güncelle.
  useEffect(() => {
    const m = meshRef.current;
    if (!m || !data || !tri) return;
    const fr = data.frames[Math.min(frame, data.frames.length - 1)];
    const pos = m.geom.getAttribute("position") as THREE.BufferAttribute;
    const col = m.geom.getAttribute("color") as THREE.BufferAttribute;
    const meta = data.scalars[scalar];
    const nodeVals = meta?.location === "node" ? fr.node?.[scalar] : undefined;
    const faceVals = meta?.location === "face" ? fr.face?.[scalar] : undefined;
    const lo = meta?.min ?? 0;
    const span = (meta?.max ?? 1) - lo || 1;
    for (let v = 0; v < tri.vtx.length; v += 1) {
      const node = tri.vtx[v];
      const face = tri.tri_face[Math.floor(v / 3)];
      const alive = !fr.face_alive || fr.face_alive[face] !== 0;
      // silinen yüz: üçgen tek noktaya çöker (görünmez)
      const src = alive ? node : tri.vtx[Math.floor(v / 3) * 3];
      pos.setXYZ(v, fr.positions[src * 3], fr.positions[src * 3 + 1], fr.positions[src * 3 + 2]);
      const val = nodeVals ? nodeVals[node] : faceVals ? faceVals[face] : lo;
      const [r, g, b] = jet((val - lo) / span);
      col.setXYZ(v, r, g, b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    m.geom.computeVertexNormals();
    m.render();
  }, [data, tri, frame, scalar]);

  useEffect(() => {
    if (!playing || !data) return;
    const id = window.setInterval(() => {
      setFrame((f) => (f + 1 >= data.frames.length ? 0 : f + 1));
    }, 120);
    return () => window.clearInterval(id);
  }, [playing, data]);

  const meta = data?.scalars[scalar];
  const fr = data?.frames[frame];
  const deleted = fr?.face_alive ? fr.face_alive.filter((a) => a === 0).length : 0;

  return (
    <figure className="cv-card crash-anim" data-testid="crash-anim">
      <span className="cv-card-head">
        <strong>Deforme şekil{title ? ` · ${title}` : ""}</strong>
        {fr && (
          <span className="ds-sb" data-testid="crash-anim-time">
            t = {fmt(fr.time ?? 0)} ms · kare {frame + 1}/{data?.frames.length}
            {deleted ? ` · silinen ${deleted}` : ""}
          </span>
        )}
      </span>
      {error && <p className="material-assign-hint">{error}</p>}
      {!data && !error && <p className="doe-empty">Animasyon hazırlanıyor… (ilk açılışta dönüştürülür)</p>}
      <div ref={holderRef} className="crash-anim-canvas" aria-label="Deforme şekil 3B görünüm" />
      {data && (
        <>
          <div className="crash-anim-controls">
            <button
              type="button"
              className="doe-btn doe-btn-ghost"
              aria-label={playing ? "Durdur" : "Oynat"}
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <input
              type="range"
              min={0}
              max={data.frames.length - 1}
              value={frame}
              aria-label="Kare"
              onChange={(e) => {
                setPlaying(false);
                setFrame(Number(e.target.value));
              }}
            />
          </div>
          <label className="mesh-field">
            <span>Renk</span>
            <select aria-label="Renk skaleri" value={scalar} onChange={(e) => setScalar(e.target.value)}>
              {Object.keys(data.scalars).map((k) => (
                <option key={k} value={k}>
                  {SCALAR_LABELS[k] ?? k}
                </option>
              ))}
            </select>
          </label>
          {meta && (
            <div className="crash-anim-legend" aria-label="Renk ölçeği">
              <span>{fmt(meta.min)}</span>
              <span className="crash-anim-bar" />
              <span>{fmt(meta.max)}</span>
            </div>
          )}
        </>
      )}
    </figure>
  );
}
