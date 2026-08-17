import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

interface GeometryViewerProps {
  stlUrl: string;
}

/**
 * Verilen STL URL'ini yükleyip döndürülebilir bir 3B görüntüleyicide gösterir.
 * Faz 0 / Geometri: sadece web önizleme (tessellation) — FEA mesh değil.
 *
 * Dikkat edilen noktalar:
 * - `DoubleSide` malzeme: STEP/IGES'ten gelen açık/ince kabuk yüzeyler (örn.
 *   sac parça, kavisli bracket) tek yönlü normal ile arkadan bakınca
 *   "delik/kurdele" gibi görünüyordu — çift taraflı render bunu çözer.
 * - Kenar (edge) çizgileri: düz gölgelendirmeyle birlikte yüzey sınırları
 *   net görünsün diye `EdgesGeometry` ile üstüne çizgi katmanı ekleniyor —
 *   gerçek CAD görüntüleyicilerindeki gibi.
 * - Kamera/kontrol parametreleri modelin boyutuna göre (bounding box'tan)
 *   dinamik ayarlanıyor; sabit değerler küçük/büyük modellerde fare
 *   hassasiyetini bozuyordu.
 */
function GeometryViewer({ stlUrl }: GeometryViewerProps) {
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

    const loader = new STLLoader();

    loader.load(
      stlUrl,
      (geometry) => {
        if (disposed) return;

        geometry.computeBoundingBox();
        geometry.computeVertexNormals();

        // Yüzey: hafif metalik olmayan, mat mühendislik-modeli görünümü.
        // DoubleSide: açık/tek katmanlı yüzeylerin arkadan bakınca
        // kaybolmaması için zorunlu.
        const material = new THREE.MeshStandardMaterial({
          color: "#5a8f73",
          metalness: 0.05,
          roughness: 0.65,
          flatShading: true,
          side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(geometry, material);
        modelGroup.add(mesh);

        // Kenar çizgileri: yüzeyler arasındaki gerçek geometrik kenarları
        // (threshold açısı üstündeki normal farklarını) çiz.
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

        // Kamera near/far ve kontrol mesafelerini modelin gerçek boyutuna
        // göre ayarla — sabit değerler küçük parçalarda "hassasiyet çok
        // kötü" hissi veriyordu (çok büyük adımlarla zoom/pan).
        camera.near = maxDim / 1000;
        camera.far = maxDim * 100;
        camera.updateProjectionMatrix();
        camera.position.set(maxDim * 1.4, maxDim * 1.1, maxDim * 1.4);
        camera.lookAt(0, 0, 0);

        controls.target.set(0, 0, 0);
        controls.minDistance = maxDim * 0.15;
        controls.maxDistance = maxDim * 8;
        controls.update();

        // Zemin ızgarası: ölçek/yön referansı için, modelin altına.
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
  }, [stlUrl]);

  return <div ref={containerRef} className="viewer-canvas" />;
}

export default GeometryViewer;
