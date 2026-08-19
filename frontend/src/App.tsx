import { useCallback, useEffect, useRef, useState } from "react";
import {
  DefeatureCandidate,
  EdgeInfo,
  GeometryUploadError,
  PhysicalGroup,
  PointInfo,
  copySurface,
  createMidsurface,
  createPhysicalGroup,
  fetchEdges,
  fetchPhysicalGroups,
  fetchPoints,
  findDefeatureCandidates,
  healGeometry,
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
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
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
  const [showEdges, setShowEdges] = useState(true);
  const [physicalGroups, setPhysicalGroups] = useState<PhysicalGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);

  // Midsurface: iki aşamalı seçim (önce A, sonra B yüzeyi).
  const [midsurfaceFirstFaceId, setMidsurfaceFirstFaceId] = useState<number | null>(null);

  // Defeature: eşik girişi + sonuç listesi paneli.
  const [showDefeaturePanel, setShowDefeaturePanel] = useState(false);
  const [defeatureThreshold, setDefeatureThreshold] = useState("5");
  const [defeatureCandidates, setDefeatureCandidates] = useState<DefeatureCandidate[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mod değişince aktif grup vurgusu, midsurface ilk seçimi ve defeature
  // sonuçları anlamsızlaşır, temizle.
  useEffect(() => {
    setActiveGroupId(null);
    setMidsurfaceFirstFaceId(null);
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);
  }, [mode]);

  async function handleFileSelected(file: File) {
    setStatus("uploading");
    setErrorMessage(null);
    setInfoMessage(null);
    setFileName(file.name);
    setSelection(null);
    setMode("surface");
    setHiddenParts(new Set());
    setActiveGroupId(null);
    setNewGroupName("");
    setMidsurfaceFirstFaceId(null);
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);

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
    setInfoMessage(null);
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
    setShowEdges(true);
    setPhysicalGroups([]);
    setActiveGroupId(null);
    setNewGroupName("");
    setMidsurfaceFirstFaceId(null);
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const handleSelectionChange = useCallback((info: SelectionInfo | null) => {
    setSelection(info);
  }, []);

  /** Bir mutasyon işleminden (copy/heal/midsurface) sonra ortak yenileme:
   * tessellation + üçgen eşlemeleri + edges/points (yeni geometri yeni kenar/
   * nokta üretmiş olabilir) hepsi tazelenir.
   */
  async function refreshAfterMutation(
    geoId: number,
    tessellation: {
      triangle_to_face: number[];
      triangle_to_part: number[];
      face_count: number;
      part_count: number;
      tessellation_url: string;
    },
  ) {
    setTriangleToFace(tessellation.triangle_to_face);
    setTriangleToPart(tessellation.triangle_to_part);
    setFaceCount(tessellation.face_count);
    setPartCount(tessellation.part_count);
    // Cache-bust: aynı dosya adı üzerine yazıldığı için tarayıcı eski STL'i
    // önbellekten kullanmasın diye zaman damgası ekleniyor.
    setStlUrl(resolveTessellationUrl(tessellation.tessellation_url, Date.now()));
    setSelection(null);

    const [edgeList, pointList] = await Promise.all([fetchEdges(geoId), fetchPoints(geoId)]);
    setEdges(edgeList);
    setPoints(pointList);
  }

  async function handleCopySurface() {
    if (!geometryId || mode !== "surface" || !selection || selection.mode !== "surface") return;

    setBusyAction("copy");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await copySurface(geometryId, selection.id);
      await refreshAfterMutation(geometryId, result);
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

  /** Heal: geometriyi düzeltir. Yüzey ID'leri yeniden numaralanabildiği için
   * (backend'de doğrulandı) kullanıcıya bunu belirten bir uyarı gösterilir.
   */
  async function handleHeal() {
    if (!geometryId) return;
    if (
      !window.confirm(
        "Geometry healing geometriyi değiştirebilir ve yüzey/kenar numaralarını " +
          "yeniden düzenleyebilir — mevcut Physical Group atamalarınız yanlış " +
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
        `Healing tamamlandı: parça ${result.volumes_before}→${result.volumes_after}, ` +
          `yüzey ${result.surfaces_before}→${result.surfaces_after}. ` +
          `Yüzey numaraları değişmiş olabilir — mevcut Physical Group atamalarınızı kontrol edin.`,
      );
      // Physical Group'lar hâlâ DB'de duruyor ama artık yanlış yüzeyi işaret
      // ediyor olabilir; listeyi yine de tazeleyelim (sayı değişmez, ama
      // tutarlılık için).
      const groups = await fetchPhysicalGroups(geometryId);
      setPhysicalGroups(groups);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Healing başarısız oldu.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  /** Defeature: sadece TESPİT — hiçbir şey kaldırılmıyor/değiştirilmiyor. */
  async function handleFindDefeatureCandidates() {
    if (!geometryId) return;
    const threshold = parseFloat(defeatureThreshold);
    if (!Number.isFinite(threshold) || threshold <= 0) {
      setErrorMessage("Geçerli bir pozitif eşik değeri girin.");
      return;
    }

    setBusyAction("defeature");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const candidates = await findDefeatureCandidates(geometryId, threshold);
      setDefeatureCandidates(candidates);
      if (candidates.length > 0) {
        // Adayları görebilmek için Kenar moduna geç (kenar çizgileri sadece
        // bu modda görünür/etkileşimli).
        setMode("edge");
        setInfoMessage(
          `${candidates.length} aday kenar bulundu ve Kenar modunda vurgulandı. ` +
            `NOT: bu sadece tespit — kaldırma henüz desteklenmiyor.`,
        );
      } else {
        setInfoMessage("Bu eşiğin altında aday kenar bulunamadı.");
      }
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Defeature adayları alınamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  /** Midsurface: iki aşamalı — önce bir yüzey seçilip buton basılır (A olarak
   * kaydedilir), sonra ikinci yüzey seçilip buton tekrar basılır (gönderilir).
   */
  async function handleMidsurfaceClick() {
    if (!geometryId || mode !== "surface" || !selection || selection.mode !== "surface") return;

    if (midsurfaceFirstFaceId === null) {
      setMidsurfaceFirstFaceId(selection.id);
      setInfoMessage(`Yüzey #${selection.id} seçildi. Şimdi ikinci (paralel) yüzeyi seçin.`);
      return;
    }

    if (selection.id === midsurfaceFirstFaceId) {
      // Aynı yüzey tekrar seçildi/tıklandı — iptal say.
      setMidsurfaceFirstFaceId(null);
      setInfoMessage(null);
      return;
    }

    const faceIdA = midsurfaceFirstFaceId;
    const faceIdB = selection.id;
    setMidsurfaceFirstFaceId(null);
    setBusyAction("midsurface");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await createMidsurface(geometryId, faceIdA, faceIdB);
      await refreshAfterMutation(geometryId, result);
      setInfoMessage(`Midsurface oluşturuldu: yeni yüzey #${result.new_face_id}.`);
    } catch (err) {
      const message =
        err instanceof GeometryUploadError ? err.message : "Midsurface oluşturulamadı.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

  const activeGroup = physicalGroups.find((g) => g.id === activeGroupId) ?? null;
  const externalHighlight = activeGroup
    ? { faceIds: activeGroup.entity_tags }
    : defeatureCandidates.length > 0
      ? { edgeIds: defeatureCandidates.map((c) => c.edge_id) }
      : null;

  const canCopySurface = mode === "surface" && selection?.mode === "surface";
  const canToggleHidePart = mode === "part" && selection?.mode === "part";
  const showGroupForm = mode === "surface" && selection?.mode === "surface";
  const canCreateGroup = showGroupForm && newGroupName.trim().length > 0;
  const canUseMidsurface = mode === "surface" && selection?.mode === "surface";

  const midsurfaceLabel =
    busyAction === "midsurface"
      ? "Oluşturuluyor…"
      : midsurfaceFirstFaceId === null
        ? "Midsurface (1. yüzey)"
        : `Midsurface (2. yüzey, A=#${midsurfaceFirstFaceId})`;

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

            {showDefeaturePanel && (
              <div className="group-create-form">
                <input
                  type="number"
                  className="group-name-input"
                  placeholder="Eşik (örn. 5)"
                  value={defeatureThreshold}
                  onChange={(e) => setDefeatureThreshold(e.target.value)}
                  disabled={busyAction === "defeature"}
                  min="0"
                  step="0.1"
                />
                <button
                  type="button"
                  className="group-create-button"
                  onClick={() => void handleFindDefeatureCandidates()}
                  disabled={busyAction === "defeature"}
                >
                  {busyAction === "defeature" ? "Aranıyor…" : "Adayları bul"}
                </button>
              </div>
            )}

            {defeatureCandidates.length > 0 && (
              <div className="defeature-results">
                <p className="face-info-total">{defeatureCandidates.length} aday kenar:</p>
                <ul className="defeature-list">
                  {defeatureCandidates.map((c) => (
                    <li key={c.edge_id}>
                      #{c.edge_id} — çap ≈ {c.approx_diameter.toFixed(2)} (parça {c.part_id})
                    </li>
                  ))}
                </ul>
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
                  {
                    key: "toggle-edges",
                    label: showEdges ? "Kenar çizgileri (açık)" : "Kenar çizgileri (kapalı)",
                    active: showEdges,
                    onClick: () => setShowEdges((prev) => !prev),
                  },
                  { key: "placeholder-2", label: "Yakında", disabled: true },
                ]}
              />
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
                    label: "Defeature",
                    active: showDefeaturePanel,
                    disabled: busyAction !== null,
                    onClick: () => setShowDefeaturePanel((prev) => !prev),
                  },
                  {
                    key: "midsurface",
                    label: midsurfaceLabel,
                    active: midsurfaceFirstFaceId !== null,
                    disabled: !canUseMidsurface || busyAction !== null,
                    onClick: () => void handleMidsurfaceClick(),
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
            <GeometryViewer
              stlUrl={stlUrl}
              triangleToFace={triangleToFace}
              triangleToPart={triangleToPart}
              edges={edges}
              points={points}
              mode={mode}
              hiddenParts={hiddenParts}
              showEdges={showEdges}
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
