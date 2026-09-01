import { useCallback, useEffect, useRef, useState } from "react";
import {
  EdgeInfo,
  GeometryUploadError,
  PhysicalGroup,
  MeshGenerateResponse,
  PointInfo,
  copySurface,
  createMidsurface,
  createMidsurfaceForPart,
  createPhysicalGroup,
  fetchEdges,
  fetchPhysicalGroups,
  fetchPoints,
  applyDefeature,
  generateMesh,
  fetchMeshPreview,
  fetchMeshQuality,
  healGeometry,
  undoLastMutation,
  resolveTessellationUrl,
  uploadGeometry,
  type MeshElementScheme,
  type MeshPreviewData,
  type MeshQualityResponse,
} from "./api/geometry";
import {
  assignMaterial,
  createMaterial,
  fetchMaterialAssignments,
  fetchMaterials,
  formatGPa,
  formatMPa,
  setMaterialSnCurve,
  solveGeometry,
  type Material,
  type MaterialAssignment,
  type SolveBC,
  type SolveResponse,
} from "./api/materials";
import {
  fetchProductTree,
  upsertComponent,
  patchComponent,
  ensureDefaultComponents,
  type ProductTree,
  type ProductTreeItem,
  type PropertyKind,
} from "./api/components";
import ButtonGroup from "./components/ButtonGroup";
import GeometryViewer from "./components/GeometryViewer";
import {
  type MeshGrowMode,
  type MeshPickInfo,
  type MultiSelectionInfo,
  SELECTION_MODES,
  type SelectionMode,
} from "./types";

type Status = "idle" | "uploading" | "error" | "success";

const ACCEPTED_EXTENSIONS = ".step,.stp,.igs,.iges";
const EMPTY_SELECTION: MultiSelectionInfo = { mode: "surface", ids: [] };

type BcKind =
  | "fixed"
  | "cload"
  | "pressure"
  | "displacement"
  | "sliding"
  | "bearing"
  | "gravity";

interface BcListItem {
  id: string;
  kind: BcKind;
  summary: string;
  payload: SolveBC;
}

const BC_KIND_LABELS: Record<BcKind, string> = {
  fixed: "Fixed",
  cload: "Nokta/yüzey yük",
  pressure: "Pressure",
  displacement: "Displacement",
  sliding: "Sliding",
  bearing: "Bearing",
  gravity: "Gravity",
};

const BC_KIND_HINTS: Record<BcKind, string> = {
  fixed: "Seçim: mesh yüzeyi (Face) veya CAD yüzey/kenar/nokta. Alan yok.",
  cload: "Seçim: mesh yüzeyi veya CAD yüzey/nokta. Fx/Fy/Fz toplam kuvvet.",
  pressure: "Seçim: mesh veya CAD yüzeyi. |P| ve isteğe bağlı yön.",
  displacement: "Seçim: mesh yüzeyi veya CAD yüzey/kenar/nokta. Ux/Uy/Uz.",
  sliding: "Seçim: mesh veya CAD yüzeyi/kenarı. Kayma düzlemi normali.",
  bearing: "Seçim: mesh veya CAD yüzeyi. Büyüklük + eksen.",
  gravity: "Seçim gerekmez. gx/gy/gz (mm/s², varsayılan −9810).",
};

function uniquePartIdsFromPreview(preview: MeshPreviewData | null): number[] {
  const parts = new Set<number>(preview?.triangle_to_part ?? [0]);
  if (parts.size === 0) parts.add(0);
  return [...parts].sort((a, b) => a - b);
}

function suggestedEdgeNodes(length: number, size: number): number {
  if (!(size > 0) || !(length > 0)) return 2;
  return Math.max(2, Math.round(length / size) + 1);
}

