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

export type ViewDir = "+X" | "-X" | "+Y" | "+Z" | "izo";

/** Kamera yönü (merkezden), birim değil — konum = merkez + v·d. */
export const VIEW_VECTORS: Record<ViewDir, [number, number, number]> = {
  "+X": [1, 0, 0],
  "-X": [-1, 0, 0],
  "+Y": [0, 1, 0],
  "+Z": [0, 0, 1],
  izo: [0.6, 0.5, 0.9],
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

/** 1.23 A4 — deformasyon ölçeği seçenekleri (×1 = gerçek). */
export const DEFORM_SCALES = [1, 2, 5, 10] as const;
/** 1.23 A5 — oynatma hızı: 1× = tüm koşu ~3 sn. */
export const PLAY_SPEEDS = [0.25, 0.5, 1, 2] as const;
const PLAY_SECONDS = 3;

/** Kareler arası doğrusal ara-değer: f kesirli kare indeksi. */
export function lerpFrame(a: ArrayLike<number>, b: ArrayLike<number>, t: number, i: number): number {
  return a[i] + (b[i] - a[i]) * t;
}

/** Ölçekli konum: ilk kareye göre yer değiştirme k ile çarpılır. */
export function scaledPos(p0: number, p: number, k: number): number {
  return p0 + (p - p0) * k;
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

export default function CrashAnimationViewer({
  runId,
  title,
  docked = false,
  onClose,
}: {
  runId: number;
  title?: string;
  /** TODO 11.4 — ana viewport'un üstünde, alanı kaplar (sidebar kutusu yerine). */
  docked?: boolean;
  onClose?: () => void;
}) {
  const [data, setData] = useState<CrashAnimation | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 1.23 A5: kesirli kare (kareler arası ara-değer); etikette en yakın kare.
  const [frameF, setFrameF] = useState(0);
  const frame = Math.round(frameF);
  const setFrame = (f: number) => setFrameF(f);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [deform, setDeform] = useState<number>(1);
  const [scalar, setScalar] = useState("disp_mag");
  const holderRef = useRef<HTMLDivElement | null>(null);
  // Tam ekran: sidebar'daki 260px kutu deforme şekli okumak için dar.
  // Ana viewport'a taşımak `animRun` durumunu App'e çıkarmayı gerektirirdi
  // (3 dosya); kaplama hem daha geniş (ribbon yok) hem tek dosya.
  const [expanded, setExpanded] = useState(false);
  const meshRef = useRef<{ geom: THREE.BufferGeometry; render: () => void } | null>(null);
  /** 1.17g — hazır görünümler: model eksenlerine göre kamera konumu */
  const viewRef = useRef<((dir: ViewDir) => void) | null>(null);

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
    viewRef.current = (dir: ViewDir) => {
      const d = size * 1.25;
      const v = VIEW_VECTORS[dir];
      camera.position.set(center.x + v[0] * d, center.y + v[1] * d, center.z + v[2] * d);
      // +Y bakışında yukarı yönü +Z al (kamera yukarı vektörü bakışa paralel olmasın;
      // −Z idi, plaka–küre koşusunda (1.18b) z ters görünüyordu)
      camera.up.set(0, dir === "+Y" ? 0 : 1, dir === "+Y" ? 1 : 0);
      controls.target.copy(center);
      controls.update();
      render();
    };
    render();

    // Kutu boyutu değişince (tam ekran aç/kapa, panel sürükleme) renderer
    // ve kamera oranı güncellenmeli; yoksa görüntü gerilir.
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
      geom.dispose();
      (mesh.material as THREE.Material).dispose();
      renderer.dispose();
      holder.removeChild(renderer.domElement);
      meshRef.current = null;
      viewRef.current = null;
    };
  }, [data, tri]);

  // Kare / skaler / ölçek değişince konum + renk güncelle. 1.23 A5: iki kare arası
  // doğrusal ara-değer; 1.23 A4: yer değiştirme (ilk kareye göre) × ölçek.
  useEffect(() => {
    const m = meshRef.current;
    if (!m || !data || !tri) return;
    const last = data.frames.length - 1;
    const f = Math.min(Math.max(frameF, 0), last);
    const i0 = Math.floor(f);
    const i1 = Math.min(i0 + 1, last);
    const t = f - i0;
    const fa = data.frames[i0];
    const fb = data.frames[i1];
    const fr = t < 0.5 ? fa : fb; // silinme: en yakın kare
    const p0 = data.frames[0].positions;
    const pos = m.geom.getAttribute("position") as THREE.BufferAttribute;
    const col = m.geom.getAttribute("color") as THREE.BufferAttribute;
    const meta = data.scalars[scalar];
    const nodeA = meta?.location === "node" ? fa.node?.[scalar] : undefined;
    const nodeB = meta?.location === "node" ? fb.node?.[scalar] : undefined;
    const faceA = meta?.location === "face" ? fa.face?.[scalar] : undefined;
    const faceB = meta?.location === "face" ? fb.face?.[scalar] : undefined;
    const lo = meta?.min ?? 0;
    const span = (meta?.max ?? 1) - lo || 1;
    for (let v = 0; v < tri.vtx.length; v += 1) {
      const node = tri.vtx[v];
      const face = tri.tri_face[Math.floor(v / 3)];
      const alive = !fr.face_alive || fr.face_alive[face] !== 0;
      // silinen yüz: üçgen tek noktaya çöker (görünmez)
      const src = alive ? node : tri.vtx[Math.floor(v / 3) * 3];
      pos.setXYZ(
        v,
        scaledPos(p0[src * 3], lerpFrame(fa.positions, fb.positions, t, src * 3), deform),
        scaledPos(p0[src * 3 + 1], lerpFrame(fa.positions, fb.positions, t, src * 3 + 1), deform),
        scaledPos(p0[src * 3 + 2], lerpFrame(fa.positions, fb.positions, t, src * 3 + 2), deform),
      );
      const val =
        nodeA && nodeB
          ? lerpFrame(nodeA, nodeB, t, node)
          : faceA && faceB
            ? lerpFrame(faceA, faceB, t, face)
            : lo;
      const [r, g, b] = jet((val - lo) / span);
      col.setXYZ(v, r, g, b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    // Konumlar her karede değişir; sınır küresi ilk (sıfır) dizilimden kalırsa
    // three.js görüş hacmi kırpması orijin görünmeyen bakışlarda modeli siler
    // (K1 Taylor çubuğu, merkez x = 25: +Y / +Z boş ekran).
    m.geom.computeBoundingSphere();
    m.geom.computeVertexNormals();
    m.render();
  }, [data, tri, frameF, scalar, deform]);

  // 1.23 A5: akıcı oynatma — requestAnimationFrame, gerçek geçen süreyle ilerler.
  useEffect(() => {
    if (!playing || !data) return;
    const last = data.frames.length - 1;
    if (last < 1) return;
    let raf = 0;
    let prev = performance.now();
    const step = (now: number) => {
      const dt = (now - prev) / 1000;
      prev = now;
      setFrameF((f) => {
        const next = f + (dt * speed * last) / PLAY_SECONDS;
        return next > last ? 0 : next;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, data, speed]);

  // 1.23 A4: veri — son karede en büyük yer değiştirme ve model boyutuna oranı.
  const dispInfo = useMemo(() => {
    if (!data || !tri || data.frames.length < 2) return null;
    const a = data.frames[0].positions;
    const b = data.frames[data.frames.length - 1].positions;
    let maxU = 0;
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (const node of tri.vtx) {
      const i = node * 3;
      const dx = b[i] - a[i];
      const dy = b[i + 1] - a[i + 1];
      const dz = b[i + 2] - a[i + 2];
      maxU = Math.max(maxU, Math.hypot(dx, dy, dz));
      for (let k = 0; k < 3; k += 1) {
        lo[k] = Math.min(lo[k], a[i + k]);
        hi[k] = Math.max(hi[k], a[i + k]);
      }
    }
    const size = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1;
    return { maxU, pct: (100 * maxU) / size };
  }, [data, tri]);

  const meta = data?.scalars[scalar];
  const fr = data?.frames[frame];
  // ESC ile çık — tam ekranda başka çıkış yolu görünmüyor.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const deleted = fr?.face_alive ? fr.face_alive.filter((a) => a === 0).length : 0;

  return (
    <figure
      className={
        expanded
          ? "cv-card crash-anim crash-anim-expanded"
          : docked
            ? "cv-card crash-anim crash-anim-docked"
            : "cv-card crash-anim"
      }
      data-testid="crash-anim"
    >
      <span className="cv-card-head">
        <strong>Deforme şekil{title ? ` · ${title}` : ""}</strong>
        {fr && (
          <span className="ds-sb" data-testid="crash-anim-time">
            t = {fmt(fr.time ?? 0)} ms · kare {frame + 1}/{data?.frames.length}
            {deleted ? ` · silinen ${deleted}` : ""}
          </span>
        )}
        <button
          type="button"
          className="crash-anim-expand"
          data-testid="crash-anim-expand"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "Küçült (ESC)" : "Tam ekran"}
          aria-label={expanded ? "Küçült" : "Tam ekran"}
        >
          {expanded ? "⤡" : "⤢"}
        </button>
        {onClose && (
          <button
            type="button"
            className="crash-anim-expand"
            data-testid="crash-anim-close"
            onClick={onClose}
            title="Geometriye dön"
            aria-label="Deforme şekli kapat"
          >
            ×
          </button>
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
              step={0.01}
              onChange={(e) => {
                setPlaying(false);
                setFrame(Number(e.target.value));
              }}
            />
            <select
              aria-label="Oynatma hızı"
              title="Oynatma hızı"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {PLAY_SPEEDS.map((v) => (
                <option key={v} value={v}>
                  {v}× hız
                </option>
              ))}
            </select>
            <select
              aria-label="Deformasyon ölçeği"
              title="Deformasyon ölçeği — yer değiştirme bu katla çizilir"
              value={deform}
              onChange={(e) => setDeform(Number(e.target.value))}
            >
              {DEFORM_SCALES.map((k) => (
                <option key={k} value={k}>
                  {k === 1 ? "ölçek ×1 (gerçek)" : `ölçek ×${k}`}
                </option>
              ))}
            </select>
          </div>
          <div className="crash-anim-deform">
            {dispInfo && (
              <span className="crash-behavior-hint" data-testid="crash-anim-disp">
                Son karede en büyük |u| {fmt(dispInfo.maxU)} mm · model boyutuna oranı %{dispInfo.pct.toFixed(1)}
                {deform !== 1 ? ` · ×${deform} çizim (gerçek değil)` : ""}
              </span>
            )}
          </div>
          <div className="crash-var-chips" role="group" aria-label="Hazır görünüm">
            {(Object.keys(VIEW_VECTORS) as ViewDir[]).map((v) => (
              <button
                key={v}
                type="button"
                className="crash-var-chip"
                title={v === "izo" ? "İzometrik" : `${v} yönünden bak`}
                onClick={() => viewRef.current?.(v)}
              >
                {v === "izo" ? "İzo" : v}
              </button>
            ))}
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
