import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ModalModePreview } from "../api/geometry";

export interface ModalPanel {
  /** Hücre başlığı — ör. "Mod 1" ya da "A · Mod 1". */
  label: string;
  /** Etiketin ikinci satırı — genelde frekans. */
  sublabel?: string;
  mode: ModalModePreview;
}

interface ModalModeGridProps {
  nodes: number[][];
  faces: number[];
  panels: ModalPanel[];
  /** Sütun sayısı. Verilmezse mod sayısına göre kareye yakın seçilir. */
  columns?: number;
  focusedIndex: number | null;
  onFocusChange: (index: number | null) => void;
  background: "white" | "black";
}

/** GeometryViewer'daki jetColor() ile BİREBİR aynı formül. */
function jetColor(t: number): THREE.Color {
  const x = Math.min(1, Math.max(0, t));
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1)));
  return new THREE.Color(r, g, b);
}

/** Mod etiketini canvas'a çizip Sprite dokusu olarak döndürür — etiket
 * 3B'de hücresiyle birlikte hareket etsin diye. HTML overlay kullanmak,
 * kamera her döndüğünde ekran koordinatı yeniden hesaplamayı gerektirirdi. */
function makeLabelSprite(text: string, sub: string, dark: boolean): THREE.Sprite {
  const cvs = document.createElement("canvas");
  cvs.width = 512;
  cvs.height = 128;
  const ctx = cvs.getContext("2d")!;
  ctx.clearRect(0, 0, cvs.width, cvs.height);
  ctx.textAlign = "center";
  ctx.fillStyle = dark ? "#f2f4f0" : "#14181a";
  ctx.font = "bold 44px system-ui, sans-serif";
  ctx.fillText(text, 256, 48);
  if (sub) {
    ctx.font = "34px system-ui, sans-serif";
    ctx.fillStyle = dark ? "#9fd6dc" : "#0d7f8a";
    ctx.fillText(sub, 256, 96);
  }
  const tex = new THREE.CanvasTexture(cvs);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({
    map: tex,
    transparent: true,
    depthTest: false,
  });
  return new THREE.Sprite(mat);
}

interface PanelRuntime {
  group: THREE.Group;
  /** Deforme EDİLMEMİŞ, merkezlenmiş üçgen-çorbası konumları. */
  base: Float32Array;
  /** Her üçgen köşesi için yer değiştirme vektörü × ölçek. */
  delta: Float32Array;
  posAttr: THREE.BufferAttribute;
  geom: THREE.BufferGeometry;
}

/**
 * N doğal modu aynı anda gösterir.
 *
 * TEK CANVAS: her mod için ayrı <canvas> açmak tarayıcının eşzamanlı WebGL
 * context sınırına (yaygın olarak 8–16) takılır; 2 analiz karşılaştırmasındaki
 * 12 panel bunu aşar ve en eski context'ler sessizce kaybolur. Bu yüzden tek
 * sahnede N kopya bir ızgaraya diziliyor.
 *
 * HÜCRE BOYUTU: ızgara adımı DEFORME OLMUŞ sınırlara göre hesaplanır.
 * Deforme edilmemiş boyuta göre hesaplamak, genliğin hücreden taşmasına ve
 * komşu modların üst üste binmesine yol açar — ilk sürümde tam olarak bu
 * oldu: 500mm'lik kirişte hücre yüksekliği 80mm iken genlik ±90mm idi.
 *
 * GENLİK: mod şekilleri özvektördür, mutlak genlikleri fiziksel anlam
 * taşımaz (çözücü keyfi normalize eder). Her panel KENDİ maksimumuna
 * normalize edilir — karşılaştırılan şekil ve frekanstır, büyüklük değil.
 */
