import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

interface GeometryViewerProps {
  stlUrl: string;
  /** STL'deki i. üçgenin ait olduğu Gmsh yüzey (face) tag'i. */
  triangleToFace: number[];
  /** Kullanıcı bir yüzeye tıkladığında çağrılır (face tag + o yüzeydeki üçgen sayısı). */
  onFaceSelect?: (faceTag: number | null, triangleCount: number) => void;
}

const BASE_COLOR = new THREE.Color("#5a8f73");
const HIGHLIGHT_COLOR = new THREE.Color("#d97757");
const CLICK_DRAG_THRESHOLD_PX = 6;

/**
 * Verilen STL URL'ini yükleyip döndürülebilir bir 3B görüntüleyicide gösterir.
 * `triangleToFace` eşlemesi verildiyse, kullanıcı bir yüzeye tıkladığında
 * (raycasting ile) o yüzeye ait tüm üçgenleri vurgular.
 *
 * Diğer görsel kalite notları (DoubleSide, edges, kalibre kamera) için bkz.
 * önceki commit — açık/ince kabuk yüzeylerde "yırtık" görünümü önlüyor.
 */
function GeometryViewer({ stlUrl, triangleToFace, onFaceSelect }: GeometryViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

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
    let colorAttribute: THREE.BufferAttribute | null = null;
    // face tag -> o yüzeye ait üçgen indeksleri (vertex boyama için).
    let faceToTriangleIndices: Map<number, number[]> = new Map();
    let highlightedFaceTag: number | null = null;

    function paintFace(faceTag: number | null) {
      if (!colorAttribute) return;
      const colors = colorAttribute.array as Float32Array;

      // Önce her şeyi taban renge döndür.
      for (let i = 0; i < colors.length; i += 3) {
        colors[i] = BASE_COLOR.r;
        colors[i + 1] = BASE_COLOR.g;
        colors[i + 2] = BASE_COLOR.b;
      }

      if (faceTag !== null) {
        const triangleIndices = faceToTriangleIndices.get(faceTag) ?? [];
        for (const triIndex of triangleIndices) {
          // Her üçgen 3 vertex'ten oluşur, her vertex 3 float (r,g,b).
          const base = triIndex * 3;
          for (let v = 0; v < 3; v++) {
            const offset = (base + v) * 3;
            colors[offset] = HIGHLIGHT_COLOR.r;
            colors[offset + 1] = HIGHLIGHT_COLOR.g;
            colors[offset + 2] = HIGHLIGHT_COLOR.b;
          }
        }
      }

      colorAttribute.needsUpdate = true;
      highlightedFaceTag = faceTag;
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerDownPos: { x: number; y: number } | null = null;

    function handlePointerDown(event: PointerEvent) {
      pointerDownPos = { x: event.clientX, y: event.clientY };
    }

    function handlePointerUp(event: PointerEvent) {
      if (!pointerDownPos || !pickMesh) return;
      const dx = event.clientX - pointerDownPos.x;
      const dy = event.clientY - pointerDownPos.y;
      const movedDistance = Math.sqrt(dx * dx + dy * dy);
      pointerDownPos = null;

      // Kamera döndürme/pan sürüklemesini tıklama sanmamak için eşik kontrolü.
      if (movedDistance > CLICK_DRAG_THRESHOLD_PX) return;

      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersections = raycaster.intersectObject(pickMesh, false);

      if (intersections.length === 0 || intersections[0].faceIndex === undefined) {
        paintFace(null);
        onFaceSelect?.(null, 0);
        return;
      }

      const triangleIndex = intersections[0].faceIndex as number;
      const faceTag = triangleToFace[triangleIndex];
      if (faceTag === undefined) return;

      const nextFaceTag = highlightedFaceTag === faceTag ? null : faceTag;
      paintFace(nextFaceTag);
      const count = nextFaceTag === null ? 0 : (faceToTriangleIndices.get(faceTag)?.length ?? 0);
      onFaceSelect?.(nextFaceTag, count);
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
        colorAttribute = new THREE.BufferAttribute(colors, 3);
        geometry.setAttribute("color", colorAttribute);

        faceToTriangleIndices = new Map();
        triangleToFace.forEach((faceTag, triIndex) => {
          const list = faceToTriangleIndices.get(faceTag);
          if (list) {
            list.push(triIndex);
          } else {
            faceToTriangleIndices.set(faceTag, [triIndex]);
          }
        });

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

        const edgesGeometry = new THREE.EdgesGeometry(geometry, 20);
        const edgesMaterial = new THREE.LineBasicMaterial({
          color: "#1b1f1c",
          transparent: true,
          opacity: 0.35,
        });
        const edges = new THREE.LineSegments(edgesGeometry, edgesMaterial);
        modelGroup.add(edges);

        const boundingBox = geometry.boundingBox;
        if (!boundingBox) return;

        const center = new THREE.Vector3();
        boundingBox.getCenter(center);
        modelGroup.position.sub(center);

        const size = new THREE.Vector3();
        boundingBox.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;

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
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          const material = obj.material as THREE.Material | THREE.Material[];
          if (Array.isArray(material)) {
            material.forEach((m) => m.dispose());
          } else {
            material.dispose();
          }
        }
      });
      if (gridHelper) {
        gridHelper.geometry.dispose();
        (gridHelper.material as THREE.Material).dispose();
      }
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [stlUrl, triangleToFace, onFaceSelect]);

  return <div ref={containerRef} className="viewer-canvas" />;
}

export default GeometryViewer;
