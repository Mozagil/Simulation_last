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

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);
    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight2.position.set(-1, -1, -1);
    scene.add(directionalLight2);

    const loader = new STLLoader();
    let mesh: THREE.Mesh | null = null;

    loader.load(
      stlUrl,
      (geometry) => {
        if (disposed) return;

        geometry.computeBoundingBox();
        geometry.computeVertexNormals();

        const material = new THREE.MeshStandardMaterial({
          color: "#5a8f73",
          metalness: 0.1,
          roughness: 0.6,
        });
        mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);

        // Geometriyi orta noktaya göre ortalayıp kamerayı boyutuna göre konumla.
        const boundingBox = geometry.boundingBox;
        if (boundingBox) {
          const center = new THREE.Vector3();
          boundingBox.getCenter(center);
          mesh.position.sub(center);

          const size = new THREE.Vector3();
          boundingBox.getSize(size);
          const maxDim = Math.max(size.x, size.y, size.z) || 1;

          camera.position.set(maxDim * 1.5, maxDim * 1.2, maxDim * 1.5);
          camera.lookAt(0, 0, 0);
          controls.target.set(0, 0, 0);
          controls.update();
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
      controls.dispose();
      renderer.dispose();
      if (mesh) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [stlUrl]);

  return <div ref={containerRef} className="viewer-canvas" />;
}

export default GeometryViewer;
