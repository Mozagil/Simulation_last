import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import type { EdgeInfo, MeshPreviewData, PointInfo, ResultsPreviewData } from "../api/geometry";
import type { MeshGrowMode, MeshPickInfo, MultiSelectionInfo, SelectionMode } from "../types";

interface GeometryViewerProps {
  stlUrl: string;
  triangleToFace: number[];
  triangleToPart: number[];
  edges: EdgeInfo[];
  points: PointInfo[];
  mode: SelectionMode;
  /** Gizlenmiş parçaların (part_id) kümesi — "Solid göster/gizle" butonu için. */
  hiddenParts: Set<number>;
  /** Kenar çizgilerini göster/gizle (İşlemler grubundaki toggle butonu). */
  showEdges: boolean;
  /** FE mesh wireframe (CAD koordinatı); null = overlay yok. */
  meshPreview: MeshPreviewData | null;
  /** Mesh overlay görünür mü (göster/gizle). */
  showMesh: boolean;
  /** Mesh dolgusunu kapat, yalnız kenar çizgisi (arka geometri görünsün). */
  meshWireframe: boolean;
  /** CalculiX .frd'den parse edilmiş düğüm bazlı sonuçlar (von Mises,
   * deplasman) — kendi (kalınlık dahil) koordinatlarıyla bağımsız bir nokta
   * bulutu olarak gösterilir (mesh önizlemesiyle node hizası GARANTİ
   * DEĞİL — gerçek bir testte doğrulandı, kabuk elemanlarda CalculiX her
   * node'u üst/alt yüzey için ikiye katlıyor). */
  resultsPreview: ResultsPreviewData | null;
  /** Sonuç nokta bulutu görünür mü. */
  showResults: boolean;
  /** Hangi alan renklendirilecek. */
  resultsField: "von_mises" | "displacement_magnitude";
  /** Katı (CAD) opaklığı 0–1; kullanıcı ayarlar, mesh açılınca otomatik düşmez. */
  cadOpacity: number;
  /** Kenar başına düğüm sayısı (mesh tohumu). */
  edgeNodeCounts?: Record<number, number>;
  onEdgeNodeCountChange?: (edgeId: number, next: number) => void;
  /** App state'teki seçim — turuncu vurgu bununla senkron (sahne rebuild sonrası da kalır). */
  selectedIds: number[];
  /** Mesh overlay: seçili eleman(lar) + Face/Attached büyüme. */
  meshPicks: MeshPickInfo[];
  meshGrow: MeshGrowMode;
  /** Tıklama dışında (örn. Physical Group) belirli yüzeyleri/kenarları vurgulamak için. */
  externalHighlight: { faceIds: number[] } | { edgeIds: number[] } | null;
  /** Aktif moddaki seçili öğe(ler) değiştiğinde çağrılır. Düz tıklama tek
   * öğeye indirger; Ctrl(/Cmd)+tık mevcut seçime ekler/çıkarır. */
  onSelectionChange?: (info: MultiSelectionInfo) => void;
  /** Mesh elemanına tıklanınca. Ctrl ile çoklu; düz tık tekile indirger. */
  onMeshPicks?: (picks: MeshPickInfo[], keepGrow: boolean) => void;
}

const MESH_FACE_COLOR = "#6aa84f";
const MESH_FACE_THREE = new THREE.Color(MESH_FACE_COLOR);
const MESH_EDGE_COLOR = "#1a1a1a";

const BASE_COLOR = new THREE.Color("#5a8f73");
/** Turuncu seçim vurgusu — yeşilden net ayrışır. */
const HIGHLIGHT_COLOR = new THREE.Color("#e85d04");
const POINT_BASE_COLOR = new THREE.Color("#1b1f1c");
const EDGE_BASE_COLOR = "#1b1f1c";
const CLICK_DRAG_THRESHOLD_PX = 6;

/** Bir üçgen grup dizisinden (triangle_to_face / triangle_to_part) id -> üçgen
 * indeksleri haritası kurar. */
function buildGroupIndex(triangleToGroup: number[]): Map<number, number[]> {
  const map = new Map<number, number[]>();
  triangleToGroup.forEach((groupId, triIndex) => {
    const list = map.get(groupId);
    if (list) list.push(triIndex);
    else map.set(groupId, [triIndex]);
  });
  return map;
}

/** Kenar paylaşan üçgenler aynı parça — tıklanınca tüm bağlı mesh turuncu olur. */
function connectedTriangleParts(faces: number[]): number[] {
  const triCount = Math.floor(faces.length / 3);
  const partOf = new Array<number>(triCount).fill(-1);
  if (triCount === 0) return partOf;

  const edgeKey = (a: number, b: number) => (a < b ? `${a}_${b}` : `${b}_${a}`);
  const edgeToTris = new Map<string, number[]>();
  for (let t = 0; t < triCount; t++) {
    const i0 = faces[t * 3];
    const i1 = faces[t * 3 + 1];
    const i2 = faces[t * 3 + 2];
    for (const [a, b] of [
      [i0, i1],
      [i1, i2],
      [i2, i0],
    ] as [number, number][]) {
      const key = edgeKey(a, b);
      const list = edgeToTris.get(key);
      if (list) list.push(t);
      else edgeToTris.set(key, [t]);
    }
  }
  const adj: number[][] = Array.from({ length: triCount }, () => []);
  for (const tris of edgeToTris.values()) {
    for (let i = 0; i < tris.length; i++) {
      for (let j = i + 1; j < tris.length; j++) {
        adj[tris[i]].push(tris[j]);
        adj[tris[j]].push(tris[i]);
      }
    }
  }
  let partId = 0;
  for (let t = 0; t < triCount; t++) {
    if (partOf[t] !== -1) continue;
    const stack = [t];
    partOf[t] = partId;
    while (stack.length) {
      const cur = stack.pop() as number;
      for (const n of adj[cur]) {
        if (partOf[n] === -1) {
          partOf[n] = partId;
          stack.push(n);
        }
      }
    }
    partId += 1;
  }
  return partOf;
}

/** Çakışan xyz düğümlerini aynı id say — ayrı Gmsh yüzleri Attached'ta birleşir. */
function connectedPartsByWeldedNodes(nodes: number[][], faces: number[]): number[] {
  const weldOf = new Array<number>(nodes.length);
  const coordToWeld = new Map<string, number>();
  let nextW = 0;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const key = `${n[0].toFixed(5)}_${n[1].toFixed(5)}_${n[2].toFixed(5)}`;
    let w = coordToWeld.get(key);
    if (w === undefined) {
      w = nextW;
      nextW += 1;
      coordToWeld.set(key, w);
    }
    weldOf[i] = w;
  }
  const welded = new Array<number>(faces.length);
  for (let i = 0; i < faces.length; i++) {
    welded[i] = weldOf[faces[i]] ?? faces[i];
  }
  return connectedTriangleParts(welded);
}

