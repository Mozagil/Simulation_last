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
  onSelectionChange?: (info: SelectionInfo | null) => void;
}

const BASE_COLOR = new THREE.Color("#5a8f73");
const HIGHLIGHT_COLOR = new THREE.Color("#d97757");
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

/**
 * STL'i yükleyip döndürülebilir bir 3B görüntüleyicide gösterir. `mode` prop'una
 * göre (Part/Surface/Edge/Point) tıklama farklı seviyede seçim yapar:
 * - Part/Surface: ana mesh üzerinde raycasting, ilgili grup (triangle_to_part /
 *   triangle_to_face) vertex-color ile vurgulanır.
 * - Edge: backend'den gelen kenar listesi (id, uç nokta koordinatları) ayrı
 *   çizgi objeleri olarak render edilir, tıklanan çizgi vurgulanır.
 *   NOT: kenarlar iki uç nokta arasında düz çizgi (kiriş) olarak çizilir —
 *   eğri (fillet gibi) kenarlarda bu görsel bir yaklaşıklık, ama kimlik/uzunluk
 *   verisi (backend'den) her zaman kesin OCC değeridir.
 * - Point: her köşe noktası küçük bir küre olarak render edilir, tıklanan
 *   nokta vurgulanır.
 *
 * Performans notu: sahne (mesh, ışıklar, kamera) sadece geometri değiştiğinde
 * yeniden kurulur; `mode` değişimi WebGL sahnesini yeniden kurmaz, sadece
 * görünürlük/vurgulama günceller.
 */