export default function ModalModeGrid({
  nodes,
  faces,
  panels,
  columns,
  focusedIndex,
  onFocusChange,
  background,
}: ModalModeGridProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const runtimeRef = useRef<PanelRuntime[]>([]);
  const onFocusRef = useRef(onFocusChange);
  onFocusRef.current = onFocusChange;

  const [animating, setAnimating] = useState(true);
  const [amplitude, setAmplitude] = useState(0.06);
  const animatingRef = useRef(animating);
  animatingRef.current = animating;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || nodes.length === 0 || panels.length === 0) return;
    const dark = background === "black";

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(dark ? "#0d0f0e" : "#eef0ec");
    sceneRef.current = scene;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 500000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.5);
    dirLight.position.set(1, 1.5, 1);
    scene.add(dirLight);

    const bbox = new THREE.Box3();
    for (const n of nodes) bbox.expandByPoint(new THREE.Vector3(n[0], n[1], n[2]));
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);
    const modelSpan = Math.max(size.x, size.y, size.z) || 1;
    const maxAmp = amplitude * modelSpan;

    // Hücre adımı deforme sınırları kapsar: genlik her yöne ±maxAmp
    // taşabilir, üstüne nefes payı.
    const cellW = (size.x + 2 * maxAmp) * 1.2;
    const cellH = (Math.max(size.y, size.z) + 2 * maxAmp) * 1.35;

    const cols = Math.max(1, columns ?? Math.ceil(Math.sqrt(panels.length)));
    const rows = Math.ceil(panels.length / cols);
    const triCount = Math.floor(faces.length / 3);
    const runtimes: PanelRuntime[] = [];

    panels.forEach((panel, pi) => {
      const g = new THREE.Group();
      const col = pi % cols;
      const row = Math.floor(pi / cols);
      g.position.set(
        (col - (cols - 1) / 2) * cellW,
        -(row - (rows - 1) / 2) * cellH,
        0,
      );

      const vec = panel.mode.displacement_vectors;
      const mag = panel.mode.displacement_magnitude;
      const maxU = panel.mode.max_displacement || 1;
      const scale = maxAmp / (maxU > 1e-30 ? maxU : 1);
      const maxMag = mag && mag.length ? Math.max(...mag) : 0;
      const safeMax = maxMag > 1e-30 ? maxMag : 1;

      const vCount = triCount * 3;
      const base = new Float32Array(vCount * 3);
      const delta = new Float32Array(vCount * 3);
      const colors = new Float32Array(vCount * 3);

      for (let t = 0; t < triCount; t++) {
        for (let v = 0; v < 3; v++) {
          const ni = faces[t * 3 + v];
          const dst = (t * 3 + v) * 3;
          base[dst] = nodes[ni][0] - center.x;
          base[dst + 1] = nodes[ni][1] - center.y;
          base[dst + 2] = nodes[ni][2] - center.z;
          const d = vec?.[ni] ?? [0, 0, 0];
          delta[dst] = d[0] * scale;
          delta[dst + 1] = d[1] * scale;
          delta[dst + 2] = d[2] * scale;
          const c = jetColor((mag?.[ni] ?? 0) / safeMax);
          colors[dst] = c.r;
          colors[dst + 1] = c.g;
          colors[dst + 2] = c.b;
        }
      }

      const pos = new Float32Array(base.length);
      for (let i = 0; i < base.length; i++) pos[i] = base[i] + delta[i];

      const geom = new THREE.BufferGeometry();
      const posAttr = new THREE.BufferAttribute(pos, 3);
      posAttr.setUsage(THREE.DynamicDrawUsage);
      geom.setAttribute("position", posAttr);
      geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      geom.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        metalness: 0.05,
        roughness: 0.6,
        side: THREE.DoubleSide,
        flatShading: true,
      });
      g.add(new THREE.Mesh(geom, mat));

      // Hücre çerçevesi — modlar görsel olarak ayrışsın.
      const frame = new THREE.LineSegments(
        new THREE.EdgesGeometry(
          new THREE.PlaneGeometry(cellW * 0.97, cellH * 0.94),
        ),
        new THREE.LineBasicMaterial({ color: dark ? "#3a4441" : "#c9cfc6" }),
      );
      g.add(frame);

      const sprite = makeLabelSprite(panel.label, panel.sublabel ?? "", dark);
      sprite.position.set(0, cellH * 0.4, 0);
      sprite.scale.set(cellW * 0.42, cellW * 0.105, 1);
      g.add(sprite);

      g.userData.panelIndex = pi;
      scene.add(g);
      runtimes.push({ group: g, base, delta, posAttr, geom });
    });
    runtimeRef.current = runtimes;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controlsRef.current = controls;

    function fitCamera(index: number | null) {
      const cam = cameraRef.current;
      const ctl = controlsRef.current;
      if (!cam || !ctl) return;
      if (index !== null && runtimes[index]) {
        const t = runtimes[index].group.position;
        ctl.target.set(t.x, t.y, t.z);
        const d = Math.max(cellW, cellH) * 1.25;
        cam.position.set(t.x, t.y + d * 0.35, t.z + d);
      } else {
        ctl.target.set(0, 0, 0);
        const span = Math.max(cols * cellW, rows * cellH);
        cam.position.set(0, span * 0.18, span * 1.05);
      }
      cam.updateProjectionMatrix();
      ctl.update();
    }
    fitCamera(focusedIndex);

    const raycaster = new THREE.Raycaster();
    function handleDoubleClick(ev: MouseEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(
        runtimes.map((r) => r.group),
        true,
      );
      if (hits.length === 0) {
        onFocusRef.current(null);
        return;
      }
      let obj: THREE.Object3D | null = hits[0].object;
      while (obj && obj.userData.panelIndex === undefined) obj = obj.parent;
      const idx = obj?.userData.panelIndex;
      onFocusRef.current(typeof idx === "number" ? idx : null);
    }
    renderer.domElement.addEventListener("dblclick", handleDoubleClick);

    let raf = 0;
    const t0 = performance.now();
    const animate = () => {
      raf = requestAnimationFrame(animate);
      if (animatingRef.current) {
        // Tüm paneller AYNI fazda salınır: gerçek frekansları kullanmak
        // yüksek modları gözle takip edilemez hale getirirdi (mod 6,
        // mod 1'den 30 kat hızlı). Amaç şekli okutmak.
        const s = Math.sin(((performance.now() - t0) / 1000) * 2 * Math.PI * 0.6);
        for (const rt of runtimes) {
          const arr = rt.posAttr.array as Float32Array;
          for (let i = 0; i < arr.length; i++) {
            arr[i] = rt.base[i] + rt.delta[i] * s;
          }
          rt.posAttr.needsUpdate = true;
          rt.geom.computeVertexNormals();
        }
      }
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      const w = container.clientWidth || 800;
      const h = container.clientHeight || 600;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("dblclick", handleDoubleClick);
      controls.dispose();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.geometry) m.geometry.dispose();
        const mm = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mm)) mm.forEach((x) => x.dispose());
        else mm?.dispose();
      });
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      rendererRef.current = null;
      runtimeRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, faces, panels, columns, background, amplitude]);

  // Odak değişimi sahneyi yeniden kurmaz, yalnız kamerayı taşır.
  useEffect(() => {
    const cam = cameraRef.current;
    const ctl = controlsRef.current;
    const rts = runtimeRef.current;
    if (!cam || !ctl || rts.length === 0) return;
    if (focusedIndex !== null && rts[focusedIndex]) {
      const t = rts[focusedIndex].group.position;
      const box = new THREE.Box3().setFromObject(rts[focusedIndex].group);
      const s = new THREE.Vector3();
      box.getSize(s);
      const d = (Math.max(s.x, s.y, s.z) || 1) * 1.3;
      ctl.target.set(t.x, t.y, t.z);
      cam.position.set(t.x, t.y + d * 0.3, t.z + d);
    } else {
      const all = new THREE.Box3();
      for (const r of rts) all.expandByObject(r.group);
      const s = new THREE.Vector3();
      all.getSize(s);
      const span = Math.max(s.x, s.y) || 1;
      ctl.target.set(0, 0, 0);
      cam.position.set(0, span * 0.18, span * 1.05);
    }
    cam.updateProjectionMatrix();
    ctl.update();
  }, [focusedIndex]);

  const jetStops = Array.from({ length: 11 }, (_, i) => {
    const c = jetColor(i / 10);
    return `rgb(${Math.round(c.r * 255)},${Math.round(c.g * 255)},${Math.round(
      c.b * 255,
    )}) ${i * 10}%`;
  }).join(", ");

  return (
    <div className="modal-mode-grid">
      <div className="modal-mode-grid-canvas" ref={containerRef}>
        <div className="modal-mode-colorbar">
          <span className="modal-mode-colorbar-title">|u| / |u|max</span>
          <div className="modal-mode-colorbar-body">
            <div
              className="modal-mode-colorbar-scale"
              style={{ background: `linear-gradient(to top, ${jetStops})` }}
            />
            <div className="modal-mode-colorbar-ticks">
              <span>1.00</span>
              <span>0.75</span>
              <span>0.50</span>
              <span>0.25</span>
              <span>0.00</span>
            </div>
          </div>
          <span className="modal-mode-colorbar-note">mod başına normalize</span>
        </div>
      </div>

      <div className="modal-mode-grid-legend">
        <button
          type="button"
          className={animating ? "active" : undefined}
          onClick={() => setAnimating((p) => !p)}
        >
          {animating ? "⏸ Durdur" : "▶ Animasyon"}
        </button>
        <label className="modal-mode-amp">
          Genlik
          <input
            type="range"
            min={0.01}
            max={0.15}
            step={0.01}
            value={amplitude}
            onChange={(e) => setAmplitude(parseFloat(e.target.value))}
          />
          <span>{(amplitude * 100).toFixed(0)}%</span>
        </label>
        <span className="modal-mode-grid-sep" />
        {panels.map((p, i) => (
          <button
            key={`panel-${i}`}
            type="button"
            className={focusedIndex === i ? "active" : undefined}
            onClick={() => onFocusChange(focusedIndex === i ? null : i)}
            title={`${p.label} ${p.sublabel ?? ""} — tek başına göster`}
          >
            {p.label}
            {p.sublabel ? ` · ${p.sublabel}` : ""}
          </button>
        ))}
        {focusedIndex !== null && (
          <button type="button" onClick={() => onFocusChange(null)}>
            ← Tüm modlar
          </button>
        )}
      </div>
    </div>
  );
}
