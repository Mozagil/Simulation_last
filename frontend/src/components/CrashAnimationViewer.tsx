import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fetchCrashAnimation, fetchCrashRun, type CrashAnimation } from "../api/crash";

/** Crash deforme şekli (1.17d): yüzey üçgenleri, kare kaydırıcı, oynat, skaler
 * renk (yer değiştirme büyüklüğü düğümde; eleman skalerleri yüzde). Renk
 * ölçeği tüm karelerin min–max'ı (sabit). Silinen eleman (EROSION_STATUS 0)
 * görünmez. Yorum yok, veri gösterir. */

const SCALAR_LABELS: Record<string, string> = {
  disp_mag: "Yer değiştirme |u| (mm)",
  disp_x: "Yönlü yer değiştirme uₓ (mm)",
  disp_y: "Yönlü yer değiştirme u_y (mm)",
  disp_z: "Yönlü yer değiştirme u_z (mm)",
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

/** 1.23 C7 — yönlü yer değiştirme: her karede uₓ, u_y, u_z = konum − ilk kare konumu
 *  (düğüm, mm, işaretli). Renk ölçeği tüm karelerin min–max'ı (diğer skalerler gibi).
 *  Iraksamış karede null konum → null. */
export function withDirectional(d: CrashAnimation): CrashAnimation {
  const p0 = d.frames[0]?.positions;
  if (!p0) return d;
  const keys = ["disp_x", "disp_y", "disp_z"] as const;
  const lo = [Infinity, Infinity, Infinity];
  const hi = [-Infinity, -Infinity, -Infinity];
  const frames = d.frames.map((fr) => {
    const n = Math.floor(fr.positions.length / 3);
    const comp = keys.map(() => new Array<number | null>(n).fill(null));
    for (let i = 0; i < n; i++) {
      for (let k = 0; k < 3; k++) {
        const p = fr.positions[i * 3 + k];
        const a = p0[i * 3 + k];
        if (p == null || a == null) continue;
        const u = p - a;
        comp[k][i] = u;
        if (u < lo[k]) lo[k] = u;
        if (u > hi[k]) hi[k] = u;
      }
    }
    return { ...fr, node: { ...fr.node, disp_x: comp[0], disp_y: comp[1], disp_z: comp[2] } };
  });
  const scalars = { ...d.scalars };
  keys.forEach((k, i) => {
    if (Number.isFinite(lo[i])) scalars[k] = { location: "node", min: lo[i], max: hi[i] };
  });
  return { ...d, frames, scalars };
}

/** 1.23 C7 — bir karede skalerin min / maks / ortalaması (aritmetik, eleman ya da düğüm
 *  başına; alan ağırlıksız). Silinen yüz ve null değer katılmaz. */
export function frameStats(
  values: (number | null)[] | undefined,
  ids: Iterable<number>,
  alive?: number[],
): { min: number; max: number; mean: number; n: number } | null {
  if (!values) return null;
  let min = Infinity;
  let max = -Infinity;
  let sum = 0;
  let n = 0;
  for (const i of ids) {
    const v = values[i];
    if (v == null || !Number.isFinite(v) || (alive && alive[i] === 0)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
    sum += v;
    n += 1;
  }
  return n ? { min, max, mean: sum / n, n } : null;
}

/** 1.23 A4 — deformasyon ölçeği seçenekleri (×1 = gerçek). */
export const DEFORM_SCALES = [1, 2, 5, 10] as const;
/** 1.23 A5 — oynatma hızı: 1× = tüm koşu ~3 sn. */
export const PLAY_SPEEDS = [0.25, 0.5, 1, 2] as const;
const PLAY_SECONDS = 3;
const VIDEO_FPS = 30;
/** 1.23 C1: video çözünürlüğü (ekrandaki kutudan bağımsız; 16:9, H.264 çift piksel) */
const VIDEO_SIZE: [number, number] = [1280, 720];

/** 1.23 C1 — video kaydı: tarayıcının desteklediği ilk biçim (MP4 önce; yoksa WebM). */
export const VIDEO_MIMES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"] as const;

export function pickVideoMime(isSupported: ((m: string) => boolean) | undefined): string | null {
  if (!isSupported) return null;
  return VIDEO_MIMES.find((m) => isSupported(m)) ?? null;
}

export function videoFileName(runId: number, scalar: string, mime: string): string {
  const safe = scalar.replace(/[^A-Za-z0-9_-]+/g, "_");
  return `crash_run${runId}_${safe}.${mime.startsWith("video/mp4") ? "mp4" : "webm"}`;
}

/** Video karesi: 3B görüntü + üstte koşu / t / renk skaleri, altta renk ölçeği (ekrandaki ile aynı veri). */
function drawVideoFrame(
  ctx: CanvasRenderingContext2D,
  src: HTMLCanvasElement,
  head: string,
  legend: { lo: string; hi: string } | null,
) {
  const { width: w, height: h } = ctx.canvas;
  ctx.drawImage(src, 0, 0, w, h);
  const fs = Math.max(12, Math.round(h / 32));
  ctx.font = `600 ${fs}px system-ui, sans-serif`;
  ctx.textBaseline = "top";
  const pad = Math.round(fs * 0.6);
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(0, 0, w, fs + pad * 2);
  ctx.fillStyle = "#fff";
  ctx.fillText(head, pad, pad);
  if (legend) {
    const barW = Math.round(w * 0.4);
    const barH = Math.round(fs * 0.6);
    const x = Math.round((w - barW) / 2);
    const y = h - barH - fs - pad * 2;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(x - pad * 6, y - pad, barW + pad * 12, barH + fs + pad * 2.5);
    const g = ctx.createLinearGradient(x, 0, x + barW, 0);
    for (const s of [0, 0.125, 0.375, 0.625, 0.875, 1]) {
      const [r, gg, b] = jet(s);
      g.addColorStop(s, `rgb(${Math.round(r * 255)},${Math.round(gg * 255)},${Math.round(b * 255)})`);
    }
    ctx.fillStyle = g;
    ctx.fillRect(x, y, barW, barH);
    ctx.fillStyle = "#fff";
    ctx.textAlign = "left";
    ctx.fillText(legend.lo, x, y + barH + pad / 2);
    ctx.textAlign = "right";
    ctx.fillText(legend.hi, x + barW, y + barH + pad / 2);
    ctx.textAlign = "left";
  }
}

/** Kareler arası doğrusal ara-değer: f kesirli kare indeksi. Iraksamış koşuda
 * null (NaN/inf) gelen değer `fallback` olur — NaN geometriyi tümden siler. */
export function lerpFrame(
  a: ArrayLike<number | null>,
  b: ArrayLike<number | null>,
  t: number,
  i: number,
  fallback = 0,
): number {
  const x = a[i] ?? b[i] ?? fallback;
  const y = b[i] ?? x;
  return x + (y - x) * t;
}

/** Ölçekli konum: ilk kareye göre yer değiştirme k ile çarpılır. */
export function scaledPos(p0: number, p: number, k: number): number {
  return p0 + (p - p0) * k;
}

/** 1.23 C2 — her yüzün kenarları (düğüm çiftleri) + kaynak yüz; mesh çizgileri için. */
export function faceEdges(faces: number[][]): { pairs: Int32Array; edge_face: Int32Array } {
  const pairs: number[] = [];
  const ef: number[] = [];
  faces.forEach((f, fi) => {
    for (let k = 0; k < f.length; k += 1) {
      pairs.push(f[k], f[(k + 1) % f.length]);
      ef.push(fi);
    }
  });
  return { pairs: Int32Array.from(pairs), edge_face: Int32Array.from(ef) };
}

/** 1.23 C3 — koşu isteğinden rijit duvar (düzlem / silindir); duvarsızda null. */
export interface WallSpec {
  kind: "plane" | "cylinder";
  point: [number, number, number];
  normal: [number, number, number];
  axis: [number, number, number];
  diameter: number | null;
}

export function wallFromRequest(req: Record<string, unknown> | null | undefined): WallSpec | null {
  if (!req || req.use_rigid_wall === false) return null;
  const barrier = req.barrier as { wall?: Record<string, unknown> } | undefined;
  const w = barrier?.wall;
  if (!w || !Array.isArray(w.point) || !Array.isArray(w.normal)) return null;
  return {
    kind: w.kind === "cylinder" ? "cylinder" : "plane",
    point: w.point as [number, number, number],
    normal: w.normal as [number, number, number],
    axis: (Array.isArray(w.axis) ? w.axis : [0, 0, 1]) as [number, number, number],
    diameter: typeof w.diameter_mm === "number" ? w.diameter_mm : null,
  };
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
  const meshRef = useRef<{
    geom: THREE.BufferGeometry;
    edgeGeom: THREE.BufferGeometry;
    lines: THREE.LineSegments;
    wall: THREE.Object3D | null;
    render: () => void;
    /** 1.23 C1: video için sabit çözünürlük; null → kutu boyutuna dön */
    videoSize: (size: [number, number] | null) => void;
  } | null>(null);
  // 1.23 C2/C3: mesh çizgileri, rijit duvar, eleman seçimi
  const [showMesh, setShowMesh] = useState(false);
  const [showWall, setShowWall] = useState(true);
  const [wallSpec, setWallSpec] = useState<WallSpec | null>(null);
  const [pick, setPick] = useState<{ face: number; node: number } | null>(null);
  /** 1.17g — hazır görünümler: model eksenlerine göre kamera konumu */
  const viewRef = useRef<((dir: ViewDir) => void) | null>(null);
  // 1.23 C1: animasyon video kaydı (MediaRecorder; ek bağımlılık yok)
  const videoMime = useMemo(
    () => pickVideoMime(typeof MediaRecorder === "undefined" ? undefined : (m) => MediaRecorder.isTypeSupported(m)),
    [],
  );
  const [recording, setRecording] = useState(false);
  const recRef = useRef<{
    ctx: CanvasRenderingContext2D;
    recorder: MediaRecorder;
    track: CanvasCaptureMediaStreamTrack;
  } | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    setFrame(0);
    fetchCrashAnimation(runId)
      .then((d) => {
        if (!alive) return;
        setData(withDirectional(d));
        const names = Object.keys(d.scalars);
        setScalar(names.find((k) => k.endsWith("Plastic_Strain")) ?? names[0] ?? "disp_mag");
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Animasyon okunamadı."));
    return () => {
      alive = false;
    };
  }, [runId]);

  const tri = useMemo(() => (data ? triangulate(data.faces) : null), [data]);
  const edges = useMemo(() => (data ? faceEdges(data.faces) : null), [data]);

  useEffect(() => {
    let alive = true;
    setWallSpec(null);
    setPick(null);
    fetchCrashRun(runId)
      .then((r) => alive && setWallSpec(wallFromRequest(r.request)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [runId]);

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

    // 1.23 C2: mesh çizgileri (yüz kenarları), konumları her karede güncellenir.
    const edgeGeom = new THREE.BufferGeometry();
    edgeGeom.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array((edges?.pairs.length ?? 0) * 3), 3),
    );
    const lines = new THREE.LineSegments(
      edgeGeom,
      new THREE.LineBasicMaterial({ color: dark ? 0xd8dde2 : 0x1d1f20, transparent: true, opacity: 0.55 }),
    );
    lines.visible = false;
    scene.add(lines);

    // Kamera: ilk kare sınır kutusu
    const p0 = data.frames[0].positions;
    const box = new THREE.Box3();
    // yalnız yüzeylerde kullanılan düğümler (rijit duvar / ana düğüm noktaları hariç)
    for (const v of tri.vtx) box.expandByPoint(new THREE.Vector3(p0[v * 3] ?? 0, p0[v * 3 + 1] ?? 0, p0[v * 3 + 2] ?? 0));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const camera = new THREE.PerspectiveCamera(35, width / height, size / 100, size * 20);
    camera.position.set(center.x + size * 0.6, center.y + size * 0.5, center.z + size * 0.9);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render);

    // 1.23 C3: rijit duvar — düzlem kare (model boyutunun 1.2 katı) ya da silindir.
    let wall: THREE.Object3D | null = null;
    if (wallSpec) {
      const mat = new THREE.MeshBasicMaterial({
        color: 0x4f7ec8,
        transparent: true,
        opacity: 0.25,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const n = new THREE.Vector3(...wallSpec.normal).normalize();
      const pt = new THREE.Vector3(...wallSpec.point);
      if (wallSpec.kind === "cylinder" && wallSpec.diameter) {
        const ax = new THREE.Vector3(...wallSpec.axis).normalize();
        const cyl = new THREE.Mesh(new THREE.CylinderGeometry(wallSpec.diameter / 2, wallSpec.diameter / 2, size * 1.2, 32, 1, true), mat);
        cyl.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), ax);
        cyl.position.copy(pt);
        wall = cyl;
      } else {
        const plane = new THREE.Mesh(new THREE.PlaneGeometry(size * 1.2, size * 1.2), mat);
        plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
        // model merkezinin düzleme izdüşümü
        const c = center.clone().sub(n.clone().multiplyScalar(center.clone().sub(pt).dot(n)));
        plane.position.copy(c);
        wall = plane;
      }
      scene.add(wall);
    }

    // 1.23 C2: elemana tıklayınca değeri (sürükleme döndürme sayılmaz).
    const ray = new THREE.Raycaster();
    let down: [number, number] | null = null;
    const onDown = (e: PointerEvent) => {
      down = [e.clientX, e.clientY];
    };
    const onUp = (e: PointerEvent) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const r = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1),
        camera,
      );
      const hit = ray.intersectObject(mesh)[0];
      if (!hit || hit.faceIndex == null) {
        setPick(null);
        return;
      }
      const t = hit.faceIndex;
      // en yakın köşe düğümü (düğüm skalerleri için)
      const posAttr = geom.getAttribute("position") as THREE.BufferAttribute;
      let best = 0;
      let bestD = Infinity;
      for (let k = 0; k < 3; k += 1) {
        const v = t * 3 + k;
        const d = hit.point.distanceTo(new THREE.Vector3(posAttr.getX(v), posAttr.getY(v), posAttr.getZ(v)));
        if (d < bestD) {
          bestD = d;
          best = v;
        }
      }
      setPick({ face: tri.tri_face[t], node: tri.vtx[best] });
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    const fit = (w: number, h: number, ratio: number, style: boolean) => {
      renderer.setPixelRatio(ratio);
      renderer.setSize(w, h, style);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    };
    let videoLock = false;
    const videoSize = (sz: [number, number] | null) => {
      videoLock = sz != null;
      // video: piksel oranı 1, tuval CSS boyutu değişmez (ekrandaki kutu oynamaz)
      if (sz) fit(sz[0], sz[1], 1, false);
      else fit(holder.clientWidth || width, holder.clientHeight || height, Math.min(window.devicePixelRatio, 2), true);
    };
    meshRef.current = { geom, edgeGeom, lines, wall, render, videoSize };
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
      if (w < 2 || h < 2 || videoLock) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    });
    ro.observe(holder);

    return () => {
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      controls.dispose();
      geom.dispose();
      edgeGeom.dispose();
      (mesh.material as THREE.Material).dispose();
      renderer.dispose();
      holder.removeChild(renderer.domElement);
      meshRef.current = null;
      viewRef.current = null;
    };
  }, [data, tri, edges, wallSpec]);

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
        scaledPos(p0[src * 3] ?? 0, lerpFrame(fa.positions, fb.positions, t, src * 3, p0[src * 3] ?? 0), deform),
        scaledPos(p0[src * 3 + 1] ?? 0, lerpFrame(fa.positions, fb.positions, t, src * 3 + 1, p0[src * 3 + 1] ?? 0), deform),
        scaledPos(p0[src * 3 + 2] ?? 0, lerpFrame(fa.positions, fb.positions, t, src * 3 + 2, p0[src * 3 + 2] ?? 0), deform),
      );
      const val =
        nodeA && nodeB
          ? lerpFrame(nodeA, nodeB, t, node, lo)
          : faceA && faceB
            ? lerpFrame(faceA, faceB, t, face, lo)
            : lo;
      const [r, g, b] = jet((val - lo) / span);
      col.setXYZ(v, r, g, b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    // 1.23 C2: mesh çizgileri — aynı konumlar; silinen yüzün kenarları çöker.
    if (edges) {
      const ep = m.edgeGeom.getAttribute("position") as THREE.BufferAttribute;
      for (let e = 0; e < edges.pairs.length; e += 1) {
        const face = edges.edge_face[Math.floor(e / 2)];
        const alive = !fr.face_alive || fr.face_alive[face] !== 0;
        const node = alive ? edges.pairs[e] : edges.pairs[Math.floor(e / 2) * 2];
        ep.setXYZ(
          e,
          scaledPos(p0[node * 3] ?? 0, lerpFrame(fa.positions, fb.positions, t, node * 3, p0[node * 3] ?? 0), deform),
          scaledPos(p0[node * 3 + 1] ?? 0, lerpFrame(fa.positions, fb.positions, t, node * 3 + 1, p0[node * 3 + 1] ?? 0), deform),
          scaledPos(p0[node * 3 + 2] ?? 0, lerpFrame(fa.positions, fb.positions, t, node * 3 + 2, p0[node * 3 + 2] ?? 0), deform),
        );
      }
      ep.needsUpdate = true;
    }
    // Konumlar her karede değişir; sınır küresi ilk (sıfır) dizilimden kalırsa
    // three.js görüş hacmi kırpması orijin görünmeyen bakışlarda modeli siler
    // (K1 Taylor çubuğu, merkez x = 25: +Y / +Z boş ekran).
    m.geom.computeBoundingSphere();
    m.geom.computeVertexNormals();
    m.render();
    // 1.23 C1: kayıtta kare, render ile aynı görevde 2B tuvale kopyalanır
    // (WebGL çizim tamponu korunmuyor; sonradan okumak boş verir).
    const rec = recRef.current;
    const gl = holderRef.current?.querySelector("canvas");
    if (rec && gl) {
      const meta = data.scalars[scalar];
      drawVideoFrame(
        rec.ctx,
        gl,
        `Koşu #${runId} · t = ${fmt((fa.time ?? 0) + t * ((fb.time ?? 0) - (fa.time ?? 0)))} ms · ${SCALAR_LABELS[scalar] ?? scalar}${deform !== 1 ? ` · ×${deform} çizim` : ""}`,
        meta ? { lo: fmt(meta.min), hi: fmt(meta.max) } : null,
      );
      rec.track.requestFrame();
    }
  }, [data, tri, edges, frameF, scalar, deform, wallSpec, runId, recording]);

  // 1.23 C2/C3: görünürlük düğmeleri
  useEffect(() => {
    const m = meshRef.current;
    if (!m) return;
    m.lines.visible = showMesh;
    if (m.wall) m.wall.visible = showWall;
    m.render();
  }, [showMesh, showWall, data, tri, wallSpec]);

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

  // 1.23 C1: kayıt — 0'dan son kareye bir kez, sabit adımla (VIDEO_FPS kare/s; süre =
  // PLAY_SECONDS / hız). Her adımda kare tuvale yazılıp akışa elle itilir (requestFrame);
  // rAF yerine zamanlayıcı: sekme arka plandayken de kareler eksiksiz biter.
  useEffect(() => {
    if (!recording || !data) return;
    const last = data.frames.length - 1;
    const n = Math.max(2, Math.round((PLAY_SECONDS / speed) * VIDEO_FPS));
    let k = 0;
    let timer = 0;
    const tick = () => {
      k += 1;
      setFrameF(Math.min((k / n) * last, last));
      timer = window.setTimeout(k >= n ? () => recRef.current?.recorder.stop() : tick, 1000 / VIDEO_FPS);
    };
    timer = window.setTimeout(tick, 1000 / VIDEO_FPS);
    return () => clearTimeout(timer);
  }, [recording, data, speed]);

  const startRecording = () => {
    const gl = holderRef.current?.querySelector("canvas");
    if (!videoMime || !gl || !data || recording || !meshRef.current) return;
    meshRef.current.videoSize(VIDEO_SIZE);
    const out = document.createElement("canvas");
    [out.width, out.height] = VIDEO_SIZE;
    const ctx = out.getContext("2d");
    if (!ctx) return;
    const stream = out.captureStream(0);
    const track = stream.getVideoTracks()[0] as CanvasCaptureMediaStreamTrack;
    const recorder = new MediaRecorder(stream, {
      mimeType: videoMime,
      videoBitsPerSecond: 8_000_000,
    });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    recorder.onstop = () => {
      recRef.current = null;
      meshRef.current?.videoSize(null);
      setRecording(false);
      if (chunks.length === 0) {
        setVideoError("Video kaydedilemedi (tarayıcı kare vermedi).");
        return;
      }
      const url = URL.createObjectURL(new Blob(chunks, { type: videoMime }));
      const a = document.createElement("a");
      a.href = url;
      a.download = videoFileName(runId, scalar, videoMime);
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    recRef.current = { ctx, recorder, track };
    setVideoError(null);
    setPlaying(false);
    recorder.start();
    setFrameF(0);
    setRecording(true); // çizim efekti `recording` ile de koşar → ilk kare (t = 0) yazılır
  };

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
      const a0 = [a[i] ?? 0, a[i + 1] ?? 0, a[i + 2] ?? 0];
      // ıraksamış karede null konum yer değiştirmeye katılmaz
      if (b[i] != null && b[i + 1] != null && b[i + 2] != null) {
        maxU = Math.max(maxU, Math.hypot(b[i]! - a0[0], b[i + 1]! - a0[1], b[i + 2]! - a0[2]));
      }
      for (let k = 0; k < 3; k += 1) {
        lo[k] = Math.min(lo[k], a0[k]);
        hi[k] = Math.max(hi[k], a0[k]);
      }
    }
    const size = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1;
    return { maxU, pct: (100 * maxU) / size };
  }, [data, tri]);

  const meta = data?.scalars[scalar];
  const fr = data?.frames[frame];
  // 1.23 C7: karedeki min / maks / ort — yüz skalerinde tüm yüzler, düğümde yüzeylerdeki düğümler
  const surfNodes = useMemo(() => (tri ? [...new Set(tri.vtx)] : []), [tri]);
  const stats = useMemo(() => {
    if (!meta || !fr || !data) return null;
    return meta.location === "face"
      ? frameStats(fr.face?.[scalar], data.faces.keys(), fr.face_alive)
      : frameStats(fr.node?.[scalar], surfNodes);
  }, [meta, fr, data, scalar, surfNodes]);
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
            {fr.nonfinite ? ` · ${fr.nonfinite} geçersiz değer (ıraksama)` : ""}
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
              disabled={recording}
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
          <div className="crash-anim-export">
            <button
              type="button"
              className="doe-btn doe-btn-ghost"
              data-testid="crash-anim-video"
              disabled={!videoMime || recording}
              onClick={startRecording}
              title={
                videoMime
                  ? "Baştan sona bir kez oynatıp video dosyası indirir (görünüm, renk, ölçek, hız ekrandaki gibi)"
                  : "Bu tarayıcı video kaydını desteklemiyor"
              }
            >
              {recording ? "● Kaydediliyor…" : `Video indir (${videoMime?.startsWith("video/mp4") ? "MP4" : "WebM"})`}
            </button>
            {videoError && <span className="crash-run-failed">{videoError}</span>}
          </div>
          <div className="crash-var-chips" role="group" aria-label="Görünürlük">
            <button
              type="button"
              className={showMesh ? "crash-var-chip active" : "crash-var-chip"}
              aria-pressed={showMesh}
              onClick={() => setShowMesh((v) => !v)}
            >
              Mesh
            </button>
            {wallSpec && (
              <button
                type="button"
                className={showWall ? "crash-var-chip active" : "crash-var-chip"}
                aria-pressed={showWall}
                onClick={() => setShowWall((v) => !v)}
              >
                Rijit duvar
              </button>
            )}
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
          {pick && data && (
            <p className="crash-behavior-hint" data-testid="crash-anim-pick">
              {(() => {
                const f = data.frames[frame];
                const m = data.scalars[scalar];
                const v = m?.location === "face" ? f.face?.[scalar]?.[pick.face] : f.node?.[scalar]?.[pick.node];
                return `Eleman (yüz) #${pick.face} · parça #${data.face_part[pick.face] ?? "—"} · ${
                  SCALAR_LABELS[scalar] ?? scalar
                } = ${v == null ? "—" : fmt(v)}${m?.location === "node" ? " (en yakın düğüm)" : ""} · t = ${fmt(f.time ?? 0)} ms`;
              })()}
            </p>
          )}
          {meta && (
            <div className="crash-anim-legend" aria-label="Renk ölçeği">
              <span>{fmt(meta.min)}</span>
              <span className="crash-anim-bar" />
              <span>{fmt(meta.max)}</span>
            </div>
          )}
          {stats && (
            <p className="crash-behavior-hint" data-testid="crash-anim-stats">
              {`Bu karede (t = ${fmt(fr?.time ?? 0)} ms) · min ${fmt(stats.min)} · maks ${fmt(stats.max)} · ort ${fmt(
                stats.mean,
              )} · ${stats.n} ${meta?.location === "face" ? "eleman" : "düğüm"} (aritmetik ortalama${
                meta?.location === "face" ? ", silinenler hariç" : ""
              })`}
            </p>
          )}
        </>
      )}
    </figure>
  );
}