function toggleMeshPicks(
  current: MeshPickInfo[],
  info: MeshPickInfo,
  ctrlPressed: boolean,
): MeshPickInfo[] {
  if (ctrlPressed) {
    const idx = current.findIndex((p) => p.elementId === info.elementId);
    if (idx >= 0) return current.filter((_, i) => i !== idx);
    return [...current, info];
  }
  if (current.length === 1 && current[0].elementId === info.elementId) {
    return [];
  }
  return [info];
}

/** Ctrl+tık ile ekle/çıkar, düz tık ile tekile indirge (aynı tek öğeye
 * tekrar düz tıklanırsa seçim temizlenir) — hem tek hem çoklu seçim için
 * ortak, mod-bağımsız mantık.
 */
function toggleSelection(current: Set<number>, id: number, ctrlPressed: boolean): Set<number> {
  if (ctrlPressed) {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  }
  if (current.size === 1 && current.has(id)) {
    return new Set();
  }
  return new Set([id]);
}

interface PartMeshEntry {
  partId: number;
  mesh: THREE.Mesh;
  colorAttribute: THREE.BufferAttribute;
  /** Bu alt-mesh'in yerel üçgen indeksinden global face_id'ye eşleme. */
  localTriangleToFace: number[];
  /** Bu alt-mesh içindeki face_id -> yerel üçgen indeksleri. */
  faceToLocalIndices: Map<number, number[]>;
  /** Bu parçanın kendi (geometrik, otomatik tespit edilen) kenar çizgileri —
   * parça gizlenince/gösterilince veya showEdges toggle'ında birlikte
   * güncellenir. */
  decorativeEdges: THREE.LineSegments;
}

/**
 * STL'i yükleyip parça bazlı AYRI mesh'ler olarak render eder (tek bir
 * birleşik mesh değil) — böylece "Solid göster/gizle" her parçayı bağımsız
 * gizleyebilir/gösterebilir.
 *
 * `mode` prop'una göre (Part/Surface/Edge/Point) tıklama farklı seviyede
 * seçim yapar. Düz tıklama seçimi TEK öğeye indirger; Ctrl(/Cmd)+tık mevcut
 * seçime ekler/çıkarır (çoklu seçim). `externalHighlight`, tıklama dışında
 * (Physical Group butonu gibi) programatik vurgulama için.
 *
 * Performans notu: sahne sadece geometri (stlUrl/edges/points/triangle
 * eşlemeleri) değiştiğinde yeniden kurulur; `mode`/`hiddenParts`/
 * `externalHighlight` değişimleri WebGL sahnesini yeniden kurmaz.
 */
