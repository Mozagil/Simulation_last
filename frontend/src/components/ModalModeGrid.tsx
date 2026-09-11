import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ModalModePreview } from "../api/geometry";

export interface ModalPanel {
  /** Bölme başlığı — ör. "Mod 1" ya da "A · Mod 1". */
  label: string;
  /** Başlığın sağındaki ikincil bilgi — genelde frekans. */
  sublabel?: string;
  mode: ModalModePreview;
}

interface ModalModeGridProps {
  nodes: number[][];
  faces: number[];
  panels: ModalPanel[];
  /** Sütun sayısı. Verilmezse mod sayısına göre seçilir. */
  columns?: number;
  /** Tek bölmeye odak; null = tüm ızgara. */
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

interface PaneRuntime {
  el: HTMLDivElement;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Deforme EDİLMEMİŞ, merkezlenmiş üçgen-çorbası konumları. */
  base: Float32Array;
  /** Her köşe için yer değiştirme vektörü × ölçek. */
  delta: Float32Array;
  posAttr: THREE.BufferAttribute;
  geom: THREE.BufferGeometry;
}

/**
 * N doğal modu DÖŞENMİŞ BÖLMELERDE gösterir.
 *
 * Her mod kendi çerçevesi, kendi başlığı ve KENDİ KAMERASI olan ayrı bir
 * bölmede durur — klasik CAE post-processor döşeme düzeni gibi. Bir bölmeyi
 * döndürmek diğerlerini etkilemez; "Kameraları eşle" açıkken hepsi birlikte
 * döner.
 *
 * TEK WebGL CONTEXT: her bölme için ayrı <canvas> açmak tarayıcının
 * eşzamanlı context sınırına (yaygın olarak 8–16) takılır ve iki analizin
 * karşılaştırmasındaki 12 bölme bunu aşar — en eski context'ler sessizce
 * kaybolur, bölmeler siyah kalır. Bunun yerine TEK renderer, `scissor test`
 * ile her bölmenin DOM dikdörtgenine ayrı ayrı çizer. Bölme başına bağımsız
 * sahne ve kamera vardır; paylaşılan tek şey context'tir.
 *
 * ÖNCEKİ TASARIM (tek sahnede yan yana kopyalar) BIRAKILDI: hücre adımını
 * elle hesaplamak gerekiyordu, deformasyon genliği hücreyi aşınca modlar
 * üst üste biniyordu ve bölme başına ayrı kamera vermek mümkün değildi.
 *
 * GENLİK: mod şekilleri özvektördür, mutlak genlikleri fiziksel anlam
 * taşımaz (çözücü keyfi normalize eder). Her bölme KENDİ maksimumuna
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
  const canvasHolderRef = useRef<HTMLDivElement | null>(null);
  const paneElsRef = useRef<(HTMLDivElement | null)[]>([]);
  const runtimeRef = useRef<PaneRuntime[]>([]);

  const [animating, setAnimating] = useState(true);
  const [amplitude, setAmplitude] = useState(0.08);
  const [syncCameras, setSyncCameras] = useState(true);
  const animatingRef = useRef(animating);
  animatingRef.current = animating;
  const syncRef = useRef(syncCameras);
  syncRef.current = syncCameras;

  const visible = focusedIndex === null ? panels : [panels[focusedIndex]];
  const cols =
    focusedIndex !== null
      ? 1
      : Math.max(
          1,
          columns ??
            (panels.length <= 3 ? panels.length : Math.ceil(panels.length / 2)),
        );

  useEffect(() => {
    const holder = canvasHolderRef.current;
    if (!holder || nodes.length === 0 || visible.length === 0) return;
    const dark = background === "black";

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setScissorTest(true);
    renderer.domElement.style.position = "absolute";
    renderer.domElement.style.inset = "0";
    // Fare olayları bölme div'lerine ulaşsın: OrbitControls onlara bağlı.
    renderer.domElement.style.pointerEvents = "none";
    holder.appendChild(renderer.domElement);

    const bbox = new THREE.Box3();
    for (const n of nodes) bbox.expandByPoint(new THREE.Vector3(n[0], n[1], n[2]));
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);
    const modelSpan = Math.max(size.x, size.y, size.z) || 1;
    const maxAmp = amplitude * modelSpan;
    const triCount = Math.floor(faces.length / 3);

    const runtimes: PaneRuntime[] = [];

    visible.forEach((panel, pi) => {
      const el = paneElsRef.current[pi];
      if (!el) return;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(dark ? "#101312" : "#f4f6f2");
      scene.add(new THREE.AmbientLight(0xffffff, 0.85));
      const dl = new THREE.DirectionalLight(0xffffff, 0.5);
      dl.position.set(1, 1.5, 1);
      scene.add(dl);

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
      scene.add(
        new THREE.Mesh(
          geom,
          new THREE.MeshStandardMaterial({
            vertexColors: true,
            metalness: 0.05,
            roughness: 0.6,
            side: THREE.DoubleSide,
            flatShading: true,
          }),
        ),
      );

      const camera = new THREE.PerspectiveCamera(
        45,
        1,
        modelSpan / 500,
        modelSpan * 60,
      );
      const d = modelSpan * 1.5;
      camera.position.set(d * 0.35, d * 0.45, d);
      camera.lookAt(0, 0, 0);

      const controls = new OrbitControls(camera, el);
      controls.enableDamping = true;
      controls.target.set(0, 0, 0);
      controls.update();

      runtimes.push({ el, scene, camera, controls, base, delta, posAttr, geom });
    });
    runtimeRef.current = runtimes;

    // Kamera eşleme: bir bölme oynayınca diğerlerine kopyala.
    const detach: (() => void)[] = [];
    runtimes.forEach((rt, i) => {
      const onChange = () => {
        if (!syncRef.current) return;
        for (let j = 0; j < runtimes.length; j++) {
          if (j === i) continue;
          const o = runtimes[j];
          o.camera.position.copy(rt.camera.position);
          o.camera.quaternion.copy(rt.camera.quaternion);
          o.controls.target.copy(rt.controls.target);
        }
      };
      rt.controls.addEventListener("change", onChange);
      detach.push(() => rt.controls.removeEventListener("change", onChange));
    });

    let raf = 0;
    const t0 = performance.now();
    const render = () => {
      raf = requestAnimationFrame(render);
      const holderRect = holder.getBoundingClientRect();
      if (holderRect.width < 1 || holderRect.height < 1) return;
      renderer.setSize(holderRect.width, holderRect.height, false);

      // Salınım: tüm bölmeler AYNI fazda. Gerçek frekansları kullanmak
      // yüksek modları gözle takip edilemez hale getirirdi (mod 6, mod 1'den
      // ~30 kat hızlı); amaç şekli okutmak.
      const s = animatingRef.current
        ? Math.sin(((performance.now() - t0) / 1000) * 2 * Math.PI * 0.55)
        : 1;

      for (const rt of runtimes) {
        if (animatingRef.current) {
          const arr = rt.posAttr.array as Float32Array;
          for (let i = 0; i < arr.length; i++) {
            arr[i] = rt.base[i] + rt.delta[i] * s;
          }
          rt.posAttr.needsUpdate = true;
          rt.geom.computeVertexNormals();
        }
        rt.controls.update();

        const r = rt.el.getBoundingClientRect();
        const left = r.left - holderRect.left;
        // WebGL viewport'unun kökeni SOL-ALT; DOM'unki sol-üst.
        const bottom = holderRect.bottom - r.bottom;
        const w = Math.max(1, r.width);
        const h = Math.max(1, r.height);
        renderer.setViewport(left, bottom, w, h);
        renderer.setScissor(left, bottom, w, h);
        rt.camera.aspect = w / h;
        rt.camera.updateProjectionMatrix();
        renderer.render(rt.scene, rt.camera);
      }
    };
    render();

    return () => {
      cancelAnimationFrame(raf);
      for (const fn of detach) fn();
      for (const rt of runtimes) {
        rt.controls.dispose();
        rt.scene.traverse((o) => {
          const m = o as THREE.Mesh;
          if (m.geometry) m.geometry.dispose();
          const mm = m.material as THREE.Material | THREE.Material[] | undefined;
          if (Array.isArray(mm)) mm.forEach((x) => x.dispose());
          else mm?.dispose();
        });
      }
      renderer.dispose();
      if (renderer.domElement.parentNode === holder) {
        holder.removeChild(renderer.domElement);
      }
      runtimeRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, faces, panels, columns, background, amplitude, focusedIndex]);

  const jetStops = Array.from({ length: 11 }, (_, i) => {
    const c = jetColor(i / 10);
    return `rgb(${Math.round(c.r * 255)},${Math.round(c.g * 255)},${Math.round(
      c.b * 255,
    )}) ${i * 10}%`;
  }).join(", ");

  return (
    <div className="modal-mode-grid">
      <div className="modal-mode-grid-toolbar">
        <button
          type="button"
          className={animating ? "active" : undefined}
          onClick={() => setAnimating((p) => !p)}
        >
          {animating ? "⏸ Durdur" : "▶ Animasyon"}
        </button>
        <button
          type="button"
          className={syncCameras ? "active" : undefined}
          onClick={() => setSyncCameras((p) => !p)}
          title="Bir bölmeyi döndürünce hepsi birlikte dönsün"
        >
          Kameraları eşle
        </button>
        <label className="modal-mode-amp">
          Genlik
          <input
            type="range"
            min={0.01}
            max={0.2}
            step={0.01}
            value={amplitude}
            onChange={(e) => setAmplitude(parseFloat(e.target.value))}
          />
          <span>{(amplitude * 100).toFixed(0)}%</span>
        </label>
        {focusedIndex !== null && (
          <button type="button" onClick={() => onFocusChange(null)}>
            ← Tüm modlar
          </button>
        )}
        <span className="modal-mode-grid-spacer" />
        <div className="modal-mode-colorbar-inline">
          <span>|u| / |u|max</span>
          <div
            className="modal-mode-colorbar-strip"
            style={{ background: `linear-gradient(to right, ${jetStops})` }}
          />
          <span>mod başına normalize</span>
        </div>
      </div>

      <div
        className="modal-mode-grid-panes"
        ref={canvasHolderRef}
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {visible.map((p, i) => (
          <div className="modal-mode-pane" key={`pane-${focusedIndex ?? "all"}-${i}`}>
            <div className="modal-mode-pane-title">
              <span>{p.label}</span>
              {p.sublabel && (
                <span className="modal-mode-pane-freq">{p.sublabel}</span>
              )}
              <button
                type="button"
                className="modal-mode-pane-zoom"
                title={
                  focusedIndex === null ? "Tek başına göster" : "Tüm modlara dön"
                }
                onClick={() => onFocusChange(focusedIndex === null ? i : null)}
              >
                {focusedIndex === null ? "⤢" : "⤡"}
              </button>
            </div>
            <div
              className="modal-mode-pane-body"
              ref={(el) => {
                paneElsRef.current[i] = el;
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
