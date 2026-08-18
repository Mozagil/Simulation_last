import { useCallback, useEffect, useRef, useState } from "react";
import {
  EdgeInfo,
  GeometryUploadError,
  PhysicalGroup,
  PointInfo,
  copySurface,
  createPhysicalGroup,
  fetchEdges,
  fetchPhysicalGroups,
  fetchPoints,
  resolveTessellationUrl,
  uploadGeometry,
} from "./api/geometry";
import ButtonGroup from "./components/ButtonGroup";
import GeometryViewer from "./components/GeometryViewer";
import { SELECTION_MODES, SelectionInfo, SelectionMode } from "./types";

type Status = "idle" | "uploading" | "error" | "success";

const ACCEPTED_EXTENSIONS = ".step,.stp,.igs,.iges";

function describeSelection(selection: SelectionInfo): string {
  switch (selection.mode) {
    case "part":
      return `Seçili parça: #${selection.id} (${selection.triangleCount} üçgen)`;
    case "surface":
      return `Seçili yüzey: #${selection.id} (${selection.triangleCount} üçgen)`;
    case "edge":
      return `Seçili kenar: #${selection.id} (${selection.length.toFixed(2)} birim uzunluk)`;
    case "point":
      return `Seçili nokta: #${selection.id} (${selection.coordinate
        .map((c) => c.toFixed(2))
        .join(", ")})`;
  }
}