function GeometryViewer({
  stlUrl,
  triangleToFace,
  triangleToPart,
  edges,
  points,
  mode,
  hiddenParts,
  showEdges,
  meshPreview,
  showMesh,
  meshWireframe,
  resultsPreview,
  showResults,
  resultsField,
  cadOpacity,
  edgeNodeCounts,
  onEdgeNodeCountChange,
  selectedIds,
  meshPicks,
  meshGrow,
  externalHighlight,
  onSelectionChange,
  onMeshPicks,
}: GeometryViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef<SelectionMode>(mode);
  const showEdgesRef = useRef<boolean>(showEdges);
  const selectedIdsRef = useRef<number[]>(selectedIds);
  selectedIdsRef.current = selectedIds;
  const externalHighlightRef = useRef(externalHighlight);
  externalHighlightRef.current = externalHighlight;
  const meshPreviewRef = useRef(meshPreview);
  meshPreviewRef.current = meshPreview;
  const showMeshRef = useRef(showMesh);
  showMeshRef.current = showMesh;
  const meshWireframeRef = useRef(meshWireframe);
  meshWireframeRef.current = meshWireframe;
  const cadOpacityRef = useRef(cadOpacity);
  cadOpacityRef.current = cadOpacity;

  const meshPicksRef = useRef(meshPicks);
  meshPicksRef.current = meshPicks;
  const meshGrowRef = useRef(meshGrow);
  meshGrowRef.current = meshGrow;
  const edgeNodeCountsRef = useRef(edgeNodeCounts);
  edgeNodeCountsRef.current = edgeNodeCounts;
  const onEdgeNodeCountChangeRef = useRef(onEdgeNodeCountChange);
  onEdgeNodeCountChangeRef.current = onEdgeNodeCountChange;
  const edgesRef = useRef(edges);
  edgesRef.current = edges;
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const edgeSeedLayerRef = useRef<HTMLDivElement>(null);

  const sceneRefs = useRef<{
    modelGroup: THREE.Group | null;
    modelCenter: THREE.Vector3;
    meshOverlay: THREE.Group | null;
    resultsOverlay: THREE.Group | null;
    overlayMesh: THREE.Mesh | null;
    overlayColorAttr: THREE.BufferAttribute | null;
    overlayTriCount: number;
    triangleToElement: number[];
    triangleToFace: number[];
    triangleToPart: number[];
    elementToTris: Map<number, number[]>;
    faceToTris: Map<number, number[]>;
    partToTris: Map<number, number[]>;
    partMeshes: PartMeshEntry[];
    partMeshByPartId: Map<number, PartMeshEntry>;
    faceIdToPart: Map<number, PartMeshEntry>;
    interactiveEdgesGroup: THREE.Group | null;
    pointsGroup: THREE.Group | null;
    edgeLineById: Map<number, THREE.Line>;
    pointMeshById: Map<number, THREE.Mesh>;
    selectedPartIds: Set<number>;
    selectedFaceIds: Set<number>;
    selectedEdgeIds: Set<number>;
    selectedPointIds: Set<number>;
    maxDim: number;
    camera: THREE.PerspectiveCamera | null;
  }>({
    modelGroup: null,
    modelCenter: new THREE.Vector3(),
    meshOverlay: null,
    resultsOverlay: null,
    overlayMesh: null,
    overlayColorAttr: null,
    overlayTriCount: 0,
    triangleToElement: [],
    triangleToFace: [],
    triangleToPart: [],
    elementToTris: new Map(),
    faceToTris: new Map(),
    partToTris: new Map(),
    partMeshes: [],
    partMeshByPartId: new Map(),
    faceIdToPart: new Map(),
    interactiveEdgesGroup: null,
    pointsGroup: null,
    edgeLineById: new Map(),
    pointMeshById: new Map(),
    selectedPartIds: new Set(),
    selectedFaceIds: new Set(),
    selectedEdgeIds: new Set(),
    selectedPointIds: new Set(),
    maxDim: 1,
    camera: null,
  });

  function clearOverlayMaps(refs: typeof sceneRefs.current) {
    refs.overlayMesh = null;
    refs.overlayColorAttr = null;
    refs.overlayTriCount = 0;
    refs.triangleToElement = [];
    refs.triangleToFace = [];
    refs.triangleToPart = [];
    refs.elementToTris = new Map();
    refs.faceToTris = new Map();
    refs.partToTris = new Map();
  }

  function disposeMeshOverlay() {
    const refs = sceneRefs.current;
    if (!refs.meshOverlay) {
      clearOverlayMaps(refs);
      return;
    }
    refs.modelGroup?.remove(refs.meshOverlay);
    refs.meshOverlay.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
        obj.geometry.dispose();
        const mat = obj.material as THREE.Material | THREE.Material[];
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat.dispose();
      }
    });
    refs.meshOverlay = null;
    clearOverlayMaps(refs);
  }

  function disposeResultsOverlay() {
    const refs = sceneRefs.current;
    if (!refs.resultsOverlay) return;
    refs.modelGroup?.remove(refs.resultsOverlay);
    refs.resultsOverlay.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        const mat = obj.material as THREE.Material | THREE.Material[];
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat.dispose();
      }
    });
    refs.resultsOverlay = null;
  }

  /** Sonuç nokta bulutunu (von Mises / deplasman renkli küreler) kurar.
   *
   * NOT: Bu koordinatlar mesh önizlemesindeki node'larla HİZALI DEĞİL —
   * kabuk elemanlarda CalculiX her node'u üst/alt yüzey için ikiye
   * katlıyor (gerçek bir testte doğrulandı). Bu yüzden mesh'e bağımlı
   * kalmadan, kendi gerçek koordinatlarıyla bağımsız bir görselleştirme.
   */
  function applyResultsOverlay(
    preview: ResultsPreviewData | null,
    visible: boolean,
    field: "von_mises" | "displacement_magnitude",
  ) {
    const refs = sceneRefs.current;
    disposeResultsOverlay();
    if (!preview || !visible || !refs.modelGroup || preview.nodes.length === 0) return;

    const values = field === "von_mises" ? preview.von_mises : preview.displacement_magnitude;
    const maxVal = field === "von_mises" ? preview.max_von_mises : preview.max_displacement;
    const safeMax = maxVal > 1e-30 ? maxVal : 1;

    const group = new THREE.Group();
    group.position.copy(refs.modelCenter).multiplyScalar(-1);

    const maxDim = refs.maxDim || 1;
    const sphereRadius = Math.max(maxDim * 0.012, 0.02);
    const sphereGeom = new THREE.SphereGeometry(sphereRadius, 8, 8);

    for (let i = 0; i < preview.nodes.length; i++) {
      const [x, y, z] = preview.nodes[i];
      const t = Math.min(1, Math.max(0, (values[i] ?? 0) / safeMax));
      // Renk skalası: mavi (düşük değer) -> kırmızı (yüksek değer).
      const hue = (1 - t) * 0.667;
      const color = new THREE.Color();
      color.setHSL(hue, 1, 0.5);
      const mat = new THREE.MeshBasicMaterial({ color });
      const sphere = new THREE.Mesh(sphereGeom, mat);
      sphere.position.set(x, y, z);
      group.add(sphere);
    }

    refs.modelGroup.add(group);
    refs.resultsOverlay = group;
  }

  function trisForGrow(picks: MeshPickInfo[], grow: MeshGrowMode): number[] {
    const refs = sceneRefs.current;
    if (picks.length === 0) return [];
    const tris = new Set<number>();
    if (grow === "face") {
      for (const faceId of new Set(picks.map((p) => p.faceId))) {
        for (const t of refs.faceToTris.get(faceId) ?? []) tris.add(t);
      }
    } else if (grow === "attached") {
      for (const partId of new Set(picks.map((p) => p.partId))) {
        for (const t of refs.partToTris.get(partId) ?? []) tris.add(t);
      }
    } else {
      for (const p of picks) {
        for (const t of refs.elementToTris.get(p.elementId) ?? []) tris.add(t);
      }
    }
    return [...tris];
  }

  function paintMeshGrow(picks: MeshPickInfo[], grow: MeshGrowMode) {
    const attr = sceneRefs.current.overlayColorAttr;
    if (!attr) return;
    const arr = attr.array as Float32Array;
    for (let i = 0; i < arr.length; i += 3) {
      arr[i] = MESH_FACE_THREE.r;
      arr[i + 1] = MESH_FACE_THREE.g;
      arr[i + 2] = MESH_FACE_THREE.b;
    }
    for (const ti of trisForGrow(picks, grow)) {
      for (let v = 0; v < 3; v++) {
        const o = (ti * 3 + v) * 3;
        arr[o] = HIGHLIGHT_COLOR.r;
        arr[o + 1] = HIGHLIGHT_COLOR.g;
        arr[o + 2] = HIGHLIGHT_COLOR.b;
      }
    }
    attr.needsUpdate = true;
  }

  function applyCadOpacity() {
    const refs = sceneRefs.current;
    const opacity = Math.min(1, Math.max(0, cadOpacityRef.current));
    const transparent = opacity < 0.999;
    for (const entry of refs.partMeshes) {
      entry.mesh.visible = opacity > 0.005 && !entry.mesh.userData._hiddenByUser;
      const mat = entry.mesh.material as THREE.MeshStandardMaterial;
      mat.transparent = transparent;
      mat.opacity = opacity;
      mat.depthWrite = !transparent;
      mat.needsUpdate = true;
    }
  }

  function setCadVisible(visible: boolean) {
    const refs = sceneRefs.current;
    for (const entry of refs.partMeshes) {
      entry.mesh.visible =
        visible && cadOpacityRef.current > 0.005 && !entry.mesh.userData._hiddenByUser;
    }
    if (visible) applyCadOpacity();
  }

  function applyMeshPreview(preview: MeshPreviewData | null, visible: boolean) {
    const refs = sceneRefs.current;
    disposeMeshOverlay();
    if (!preview || !visible || !refs.modelGroup || preview.nodes.length === 0) {
      setCadVisible(true);
      return;
    }
    const faces = preview.faces ?? [];
    const linesIdx = preview.lines ?? [];
    if (faces.length < 3 && linesIdx.length < 2) {
      setCadVisible(true);
      return;
    }

    const nodePos = new Float32Array(preview.nodes.length * 3);
    for (let i = 0; i < preview.nodes.length; i++) {
      const n = preview.nodes[i];
      nodePos[i * 3] = n[0];
      nodePos[i * 3 + 1] = n[1];
      nodePos[i * 3 + 2] = n[2];
    }

    const group = new THREE.Group();
    group.position.copy(refs.modelCenter).multiplyScalar(-1);

    if (faces.length >= 3) {
      const triCount = Math.floor(faces.length / 3);
      const tFace =
        preview.triangle_to_face && preview.triangle_to_face.length >= triCount
          ? preview.triangle_to_face.slice(0, triCount)
          : connectedTriangleParts(faces).slice(0, triCount);
      const tElem =
        preview.triangle_to_element && preview.triangle_to_element.length >= triCount
          ? preview.triangle_to_element.slice(0, triCount)
          : Array.from({ length: triCount }, (_, i) => i);
      const tPart = connectedPartsByWeldedNodes(preview.nodes, faces).slice(0, triCount);

      const positions = new Float32Array(triCount * 9);
      const colors = new Float32Array(triCount * 9);
      for (let t = 0; t < triCount; t++) {
        for (let v = 0; v < 3; v++) {
          const ni = faces[t * 3 + v];
          const dst = (t * 3 + v) * 3;
          positions[dst] = nodePos[ni * 3];
          positions[dst + 1] = nodePos[ni * 3 + 1];
          positions[dst + 2] = nodePos[ni * 3 + 2];
          colors[dst] = MESH_FACE_THREE.r;
          colors[dst + 1] = MESH_FACE_THREE.g;
          colors[dst + 2] = MESH_FACE_THREE.b;
        }
      }
      const faceGeom = new THREE.BufferGeometry();
      faceGeom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      const colorAttr = new THREE.BufferAttribute(colors, 3);
      faceGeom.setAttribute("color", colorAttr);
      faceGeom.computeVertexNormals();
      const faceMat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        metalness: 0.05,
        roughness: 0.55,
        side: THREE.DoubleSide,
        flatShading: true,
        polygonOffset: true,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
      });
      const mesh = new THREE.Mesh(faceGeom, faceMat);
      group.add(mesh);
      refs.overlayMesh = mesh;
      refs.overlayColorAttr = colorAttr;
      refs.overlayTriCount = triCount;
      refs.triangleToElement = tElem;
      refs.triangleToFace = tFace;
      refs.triangleToPart = tPart;
      refs.elementToTris = buildGroupIndex(tElem);
      refs.faceToTris = buildGroupIndex(tFace);
      refs.partToTris = buildGroupIndex(tPart);
    }

    if (linesIdx.length >= 2) {
      const edgeGeom = new THREE.BufferGeometry();
      edgeGeom.setAttribute("position", new THREE.BufferAttribute(nodePos.slice(), 3));
      edgeGeom.setIndex(new THREE.BufferAttribute(new Uint32Array(linesIdx), 1));
      const edgeMat = new THREE.LineBasicMaterial({ color: MESH_EDGE_COLOR });
      group.add(new THREE.LineSegments(edgeGeom, edgeMat));
    }

    refs.modelGroup.add(group);
    refs.meshOverlay = group;
    paintMeshGrow(meshPicksRef.current, meshGrowRef.current);
    setCadVisible(true);
    applyMeshWireframe(meshWireframeRef.current);
  }

  function applyMeshWireframe(wire: boolean) {
    const mesh = sceneRefs.current.overlayMesh;
    if (!mesh) return;
    const mat = mesh.material as THREE.MeshStandardMaterial;
    if (wire) {
      mat.transparent = true;
      mat.opacity = 0;
      mat.depthWrite = false;
    } else {
      mat.transparent = false;
      mat.opacity = 1;
      mat.depthWrite = true;
    }
    mat.needsUpdate = true;
  }

  function updateEdgeSeedScreenPositions() {
    const layer = edgeSeedLayerRef.current;
    const camera = sceneRefs.current.camera;
    if (!layer || !camera) return;
    const counts = edgeNodeCountsRef.current ?? {};
    const edgeList = edgesRef.current;
    const pointList = pointsRef.current;
    if (edgeList.length === 0) {
      layer.replaceChildren();
      return;
    }
    const pointById = new Map(pointList.map((p) => [p.id, p.coordinate]));
    const selected = new Set(selectedIdsRef.current);
    const showAll = edgeList.length <= 40 || modeRef.current === "edge";
    const width = layer.clientWidth;
    const height = layer.clientHeight;
    if (width < 2 || height < 2) return;
    const center = sceneRefs.current.modelCenter;
    const visibleIds = new Set<number>();
    const ndc = new THREE.Vector3();
    for (const edge of edgeList) {
      const n = counts[edge.id];
      if (n == null) continue;
      if (!showAll && !selected.has(edge.id)) continue;
      const a = pointById.get(edge.start_point);
      const b = pointById.get(edge.end_point);
      if (!a || !b) continue;
      ndc.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2);
      ndc.sub(center);
      ndc.project(camera);
      if (ndc.z < -1 || ndc.z > 1) continue;
      visibleIds.add(edge.id);
      let chip = layer.querySelector(`[data-edge-id="${edge.id}"]`) as HTMLDivElement | null;
      if (!chip) {
        chip = document.createElement("div");
        chip.className = "edge-seed-chip";
        chip.dataset.edgeId = String(edge.id);
        chip.innerHTML =
          '<button type="button" data-delta="-1" tabindex="-1">−</button>' +
          '<span></span>' +
          '<button type="button" data-delta="1" tabindex="-1">+</button>';
        layer.appendChild(chip);
      }
      const span = chip.querySelector("span");
      if (span) span.textContent = String(n);
      const x = (ndc.x * 0.5 + 0.5) * width;
      const y = (-ndc.y * 0.5 + 0.5) * height;
      chip.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
    }
    for (const child of [...layer.children]) {
      const id = Number((child as HTMLElement).dataset.edgeId);
      if (!visibleIds.has(id)) child.remove();
    }
  }

  // Ana sahne kurulumu — sadece geometri değiştiğinde.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let animationFrameId: number;
    let disposed = false;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#eef0ec");

    const camera = new THREE.PerspectiveCamera(
      45,
      (container.clientWidth || 1) / (container.clientHeight || 1),
      0.1,
      10000,
    );
    camera.position.set(10, 8, 10);
    sceneRefs.current.camera = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const axesCanvas = document.createElement("canvas");
    axesCanvas.className = "viewer-axes";
    axesCanvas.width = 88;
    axesCanvas.height = 88;
    container.appendChild(axesCanvas);
    const axesRenderer = new THREE.WebGLRenderer({
      canvas: axesCanvas,
      alpha: true,
      antialias: true,
    });
    axesRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    axesRenderer.setSize(88, 88, false);
    const axesScene = new THREE.Scene();
    const axesHelper = new THREE.AxesHelper(1);
    axesScene.add(axesHelper);
    const makeAxisLabel = (text: string, color: string, x: number, y: number, z: number) => {
      const c = document.createElement("canvas");
      c.width = 64;
      c.height = 64;
      const ctx = c.getContext("2d");
      if (ctx) {
        ctx.fillStyle = color;
        ctx.font = "bold 42px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, 32, 36);
      }
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }),
      );
      sprite.position.set(x, y, z);
      sprite.scale.set(0.4, 0.4, 0.4);
      axesScene.add(sprite);
    };
    makeAxisLabel("X", "#c0392b", 1.2, 0, 0);
    makeAxisLabel("Y", "#1e8449", 0, 1.2, 0);
    makeAxisLabel("Z", "#2471a3", 0, 0, 1.2);
    const axesCam = new THREE.PerspectiveCamera(50, 1, 0.1, 10);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.7;
    controls.zoomSpeed = 0.8;
    controls.panSpeed = 0.6;
    controls.screenSpacePanning = true;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.55);
    scene.add(ambientLight);
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
    keyLight.position.set(1, 1.4, 1);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
    fillLight.position.set(-1, -0.6, -1);
    scene.add(fillLight);

    const modelGroup = new THREE.Group();
    scene.add(modelGroup);
    sceneRefs.current.modelGroup = modelGroup;
    sceneRefs.current.meshOverlay = null;
    sceneRefs.current.resultsOverlay = null;
    clearOverlayMaps(sceneRefs.current);

    let gridHelper: THREE.GridHelper | null = null;

    function resetPartColor(entry: PartMeshEntry) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
    }

    function paintLocalIndices(entry: PartMeshEntry, localIndices: number[], color: THREE.Color) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (const triIndex of localIndices) {
        const base = triIndex * 3;
        for (let v = 0; v < 3; v++) {
          const offset = (base + v) * 3;
          colors[offset] = color.r;
          colors[offset + 1] = color.g;
          colors[offset + 2] = color.b;
        }
      }
      entry.colorAttribute.needsUpdate = true;
    }

    function repaintFaceSelection(selectedIds: Set<number>) {
      const refs = sceneRefs.current;
      for (const entry of refs.partMeshes) resetPartColor(entry);
      for (const faceId of selectedIds) {
        const entry = refs.faceIdToPart.get(faceId);
        if (!entry) continue;
        const localIndices = entry.faceToLocalIndices.get(faceId) ?? [];
        paintLocalIndices(entry, localIndices, HIGHLIGHT_COLOR);
      }
    }

    function applyHighlightFromAppState() {
      const refs = sceneRefs.current;
      if (refs.partMeshes.length === 0) return;
      const ext = externalHighlightRef.current;
      const ids = selectedIdsRef.current;
      const currentMode = modeRef.current;

      for (const entry of refs.partMeshes) resetPartColor(entry);
      for (const line of refs.edgeLineById.values()) {
        (line.material as THREE.LineBasicMaterial).color.set(EDGE_BASE_COLOR);
      }
      for (const pm of refs.pointMeshById.values()) {
        (pm.material as THREE.MeshBasicMaterial).color.set(POINT_BASE_COLOR);
      }

      if (ext && "faceIds" in ext) {
        for (const faceId of ext.faceIds) {
          const entry = refs.faceIdToPart.get(faceId);
          if (!entry) continue;
          paintLocalIndices(entry, entry.faceToLocalIndices.get(faceId) ?? [], HIGHLIGHT_COLOR);
        }
        return;
      }
      if (ext && "edgeIds" in ext) {
        for (const edgeId of ext.edgeIds) {
          const line = refs.edgeLineById.get(edgeId);
          if (line) (line.material as THREE.LineBasicMaterial).color.set(HIGHLIGHT_COLOR);
        }
        return;
      }

      if (currentMode === "surface") {
        refs.selectedFaceIds = new Set(ids);
        repaintFaceSelection(refs.selectedFaceIds);
      } else if (currentMode === "part") {
        refs.selectedPartIds = new Set(ids);
        repaintPartSelection(refs.selectedPartIds);
      } else if (currentMode === "edge") {
        refs.selectedEdgeIds = new Set(ids);
        repaintEdgeSelection(refs.selectedEdgeIds);
      } else if (currentMode === "point") {
        refs.selectedPointIds = new Set(ids);
        repaintPointSelection(refs.selectedPointIds);
      }
    }

    function repaintPartSelection(selectedIds: Set<number>) {
      const refs = sceneRefs.current;
      for (const entry of refs.partMeshes) resetPartColor(entry);
      for (const partId of selectedIds) {
        const entry = refs.partMeshByPartId.get(partId);
        if (!entry) continue;
        const colors = entry.colorAttribute.array as Float32Array;
        for (let i = 0; i < colors.length; i += 3) {
          colors[i] = HIGHLIGHT_COLOR.r;
          colors[i + 1] = HIGHLIGHT_COLOR.g;
          colors[i + 2] = HIGHLIGHT_COLOR.b;
        }
        entry.colorAttribute.needsUpdate = true;
      }
    }

    function repaintEdgeSelection(selectedIds: Set<number>) {
      const refs = sceneRefs.current;
      for (const line of refs.edgeLineById.values()) {
        (line.material as THREE.LineBasicMaterial).color.set(EDGE_BASE_COLOR);
      }
      for (const edgeId of selectedIds) {
        const line = refs.edgeLineById.get(edgeId);
        if (line) (line.material as THREE.LineBasicMaterial).color.set(HIGHLIGHT_COLOR);
      }
    }

    function repaintPointSelection(selectedIds: Set<number>) {
      const refs = sceneRefs.current;
      for (const pm of refs.pointMeshById.values()) {
        (pm.material as THREE.MeshBasicMaterial).color.set(POINT_BASE_COLOR);
      }
      for (const pointId of selectedIds) {
        const pm = refs.pointMeshById.get(pointId);
        if (pm) (pm.material as THREE.MeshBasicMaterial).color.set(HIGHLIGHT_COLOR);
      }
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerDownPos: { x: number; y: number } | null = null;

    function handlePointerDown(event: PointerEvent) {
      pointerDownPos = { x: event.clientX, y: event.clientY };
    }

    function handlePointerUp(event: PointerEvent) {
      if (!pointerDownPos) return;
      const dx = event.clientX - pointerDownPos.x;
      const dy = event.clientY - pointerDownPos.y;
      const movedDistance = Math.sqrt(dx * dx + dy * dy);
      pointerDownPos = null;
      if (movedDistance > CLICK_DRAG_THRESHOLD_PX) return;

      const ctrlPressed = event.ctrlKey || event.metaKey;

      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const refs = sceneRefs.current;
      const currentMode = modeRef.current;
      const overlayVisible =
        Boolean(showMeshRef.current && meshPreviewRef.current) &&
        refs.overlayMesh !== null;

      if (overlayVisible && refs.overlayMesh) {
        const overlayHits = raycaster.intersectObject(refs.overlayMesh, false);
        if (overlayHits.length > 0 && overlayHits[0].faceIndex !== undefined) {
          const triIndex = overlayHits[0].faceIndex as number;
          const info: MeshPickInfo = {
            elementId: refs.triangleToElement[triIndex] ?? triIndex,
            faceId: refs.triangleToFace[triIndex] ?? 0,
            partId: refs.triangleToPart[triIndex] ?? 0,
          };
          const next = toggleMeshPicks(meshPicksRef.current, info, ctrlPressed);
          meshPicksRef.current = next;
          const grow = ctrlPressed ? meshGrowRef.current : "element";
          paintMeshGrow(next, grow);
          onMeshPicks?.(next, ctrlPressed);
          return;
        }
        if (!ctrlPressed) {
          meshPicksRef.current = [];
          paintMeshGrow([], "element");
          onMeshPicks?.([], false);
        }
        return;
      }

      if (currentMode === "surface" || currentMode === "part") {
        const meshes = refs.partMeshes
          .filter((e) => e.mesh.visible)
          .map((e) => e.mesh);
        const intersections = raycaster.intersectObjects(meshes, false);
        if (intersections.length === 0 || intersections[0].faceIndex === undefined) {
          if (!ctrlPressed) {
            if (currentMode === "part") {
              refs.selectedPartIds = new Set();
              repaintPartSelection(refs.selectedPartIds);
            } else {
              refs.selectedFaceIds = new Set();
              repaintFaceSelection(refs.selectedFaceIds);
            }
            onSelectionChange?.({ mode: currentMode, ids: [] });
          }
          return;
        }

        const hitMesh = intersections[0].object as THREE.Mesh;
        const hitEntry = refs.partMeshes.find((e) => e.mesh === hitMesh);
        if (!hitEntry) return;
        const localTriIndex = intersections[0].faceIndex as number;

        if (currentMode === "part") {
          refs.selectedPartIds = toggleSelection(refs.selectedPartIds, hitEntry.partId, ctrlPressed);
          repaintPartSelection(refs.selectedPartIds);
          onSelectionChange?.({ mode: "part", ids: [...refs.selectedPartIds] });
        } else {
          const faceId = hitEntry.localTriangleToFace[localTriIndex];
          refs.selectedFaceIds = toggleSelection(refs.selectedFaceIds, faceId, ctrlPressed);
          repaintFaceSelection(refs.selectedFaceIds);
          onSelectionChange?.({ mode: "surface", ids: [...refs.selectedFaceIds] });
        }
        return;
      }

      if (currentMode === "edge" && refs.interactiveEdgesGroup) {
        raycaster.params.Line = { threshold: refs.maxDim * 0.015 };
        const intersections = raycaster.intersectObjects(refs.interactiveEdgesGroup.children, false);
        if (intersections.length === 0) {
          if (!ctrlPressed) {
            refs.selectedEdgeIds = new Set();
            repaintEdgeSelection(refs.selectedEdgeIds);
            onSelectionChange?.({ mode: "edge", ids: [] });
          }
          return;
        }
        const edgeId = intersections[0].object.userData.edgeId as number;
        refs.selectedEdgeIds = toggleSelection(refs.selectedEdgeIds, edgeId, ctrlPressed);
        repaintEdgeSelection(refs.selectedEdgeIds);
        onSelectionChange?.({ mode: "edge", ids: [...refs.selectedEdgeIds] });
        return;
      }

      if (currentMode === "point" && refs.pointsGroup) {
        const intersections = raycaster.intersectObjects(refs.pointsGroup.children, false);
        if (intersections.length === 0) {
          if (!ctrlPressed) {
            refs.selectedPointIds = new Set();
            repaintPointSelection(refs.selectedPointIds);
            onSelectionChange?.({ mode: "point", ids: [] });
          }
          return;
        }
        const pointId = intersections[0].object.userData.pointId as number;
        refs.selectedPointIds = toggleSelection(refs.selectedPointIds, pointId, ctrlPressed);
        repaintPointSelection(refs.selectedPointIds);
        onSelectionChange?.({ mode: "point", ids: [...refs.selectedPointIds] });
      }
    }

    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);

    const loader = new STLLoader();

    loader.load(
      stlUrl,
      (geometry) => {
        if (disposed) return;

        geometry.computeBoundingBox();
        geometry.computeVertexNormals();

        const boundingBox = geometry.boundingBox;
        if (!boundingBox) return;

        const center = new THREE.Vector3();
        boundingBox.getCenter(center);
        sceneRefs.current.modelCenter.copy(center);
        const size = new THREE.Vector3();
        boundingBox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        sceneRefs.current.maxDim = maxDim;

        const positions = geometry.attributes.position.array as Float32Array;
        const normalsArr = geometry.attributes.normal.array as Float32Array;

        let partToTriangleIndices = buildGroupIndex(triangleToPart);
        // Eşleme boş/eksik gelse bile ham STL'i tek parça olarak çiz — aksi halde
        // kamera/grid kurulur, katı hiç eklenmez, viewport boş kalır.
        if (partToTriangleIndices.size === 0) {
          const triCount = Math.floor(positions.length / 9);
          if (triCount > 0) {
            partToTriangleIndices = new Map([
              [0, Array.from({ length: triCount }, (_, i) => i)],
            ]);
          }
        }
        const partMeshes: PartMeshEntry[] = [];
        const partMeshByPartId = new Map<number, PartMeshEntry>();
        const faceIdToPart = new Map<number, PartMeshEntry>();

        for (const [partId, triIndices] of partToTriangleIndices) {
          const triCount = triIndices.length;
          const subPositions = new Float32Array(triCount * 9);
          const subNormals = new Float32Array(triCount * 9);
          const subColors = new Float32Array(triCount * 9);
          const localTriangleToFace: number[] = new Array(triCount);

          triIndices.forEach((globalTriIdx, localIdx) => {
            const srcOffset = globalTriIdx * 9;
            const dstOffset = localIdx * 9;
            subPositions.set(positions.subarray(srcOffset, srcOffset + 9), dstOffset);
            subNormals.set(normalsArr.subarray(srcOffset, srcOffset + 9), dstOffset);
            localTriangleToFace[localIdx] = triangleToFace[globalTriIdx];
          });
          for (let i = 0; i < subColors.length; i += 3) {
            subColors[i] = BASE_COLOR.r;
            subColors[i + 1] = BASE_COLOR.g;
            subColors[i + 2] = BASE_COLOR.b;
          }

          const subGeometry = new THREE.BufferGeometry();
          subGeometry.setAttribute("position", new THREE.BufferAttribute(subPositions, 3));
          subGeometry.setAttribute("normal", new THREE.BufferAttribute(subNormals, 3));
          const colorAttribute = new THREE.BufferAttribute(subColors, 3);
          subGeometry.setAttribute("color", colorAttribute);

          const material = new THREE.MeshStandardMaterial({
            vertexColors: true,
            metalness: 0.05,
            roughness: 0.65,
            flatShading: true,
            side: THREE.DoubleSide,
            polygonOffset: true,
            polygonOffsetFactor: 1,
            polygonOffsetUnits: 1,
          });
          const mesh = new THREE.Mesh(subGeometry, material);
          mesh.userData.partId = partId;
          mesh.position.sub(center);
          modelGroup.add(mesh);

          const edgesMaterial = new THREE.LineBasicMaterial({
            color: "#0d100e",
            transparent: true,
            opacity: 0.7,
          });
          // EdgesGeometry 30k+ üçgende ana iş parçacığını saniyelerce kilitler;
          // ilk karede katı görünmez kalır. Kenarları bir sonraki kareye erteliyoruz.
          const decorativeEdges = new THREE.LineSegments(new THREE.BufferGeometry(), edgesMaterial);
          decorativeEdges.visible = showEdgesRef.current;
          mesh.add(decorativeEdges);
          requestAnimationFrame(() => {
            if (disposed) return;
            const edgesGeometry = new THREE.EdgesGeometry(subGeometry, 30);
            decorativeEdges.geometry.dispose();
            decorativeEdges.geometry = edgesGeometry;
          });

          const faceToLocalIndices = buildGroupIndex(localTriangleToFace);
          const entry: PartMeshEntry = {
            partId,
            mesh,
            colorAttribute,
            localTriangleToFace,
            faceToLocalIndices,
            decorativeEdges,
          };
          partMeshes.push(entry);
          partMeshByPartId.set(partId, entry);
          for (const faceId of faceToLocalIndices.keys()) {
            faceIdToPart.set(faceId, entry);
          }
        }

        camera.near = maxDim / 1000;
        camera.far = maxDim * 100;
        camera.updateProjectionMatrix();
        camera.position.set(maxDim * 1.4, maxDim * 1.1, maxDim * 1.4);
        camera.lookAt(0, 0, 0);

        controls.target.set(0, 0, 0);
        controls.minDistance = maxDim * 0.15;
        controls.maxDistance = maxDim * 8;
        controls.update();

        gridHelper = new THREE.GridHelper(maxDim * 3, 20, "#c7ccc3", "#dde1d8");
        gridHelper.position.y = boundingBox.min.y - center.y;
        scene.add(gridHelper);

        const pointById = new Map(points.map((p) => [p.id, p.coordinate] as const));
        const interactiveEdgesGroup = new THREE.Group();
        const edgeLineById = new Map<number, THREE.Line>();
        for (const edge of edges) {
          const startCoord = pointById.get(edge.start_point);
          const endCoord = pointById.get(edge.end_point);
          if (!startCoord || !endCoord) continue;

          const lineGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(...startCoord),
            new THREE.Vector3(...endCoord),
          ]);
          const lineMaterial = new THREE.LineBasicMaterial({ color: EDGE_BASE_COLOR });
          const line = new THREE.Line(lineGeometry, lineMaterial);
          line.userData.edgeId = edge.id;
          interactiveEdgesGroup.add(line);
          edgeLineById.set(edge.id, line);
        }
        interactiveEdgesGroup.position.sub(center);
        interactiveEdgesGroup.visible = modeRef.current === "edge";
        modelGroup.add(interactiveEdgesGroup);

        const pointsGroup = new THREE.Group();
        const pointMeshById = new Map<number, THREE.Mesh>();
        const pointRadius = Math.max(maxDim * 0.008, 0.04);
        const sphereGeometry = new THREE.SphereGeometry(pointRadius, 12, 12);
        for (const point of points) {
          const pointMaterial = new THREE.MeshBasicMaterial({ color: POINT_BASE_COLOR });
          const sphere = new THREE.Mesh(sphereGeometry, pointMaterial);
          sphere.position.set(...point.coordinate);
          sphere.userData.pointId = point.id;
          pointsGroup.add(sphere);
          pointMeshById.set(point.id, sphere);
        }
        pointsGroup.position.sub(center);
        pointsGroup.visible = modeRef.current === "point";
        modelGroup.add(pointsGroup);

        sceneRefs.current.partMeshes = partMeshes;
        sceneRefs.current.partMeshByPartId = partMeshByPartId;
        sceneRefs.current.faceIdToPart = faceIdToPart;
        sceneRefs.current.interactiveEdgesGroup = interactiveEdgesGroup;
        sceneRefs.current.pointsGroup = pointsGroup;
        sceneRefs.current.edgeLineById = edgeLineById;
        sceneRefs.current.pointMeshById = pointMeshById;

        for (const entry of partMeshes) {
          entry.mesh.userData._hiddenByUser = hiddenParts.has(entry.partId);
          entry.mesh.visible = !entry.mesh.userData._hiddenByUser;
        }

        applyHighlightFromAppState();
        applyMeshPreview(meshPreviewRef.current, showMeshRef.current);
        applyCadOpacity();
      },
      undefined,
      (error) => {
        console.error("STL yüklenemedi:", error);
      },
    );

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
      const offset = camera.position.clone().sub(controls.target).normalize().multiplyScalar(2.4);
      axesCam.position.copy(offset);
      axesCam.up.copy(camera.up);
      axesCam.lookAt(0, 0, 0);
      axesRenderer.render(axesScene, axesCam);
      updateEdgeSeedScreenPositions();
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width < 2 || height < 2) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    handleResize();
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);
    window.addEventListener("resize", handleResize);

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      controls.dispose();
      renderer.dispose();
      axesRenderer.dispose();
      axesScene.traverse((obj) => {
        if (obj instanceof THREE.Sprite) {
          const mat = obj.material as THREE.SpriteMaterial;
          mat.map?.dispose();
          mat.dispose();
        }
      });
      if (axesCanvas.parentElement === container) {
        container.removeChild(axesCanvas);
      }
      modelGroup.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments || obj instanceof THREE.Line) {
          obj.geometry.dispose();
          const mat = obj.material as THREE.Material | THREE.Material[];
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else mat.dispose();
        }
      });
      if (gridHelper) {
        gridHelper.geometry.dispose();
        (gridHelper.material as THREE.Material).dispose();
      }
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
      sceneRefs.current = {
        modelGroup: null,
        modelCenter: new THREE.Vector3(),
        meshOverlay: null,
        resultsOverlay: null,
        overlayMesh: null,
        overlayColorAttr: null,
        overlayTriCount: 0,
        triangleToElement: [],
        triangleToFace: [],
        triangleToPart: [],
        elementToTris: new Map(),
        faceToTris: new Map(),
        partToTris: new Map(),
        partMeshes: [],
        partMeshByPartId: new Map(),
        faceIdToPart: new Map(),
        interactiveEdgesGroup: null,
        pointsGroup: null,
        edgeLineById: new Map(),
        pointMeshById: new Map(),
        selectedPartIds: new Set(),
        selectedFaceIds: new Set(),
        selectedEdgeIds: new Set(),
        selectedPointIds: new Set(),
        maxDim: 1,
        camera: null,
      };
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stlUrl, edges, points, triangleToFace, triangleToPart]);

  // Mesh wireframe overlay — sahne rebuild etmeden güncellenir.
  useEffect(() => {
    applyMeshPreview(meshPreview, showMesh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meshPreview, showMesh]);

  // Sonuç nokta bulutu (von Mises / deplasman) — sahne rebuild etmeden güncellenir.
  useEffect(() => {
    applyResultsOverlay(resultsPreview, showResults, resultsField);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultsPreview, showResults, resultsField]);

  useEffect(() => {
    meshWireframeRef.current = meshWireframe;
    applyMeshWireframe(meshWireframe);
  }, [meshWireframe]);

  // Mod değişimi: görünürlük + App seçimini yeniden boya (sahne rebuild yok).
  useEffect(() => {
    modeRef.current = mode;
    const refs = sceneRefs.current;
    if (refs.interactiveEdgesGroup) refs.interactiveEdgesGroup.visible = mode === "edge";
    if (refs.pointsGroup) refs.pointsGroup.visible = mode === "point";

    // Seçimi App temizler (mode change handler); burada sadece görünürlük.
    for (const entry of refs.partMeshes) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // hiddenParts değişimi: sahneyi yeniden kurmadan sadece görünürlük.
  useEffect(() => {
    const refs = sceneRefs.current;
    for (const entry of refs.partMeshes) {
      entry.mesh.userData._hiddenByUser = hiddenParts.has(entry.partId);
    }
    applyCadOpacity();
  }, [hiddenParts]);

  useEffect(() => {
    cadOpacityRef.current = cadOpacity;
    applyCadOpacity();
  }, [cadOpacity]);

  // showEdges değişimi: her parçanın kendi kenar çizgisinin görünürlüğünü
  // toplu güncelle.
  useEffect(() => {
    showEdgesRef.current = showEdges;
    const refs = sceneRefs.current;
    for (const entry of refs.partMeshes) {
      entry.decorativeEdges.visible = showEdges;
    }
  }, [showEdges]);

  // App seçimi / externalHighlight → turuncu vurgu (STL yüklüyse).
  useEffect(() => {
    const refs = sceneRefs.current;
    if (refs.partMeshes.length === 0) return;

    for (const entry of refs.partMeshes) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
    }
    for (const line of refs.edgeLineById.values()) {
      (line.material as THREE.LineBasicMaterial).color.set(EDGE_BASE_COLOR);
    }
    for (const pm of refs.pointMeshById.values()) {
      (pm.material as THREE.MeshBasicMaterial).color.set(POINT_BASE_COLOR);
    }

    if (externalHighlight && "faceIds" in externalHighlight) {
      for (const faceId of externalHighlight.faceIds) {
        const entry = refs.faceIdToPart.get(faceId);
        if (!entry) continue;
        const localIndices = entry.faceToLocalIndices.get(faceId) ?? [];
        const colors = entry.colorAttribute.array as Float32Array;
        for (const triIndex of localIndices) {
          const base = triIndex * 3;
          for (let v = 0; v < 3; v++) {
            const offset = (base + v) * 3;
            colors[offset] = HIGHLIGHT_COLOR.r;
            colors[offset + 1] = HIGHLIGHT_COLOR.g;
            colors[offset + 2] = HIGHLIGHT_COLOR.b;
          }
        }
        entry.colorAttribute.needsUpdate = true;
      }
      return;
    }
    if (externalHighlight && "edgeIds" in externalHighlight) {
      for (const edgeId of externalHighlight.edgeIds) {
        const line = refs.edgeLineById.get(edgeId);
        if (line) (line.material as THREE.LineBasicMaterial).color.set(HIGHLIGHT_COLOR);
      }
      return;
    }

    if (mode === "surface") {
      for (const faceId of selectedIds) {
        const entry = refs.faceIdToPart.get(faceId);
        if (!entry) continue;
        const localIndices = entry.faceToLocalIndices.get(faceId) ?? [];
        const colors = entry.colorAttribute.array as Float32Array;
        for (const triIndex of localIndices) {
          const base = triIndex * 3;
          for (let v = 0; v < 3; v++) {
            const offset = (base + v) * 3;
            colors[offset] = HIGHLIGHT_COLOR.r;
            colors[offset + 1] = HIGHLIGHT_COLOR.g;
            colors[offset + 2] = HIGHLIGHT_COLOR.b;
          }
        }
        entry.colorAttribute.needsUpdate = true;
      }
    } else if (mode === "part") {
      for (const partId of selectedIds) {
        const entry = refs.partMeshByPartId.get(partId);
        if (!entry) continue;
        const colors = entry.colorAttribute.array as Float32Array;
        for (let i = 0; i < colors.length; i += 3) {
          colors[i] = HIGHLIGHT_COLOR.r;
          colors[i + 1] = HIGHLIGHT_COLOR.g;
          colors[i + 2] = HIGHLIGHT_COLOR.b;
        }
        entry.colorAttribute.needsUpdate = true;
      }
    } else if (mode === "edge") {
      for (const edgeId of selectedIds) {
        const line = refs.edgeLineById.get(edgeId);
        if (line) (line.material as THREE.LineBasicMaterial).color.set(HIGHLIGHT_COLOR);
      }
    } else if (mode === "point") {
      for (const pointId of selectedIds) {
        const pm = refs.pointMeshById.get(pointId);
        if (pm) (pm.material as THREE.MeshBasicMaterial).color.set(HIGHLIGHT_COLOR);
      }
    }
    paintMeshGrow(meshPicks, meshGrow);
  }, [selectedIds, mode, externalHighlight, meshPicks, meshGrow]);

  useEffect(() => {
    const layer = edgeSeedLayerRef.current;
    if (!layer) return;
    const onPointerDown = (ev: PointerEvent) => {
      ev.stopPropagation();
      const target = ev.target as HTMLElement | null;
      const btn = target?.closest("button[data-delta]") as HTMLButtonElement | null;
      if (!btn) return;
      const chip = btn.closest("[data-edge-id]") as HTMLElement | null;
      if (!chip) return;
      const edgeId = Number(chip.dataset.edgeId);
      const delta = Number(btn.dataset.delta);
      if (!Number.isFinite(edgeId) || !Number.isFinite(delta)) return;
      const current = edgeNodeCountsRef.current?.[edgeId] ?? 2;
      const next = Math.max(2, Math.min(500, current + delta));
      onEdgeNodeCountChangeRef.current?.(edgeId, next);
    };
    layer.addEventListener("pointerdown", onPointerDown);
    return () => layer.removeEventListener("pointerdown", onPointerDown);
  }, []);

  return (
    <div ref={containerRef} className="viewer-canvas">
      <div ref={edgeSeedLayerRef} className="edge-seed-layer" />
    </div>
  );
}

export default GeometryViewer;
