import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ModalModePreview } from "../api/geometry";

/** Bir grid hücresi: tek bir doğal mod ve onun ait olduğu analiz. */
export interface ModalPanel {
  /** Hücre başlığı — ör. "Mod 1 · 33.27 Hz" ya da "A · Mod 1 · 33.27 Hz". */
  label: string;
  mode: ModalModePreview;
}

interface ModalModeGridProps {
  /** Deforme edilecek taban mesh — sonuç önizlemesinin düğüm koordinatları. */
  nodes: number[][];
  /** Üçgen indeksleri [i0,i1,i2, ...]. Boşsa nokta bulutu çizilir. */
  faces: number[];
  panels: ModalPanel[];
  /** Sütun sayısı. Verilmezse kareye yakın bir düzen seçilir; iki analizi
   * karşılaştırırken satır başına mod sayısını vermek için kullanılır. */
  columns?: number;
  /** Tek moda odaklanma: null = tüm grid. */
  focusedIndex: number | null;
  onFocusChange: (index: number | null) => void;
  background: "white" | "black";
  /** Mod şekli büyütme oranı — model boyutunun yüzdesi (0.05 = %5). */
  amplitude?: number;
}

/** GeometryViewer'daki jetColor() ile BİREBİR aynı formül — iki görünüm
 * arasında renk skalası tutarlı olmalı. */
function jetColor(t: number): THREE.Color {
  const x = Math.min(1, Math.max(0, t));
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1)));
  return new THREE.Color(r, g, b);
}

/**
 * N doğal modu AYNI ANDA gösterir.
 *
 * TASARIM KARARI — neden tek canvas: her mod için ayrı bir <canvas>
 * açmak en doğal çözüm gibi görünür ama tarayıcılar eşzamanlı WebGL
 * context sayısını sınırlar (yaygın olarak 8–16). 6 mod bunu zorlar,
 * iki analizi karşılaştırırken gereken 12 panel ise sınırı büyük
 * olasılıkla aşar ve en eski context'ler sessizce kaybolur (siyah
 * kutular). Bu yüzden TEK bir sahnede N model kopyası bir ızgaraya
 * diziliyor: context sayısı her zaman 1, panel sayısı serbestçe artar.
 *
 * Mod şekilleri özvektördür — mutlak genlikleri fiziksel bir anlam
 * taşımaz (çözücü keyfi normalize eder). Bu yüzden her panel KENDİ
 * maksimumuna göre normalize edilir; paneller arası genlik
 * karşılaştırması yapılmamalıdır, karşılaştırılacak olan şekil ve
 * frekanstır.
 */