function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [geometryId, setGeometryId] = useState<number | null>(null);
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [triangleToFace, setTriangleToFace] = useState<number[]>([]);
  const [triangleToPart, setTriangleToPart] = useState<number[]>([]);
  const [faceCount, setFaceCount] = useState<number | null>(null);
  const [partCount, setPartCount] = useState<number | null>(null);
  const [edges, setEdges] = useState<EdgeInfo[]>([]);
  const [points, setPoints] = useState<PointInfo[]>([]);
  const [mode, setMode] = useState<SelectionMode>("surface");
  const [selection, setSelection] = useState<SelectionInfo | null>(null);
  const [hiddenParts, setHiddenParts] = useState<Set<number>>(new Set());
  const [physicalGroups, setPhysicalGroups] = useState<PhysicalGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mod değişince aktif grup vurgusu ve seçim anlamsızlaşır, temizle.
  useEffect(() => {
    setActiveGroupId(null);
  }, [mode]);

  async function handleFileSelected(file: File) {
    setStatus("uploading");
    setErrorMessage(null);
    setFileName(file.name);
    setSelection(null);
    setMode("surface");
    setHiddenParts(new Set());
    setActiveGroupId(null);
    setNewGroupName("");

    try {
      const result = await uploadGeometry(file);
      setGeometryId(result.geometry_id);
      setStlUrl(resolveTessellationUrl(result.tessellation_url));
      setTriangleToFace(result.triangle_to_face);
      setTriangleToPart(result.triangle_to_part);
      setFaceCount(result.face_count);
      setPartCount(result.part_count);

      const [edgeList, pointList, groupList] = await Promise.all([
        fetchEdges(result.geometry_id),
        fetchPoints(result.geometry_id),
        fetchPhysicalGroups(result.geometry_id),
      ]);
      setEdges(edgeList);
      setPoints(pointList);
      setPhysicalGroups(groupList);

      setStatus("success");
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
    setStatus("idle");
    setErrorMessage(null);
    setFileName(null);
    setGeometryId(null);
    setStlUrl(null);
    setTriangleToFace([]);
    setTriangleToPart([]);
    setFaceCount(null);
    setPartCount(null);
    setEdges([]);
    setPoints([]);
    setSelection(null);
    setMode("surface");
    setHiddenParts(new Set());
    setPhysicalGroups([]);
    setActiveGroupId(null);
    setNewGroupName("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const handleSelectionChange = useCallback((info: SelectionInfo | null) => {
    setSelection(info);
  }, []);

  async function handleCopySurface() {
    if (!geometryId || mode !== "surface" || !selection || selection.mode !== "surface") return;

    setBusyAction("copy");
    setErrorMessage(null);
    try {
      const result = await copySurface(geometryId, selection.id);
      setTriangleToFace(result.triangle_to_face);
      setTriangleToPart(result.triangle_to_part);
      setFaceCount(result.face_count);
      setPartCount(result.part_count);
      // Cache-bust: aynı dosya adı üzerine yazıldığı için tarayıcı eski STL'i
      // önbellekten kullanmasın diye zaman damgası ekleniyor.
      setStlUrl(resolveTessellationUrl(result.tessellation_url, Date.now()));
      setSelection(null);

      const [edgeList, pointList] = await Promise.all([
        fetchEdges(geometryId),
        fetchPoints(geometryId),
      ]);
      setEdges(edgeList);
      setPoints(pointList);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Yüzey kopyalanamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  function handleToggleHidePart() {
    if (mode !== "part" || !selection || selection.mode !== "part") return;
    setHiddenParts((prev) => {
      const next = new Set(prev);
      if (next.has(selection.id)) next.delete(selection.id);
      else next.add(selection.id);
      return next;
    });
  }

  async function handleCreatePhysicalGroup() {
    const trimmedName = newGroupName.trim();
    if (!geometryId || mode !== "surface" || !selection || selection.mode !== "surface") return;
    if (!trimmedName) return;

    setBusyAction("create-group");
    setErrorMessage(null);
    try {
      await createPhysicalGroup(geometryId, trimmedName, [selection.id]);
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

  const activeGroup = physicalGroups.find((g) => g.id === activeGroupId) ?? null;
  const externalHighlight = activeGroup ? { faceIds: activeGroup.entity_tags } : null;

  const canCopySurface = mode === "surface" && selection?.mode === "surface";
  const canToggleHidePart = mode === "part" && selection?.mode === "part";
  const showGroupForm = mode === "surface" && selection?.mode === "surface";
  const canCreateGroup = showGroupForm && newGroupName.trim().length > 0;

  return (
    <main className="page">
      <div className="panel">
        <span className="eyebrow">Faz 0 · Geometri önizleme</span>
        <h1>Geometri yükle</h1>
        <p className="lead">
          STEP ya da IGES dosyanızı seçin, sunucu Gmsh ile tessellation üretsin —
          sonucu aşağıda döndürerek inceleyebilir, seçim modunu değiştirerek
          parça/yüzey/kenar/nokta seçebilirsiniz.
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

        {status === "error" && errorMessage && (
          <p className="error-message" role="alert">
            {errorMessage}
          </p>
        )}

        {status === "success" && faceCount !== null && (
          <div className="face-info">
            <p className="face-info-total">
              {faceCount} yüzey, {partCount} parça, {edges.length} kenar, {points.length} nokta
              bulundu.
            </p>
            {selection ? (
              <p className="face-info-selected">{describeSelection(selection)}</p>
            ) : (
              <p className="face-info-selected muted">
                Yukarıdaki moda göre bir öğeye tıklayarak seçin.
              </p>
            )}

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
                  onClick: () => setMode(m),
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
                    label:
                      canToggleHidePart && selection?.mode === "part" && hiddenParts.has(selection.id)
                        ? "Solid göster"
                        : "Solid gizle",
                    disabled: !canToggleHidePart,
                    onClick: handleToggleHidePart,
                  },
                  { key: "placeholder-1", label: "Yakında", disabled: true },
                  { key: "placeholder-2", label: "Yakında", disabled: true },
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
            <GeometryViewer
              stlUrl={stlUrl}
              triangleToFace={triangleToFace}
              triangleToPart={triangleToPart}
              edges={edges}
              points={points}
              mode={mode}
              hiddenParts={hiddenParts}
              externalHighlight={externalHighlight}
              onSelectionChange={handleSelectionChange}
            />
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
