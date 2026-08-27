import { useCallback, useEffect, useRef, useState } from "react";
import {
  DefeatureCandidate,
  EdgeInfo,
  GeometryUploadError,
  PhysicalGroup,
  PointInfo,
  copySurface,
  createMidsurface,
  createMidsurfaceForPart,
  createPhysicalGroup,
  fetchEdges,
  fetchPhysicalGroups,
  fetchPoints,
  findDefeatureCandidates,
  healGeometry,
  undoLastMutation,
  resolveTessellationUrl,
  uploadGeometry,
} from "./api/geometry";
import ButtonGroup from "./components/ButtonGroup";
import GeometryViewer from "./components/GeometryViewer";
import { MultiSelectionInfo, SELECTION_MODES, SelectionMode } from "./types";

type Status = "idle" | "uploading" | "error" | "success";

const ACCEPTED_EXTENSIONS = ".step,.stp,.igs,.iges";
const EMPTY_SELECTION: MultiSelectionInfo = { mode: "surface", ids: [] };

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

  // Defeature: eşik girişi + sonuç listesi paneli.
  const [showDefeaturePanel, setShowDefeaturePanel] = useState(false);
  const [defeatureThreshold, setDefeatureThreshold] = useState("5");
  const [defeatureCandidates, setDefeatureCandidates] = useState<DefeatureCandidate[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mod değişince aktif grup vurgusu ve defeature sonuçları anlamsızlaşır, temizle.
  useEffect(() => {
    setActiveGroupId(null);
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);
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
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);
    setCanUndo(false);

    try {
      const result = await uploadGeometry(file);
      setGeometryId(result.geometry_id);
      setStlUrl(resolveTessellationUrl(result.tessellation_url));
      setTriangleToFace(result.triangle_to_face);
      setTriangleToPart(result.triangle_to_part);
      setVolumePartIds(result.volume_part_ids);
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
    setDefeatureCandidates([]);
    setShowDefeaturePanel(false);
    setCanUndo(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const handleSelectionChange = useCallback((info: MultiSelectionInfo) => {
    setSelection(info);
  }, []);

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
      const groups = await fetchPhysicalGroups(geometryId);
      setPhysicalGroups(groups);
    } catch (err) {
      const message = err instanceof GeometryUploadError ? err.message : "Healing başarısız oldu.";
      setErrorMessage(message);
    } finally {
      setBusyAction(null);
    }
  }

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

  /** Midsurface: kullanıcı Parça modunda TEK bir parça seçer, backend o
   * parçanın en uygun paralel/düzlemsel yüzey çiftini kendisi bulur.
   */
  async function handleMidsurfaceForPart() {
    if (!geometryId || mode !== "part" || selection.ids.length !== 1) return;
    const partId = selection.ids[0];

    setBusyAction("midsurface");
    setErrorMessage(null);
    setInfoMessage(null);
    try {
      const result = await createMidsurfaceForPart(geometryId, partId);
      await refreshAfterMutation(geometryId, result);
      setInfoMessage(
        `Midsurface oluşturuldu: parça #${partId}'in yüzey ${result.chosen_face_id_a} ve ` +
          `${result.chosen_face_id_b} arasında, yeni yüzey #${result.new_face_id}.`,
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
  const externalHighlight = activeGroup
    ? { faceIds: activeGroup.entity_tags }
    : defeatureCandidates.length > 0
      ? { edgeIds: defeatureCandidates.map((c) => c.edge_id) }
      : null;

  const canCopySurface = mode === "surface" && selection.ids.length === 1;
  const showGroupForm = mode === "surface" && selection.ids.length > 0;
  const canCreateGroup = showGroupForm && newGroupName.trim().length > 0;

  // "Solid gizle/göster" HER ZAMAN aktif (model yüklüyse) — sadece GERÇEK
  // solid'leri hedefler (volume_part_ids), copy_surface/midsurface çıktısı
  // gibi düz yüzeyleri asla hedeflemez. Seçim yoksa tüm gerçek solid'ler,
  // seçim varsa (hangi modda olursa olsun) sadece o seçime karşılık gelen
  // gerçek solid'ler.
  const volumePartIdSet = new Set(volumePartIds);
  const resolvedPartIdsForHide =
    selection.ids.length > 0
      ? resolvePartIdsForSelection(selection).filter((id) => volumePartIdSet.has(id))
      : volumePartIds;
  const canToggleHidePart = geometryId !== null && volumePartIds.length > 0;
  const allSelectedPartsHidden =
    resolvedPartIdsForHide.length > 0 &&
    resolvedPartIdsForHide.every((id) => hiddenParts.has(id));

  // Midsurface: Parça modunda TEK parça seçiliyse OTOMATİK tespit; Yüzey
  // modunda TAM 2 yüzey seçiliyse MANUEL (kullanıcı kendi çifti belirler —
  // otomatik tespit karmaşık profillerde (örn. 4 köşeli C-kanal) yanlış
  // çifti seçebiliyor, bu yüzden manuel bir yedek yol tutuluyor).
  const canUseMidsurfaceAuto = mode === "part" && selection.ids.length === 1;
  const canUseMidsurfaceManual = mode === "surface" && selection.ids.length === 2;
  const canUseMidsurface = canUseMidsurfaceAuto || canUseMidsurfaceManual;

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
                    label: allSelectedPartsHidden ? "Solid göster" : "Solid gizle",
                    disabled: !canToggleHidePart,
                    onClick: handleToggleHidePart,
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