function GeometryViewer({
  stlUrl,
  triangleToFace,
  triangleToPart,
  edges,
  points,
  mode,
  onSelectionChange,
}: GeometryViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef<SelectionMode>(mode);

  // Sahne kurulumundan sonra oluşan, mod değişiminde erişilmesi gereken
  // nesneleri burada tutuyoruz (yeniden render tetiklemeden).
  const sceneRefs = useRef<{
    colorAttribute: THREE.BufferAttribute | null;
    faceToTriangleIndices: Map<number, number[]>;
    partToTriangleIndices: Map<number, number[]>;
    interactiveEdgesGroup: THREE.Group | null;
    pointsGroup: THREE.Group | null;
    edgeLineById: Map<number, THREE.Line>;
    pointMeshById: Map<number, THREE.Mesh>;
    highlightedGroupId: number | null;
    highlightedEdgeId: number | null;
    highlightedPointId: number | null;
    maxDim: number;
  }>({
    colorAttribute: null,
    faceToTriangleIndices: new Map(),
    partToTriangleIndices: new Map(),
    interactiveEdgesGroup: null,
    pointsGroup: null,
    edgeLineById: new Map(),
    pointMeshById: new Map(),
    highlightedGroupId: null,
    highlightedEdgeId: null,
    highlightedPointId: null,
    maxDim: 1,
  });

  // Ana sahne kurulumu — sadece geometri (stlUrl/edges/points) değiştiğinde.
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
    let pickMesh: THREE.Mesh | null = null;

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerDownPos: { x: number; y: number } | null = null;

    function resetHighlights() {
      const refs = sceneRefs.current;
      if (refs.colorAttribute) {
        const colors = refs.colorAttribute.array as Float32Array;
        for (let i = 0; i < colors.length; i += 3) {
          colors[i] = BASE_COLOR.r;
          colors[i + 1] = BASE_COLOR.g;
          colors[i + 2] = BASE_COLOR.b;
        }
        refs.colorAttribute.needsUpdate = true;
      }
      refs.highlightedGroupId = null;

      if (refs.highlightedEdgeId !== null) {
        const line = refs.edgeLineById.get(refs.highlightedEdgeId);
        if (line) (line.material as THREE.LineBasicMaterial).color.set("#1b1f1c");
      }
      refs.highlightedEdgeId = null;

      if (refs.highlightedPointId !== null) {
        const mesh = refs.pointMeshById.get(refs.highlightedPointId);
        if (mesh) (mesh.material as THREE.MeshBasicMaterial).color.set(BASE_COLOR);
      }
      refs.highlightedPointId = null;
    }

    function paintTriangleGroup(groupId: number | null, mapping: Map<number, number[]>) {
      const refs = sceneRefs.current;
      if (!refs.colorAttribute) return;
      const colors = refs.colorAttribute.array as Float32Array;

      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }

      if (groupId !== null) {
        const triangleIndices = mapping.get(groupId) ?? [];
        for (const triIndex of triangleIndices) {
          const base = triIndex * 3;
          for (let v = 0; v < 3; v++) {
            const offset = (base + v) * 3;
            colors[offset] = HIGHLIGHT_COLOR.r;
            colors[offset + 1] = HIGHLIGHT_COLOR.g;
            colors[offset + 2] = HIGHLIGHT_COLOR.b;
          }
        }
      }

      refs.colorAttribute.needsUpdate = true;
      refs.highlightedGroupId = groupId;
    }

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

      if ((currentMode === "surface" || currentMode === "part") && pickMesh) {
        const intersections = raycaster.intersectObject(pickMesh, false);
        if (intersections.length === 0 || intersections[0].faceIndex === undefined) {
          resetHighlights();
          onSelectionChange?.(null);
          return;
        }
        const triangleIndex = intersections[0].faceIndex as number;
        const mapping =
          currentMode === "surface" ? refs.faceToTriangleIndices : refs.partToTriangleIndices;
        const source = currentMode === "surface" ? triangleToFace : triangleToPart;
        const groupId = source[triangleIndex];
        if (groupId === undefined) return;

        const next = refs.highlightedGroupId === groupId ? null : groupId;
        resetHighlights();
        if (next !== null) {
          paintTriangleGroup(next, mapping);
          const count = mapping.get(next)?.length ?? 0;
          onSelectionChange?.({ mode: currentMode, id: next, triangleCount: count });
        } else {
          onSelectionChange?.(null);
        }
        return;
      }

      if (currentMode === "edge" && refs.interactiveEdgesGroup) {
        raycaster.params.Line = { threshold: refs.maxDim * 0.015 };
        const intersections = raycaster.intersectObjects(refs.interactiveEdgesGroup.children, false);
        if (intersections.length === 0) {
          resetHighlights();
          onSelectionChange?.(null);
          return;
        }
        const edgeId = intersections[0].object.userData.edgeId as number;
        const next = refs.highlightedEdgeId === edgeId ? null : edgeId;
        resetHighlights();
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
          resetHighlights();
          onSelectionChange?.(null);
          return;
        }
        const pointId = intersections[0].object.userData.pointId as number;
        const next = refs.highlightedPointId === pointId ? null : pointId;
        resetHighlights();
        if (next !== null) {
          const mesh = refs.pointMeshById.get(next);
          if (mesh) (mesh.material as THREE.MeshBasicMaterial).color.set(HIGHLIGHT_COLOR);
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

        const vertexCount = geometry.attributes.position.count;
        const colors = new Float32Array(vertexCount * 3);
        for (let i = 0; i < colors.length; i += 3) {
          colors[i] = BASE_COLOR.r;
          colors[i + 1] = BASE_COLOR.g;
          colors[i + 2] = BASE_COLOR.b;
        }
        const colorAttribute = new THREE.BufferAttribute(colors, 3);
        geometry.setAttribute("color", colorAttribute);

        const material = new THREE.MeshStandardMaterial({
          vertexColors: true,
          metalness: 0.05,
          roughness: 0.65,
          flatShading: true,
          side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(geometry, material);
        modelGroup.add(mesh);
        pickMesh = mesh;

        // Dekoratif kenar çizgileri (geometrik olarak otomatik tespit edilen,
        // Gmsh ID'siyle ilişkisi yok) — her zaman görünür, sadece görsel.
        const decorativeEdgesGeometry = new THREE.EdgesGeometry(geometry, 20);
        const decorativeEdgesMaterial = new THREE.LineBasicMaterial({
          color: "#1b1f1c",
          transparent: true,
          opacity: 0.35,
        });
        const decorativeEdges = new THREE.LineSegments(decorativeEdgesGeometry, decorativeEdgesMaterial);
        modelGroup.add(decorativeEdges);

        const boundingBox = geometry.boundingBox;
        if (!boundingBox) return;

        const center = new THREE.Vector3();
        boundingBox.getCenter(center);
        modelGroup.position.sub(center);

        const size = new THREE.Vector3();
        boundingBox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        sceneRefs.current.maxDim = maxDim;

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
        const pointById = new Map(points.map((p) => [p.id, p.coordinate] as const));
        const interactiveEdgesGroup = new THREE.Group();
        const edgeLineById = new Map<number, THREE.Line>();
        for (const edge of edges) {
          const startCoord = pointById.get(edge.start_point);
          const endCoord = pointById.get(edge.end_point);
          if (!startCoord || !endCoord) continue;

          const lineGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(...startCoord).sub(center),
            new THREE.Vector3(...endCoord).sub(center),
          ]);
          const lineMaterial = new THREE.LineBasicMaterial({ color: "#1b1f1c" });
          const line = new THREE.Line(lineGeometry, lineMaterial);
          line.userData.edgeId = edge.id;
          interactiveEdgesGroup.add(line);
          edgeLineById.set(edge.id, line);
        }
        interactiveEdgesGroup.visible = modeRef.current === "edge";
        modelGroup.add(interactiveEdgesGroup);

        // Nokta işaretçileri (Point modunda görünür).
        const pointsGroup = new THREE.Group();
        const pointMeshById = new Map<number, THREE.Mesh>();
        const pointRadius = Math.max(maxDim * 0.015, 0.05);
        const sphereGeometry = new THREE.SphereGeometry(pointRadius, 12, 12);
        for (const point of points) {
          const pointMaterial = new THREE.MeshBasicMaterial({ color: BASE_COLOR });
          const sphere = new THREE.Mesh(sphereGeometry, pointMaterial);
          sphere.position.set(...point.coordinate).sub(center);
          sphere.userData.pointId = point.id;
          pointsGroup.add(sphere);
          pointMeshById.set(point.id, sphere);
        }
        pointsGroup.visible = modeRef.current === "point";
        modelGroup.add(pointsGroup);

        sceneRefs.current.colorAttribute = colorAttribute;
        sceneRefs.current.faceToTriangleIndices = buildGroupIndex(triangleToFace);
        sceneRefs.current.partToTriangleIndices = buildGroupIndex(triangleToPart);
        sceneRefs.current.interactiveEdgesGroup = interactiveEdgesGroup;
        sceneRefs.current.pointsGroup = pointsGroup;
        sceneRefs.current.edgeLineById = edgeLineById;
        sceneRefs.current.pointMeshById = pointMeshById;
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
        colorAttribute: null,
        faceToTriangleIndices: new Map(),
        partToTriangleIndices: new Map(),
        interactiveEdgesGroup: null,
        pointsGroup: null,
        edgeLineById: new Map(),
        pointMeshById: new Map(),
        highlightedGroupId: null,
        highlightedEdgeId: null,
        highlightedPointId: null,
        maxDim: 1,
      };
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stlUrl, edges, points, triangleToFace, triangleToPart]);

  // Mod değişimi: sahneyi yeniden kurmadan sadece görünürlük + vurgu sıfırlama.
  useEffect(() => {
    modeRef.current = mode;
    const refs = sceneRefs.current;

    if (refs.colorAttribute) {
      const colors = refs.colorAttribute.array as Float32Array;
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }
      refs.colorAttribute.needsUpdate = true;
    }
    refs.highlightedGroupId = null;

    if (refs.highlightedEdgeId !== null) {
      const line = refs.edgeLineById.get(refs.highlightedEdgeId);
      if (line) (line.material as THREE.LineBasicMaterial).color.set("#1b1f1c");
    }
    refs.highlightedEdgeId = null;

    if (refs.highlightedPointId !== null) {
      const meshObj = refs.pointMeshById.get(refs.highlightedPointId);
      if (meshObj) (meshObj.material as THREE.MeshBasicMaterial).color.set(BASE_COLOR);
    }
    refs.highlightedPointId = null;

    if (refs.interactiveEdgesGroup) refs.interactiveEdgesGroup.visible = mode === "edge";
    if (refs.pointsGroup) refs.pointsGroup.visible = mode === "point";

    onSelectionChange?.(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  return <div ref={containerRef} className="viewer-canvas" />;
}

export default GeometryViewer;