function ProductTreeRow({
  item,
  materials,
  busy,
  onSave,
}: {
  item: ProductTreeItem;
  materials: Material[];
  busy: boolean;
  onSave: (componentId: number, thickness: string, materialId: number | null) => void;
}) {
  const component = item.component;
  const [thickness, setThickness] = useState(String(item.thickness ?? ""));
  const [materialId, setMaterialId] = useState<number | "">(
    component?.material_id ?? "",
  );
  if (!component) return null;
  return (
    <li className="product-tree-item">
      <div className="product-tree-row">
        <strong>{component.name}</strong>
        <span className="product-tree-meta">{item.label}</span>
      </div>
      <div className="product-tree-props">
        {component.property_kind === "shell" && (
          <label className="mesh-field">
            <span>Kalınlık</span>
            <input value={thickness} onChange={(e) => setThickness(e.target.value)} />
          </label>
        )}
        <label className="mesh-field">
          <span>Malzeme</span>
          <select
            value={materialId}
            onChange={(e) =>
              setMaterialId(e.target.value === "" ? "" : Number(e.target.value))
            }
          >
            <option value="">— seçin —</option>
            {materials.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="material-secondary-button"
          disabled={busy}
          onClick={() =>
            onSave(component.id, thickness, materialId === "" ? null : materialId)
          }
        >
          Kaydet
        </button>
      </div>
    </li>
  );
}

function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [geometryId, setGeometryId] = useState<number | null>(null);
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [triangleToFace, setTriangleToFace] = useState<number[]>([]);
  const [triangleToPart, setTriangleToPart] = useState<number[]>([]);
  const [volumePartIds, setVolumePartIds] = useState<number[]>([]);
  const [faceCount, setFaceCount] = useState<number | null>(null);
  const [partCount, setPartCount] = useState<number | null>(null);
  const [edges, setEdges] = useState<EdgeInfo[]>([]);
  const [points, setPoints] = useState<PointInfo[]>([]);
  const [mode, setMode] = useState<SelectionMode>("surface");
  const [selection, setSelection] = useState<MultiSelectionInfo>(EMPTY_SELECTION);
  const [hiddenParts, setHiddenParts] = useState<Set<number>>(new Set());
  const [showEdges, setShowEdges] = useState(true);
  const [physicalGroups, setPhysicalGroups] = useState<PhysicalGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  /** Aktif yükleme kimliği — eski kenar/nokta yanıtlarının state'i ezmesini engeller. */
  const activeGeometryIdRef = useRef<number | null>(null);

  // Mesh paneli (viewer sağında)
  const [meshElementSize, setMeshElementSize] = useState("5");
  const [meshDimension, setMeshDimension] = useState<2 | 3>(2);
  const [meshScheme, setMeshScheme] = useState<MeshElementScheme>("quad");
  const [meshResult, setMeshResult] = useState<MeshGenerateResponse | null>(null);
  const [meshPreview, setMeshPreview] = useState<MeshPreviewData | null>(null);
  const [showMesh, setShowMesh] = useState(true);
  const [meshWireframe, setMeshWireframe] = useState(false);
  const [cadOpacityPct, setCadOpacityPct] = useState(100);
  const [meshQuality, setMeshQuality] = useState<MeshQualityResponse | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [materialAssignments, setMaterialAssignments] = useState<MaterialAssignment[]>([]);
  const [customName, setCustomName] = useState("");
  const [customE, setCustomE] = useState("210"); // GPa
  const [customNu, setCustomNu] = useState("0.3");
  const [customRho, setCustomRho] = useState("7850");
  const [customFy, setCustomFy] = useState("235"); // MPa
  const [customRm, setCustomRm] = useState("360"); // MPa
  const [snEstimate, setSnEstimate] = useState(true);
  const [solveResult, setSolveResult] = useState<SolveResponse | null>(null);
  const [bcList, setBcList] = useState<BcListItem[]>([]);
  const [bcDraftKind, setBcDraftKind] = useState<BcKind>("fixed");
  const [bcFx, setBcFx] = useState("0");
  const [bcFy, setBcFy] = useState("0");
  const [bcFz, setBcFz] = useState("-1000");
  const [bcMagnitude, setBcMagnitude] = useState("1e5");
  const [bcUx, setBcUx] = useState("0");
  const [bcUy, setBcUy] = useState("0");
  const [bcUz, setBcUz] = useState("0");
  const [bcNx, setBcNx] = useState("0");
  const [bcNy, setBcNy] = useState("0");
  const [bcNz, setBcNz] = useState("1");
  const [bcAx, setBcAx] = useState("0");
  const [bcAy, setBcAy] = useState("0");
  const [bcAz, setBcAz] = useState("-1");
  const [bcGx, setBcGx] = useState("0");
  const [bcGy, setBcGy] = useState("0");
  const [bcGz, setBcGz] = useState("-9810");
  const [shellThickness, setShellThickness] = useState("3");
  const [runCcx, setRunCcx] = useState(false);
  const [meshPicks, setMeshPicks] = useState<MeshPickInfo[]>([]);
  const [meshGrow, setMeshGrow] = useState<MeshGrowMode>("element");
  const [productTree, setProductTree] = useState<ProductTree | null>(null);
  const [componentName, setComponentName] = useState("");
  const [propertyKind, setPropertyKind] = useState<PropertyKind>("shell");
  const [edgeNodeCounts, setEdgeNodeCounts] = useState<Record<number, number>>({});
  const edgeSeedManualRef = useRef(new Set<number>());

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Malzeme kütüphanesini bir kez yükle.
  useEffect(() => {
    let cancelled = false;
    void fetchMaterials()
      .then((list) => {
        if (cancelled) return;
        setMaterials(list);
        if (list.length > 0) setSelectedMaterialId(list[0].id);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.error(err);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const size = parseFloat(meshElementSize);
    const elemSize = Number.isFinite(size) && size > 0 ? size : 5;
    setEdgeNodeCounts((prev) => {
      const next = { ...prev };
      for (const e of edges) {
        if (edgeSeedManualRef.current.has(e.id)) continue;
        next[e.id] = suggestedEdgeNodes(e.length, elemSize);
      }
      return next;
    });
  }, [edges, meshElementSize]);

  // Mod değişince aktif grup vurgusu anlamsızlaşır, temizle.
  useEffect(() => {
    setActiveGroupId(null);
  }, [mode]);

  async function handleFileSelected(file: File) {
    setStatus("uploading");
    setErrorMessage(null);
    setInfoMessage(null);
    setFileName(file.name);
    setSelection(EMPTY_SELECTION);
    setMode("surface");
    setHiddenParts(new Set());
    setActiveGroupId(null);
    setNewGroupName("");
    setCanUndo(false);
    setMeshResult(null);
    setMeshPreview(null);
    setShowMesh(true);
    setMeshWireframe(false);
    setMeshQuality(null);
    setMaterialAssignments([]);
    setSolveResult(null);
    setMeshPicks([]);
    setMeshGrow("element");
    setProductTree(null);
    setComponentName("");
    setEdgeNodeCounts({});
    edgeSeedManualRef.current = new Set();

    try {
      const result = await uploadGeometry(file);
      activeGeometryIdRef.current = result.geometry_id;
      setGeometryId(result.geometry_id);
      setStlUrl(resolveTessellationUrl(result.tessellation_url));
      setTriangleToFace(result.triangle_to_face);
      setTriangleToPart(result.triangle_to_part);
      setVolumePartIds(result.volume_part_ids);
      setFaceCount(result.face_count);
      setPartCount(result.part_count);
      setEdges([]);
      setPoints([]);
      setPhysicalGroups([]);
      // Önizlemeyi kenar/nokta bitmeden göster — büyük STEP'lerde edges/points
      // Gmsh kilidini uzun süre tutup UI'yi "Yükleniyor"da bırakıyordu.
      setStatus("success");
      setInfoMessage("Önizleme hazır. Kenar/nokta listesi arka planda yükleniyor…");

      const geoId = result.geometry_id;
      void (async () => {
        try {
          const [edgeList, pointList, groupList, assignments] = await Promise.all([
            fetchEdges(geoId),
            fetchPoints(geoId),
            fetchPhysicalGroups(geoId),
            fetchMaterialAssignments(geoId),
          ]);
          if (activeGeometryIdRef.current !== geoId) return;
          setEdges(edgeList);
          setPoints(pointList);
          setPhysicalGroups(groupList);
          setMaterialAssignments(assignments);
          setInfoMessage(null);
        } catch (err) {
          if (activeGeometryIdRef.current !== geoId) return;
          const message =
            err instanceof GeometryUploadError
              ? err.message
              : "Kenar/nokta listesi yüklenemedi (önizleme kullanılabilir).";
          setErrorMessage(message);
        }
      })();
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Beklenmeyen bir hata oluştu.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      void handleFileSelected(file);
    }
  }

  function handleReset() {
    activeGeometryIdRef.current = null;
    setStatus("idle");
    setErrorMessage(null);
    setInfoMessage(null);
    setFileName(null);
    setGeometryId(null);
    setStlUrl(null);
    setTriangleToFace([]);
    setTriangleToPart([]);
    setVolumePartIds([]);
    setFaceCount(null);
    setPartCount(null);
    setEdges([]);
    setPoints([]);
    setSelection(EMPTY_SELECTION);
    setMode("surface");
    setHiddenParts(new Set());
    setShowEdges(true);
    setPhysicalGroups([]);
    setActiveGroupId(null);
    setNewGroupName("");
    setCanUndo(false);
    setMeshResult(null);
    setMeshPreview(null);
    setShowMesh(true);
    setMeshWireframe(false);
    setMeshQuality(null);
    setMaterialAssignments([]);
    setMeshPicks([]);
    setMeshGrow("element");
    setProductTree(null);
    setComponentName("");
    setEdgeNodeCounts({});
    edgeSeedManualRef.current = new Set();
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const handleSelectionChange = useCallback((info: MultiSelectionInfo) => {
    setSelection(info);
    setMode(info.mode);
    setMeshPicks([]);
    setMeshGrow("element");
  }, []);

  const handleMeshPicks = useCallback((picks: MeshPickInfo[], keepGrow: boolean) => {
    setMeshPicks(picks);
    if (picks.length === 0 || !keepGrow) setMeshGrow("element");
    if (picks.length > 0) {
      setMode("part");
      if (!keepGrow) setSelection({ mode: "part", ids: [] });
    }
  }, []);

  function handleMeshGrow(grow: MeshGrowMode) {
    if (meshPicks.length === 0) return;
    setMeshGrow(grow);
    if (grow === "attached") {
      const ids = [...new Set(meshPicks.map((p) => p.partId))];
      setMode("part");
      setSelection({ mode: "part", ids });
    }
  }

  /** Bir mutasyon işleminden (copy/heal/midsurface) sonra ortak yenileme. */
  async function refreshAfterMutation(
    geoId: number,
    tessellation: {
      triangle_to_face: number[];
      triangle_to_part: number[];
      face_count: number;
      part_count: number;
      tessellation_url: string;
      volume_part_ids: number[];
    },
  ) {
    setTriangleToFace(tessellation.triangle_to_face);
    setTriangleToPart(tessellation.triangle_to_part);
    setFaceCount(tessellation.face_count);
    setPartCount(tessellation.part_count);
    setVolumePartIds(tessellation.volume_part_ids);
    setStlUrl(resolveTessellationUrl(tessellation.tessellation_url, Date.now()));
    setSelection((prev) => ({ mode: prev.mode, ids: [] }));
    setCanUndo(true);

    const [edgeList, pointList] = await Promise.all([fetchEdges(geoId), fetchPoints(geoId)]);
    setEdges(edgeList);
    setPoints(pointList);
  }

  async function handleCopySurface() {
    if (!geometryId || mode !== "surface" || selection.ids.length !== 1) return;

    setBusyAction("copy");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await copySurface(geometryId, selection.ids[0]);
      await refreshAfterMutation(geometryId, result);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Yüzey kopyalanamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  /** Aktif moddaki seçimi (hangi mod olursa olsun) ilgili parça id'lerine
   * çözümler — "Solid gizle/göster" artık sadece Parça modunda değil, her
   * modda (Yüzey/Kenar/Nokta) seçili öğenin ait olduğu parça(lar) üzerinde
   * çalışabilsin diye.
   */
  function resolvePartIdsForSelection(sel: MultiSelectionInfo): number[] {
    if (sel.ids.length === 0) return [];
    switch (sel.mode) {
      case "part":
        return sel.ids;
      case "surface": {
        // triangleToFace / triangleToPart aynı üçgen indeksine göre paralel
        // dizilerdir — bir face_id'nin part_id'sini bulmak için bu üçgen
        // eşleşmesini kullanıyoruz.
        const partIds = new Set<number>();
        for (const faceId of sel.ids) {
          const triIndex = triangleToFace.indexOf(faceId);
          if (triIndex !== -1) partIds.add(triangleToPart[triIndex]);
        }
        return [...partIds];
      }
      case "edge": {
        const partIds = new Set<number>();
        for (const edgeId of sel.ids) {
          const edge = edges.find((e) => e.id === edgeId);
          if (edge) partIds.add(edge.part_id);
        }
        return [...partIds];
      }
      case "point": {
        const partIds = new Set<number>();
        for (const pointId of sel.ids) {
          const point = points.find((p) => p.id === pointId);
          if (point) partIds.add(point.part_id);
        }
        return [...partIds];
      }
    }
  }

  function toggleHiddenPartIds(targetPartIds: number[]) {
    if (targetPartIds.length === 0) return;
    setHiddenParts((prev) => {
      const next = new Set(prev);
      const allHidden = targetPartIds.every((id) => next.has(id));
      for (const id of targetPartIds) {
        if (allHidden) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  function handleToggleHidePart() {
    // Hiçbir şey seçili değilse TÜM gerçek solid'leri hedefle (global
    // göster/gizle) — "Solid gizle/göster" her zaman aktif olmalı, seçim
    // şartı aranmıyor. Sadece GERÇEK solid'ler (volume_part_ids) hedeflenir
    // — copy_surface/midsurface çıktısı gibi düz yüzeyler HİÇBİR ZAMAN
    // hedeflenmez, çünkü bunlar "solid" değil.
    const volumeSet = new Set(volumePartIds);
    const targetPartIds =
      selection.ids.length > 0
        ? resolvePartIdsForSelection(selection).filter((id) => volumeSet.has(id))
        : volumePartIds;
    toggleHiddenPartIds(targetPartIds);
  }

  function handleToggleHideSurfaces() {
    // Solid'den ayrı: midsurface / yüzey kopyası gibi hacimsiz CAD parçaları.
    const volumeSet = new Set(volumePartIds);
    const allSurfaceIds: number[] = [];
    const seen = new Set<number>();
    for (const pid of triangleToPart) {
      if (pid < 0 || volumeSet.has(pid) || seen.has(pid)) continue;
      seen.add(pid);
      allSurfaceIds.push(pid);
    }
    const fromSelection =
      selection.ids.length > 0
        ? resolvePartIdsForSelection(selection).filter((id) => seen.has(id))
        : [];
    toggleHiddenPartIds(fromSelection.length > 0 ? fromSelection : allSurfaceIds);
  }

  async function handleCreatePhysicalGroup() {
    const trimmedName = newGroupName.trim();
    if (!geometryId || mode !== "surface" || selection.ids.length === 0) return;
    if (!trimmedName) return;

    setBusyAction("create-group");
    setErrorMessage(null);
    try {
      await createPhysicalGroup(geometryId, trimmedName, selection.ids);
      setNewGroupName("");
      const groups = await fetchPhysicalGroups(geometryId);
      setPhysicalGroups(groups);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Grup oluşturulamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  function handleGroupButtonClick(groupId: number) {
    setActiveGroupId((prev) => (prev === groupId ? null : groupId));
  }

  async function handleHeal() {
    if (!geometryId) return;
    if (
      !window.confirm(
        "Geometry healing (delik kapatma dahil) geometriyi değiştirebilir ve yüzey/kenar " +
          "numaralarını yeniden düzenleyebilir — mevcut Physical Group atamalarınız yanlış " +
          "yüzeyleri işaret eder hale gelebilir. Devam etmek istiyor musunuz?",
      )
    ) {
      return;
    }

    setBusyAction("heal");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await healGeometry(geometryId);
      await refreshAfterMutation(geometryId, result);
      setInfoMessage(
        `Heal tamamlandı (tolerans + silindirik delik kapatma): parça ` +
          `${result.volumes_before}→${result.volumes_after}, ` +
          `yüzey ${result.surfaces_before}→${result.surfaces_after}. ` +
          `Yüzey numaraları değişmiş olabilir — mevcut Physical Group atamalarınızı kontrol edin.`,
      );
      const groups = await fetchPhysicalGroups(geometryId);
      setPhysicalGroups(groups);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Healing başarısız oldu.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleApplyDefeature() {
    if (!geometryId) return;

    const faceIds =
      selection.mode === "surface" && selection.ids.length > 0 ? [...selection.ids] : [];

    // Mid radyusları görünsün diye solid'leri gizle
    if (volumePartIds.length > 0) {
      setHiddenParts(new Set(volumePartIds));
    }
    setMode("surface");
    setErrorMessage(null);
    setBusyAction("defeature");
    setInfoMessage(null);
    try {
      let result;
      if (faceIds.length > 0) {
        try {
          result = await applyDefeature(geometryId, { faceIds });
        } catch {
          // Solid yüzeyi seçildiyse mid kabuktaki tüm radyusları kaldır
          result = await applyDefeature(geometryId, { maxRadius: 50 });
        }
      } else {
        result = await applyDefeature(geometryId, { maxRadius: 50 });
      }
      await refreshAfterMutation(geometryId, result);
      setSelection(EMPTY_SELECTION);
      setInfoMessage(
        `Fillet kaldırıldı: yüzey ${result.surfaces_before}→${result.surfaces_after} (keskin köşe).`,
      );
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Defeature başarısız.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleGenerateMesh() {
    if (!geometryId) return;
    const size = parseFloat(meshElementSize);
    if (!Number.isFinite(size) || size <= 0) {
      setErrorMessage("Geçerli bir pozitif mesh boyutu girin.");
      return;
    }

    setBusyAction("mesh");
    setErrorMessage(null);
    setInfoMessage(null);
    setMeshPreview(null);
    setMeshQuality(null);
    setMeshPicks([]);
    setMeshGrow("element");
    try {
      const result = await generateMesh(
        geometryId,
        size,
        meshDimension,
        meshScheme,
        edgeNodeCounts,
      );
      setMeshResult(result);
      setMeshDimension(result.dimension === 3 ? 3 : 2);
      if (result.element_scheme === "tet" || result.element_scheme === "quad" || result.element_scheme === "mix") {
        setMeshScheme(result.element_scheme);
      }
      if (result.preview_url) {
        const preview = await fetchMeshPreview(result.preview_url);
        setMeshPreview(preview);
        setShowMesh(true);
        setPropertyKind(result.dimension === 2 ? "shell" : "solid");
        const partIds = uniquePartIdsFromPreview(preview);
        const thickness = parseFloat(shellThickness);
        try {
          await ensureDefaultComponents(geometryId, {
            part_ids: partIds,
            property_kind: result.dimension === 2 ? "shell" : "solid",
            thickness:
              result.dimension === 2 && Number.isFinite(thickness) && thickness > 0
                ? thickness
                : result.dimension === 2
                  ? 3
                  : null,
            material_id: selectedMaterialId,
          });
          const tree = await fetchProductTree(geometryId, 0);
          setProductTree(tree);
          const assignments = await fetchMaterialAssignments(geometryId);
          setMaterialAssignments(assignments);
        } catch (compErr) {
          console.error(compErr);
        }
      }
      const dim = result.dimension === 3 ? 3 : 2;
      setInfoMessage(
        `Mesh üretildi (${dim === 2 ? "2D shell" : "3D solid"}): ` +
          `${result.node_count} düğüm, ${result.element_count} eleman. ` +
          `Varsayılan component ürün ağacında.`,
      );
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Mesh üretilemedi.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleMeshQuality() {
    if (!geometryId || !meshResult) return;
    const dim = (meshResult.dimension === 3 ? 3 : 2) as 2 | 3;
    setBusyAction("mesh-quality");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const quality = await fetchMeshQuality(geometryId, dim);
      setMeshQuality(quality);
      setInfoMessage(
        `Kalite (dim ${dim}): Jacobian min=${quality.jacobian.min.toFixed(4)} ` +
          `mean=${quality.jacobian.mean.toFixed(4)} max=${quality.jacobian.max.toFixed(4)}; ` +
          `aspect min=${quality.aspect_ratio.min.toFixed(3)} ` +
          `mean=${quality.aspect_ratio.mean.toFixed(3)} max=${quality.aspect_ratio.max.toFixed(3)}.`,
      );
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Mesh kalite alınamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  /** Midsurface: Parça modunda seçili katı(lar)ın ince cidarları. */
  async function handleMidsurfaceForPart() {
    if (!geometryId || mode !== "part") return;
    const partIds = selection.ids.filter((id) => volumePartIds.includes(id));
    if (partIds.length === 0) return;

    setBusyAction("midsurface");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      let lastResult: Awaited<ReturnType<typeof createMidsurfaceForPart>> | null = null;
      let totalMids = 0;
      const allNew: number[] = [];
      for (const partId of partIds) {
        lastResult = await createMidsurfaceForPart(geometryId, partId);
        totalMids += lastResult.midsurface_count;
        allNew.push(...lastResult.new_face_ids);
      }
      if (lastResult) {
        await refreshAfterMutation(geometryId, lastResult);
      }
      const leftover = volumePartIds.filter((id) => !partIds.includes(id));
      const extra =
        leftover.length > 0
          ? ` Diğer katı(lar) #${leftover.join(", #")} hâlâ duruyor — onları da seçip Midsurface alın.`
          : "";
      setInfoMessage(
        `Midsurface: ${partIds.length} parça, ${totalMids} cidar (yüzeyler: ${allNew.join(", ")}). Katı duruyor; gizlemek için Solid gizle.${extra}`,
      );
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Midsurface oluşturulamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  /** Manuel midsurface: Yüzey modunda Ctrl+tıkla seçilmiş TAM 2 yüzey
   * arasında — otomatik tespitin yanlış çift seçtiği durumlar için yedek yol.
   */
  async function handleMidsurfaceManual() {
    if (!geometryId || mode !== "surface" || selection.ids.length !== 2) return;
    const [faceIdA, faceIdB] = selection.ids;

    setBusyAction("midsurface");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await createMidsurface(geometryId, faceIdA, faceIdB);
      await refreshAfterMutation(geometryId, result);
      setInfoMessage(
        `Midsurface oluşturuldu: yüzey #${faceIdA} ve #${faceIdB} arasında, yeni yüzey #${result.new_face_id}.`,
      );
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Midsurface oluşturulamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  function handleMidsurfaceClick() {
    if (canUseMidsurfaceAuto) void handleMidsurfaceForPart();
    else if (canUseMidsurfaceManual) void handleMidsurfaceManual();
  }

  /** Son mutasyon işlemini (copy/heal/midsurface) geri alır. Tek seviyeli —
   * sadece en son işlem geri alınabilir.
   */
  async function handleUndo() {
    if (!geometryId || !canUndo) return;

    setBusyAction("undo");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await undoLastMutation(geometryId);
      await refreshAfterMutation(geometryId, result);
      setCanUndo(false);
      setInfoMessage("Son işlem geri alındı.");
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Geri alma başarısız oldu.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  const activeGroup = physicalGroups.find((g) => g.id === activeGroupId) ?? null;
  const externalHighlight = activeGroup ? { faceIds: activeGroup.entity_tags } : null;

  const canCopySurface = mode === "surface" && selection.ids.length === 1;
  const canDefeature = geometryId !== null;
  const showGroupForm = mode === "surface" && selection.ids.length > 0;
  const canCreateGroup = showGroupForm && newGroupName.trim().length > 0;

  // "Solid gizle/göster" HER ZAMAN aktif (model yüklüyse) — sadece GERÇEK
  // solid'leri hedefler (volume_part_ids), copy_surface/midsurface çıktısı
  // gibi düz yüzeyleri asla hedeflemez. Seçim yoksa tüm gerçek solid'ler,
  // seçim varsa (hangi modda olursa olsun) sadece o seçime karşılık gelen
  // gerçek solid'ler.
  const volumePartIdSet = new Set(volumePartIds);
  const surfacePartIds: number[] = [];
  {
    const seen = new Set<number>();
    for (const pid of triangleToPart) {
      if (pid < 0 || volumePartIdSet.has(pid) || seen.has(pid)) continue;
      seen.add(pid);
      surfacePartIds.push(pid);
    }
  }
  const surfacePartIdSet = new Set(surfacePartIds);
  const resolvedPartIdsForHide =
    selection.ids.length > 0
      ? resolvePartIdsForSelection(selection).filter((id) => volumePartIdSet.has(id))
      : volumePartIds;
  const resolvedSurfaceIdsForHide =
    selection.ids.length > 0
      ? resolvePartIdsForSelection(selection).filter((id) => surfacePartIdSet.has(id))
      : [];
  const surfaceIdsForToggle =
    resolvedSurfaceIdsForHide.length > 0 ? resolvedSurfaceIdsForHide : surfacePartIds;
  const canToggleHidePart = geometryId !== null && volumePartIds.length > 0;
  const canToggleHideSurfaces = geometryId !== null && surfacePartIds.length > 0;
  const allSelectedPartsHidden =
    resolvedPartIdsForHide.length > 0 &&
    resolvedPartIdsForHide.every((id) => hiddenParts.has(id));
  const allSelectedSurfacesHidden =
    surfaceIdsForToggle.length > 0 &&
    surfaceIdsForToggle.every((id) => hiddenParts.has(id));

  // Midsurface: Parça modunda TEK parça seçiliyse OTOMATİK tespit; Yüzey
  // modunda TAM 2 yüzey seçiliyse MANUEL (kullanıcı kendi çifti belirler —
  // otomatik tespit karmaşık profillerde (örn. 4 köşeli C-kanal) yanlış
  // çifti seçebiliyor, bu yüzden manuel bir yedek yol tutuluyor).
  const canUseMidsurfaceAuto =
    mode === "part" && selection.ids.some((id) => volumePartIdSet.has(id));
  const canUseMidsurfaceManual = mode === "surface" && selection.ids.length === 2;
  const canUseMidsurface = canUseMidsurfaceAuto || canUseMidsurfaceManual;

  const selectedMaterial =
    materials.find((m) => m.id === selectedMaterialId) ?? null;

  const meshPartIds = [...new Set(meshPicks.map((p) => p.partId))];
  const cadPartId =
    meshPicks.length === 0 && mode === "part" && selection.ids.length === 1
      ? selection.ids[0]
      : null;
  const assignPartId = meshPartIds.length === 1 ? meshPartIds[0] : cadPartId;

  const canAssignMaterial =
    geometryId !== null &&
    selectedMaterialId !== null &&
    (meshPartIds.length > 0 || cadPartId !== null);

  const canCreateComponent = geometryId !== null && meshPartIds.length > 0;

  async function handleAssignMaterial() {
    const partIds =
      meshPartIds.length > 0
        ? meshPartIds
        : assignPartId !== null
          ? [assignPartId]
          : [];
    if (!geometryId || selectedMaterialId === null || partIds.length === 0) {
      return;
    }
    setBusyAction("assign-material");
    setErrorMessage(null);
    try {
      let last = null as MaterialAssignment | null;
      for (const partId of partIds) {
        const assignment = await assignMaterial(geometryId, partId, selectedMaterialId);
        last = assignment;
        setMaterialAssignments((prev) => {
          const without = prev.filter((a) => a.part_id !== assignment.part_id);
          return [...without, assignment].sort((a, b) => a.part_id - b.part_id);
        });
      }
      const tree = await fetchProductTree(geometryId, 0);
      setProductTree(tree);
      setInfoMessage(
        last
          ? `Malzeme atandı: parça #${partIds.join(", #")} → ${last.material_name}.`
          : "Malzeme atandı.",
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Malzeme atanamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleUpsertComponent() {
    if (!geometryId || meshPartIds.length === 0) return;
    const thickness = parseFloat(shellThickness);
    if (propertyKind === "shell" && (!Number.isFinite(thickness) || thickness <= 0)) {
      setErrorMessage("Shell property için geçerli bir kalınlık girin.");
      return;
    }
    setBusyAction("component");
    setErrorMessage(null);
    try {
      let last = null as Awaited<ReturnType<typeof upsertComponent>> | null;
      for (const partId of meshPartIds) {
        last = await upsertComponent(geometryId, {
          part_id: partId,
          name: componentName.trim() || `COMP_PART_${partId}`,
          source: "mesh",
          material_id: selectedMaterialId,
          property_kind: propertyKind,
          thickness: propertyKind === "shell" ? thickness : null,
        });
        if (selectedMaterialId !== null && selectedMaterial) {
          setMaterialAssignments((prev) => {
            const without = prev.filter((a) => a.part_id !== partId);
            return [
              ...without,
              {
                id: last!.id,
                geometry_id: geometryId,
                part_id: partId,
                material_id: selectedMaterialId,
                material_name: selectedMaterial.name,
                material_category: selectedMaterial.category,
              },
            ].sort((a, b) => a.part_id - b.part_id);
          });
        }
      }
      const tree = await fetchProductTree(geometryId, 0);
      setProductTree(tree);
      setInfoMessage(
        last
          ? `Component kaydedildi: ${meshPartIds.map((id) => `PART_${id}`).join(", ")}.`
          : "Component kaydedildi.",
      );
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Component kaydedilemedi.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handlePatchTreeComponent(
    componentId: number,
    thicknessRaw: string,
    materialId: number | null,
  ) {
    const thickness = parseFloat(thicknessRaw);
    setBusyAction("component");
    setErrorMessage(null);
    try {
      const updated = await patchComponent(componentId, {
        ...(Number.isFinite(thickness) && thickness > 0 ? { thickness } : {}),
        material_id: materialId ?? 0,
      });
      if (updated.thickness != null) {
        setShellThickness(String(updated.thickness));
      }
      if (updated.material_id != null) {
        setSelectedMaterialId(updated.material_id);
      }
      if (geometryId !== null) {
        const tree = await fetchProductTree(geometryId, 0);
        setProductTree(tree);
        const assignments = await fetchMaterialAssignments(geometryId);
        setMaterialAssignments(assignments);
      }
      setInfoMessage(
        `Component güncellendi: ${updated.name} · ${updated.material_name ?? "malzeme yok"}${
          updated.thickness != null ? ` · t=${updated.thickness}` : ""
        }.`,
      );
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Component güncellenemedi.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCreateCustomMaterial() {
    const name = customName.trim();
    const E = parseFloat(customE) * 1e9;
    const nu = parseFloat(customNu);
    const rho = parseFloat(customRho);
    const fy = parseFloat(customFy) * 1e6;
    const rm = parseFloat(customRm) * 1e6;
    if (!name || ![E, nu, rho, fy, rm].every((v) => Number.isFinite(v) && v > 0)) {
      setErrorMessage("Özel malzeme alanlarını kontrol edin (E GPa, akma/Rm MPa).");
      return;
    }
    setBusyAction("create-material");
    setErrorMessage(null);
    try {
      const mat = await createMaterial({
        name,
        density: rho,
        youngs_modulus: E,
        poisson_ratio: nu,
        yield_strength: fy,
        ultimate_strength: rm,
        sn_mode: snEstimate ? "estimated" : "none",
      });
      setMaterials((prev) => [...prev, mat].sort((a, b) => a.name.localeCompare(b.name)));
      setSelectedMaterialId(mat.id);
      setCustomName("");
      setInfoMessage(`Özel malzeme eklendi: ${mat.name}.`);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Malzeme eklenemedi.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleEstimateSn() {
    if (selectedMaterialId === null) return;
    setBusyAction("sn-curve");
    setErrorMessage(null);
    try {
      const mat = await setMaterialSnCurve(selectedMaterialId, "estimated");
      setMaterials((prev) => prev.map((m) => (m.id === mat.id ? mat : m)));
      setInfoMessage(`S-N (tahmini) güncellendi: ${mat.name}.`);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "S-N güncellenemedi.");
    } finally {
      setBusyAction(null);
    }
  }

  function handleAddBc(kind: BcKind) {
    const meshFaceIds =
      showMesh && meshPicks.length > 0
        ? [...new Set(meshPicks.map((p) => p.faceId).filter((id) => id > 0))]
        : [];
    const faceIds =
      meshFaceIds.length > 0 ? meshFaceIds : mode === "surface" ? [...selection.ids] : [];
    const edgeIds = meshFaceIds.length > 0 ? [] : mode === "edge" ? [...selection.ids] : [];
    const nodeIds = meshFaceIds.length > 0 ? [] : mode === "point" ? [...selection.ids] : [];
    const id = `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const meshTag = meshFaceIds.length > 0 ? "mesh yüzey" : "yüzey";

    let payload: SolveBC;
    let summary: string;

    if (kind === "fixed") {
      if (faceIds.length === 0 && edgeIds.length === 0 && nodeIds.length === 0) {
        setErrorMessage("Fixed için mesh yüzeyi (Face) veya CAD yüzey/kenar/nokta seçin.");
        return;
      }
      payload = {
        type: "fixed",
        ...(faceIds.length ? { face_ids: faceIds } : {}),
        ...(edgeIds.length ? { edge_ids: edgeIds } : {}),
        ...(nodeIds.length ? { node_ids: nodeIds } : {}),
      };
      summary = `Fixed · ${faceIds.length ? `${meshTag} ${faceIds.join(",")}` : ""}${
        edgeIds.length ? `kenar ${edgeIds.join(",")}` : ""
      }${nodeIds.length ? `nokta ${nodeIds.join(",")}` : ""}`.trim();
    } else if (kind === "cload") {
      const fx = parseFloat(bcFx);
      const fy = parseFloat(bcFy);
      const fz = parseFloat(bcFz);
      if (!Number.isFinite(fx) || !Number.isFinite(fy) || !Number.isFinite(fz)) {
        setErrorMessage("CLOAD için geçerli Fx/Fy/Fz girin.");
        return;
      }
      if (faceIds.length === 0 && nodeIds.length === 0) {
        setErrorMessage("Nokta/yüzey yük için mesh yüzeyi veya CAD yüzey/nokta seçin.");
        return;
      }
      payload = {
        type: "cload",
        fx,
        fy,
        fz,
        ...(faceIds.length ? { face_ids: faceIds } : {}),
        ...(nodeIds.length ? { node_ids: nodeIds } : {}),
      };
      summary = `CLOAD (${fx},${fy},${fz}) · ${
        faceIds.length ? `${meshTag} ${faceIds.join(",")}` : `nokta ${nodeIds.join(",")}`
      }`;
    } else if (kind === "pressure") {
      const magnitude = parseFloat(bcMagnitude);
      if (!Number.isFinite(magnitude) || faceIds.length === 0) {
        setErrorMessage("Pressure için mesh veya CAD yüzeyi seçin ve büyüklük girin.");
        return;
      }
      const dx = parseFloat(bcNx);
      const dy = parseFloat(bcNy);
      const dz = parseFloat(bcNz);
      payload = {
        type: "pressure",
        face_ids: faceIds,
        magnitude,
        dx: Number.isFinite(dx) ? dx : 0,
        dy: Number.isFinite(dy) ? dy : 0,
        dz: Number.isFinite(dz) ? dz : -1,
      };
      summary = `Pressure ${magnitude} · ${meshTag} ${faceIds.join(",")}`;
    } else if (kind === "displacement") {
      const ux = parseFloat(bcUx);
      const uy = parseFloat(bcUy);
      const uz = parseFloat(bcUz);
      if (!Number.isFinite(ux) || !Number.isFinite(uy) || !Number.isFinite(uz)) {
        setErrorMessage("Displacement için Ux/Uy/Uz girin.");
        return;
      }
      if (faceIds.length === 0 && edgeIds.length === 0 && nodeIds.length === 0) {
        setErrorMessage("Displacement için mesh yüzeyi veya CAD yüzey/kenar/nokta seçin.");
        return;
      }
      payload = {
        type: "displacement",
        dofs: { "1": ux, "2": uy, "3": uz },
        ...(faceIds.length ? { face_ids: faceIds } : {}),
        ...(edgeIds.length ? { edge_ids: edgeIds } : {}),
        ...(nodeIds.length ? { node_ids: nodeIds } : {}),
      };
      summary = `U=(${ux},${uy},${uz}) · seçim ${[...faceIds, ...edgeIds, ...nodeIds].join(",")}`;
    } else if (kind === "sliding") {
      const nx = parseFloat(bcNx);
      const ny = parseFloat(bcNy);
      const nz = parseFloat(bcNz);
      if (!Number.isFinite(nx) || !Number.isFinite(ny) || !Number.isFinite(nz)) {
        setErrorMessage("Sliding için normal (Nx,Ny,Nz) girin.");
        return;
      }
      if (faceIds.length === 0 && edgeIds.length === 0) {
        setErrorMessage("Sliding için mesh veya CAD yüzeyi/kenarı seçin.");
        return;
      }
      payload = {
        type: "sliding",
        normal: [nx, ny, nz],
        ...(faceIds.length ? { face_ids: faceIds } : {}),
        ...(edgeIds.length ? { edge_ids: edgeIds } : {}),
      };
      summary = `Sliding n=(${nx},${ny},${nz}) · ${
        faceIds.length ? `${meshTag} ${faceIds.join(",")}` : `kenar ${edgeIds.join(",")}`
      }`;
    } else if (kind === "bearing") {
      const magnitude = parseFloat(bcMagnitude);
      const ax = parseFloat(bcAx);
      const ay = parseFloat(bcAy);
      const az = parseFloat(bcAz);
      if (!Number.isFinite(magnitude) || faceIds.length === 0) {
        setErrorMessage("Bearing için mesh veya CAD yüzeyi ve büyüklük gerekli.");
        return;
      }
      payload = {
        type: "bearing",
        face_ids: faceIds,
        magnitude,
        axis: [
          Number.isFinite(ax) ? ax : 0,
          Number.isFinite(ay) ? ay : 0,
          Number.isFinite(az) ? az : -1,
        ],
      };
      summary = `Bearing ${magnitude} · ${meshTag} ${faceIds.join(",")}`;
    } else {
      const gx = parseFloat(bcGx);
      const gy = parseFloat(bcGy);
      const gz = parseFloat(bcGz);
      if (!Number.isFinite(gx) || !Number.isFinite(gy) || !Number.isFinite(gz)) {
        setErrorMessage("Gravity için gx/gy/gz girin.");
        return;
      }
      payload = { type: "gravity", gx, gy, gz };
      summary = `Gravity (${gx},${gy},${gz})`;
    }

    setErrorMessage(null);
    setBcList((prev) => [...prev, { id, kind, summary, payload }]);
    setInfoMessage(`BC eklendi: ${BC_KIND_LABELS[kind]}`);
  }

  function handleRemoveBc(id: string) {
    setBcList((prev) => prev.filter((b) => b.id !== id));
  }

  async function handleSolve() {
    if (!geometryId || !meshResult) {
      setErrorMessage("Önce mesh üretin ve malzeme atayın.");
      return;
    }
    if (bcList.length === 0) {
      setErrorMessage("En az bir BC ekleyin (Fixed, yük, gravity…).");
      return;
    }
    const dim = (meshResult.dimension === 3 ? 3 : 2) as 2 | 3;
    const bcs = bcList.map((b) => b.payload);

    setBusyAction("solve");
    setErrorMessage(null);
    const treeThickness = productTree?.items.find(
      (i) => i.thickness != null && Number(i.thickness) > 0,
    )?.thickness;
    const thickness =
      treeThickness ??
      (Number.isFinite(parseFloat(shellThickness)) ? parseFloat(shellThickness) : 3);
    try {
      const result = await solveGeometry(geometryId, {
        dimension: dim,
        shell_thickness: thickness,
        run_solver: runCcx,
        bcs,
      });
      setSolveResult(result);
      setInfoMessage(result.message);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Solve başarısız.");
    } finally {
      setBusyAction(null);
    }
  }

  function describeSelection(sel: MultiSelectionInfo): string {
    if (sel.ids.length === 0) {
      return "Yukarıdaki moda göre bir öğeye tıklayın. Ctrl (ya da Cmd) basılı tutup birden fazla öğe seçebilirsiniz.";
    }
    const idList = sel.ids.join(", #");
    switch (sel.mode) {
      case "part": {
        const total = sel.ids.reduce(
          (sum, id) => sum + triangleToPart.filter((p) => p === id).length,
          0,
        );
        return `${sel.ids.length} parça seçili (#${idList}) — toplam ${total} üçgen`;
      }
      case "surface": {
        const total = sel.ids.reduce(
          (sum, id) => sum + triangleToFace.filter((f) => f === id).length,
          0,
        );
        return `${sel.ids.length} yüzey seçili (#${idList}) — toplam ${total} üçgen`;
      }
      case "edge": {
        const total = sel.ids.reduce(
          (sum, id) => sum + (edges.find((e) => e.id === id)?.length ?? 0),
          0,
        );
        return `${sel.ids.length} kenar seçili (#${idList}) — toplam ${total.toFixed(2)} birim`;
      }
      case "point":
        return `${sel.ids.length} nokta seçili (#${idList})`;
    }
  }

  return (
    <main className="page">
      <div className="left-column">
      <div className="panel">
        <span className="eyebrow">Faz 0 · Geometri önizleme</span>
        <h1>Geometri yükle</h1>
        <p className="lead">
          STEP ya da IGES dosyanızı seçin, sunucu Gmsh ile tessellation üretsin —
          sonucu aşağıda döndürerek inceleyebilir, seçim modunu değiştirerek
          parça/yüzey/kenar/nokta seçebilirsiniz. Ctrl (Cmd) + tık ile birden
          fazla öğe seçebilirsiniz.
        </p>

        <label className="upload-control">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={handleInputChange}
            disabled={status === "uploading"}
          />
          <span>{status === "uploading" ? "Yükleniyor…" : "Dosya seç (.step / .iges)"}</span>
        </label>

        {fileName && (
          <p className="filename">
            {fileName}
            {status === "success" && " — yüklendi"}
          </p>
        )}

        {errorMessage && (
          <p className="error-message" role="alert">
            {errorMessage}
          </p>
        )}

        {status === "success" && infoMessage && <p className="info-message">{infoMessage}</p>}

        {status === "success" && faceCount !== null && (
          <div className="face-info">
            <p className="face-info-total">
              {faceCount} yüzey, {partCount} parça, {edges.length} kenar, {points.length} nokta
              bulundu.
            </p>
            <p className="face-info-selected">{describeSelection(selection)}</p>

            {showGroupForm && (
              <div className="group-create-form">
                <input
                  type="text"
                  className="group-name-input"
                  placeholder="Grup adı (örn. inlet)"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  disabled={busyAction === "create-group"}
                />
                <button
                  type="button"
                  className="group-create-button"
                  onClick={() => void handleCreatePhysicalGroup()}
                  disabled={!canCreateGroup || busyAction === "create-group"}
                >
                  {busyAction === "create-group" ? "Oluşturuluyor…" : "Grup oluştur"}
                </button>
              </div>
            )}
          </div>
        )}

        {status !== "idle" && (
          <button type="button" className="reset-button" onClick={handleReset}>
            Yeni dosya seç
          </button>
        )}
      </div>

      <div className="panel material-panel">
        <span className="eyebrow">Faz 0 · Malzeme</span>
        <h1>Malzeme</h1>
        <p className="lead material-lead">
          Kütüphaneden tipik/nominal değer seçin. Mesh sonrası component
          otomatik oluşur; kalınlık ve malzeme ürün ağacından girilir.
        </p>
        {materials.length === 0 ? (
          <p className="filename">Malzeme listesi yükleniyor…</p>
        ) : (
          <>
            <label className="mesh-field material-field">
              <span>Kütüphane</span>
              <select
                value={selectedMaterialId ?? ""}
                onChange={(e) => setSelectedMaterialId(Number(e.target.value))}
              >
                {materials.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.category})
                  </option>
                ))}
              </select>
            </label>
            {selectedMaterial && (
              <div className="material-props">
                <p>
                  <span>Kaynak</span>
                  {selectedMaterial.source === "library"
                    ? "kütüphane (tipik)"
                    : selectedMaterial.source === "user_defined"
                      ? "kullanıcı tanımlı"
                      : selectedMaterial.source}
                </p>
                {selectedMaterial.standard && (
                  <p>
                    <span>Standart</span>
                    {selectedMaterial.standard}
                  </p>
                )}
                <p>
                  <span>E</span>
                  {formatGPa(selectedMaterial.youngs_modulus)}
                </p>
                <p>
                  <span>ν</span>
                  {selectedMaterial.poisson_ratio.toFixed(2)}
                </p>
                <p>
                  <span>ρ</span>
                  {selectedMaterial.density.toFixed(0)} kg/m³
                </p>
                <p>
                  <span>Rp0.2</span>
                  {formatMPa(selectedMaterial.yield_strength)}
                </p>
                <p>
                  <span>Rm</span>
                  {formatMPa(selectedMaterial.ultimate_strength)}
                </p>
                {selectedMaterial.elongation != null && (
                  <p>
                    <span>A</span>
                    {selectedMaterial.elongation.toFixed(0)} %
                  </p>
                )}
                <p>
                  <span>S-N</span>
                  {selectedMaterial.sn_curve &&
                  typeof selectedMaterial.sn_curve === "object" &&
                  "source" in selectedMaterial.sn_curve
                    ? String(
                        (selectedMaterial.sn_curve as { source?: string }).source ===
                          "estimated"
                          ? "tahmini"
                          : (selectedMaterial.sn_curve as { source?: string }).source ===
                              "tested"
                            ? "test"
                            : "var",
                      )
                    : "yok"}
                </p>
              </div>
            )}
            <button
              type="button"
              className="material-assign-button"
              disabled={!canAssignMaterial || busyAction !== null}
              onClick={() => void handleAssignMaterial()}
            >
              {busyAction === "assign-material" ? "Atanıyor…" : "Malzeme ata"}
            </button>
            <label className="mesh-field material-field">
              <span>Component adı</span>
              <input
                value={componentName}
                onChange={(e) => setComponentName(e.target.value)}
                placeholder={
                  meshPartIds.length > 0
                    ? `COMP_PART_${meshPartIds[0]}`
                    : "COMP_PART_n"
                }
              />
            </label>
            <label className="mesh-field material-field">
              <span>Property</span>
              <select
                value={propertyKind}
                onChange={(e) => setPropertyKind(e.target.value as PropertyKind)}
              >
                <option value="shell">shell (kalınlık)</option>
                <option value="solid">solid</option>
              </select>
            </label>
            {propertyKind === "shell" && (
              <label className="mesh-field material-field">
                <span>Kalınlık</span>
                <input
                  value={shellThickness}
                  onChange={(e) => setShellThickness(e.target.value)}
                />
              </label>
            )}
            <button
              type="button"
              className="material-assign-button"
              disabled={!canCreateComponent || busyAction !== null}
              onClick={() => void handleUpsertComponent()}
            >
              {busyAction === "component" ? "Kaydediliyor…" : "Component güncelle"}
            </button>
            <button
              type="button"
              className="material-secondary-button"
              disabled={selectedMaterialId === null || busyAction !== null}
              onClick={() => void handleEstimateSn()}
            >
              {busyAction === "sn-curve" ? "S-N…" : "Tahmini S-N üret"}
            </button>
            {!canAssignMaterial && geometryId !== null && (
              <p className="material-assign-hint">
                Mesh elemanına tıklayın. Face: o CAD yüzeyi. Attached: tüm parça.
              </p>
            )}
            {canCreateComponent && !canAssignMaterial && (
              <p className="material-assign-hint">Kütüphaneden malzeme seçin.</p>
            )}
            {productTree && productTree.items.filter((i) => i.component).length > 0 && (
              <div className="product-tree">
                <p className="material-assignments-title">Ürün ağacı</p>
                <ul className="product-tree-list">
                  {productTree.items
                    .filter((i) => i.component)
                    .map((item) => (
                      <ProductTreeRow
                        key={item.component?.id ?? item.part_id}
                        item={item}
                        materials={materials}
                        busy={busyAction !== null}
                        onSave={(componentId, thickness, materialId) =>
                          void handlePatchTreeComponent(componentId, thickness, materialId)
                        }
                      />
                    ))}
                </ul>
              </div>
            )}
            {materialAssignments.length > 0 && (
              <div className="material-assignments">
                <p className="material-assignments-title">Atamalar</p>
                <ul>
                  {materialAssignments.map((a) => (
                    <li key={a.id}>
                      Parça #{a.part_id} → {a.material_name}
                      {a.material_category ? ` (${a.material_category})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="material-custom">
              <p className="material-assignments-title">Özel malzeme</p>
              <label className="mesh-field material-field">
                <span>Ad</span>
                <input
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="Örn. OzelCelik"
                />
              </label>
              <div className="material-custom-grid">
                <label className="mesh-field">
                  <span>E (GPa)</span>
                  <input value={customE} onChange={(e) => setCustomE(e.target.value)} />
                </label>
                <label className="mesh-field">
                  <span>ν</span>
                  <input value={customNu} onChange={(e) => setCustomNu(e.target.value)} />
                </label>
                <label className="mesh-field">
                  <span>ρ</span>
                  <input value={customRho} onChange={(e) => setCustomRho(e.target.value)} />
                </label>
                <label className="mesh-field">
                  <span>Rp0.2 (MPa)</span>
                  <input value={customFy} onChange={(e) => setCustomFy(e.target.value)} />
                </label>
                <label className="mesh-field">
                  <span>Rm (MPa)</span>
                  <input value={customRm} onChange={(e) => setCustomRm(e.target.value)} />
                </label>
              </div>
              <label className="material-check">
                <input
                  type="checkbox"
                  checked={snEstimate}
                  onChange={(e) => setSnEstimate(e.target.checked)}
                />
                Oluştururken tahmini S-N ekle
              </label>
              <button
                type="button"
                className="material-secondary-button"
                disabled={busyAction !== null}
                onClick={() => void handleCreateCustomMaterial()}
              >
                {busyAction === "create-material" ? "Ekleniyor…" : "Özel malzeme ekle"}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="panel material-panel">
        <span className="eyebrow">Faz 0 · CalculiX</span>
        <h1>Solver / BC</h1>
        <p className="lead material-lead">
          Mesh elemanına tıklayın (Face = tüm yüzey) → BC türünü seçin → Listeye ekle.
          Kalınlık ürün ağacındadır.
        </p>
        {showMesh && meshPicks.length > 0 && (
          <p className="material-assign-hint">
            Mesh seçim: {meshGrow} · yüzey{" "}
            {[...new Set(meshPicks.map((p) => p.faceId))].join(", ")} · parça{" "}
            {meshPartIds.join(", ")}
          </p>
        )}

        <p className="material-assignments-title">BC türü</p>
        <div className="bc-button-row">
          {(
            [
              "fixed",
              "cload",
              "pressure",
              "displacement",
              "sliding",
              "bearing",
              "gravity",
            ] as BcKind[]
          ).map((kind) => (
            <button
              key={kind}
              type="button"
              className={`bc-add-button${bcDraftKind === kind ? " active" : ""}`}
              disabled={busyAction !== null}
              onClick={() => setBcDraftKind(kind)}
            >
              {BC_KIND_LABELS[kind]}
            </button>
          ))}
        </div>
        <p className="material-assign-hint">{BC_KIND_HINTS[bcDraftKind]}</p>

        {bcDraftKind === "cload" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>Fx</span>
              <input value={bcFx} onChange={(e) => setBcFx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Fy</span>
              <input value={bcFy} onChange={(e) => setBcFy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Fz</span>
              <input value={bcFz} onChange={(e) => setBcFz(e.target.value)} />
            </label>
          </div>
        )}
        {bcDraftKind === "pressure" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>|P|</span>
              <input value={bcMagnitude} onChange={(e) => setBcMagnitude(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>dx</span>
              <input value={bcNx} onChange={(e) => setBcNx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>dy</span>
              <input value={bcNy} onChange={(e) => setBcNy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>dz</span>
              <input value={bcNz} onChange={(e) => setBcNz(e.target.value)} />
            </label>
          </div>
        )}
        {bcDraftKind === "displacement" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>Ux</span>
              <input value={bcUx} onChange={(e) => setBcUx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Uy</span>
              <input value={bcUy} onChange={(e) => setBcUy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Uz</span>
              <input value={bcUz} onChange={(e) => setBcUz(e.target.value)} />
            </label>
          </div>
        )}
        {bcDraftKind === "sliding" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>Nx</span>
              <input value={bcNx} onChange={(e) => setBcNx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ny</span>
              <input value={bcNy} onChange={(e) => setBcNy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Nz</span>
              <input value={bcNz} onChange={(e) => setBcNz(e.target.value)} />
            </label>
          </div>
        )}
        {bcDraftKind === "bearing" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>Büyüklük</span>
              <input value={bcMagnitude} onChange={(e) => setBcMagnitude(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Axis x</span>
              <input value={bcAx} onChange={(e) => setBcAx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Axis y</span>
              <input value={bcAy} onChange={(e) => setBcAy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Axis z</span>
              <input value={bcAz} onChange={(e) => setBcAz(e.target.value)} />
            </label>
          </div>
        )}
        {bcDraftKind === "gravity" && (
          <div className="bc-fields">
            <label className="mesh-field">
              <span>gx</span>
              <input value={bcGx} onChange={(e) => setBcGx(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>gy</span>
              <input value={bcGy} onChange={(e) => setBcGy(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>gz</span>
              <input value={bcGz} onChange={(e) => setBcGz(e.target.value)} />
            </label>
          </div>
        )}

        <button
          type="button"
          className="material-assign-button bc-add-confirm"
          disabled={busyAction !== null}
          onClick={() => handleAddBc(bcDraftKind)}
        >
          Listeye ekle
        </button>

        {bcList.length > 0 && (
          <div className="material-assignments">
            <p className="material-assignments-title">Eklenen BC ({bcList.length})</p>
            <ul>
              {bcList.map((b) => (
                <li key={b.id} className="bc-list-item">
                  <span>{b.summary}</span>
                  <button type="button" className="bc-remove-button" onClick={() => handleRemoveBc(b.id)}>
                    Sil
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <label className="material-check">
          <input
            type="checkbox"
            checked={runCcx}
            onChange={(e) => setRunCcx(e.target.checked)}
          />
          ccx çalıştır (kuruluysa)
        </label>
        <button
          type="button"
          className="material-assign-button"
          disabled={busyAction !== null || geometryId === null || meshResult === null}
          onClick={() => void handleSolve()}
        >
          {busyAction === "solve" ? "Üretiliyor…" : ".inp üret / çöz"}
        </button>
        {solveResult && (
          <div className="material-assignments">
            <p className="material-assignments-title">Sonuç</p>
            <p className="material-assign-hint">{solveResult.message}</p>
            <p className="material-assign-hint">
              MATERIAL={String(solveResult.cards.has_material)} · SECTION=
              {String(solveResult.cards.has_section)} · ccx=
              {String(solveResult.ccx_available)} · ran=
              {String(solveResult.solver_ran)}
            </p>
            <a className="material-inp-link" href={`http://localhost:8000${solveResult.inp_url}`} target="_blank" rel="noreferrer">
              .inp indir
            </a>
          </div>
        )}
      </div>
      </div>

      <div className="viewer-panel">
        {stlUrl && geometryId !== null ? (
          <>
            <div className="button-group-stack">
              <ButtonGroup
                title="Seçim modu"
                items={SELECTION_MODES.map(({ mode: m, label }) => ({
                  key: m,
                  label,
                  active: mode === m,
                  onClick: () => {
                    setMode(m);
                    setSelection({ mode: m, ids: [] });
                    setMeshPicks([]);
                    setMeshGrow("element");
                  },
                }))}
              />
              <ButtonGroup
                title="İşlemler"
                items={[
                  {
                    key: "copy-surface",
                    label: busyAction === "copy" ? "Kopyalanıyor…" : "Yüzey kopyala",
                    disabled: !canCopySurface || busyAction !== null,
                    onClick: () => void handleCopySurface(),
                  },
                  {
                    key: "toggle-hide-part",
                    label: allSelectedPartsHidden ? "Solid göster" : "Solid gizle",
                    disabled: !canToggleHidePart,
                    onClick: handleToggleHidePart,
                  },
                  {
                    key: "toggle-hide-surfaces",
                    label: allSelectedSurfacesHidden ? "Surface göster" : "Surface gizle",
                    disabled: !canToggleHideSurfaces,
                    onClick: handleToggleHideSurfaces,
                  },
                  {
                    key: "toggle-mesh",
                    label: showMesh ? "Mesh gizle" : "Mesh göster",
                    disabled: meshPreview === null,
                    active: showMesh && meshPreview !== null,
                    onClick: () => setShowMesh((prev) => !prev),
                  },
                  {
                    key: "toggle-mesh-wireframe",
                    label: meshWireframe ? "Mesh tel kafes (açık)" : "Mesh tel kafes",
                    disabled: meshPreview === null || !showMesh,
                    active: meshWireframe && showMesh && meshPreview !== null,
                    onClick: () => setMeshWireframe((prev) => !prev),
                  },
                  {
                    key: "toggle-edges",
                    label: showEdges ? "Kenar çizgileri (açık)" : "Kenar çizgileri (kapalı)",
                    active: showEdges,
                    onClick: () => setShowEdges((prev) => !prev),
                  },
                  {
                    key: "undo",
                    label: busyAction === "undo" ? "Geri alınıyor…" : "Geri al",
                    disabled: !canUndo || busyAction !== null,
                    onClick: () => void handleUndo(),
                  },
                ]}
              />
              <label className="opacity-field">
                <span>Katı opaklık {cadOpacityPct}%</span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={cadOpacityPct}
                  onChange={(e) => setCadOpacityPct(Number(e.target.value))}
                />
              </label>
              <ButtonGroup
                title="Geometri"
                items={[
                  {
                    key: "heal",
                    label: busyAction === "heal" ? "Düzeltiliyor…" : "Heal",
                    disabled: busyAction !== null,
                    onClick: () => void handleHeal(),
                  },
                  {
                    key: "defeature",
                    label: busyAction === "defeature" ? "Kaldırılıyor…" : "Fillet kaldır",
                    disabled: !canDefeature || busyAction !== null,
                    onClick: () => void handleApplyDefeature(),
                  },
                  {
                    key: "midsurface",
                    label:
                      busyAction === "midsurface"
                        ? "Oluşturuluyor…"
                        : canUseMidsurfaceManual
                          ? "Midsurface (2 yüzey)"
                          : "Midsurface (parça seç)",
                    disabled: !canUseMidsurface || busyAction !== null,
                    onClick: handleMidsurfaceClick,
                  },
                  { key: "placeholder-geometry", label: "Yakında", disabled: true },
                ]}
              />
              <ButtonGroup
                title="Physical Group'lar"
                items={physicalGroups.map((g) => ({
                  key: String(g.id),
                  label: g.name,
                  active: activeGroupId === g.id,
                  onClick: () => handleGroupButtonClick(g.id),
                }))}
                emptyLabel="Henüz grup yok"
              />
            </div>
            <div className="viewer-body">
              <div className="viewer-stage">
                {showMesh && meshPreview !== null && meshPicks.length > 0 && (
                  <div className="mesh-grow-bar">
                    <ButtonGroup
                      title="Mesh seçim"
                      items={[
                        {
                          key: "face",
                          label: "Face",
                          active: meshGrow === "face",
                          onClick: () => handleMeshGrow("face"),
                        },
                        {
                          key: "attached",
                          label: "Attached",
                          active: meshGrow === "attached",
                          onClick: () => handleMeshGrow("attached"),
                        },
                      ]}
                    />
                  </div>
                )}
                <GeometryViewer
                  stlUrl={stlUrl}
                  triangleToFace={triangleToFace}
                  triangleToPart={triangleToPart}
                  edges={edges}
                  points={points}
                  mode={mode}
                  hiddenParts={hiddenParts}
                  showEdges={showEdges}
                  meshPreview={meshPreview}
                  showMesh={showMesh}
                  meshWireframe={meshWireframe}
                  cadOpacity={cadOpacityPct / 100}
                  meshPicks={meshPicks}
                  meshGrow={meshGrow}
                  externalHighlight={externalHighlight}
                  selectedIds={selection.ids}
                  edgeNodeCounts={edgeNodeCounts}
                  onEdgeNodeCountChange={(edgeId, next) => {
                    edgeSeedManualRef.current.add(edgeId);
                    setEdgeNodeCounts((prev) => ({ ...prev, [edgeId]: next }));
                  }}
                  onSelectionChange={handleSelectionChange}
                  onMeshPicks={handleMeshPicks}
                />
              </div>
              <aside className="mesh-side-panel" aria-label="Mesh">
                <p className="mesh-side-title">Mesh</p>
                <label className="mesh-field">
                  <span>Eleman boyutu</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.1"
                    value={meshElementSize}
                    onChange={(e) => setMeshElementSize(e.target.value)}
                    disabled={busyAction === "mesh"}
                  />
                </label>
                <div className="mesh-dim-row" role="group" aria-label="Mesh boyutu">
                  <button
                    type="button"
                    className={meshDimension === 2 ? "active" : undefined}
                    disabled={busyAction === "mesh"}
                    onClick={() => {
                      setMeshDimension(2);
                      setMeshScheme("quad");
                    }}
                  >
                    2D shell
                  </button>
                  <button
                    type="button"
                    className={meshDimension === 3 ? "active" : undefined}
                    disabled={busyAction === "mesh"}
                    onClick={() => {
                      setMeshDimension(3);
                      setMeshScheme("tet");
                    }}
                  >
                    3D solid
                  </button>
                </div>
                <label className="mesh-field">
                  <span>Eleman tipi</span>
                  <select
                    value={meshScheme}
                    disabled={busyAction === "mesh"}
                    onChange={(e) => setMeshScheme(e.target.value as MeshElementScheme)}
                  >
                    <option value="tet">tet</option>
                    <option value="quad">quad</option>
                    <option value="mix">mix</option>
                  </select>
                </label>
                <p className="mesh-side-hint">
                  Kenar üzerindeki sayı o kenardaki düğüm sayısıdır. +/− ile
                  değiştirin (4 mm / 5 mm topoloji sıçramasını azaltır).
                </p>
                <button
                  type="button"
                  className="mesh-generate-button"
                  disabled={busyAction !== null}
                  onClick={() => void handleGenerateMesh()}
                >
                  {busyAction === "mesh" ? "Üretiliyor…" : "Mesh üret"}
                </button>
                <div className="mesh-tools" role="group" aria-label="Mesh araçları">
                  <button
                    type="button"
                    disabled={busyAction !== null || meshResult === null}
                    onClick={() => void handleMeshQuality()}
                  >
                    {busyAction === "mesh-quality" ? "Hesaplanıyor…" : "Kalite"}
                  </button>
                  <button type="button" disabled title="Sonraki adım">
                    Free edge
                  </button>
                  <button type="button" disabled title="Sonraki adım">
                    Equivalence
                  </button>
                  <button type="button" disabled title="Sonraki adım">
                    Rigid body
                  </button>
                </div>
                {meshResult && (
                  <div className="mesh-result">
                    <p>
                      {meshResult.dimension === 2 ? "Shell" : "Solid"} ·{" "}
                      {meshResult.element_scheme} · size {meshResult.element_size}
                    </p>
                    <p>
                      {meshResult.node_count} düğüm · {meshResult.element_count} eleman
                    </p>
                    <ul>
                      {Object.entries(meshResult.element_type_counts).map(([name, n]) => (
                        <li key={name}>
                          {name}: {n}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {meshQuality && (
                  <div className="mesh-result mesh-quality-result">
                    <p>Kalite · {meshQuality.element_count} eleman</p>
                    <p>
                      Jacobian (minSJ): {meshQuality.jacobian.min.toFixed(4)} /{" "}
                      {meshQuality.jacobian.mean.toFixed(4)} /{" "}
                      {meshQuality.jacobian.max.toFixed(4)}
                    </p>
                    <p>
                      Aspect: {meshQuality.aspect_ratio.min.toFixed(3)} /{" "}
                      {meshQuality.aspect_ratio.mean.toFixed(3)} /{" "}
                      {meshQuality.aspect_ratio.max.toFixed(3)}
                    </p>
                    <p className="mesh-quality-hint">min / mean / max</p>
                  </div>
                )}
              </aside>
            </div>
          </>
        ) : (
          <div className="viewer-placeholder">
            <p>Bir geometri yüklendiğinde 3B önizleme burada görünecek.</p>
          </div>
        )}
      </div>
    </main>
  );
}

export default App;