export default function ModalModeGrid({
  nodes,
  faces,
  panels,
  columns,
  focusedIndex,
  onFocusChange,
  background,
  amplitude = 0.18,
}: ModalModeGridProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const panelGroupsRef = useRef<THREE.Group[]>([]);
  const onFocusRef = useRef(onFocusChange);
  onFocusRef.current = onFocusChange;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || nodes.length === 0 || panels.length === 0) return;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const dir = new THREE.DirectionalLight(0xffffff, 0.55);
    dir.position.set(1, 1.5, 1);
    scene.add(dir);

    // --- Taban geometri ölçüleri ---
    const bbox = new THREE.Box3();
    for (const n of nodes) bbox.expandByPoint(new THREE.Vector3(n[0], n[1], n[2]));
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);
    const modelSpan = Math.max(size.x, size.y, size.z) || 1;

    const cols = Math.max(1, columns ?? Math.ceil(Math.sqrt(panels.length)));
    const rows = Math.ceil(panels.length / cols);
    // Hücreler arası boşluk: modelin en geniş ekseninin %25'i kadar pay.
    const cellW = size.x * 1.25 || modelSpan;
    const cellH = Math.max(size.y, size.z) * 1.6 || modelSpan;

    const triCount = Math.floor(faces.length / 3);
    const panelGroups: THREE.Group[] = [];

    panels.forEach((panel, pi) => {
      const g = new THREE.Group();
      const col = pi % cols;
      const row = Math.floor(pi / cols);
      // Izgarada konumla; merkeze göre kaydır.
      g.position.set(
        (col - (cols - 1) / 2) * cellW,
        -(row - (rows - 1) / 2) * cellH,
        0,
      );

      const vec = panel.mode.displacement_vectors;
      const mag = panel.mode.displacement_magnitude;
      const maxU = panel.mode.max_displacement || 1;
      // Özvektör genliği keyfidir — her panel kendi maksimumuna normalize
      // edilir, böylece hepsi görsel olarak aynı ölçekte deforme görünür.
      const scale = (amplitude * modelSpan) / (maxU > 1e-30 ? maxU : 1);

      const deformed = new Float32Array(nodes.length * 3);
      for (let i = 0; i < nodes.length; i++) {
        const d = vec?.[i] ?? [0, 0, 0];
        deformed[i * 3] = nodes[i][0] - center.x + d[0] * scale;
        deformed[i * 3 + 1] = nodes[i][1] - center.y + d[1] * scale;
        deformed[i * 3 + 2] = nodes[i][2] - center.z + d[2] * scale;
      }

      const maxMag = mag && mag.length ? Math.max(...mag) : 0;
      const safeMax = maxMag > 1e-30 ? maxMag : 1;

      if (triCount > 0) {
        const pos = new Float32Array(triCount * 9);
        const col3 = new Float32Array(triCount * 9);
        for (let t = 0; t < triCount; t++) {
          for (let v = 0; v < 3; v++) {
            const ni = faces[t * 3 + v];
            const dst = (t * 3 + v) * 3;
            pos[dst] = deformed[ni * 3];
            pos[dst + 1] = deformed[ni * 3 + 1];
            pos[dst + 2] = deformed[ni * 3 + 2];
            const c = jetColor((mag?.[ni] ?? 0) / safeMax);
            col3[dst] = c.r;
            col3[dst + 1] = c.g;
            col3[dst + 2] = c.b;
          }
        }
        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        geom.setAttribute("color", new THREE.BufferAttribute(col3, 3));
        geom.computeVertexNormals();
        const mat = new THREE.MeshStandardMaterial({
          vertexColors: true,
          metalness: 0.05,
          roughness: 0.6,
          side: THREE.DoubleSide,
          flatShading: true,
        });
        g.add(new THREE.Mesh(geom, mat));
      } else {
        // Yüzey üçgeni yoksa (ör. önizleme yalnız düğüm taşıyorsa) nokta
        // bulutuna düş — hiç çizmemektense şekil yine okunur.
        const pGeom = new THREE.BufferGeometry();
        pGeom.setAttribute("position", new THREE.BufferAttribute(deformed, 3));
        const pCol = new Float32Array(nodes.length * 3);
        for (let i = 0; i < nodes.length; i++) {
          const c = jetColor((mag?.[i] ?? 0) / safeMax);
          pCol[i * 3] = c.r;
          pCol[i * 3 + 1] = c.g;
          pCol[i * 3 + 2] = c.b;
        }
        pGeom.setAttribute("color", new THREE.BufferAttribute(pCol, 3));
        g.add(
          new THREE.Points(
            pGeom,
            new THREE.PointsMaterial({
              size: modelSpan * 0.004,
              vertexColors: true,
              sizeAttenuation: true,
            }),
          ),
        );
      }

      g.userData.panelIndex = pi;
      scene.add(g);
      panelGroups.push(g);
    });
    panelGroupsRef.current = panelGroups;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controlsRef.current = controls;

    // --- Kamera: odak varsa o hücreye, yoksa tüm ızgaraya sığdır ---
    function fit(index: number | null) {
      const cam = cameraRef.current;
      const ctl = controlsRef.current;
      if (!cam || !ctl) return;
      if (index !== null && panelGroups[index]) {
        const t = panelGroups[index].position;
        ctl.target.set(t.x, t.y, t.z);
        const d = modelSpan * 1.9;
        cam.position.set(t.x + d, t.y + d * 0.8, t.z + d);
      } else {
        const gridW = cols * cellW;
        const gridH = rows * cellH;
        const span = Math.max(gridW, gridH);
        ctl.target.set(0, 0, 0);
        const d = span * 1.15;
        cam.position.set(d * 0.55, d * 0.45, d);
      }
      cam.updateProjectionMatrix();
      ctl.update();
    }
    fit(focusedIndex);

    // Bir panele çift tıklama o moda odaklanır / odaktan çıkar.
    const raycaster = new THREE.Raycaster();
    function handleDoubleClick(ev: MouseEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(panelGroups, true);
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
    const animate = () => {
      raf = requestAnimationFrame(animate);
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
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else mat?.dispose();
      });
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      rendererRef.current = null;
      panelGroupsRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, faces, panels, columns, amplitude]);

  // Odak değişimi sahneyi YENİDEN KURMAZ — yalnız kamerayı taşır.
  useEffect(() => {
    const cam = cameraRef.current;
    const ctl = controlsRef.current;
    const groups = panelGroupsRef.current;
    if (!cam || !ctl || groups.length === 0) return;
    if (focusedIndex !== null && groups[focusedIndex]) {
      const t = groups[focusedIndex].position;
      ctl.target.set(t.x, t.y, t.z);
      const bboxAll = new THREE.Box3().setFromObject(groups[focusedIndex]);
      const s = new THREE.Vector3();
      bboxAll.getSize(s);
      const d = (Math.max(s.x, s.y, s.z) || 1) * 1.9;
      cam.position.set(t.x + d, t.y + d * 0.8, t.z + d);
    } else {
      const all = new THREE.Box3();
      for (const g of groups) all.expandByObject(g);
      const s = new THREE.Vector3();
      all.getSize(s);
      const span = Math.max(s.x, s.y, s.z) || 1;
      ctl.target.set(0, 0, 0);
      cam.position.set(span * 0.55, span * 0.45, span * 1.05);
    }
    cam.updateProjectionMatrix();
    ctl.update();
  }, [focusedIndex]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (scene) {
      scene.background = new THREE.Color(background === "black" ? "#0d0f0e" : "#eef0ec");
    }
  }, [background]);

  return (
    <div className="modal-mode-grid">
      <div className="modal-mode-grid-canvas" ref={containerRef} />
      <div className="modal-mode-grid-legend">
        {panels.map((p, i) => (
          <button
            key={`panel-${i}`}
            type="button"
            className={focusedIndex === i ? "active" : undefined}
            onClick={() => onFocusChange(focusedIndex === i ? null : i)}
            title={`${p.label} — tek başına göster`}
          >
            {p.label}
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
