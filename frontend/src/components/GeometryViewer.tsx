import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import type { EdgeInfo, PointInfo } from "../api/geometry";
import type { SelectionInfo, SelectionMode } from "../types";

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
  /** Tıklama dışında (örn. bir Physical Group butonuna basınca) belirli
   * yüzeyleri vurgulamak için. null verilince vurgu temizlenir. */
  externalHighlight: { faceIds: number[] } | null;
  onSelectionChange?: (info: SelectionInfo | null) => void;
}

const BASE_COLOR = new THREE.Color("#5a8f73");
const HIGHLIGHT_COLOR = new THREE.Color("#d97757");
const POINT_BASE_COLOR = new THREE.Color("#1b1f1c");
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
 * gizleyebilir/gösterebilir (three.js'te tek bir mesh'in bir kısmını
 * gizlemek mümkün değil, bu yüzden bu bölünme gerekli).
 *
 * `mode` prop'una göre (Part/Surface/Edge/Point) tıklama farklı seviyede
 * seçim yapar. `externalHighlight`, tıklama dışında (Physical Group butonu
 * gibi) programatik vurgulama için.
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
  externalHighlight,
  onSelectionChange,
}: GeometryViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef<SelectionMode>(mode);
  const showEdgesRef = useRef<boolean>(showEdges);

  const sceneRefs = useRef<{
    partMeshes: PartMeshEntry[];
    partMeshByPartId: Map<number, PartMeshEntry>;
    faceIdToPart: Map<number, PartMeshEntry>;
    interactiveEdgesGroup: THREE.Group | null;
    pointsGroup: THREE.Group | null;
    edgeLineById: Map<number, THREE.Line>;
    pointMeshById: Map<number, THREE.Mesh>;
    highlightedPartId: number | null;
    highlightedFaceId: number | null;
    highlightedEdgeId: number | null;
    highlightedPointId: number | null;
    externalHighlightedFaceIds: number[];
    maxDim: number;
  }>({
    partMeshes: [],
    partMeshByPartId: new Map(),
    faceIdToPart: new Map(),
    interactiveEdgesGroup: null,
    pointsGroup: null,
    edgeLineById: new Map(),
    pointMeshById: new Map(),
    highlightedPartId: null,
    highlightedFaceId: null,
    highlightedEdgeId: null,
    highlightedPointId: null,
    externalHighlightedFaceIds: [],
    maxDim: 1,
  });

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
      container.clientWidth / container.clientHeight,
      0.1,
      10000,
    );
    camera.position.set(10, 8, 10);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

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

    function resetAllHighlights() {
      const refs = sceneRefs.current;
      for (const entry of refs.partMeshes) resetPartColor(entry);
      refs.highlightedPartId = null;
      refs.highlightedFaceId = null;
      refs.externalHighlightedFaceIds = [];

      if (refs.highlightedEdgeId !== null) {
        const line = refs.edgeLineById.get(refs.highlightedEdgeId);
        if (line) (line.material as THREE.LineBasicMaterial).color.set("#1b1f1c");
      }
      refs.highlightedEdgeId = null;

      if (refs.highlightedPointId !== null) {
        const pm = refs.pointMeshById.get(refs.highlightedPointId);
        if (pm) (pm.material as THREE.MeshBasicMaterial).color.set(POINT_BASE_COLOR);
      }
      refs.highlightedPointId = null;
    }

    function highlightPart(partId: number) {
      const refs = sceneRefs.current;
      const entry = refs.partMeshByPartId.get(partId);
      if (!entry) return;
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = HIGHLIGHT_COLOR.r;
        colors[i + 1] = HIGHLIGHT_COLOR.g;
        colors[i + 2] = HIGHLIGHT_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
      refs.highlightedPartId = partId;
    }

    function highlightFace(faceId: number) {
      const refs = sceneRefs.current;
      const entry = refs.faceIdToPart.get(faceId);
      if (!entry) return;
      const localIndices = entry.faceToLocalIndices.get(faceId) ?? [];
      paintLocalIndices(entry, localIndices, HIGHLIGHT_COLOR);
      refs.highlightedFaceId = faceId;
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

      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const refs = sceneRefs.current;
      const currentMode = modeRef.current;

      if (currentMode === "surface" || currentMode === "part") {
        const meshes = refs.partMeshes.map((e) => e.mesh);
        const intersections = raycaster.intersectObjects(meshes, false);
        if (intersections.length === 0 || intersections[0].faceIndex === undefined) {
          resetAllHighlights();
          onSelectionChange?.(null);
          return;
        }

        const hitMesh = intersections[0].object as THREE.Mesh;
        const hitEntry = refs.partMeshes.find((e) => e.mesh === hitMesh);
        if (!hitEntry) return;
        const localTriIndex = intersections[0].faceIndex as number;

        if (currentMode === "part") {
          const nextPartId = refs.highlightedPartId === hitEntry.partId ? null : hitEntry.partId;
          resetAllHighlights();
          if (nextPartId !== null) {
            highlightPart(nextPartId);
            const triangleCount = hitEntry.localTriangleToFace.length;
            onSelectionChange?.({ mode: "part", id: nextPartId, triangleCount });
          } else {
            onSelectionChange?.(null);
          }
        } else {
          const faceId = hitEntry.localTriangleToFace[localTriIndex];
          const nextFaceId = refs.highlightedFaceId === faceId ? null : faceId;
          resetAllHighlights();
          if (nextFaceId !== null) {
            highlightFace(nextFaceId);
            const count = hitEntry.faceToLocalIndices.get(nextFaceId)?.length ?? 0;
            onSelectionChange?.({ mode: "surface", id: nextFaceId, triangleCount: count });
          } else {
            onSelectionChange?.(null);
          }
        }
        return;
      }

      if (currentMode === "edge" && refs.interactiveEdgesGroup) {
        raycaster.params.Line = { threshold: refs.maxDim * 0.015 };
        const intersections = raycaster.intersectObjects(refs.interactiveEdgesGroup.children, false);
        if (intersections.length === 0) {
          resetAllHighlights();
          onSelectionChange?.(null);
          return;
        }
        const edgeId = intersections[0].object.userData.edgeId as number;
        const next = refs.highlightedEdgeId === edgeId ? null : edgeId;
        resetAllHighlights();
        if (next !== null) {
          const line = refs.edgeLineById.get(next);
          if (line) (line.material as THREE.LineBasicMaterial).color.set(HIGHLIGHT_COLOR);
          refs.highlightedEdgeId = next;
          const edgeInfo = edges.find((e) => e.id === next);
          onSelectionChange?.({ mode: "edge", id: next, length: edgeInfo?.length ?? 0 });
        } else {
          onSelectionChange?.(null);
        }
        return;
      }

      if (currentMode === "point" && refs.pointsGroup) {
        const intersections = raycaster.intersectObjects(refs.pointsGroup.children, false);
        if (intersections.length === 0) {
          resetAllHighlights();
          onSelectionChange?.(null);
          return;
        }
        const pointId = intersections[0].object.userData.pointId as number;
        const next = refs.highlightedPointId === pointId ? null : pointId;
        resetAllHighlights();
        if (next !== null) {
          const pm = refs.pointMeshById.get(next);
          if (pm) (pm.material as THREE.MeshBasicMaterial).color.set(HIGHLIGHT_COLOR);
          refs.highlightedPointId = next;
          const pointInfo = points.find((p) => p.id === next);
          onSelectionChange?.({
            mode: "point",
            id: next,
            coordinate: pointInfo?.coordinate ?? [0, 0, 0],
          });
        } else {
          onSelectionChange?.(null);
        }
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
        const size = new THREE.Vector3();
        boundingBox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        sceneRefs.current.maxDim = maxDim;

        const positions = geometry.attributes.position.array as Float32Array;
        const normalsArr = geometry.attributes.normal.array as Float32Array;

        const partToTriangleIndices = buildGroupIndex(triangleToPart);
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
            // Kenar/nokta çizgileriyle z-fighting yaşamamak için (bkz. önceki
            // fix): dolu yüzeyi derinlik tamponunda hafifçe geriye it.
            polygonOffset: true,
            polygonOffsetFactor: 1,
            polygonOffsetUnits: 1,
          });
          const mesh = new THREE.Mesh(subGeometry, material);
          mesh.userData.partId = partId;
          mesh.position.sub(center);
          modelGroup.add(mesh);

          // Bu parçaya özel kenar çizgileri — parça gizlenince/gösterilince
          // ya da showEdges kapatılınca bu parçanın kendi çizgisi de
          // birlikte güncellenir (önceki global/tek-obje yaklaşımının
          // "hayalet kenar" sorununu önler).
          const edgesGeometry = new THREE.EdgesGeometry(subGeometry, 30);
          const edgesMaterial = new THREE.LineBasicMaterial({
            color: "#1b1f1c",
            transparent: true,
            opacity: 0.35,
          });
          const decorativeEdges = new THREE.LineSegments(edgesGeometry, edgesMaterial);
          decorativeEdges.visible = showEdgesRef.current;
          mesh.add(decorativeEdges);

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

        // NOT (geçmiş): Kenar çizgileri önce tüm modelden TEK bir global
        // obje olarak üretiliyordu — bu, bir parça gizlenince onun kenar
        // çizgilerinin "hayalet" gibi kalmasına sebep oluyordu. Şimdi her
        // parçanın kendi mesh'ine ÇOCUK olarak ekleniyor (yukarıda), böylece
        // parçayla birlikte otomatik gizlenip gösteriliyor.

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

        // Etkileşimli kenar çizgileri (Gmsh curve ID'li, Edge modunda görünür).
        // NOT: iki uç nokta arasında düz çizgi olarak çizilir — eğri kenarlarda
        // görsel bir yaklaşıklık, ama kimlik/uzunluk verisi backend'den kesin.
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
          const lineMaterial = new THREE.LineBasicMaterial({ color: "#1b1f1c" });
          const line = new THREE.Line(lineGeometry, lineMaterial);
          line.userData.edgeId = edge.id;
          interactiveEdgesGroup.add(line);
          edgeLineById.set(edge.id, line);
        }
        interactiveEdgesGroup.position.sub(center);
        interactiveEdgesGroup.visible = modeRef.current === "edge";
        modelGroup.add(interactiveEdgesGroup);

        // Nokta işaretçileri (Point modunda görünür).
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

        // Bu render anına kadar prop olarak gelmiş olabilecek hiddenParts'ı uygula.
        for (const entry of partMeshes) {
          entry.mesh.visible = !hiddenParts.has(entry.partId);
        }
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
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      controls.dispose();
      renderer.dispose();
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
        partMeshes: [],
        partMeshByPartId: new Map(),
        faceIdToPart: new Map(),
        interactiveEdgesGroup: null,
        pointsGroup: null,
        edgeLineById: new Map(),
        pointMeshById: new Map(),
        highlightedPartId: null,
        highlightedFaceId: null,
        highlightedEdgeId: null,
        highlightedPointId: null,
        externalHighlightedFaceIds: [],
        maxDim: 1,
      };
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stlUrl, edges, points, triangleToFace, triangleToPart]);

  // Mod değişimi: sahneyi yeniden kurmadan sadece görünürlük + vurgu sıfırlama.
  useEffect(() => {
    modeRef.current = mode;
    const refs = sceneRefs.current;

    for (const entry of refs.partMeshes) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
    }
    refs.highlightedPartId = null;
    refs.highlightedFaceId = null;
    refs.externalHighlightedFaceIds = [];

    if (refs.highlightedEdgeId !== null) {
      const line = refs.edgeLineById.get(refs.highlightedEdgeId);
      if (line) (line.material as THREE.LineBasicMaterial).color.set("#1b1f1c");
    }
    refs.highlightedEdgeId = null;

    if (refs.highlightedPointId !== null) {
      const pm = refs.pointMeshById.get(refs.highlightedPointId);
      if (pm) (pm.material as THREE.MeshBasicMaterial).color.set(POINT_BASE_COLOR);
    }
    refs.highlightedPointId = null;

    if (refs.interactiveEdgesGroup) refs.interactiveEdgesGroup.visible = mode === "edge";
    if (refs.pointsGroup) refs.pointsGroup.visible = mode === "point";

    onSelectionChange?.(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // hiddenParts değişimi: sahneyi yeniden kurmadan sadece görünürlük.
  // NOT: decorativeEdges her parçanın mesh'ine ÇOCUK olarak eklendiği için
  // (yukarıda), mesh.visible=false olunca kenar çizgileri de otomatik
  // gizleniyor — ayrı bir işlem gerekmiyor.
  useEffect(() => {
    const refs = sceneRefs.current;
    for (const entry of refs.partMeshes) {
      entry.mesh.visible = !hiddenParts.has(entry.partId);
    }
  }, [hiddenParts]);

  // showEdges değişimi: her parçanın kendi kenar çizgisinin görünürlüğünü
  // toplu güncelle (sahneyi yeniden kurmadan).
  useEffect(() => {
    showEdgesRef.current = showEdges;
    const refs = sceneRefs.current;
    for (const entry of refs.partMeshes) {
      entry.decorativeEdges.visible = showEdges;
    }
  }, [showEdges]);

  // externalHighlight değişimi: Physical Group butonu gibi tıklama-dışı vurgular.
  useEffect(() => {
    const refs = sceneRefs.current;

    // Önce tüm parçaların rengini sıfırla.
    for (const entry of refs.partMeshes) {
      const colors = entry.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      entry.colorAttribute.needsUpdate = true;
    }
    refs.highlightedPartId = null;
    refs.highlightedFaceId = null;

    if (externalHighlight) {
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
      refs.externalHighlightedFaceIds = externalHighlight.faceIds;
    } else {
      refs.externalHighlightedFaceIds = [];
    }
  }, [externalHighlight]);

  return <div ref={containerRef} className="viewer-canvas" />;
}

export default GeometryViewer;
