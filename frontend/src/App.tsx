import { useCallback, useRef, useState } from "react";
import {
  EdgeInfo,
  GeometryUploadError,
  PointInfo,
  fetchEdges,
  fetchPoints,
  resolveTessellationUrl,
  uploadGeometry,
} from "./api/geometry";
import GeometryViewer from "./components/GeometryViewer";
import SelectionModeBar from "./components/SelectionModeBar";
import { SelectionInfo, SelectionMode } from "./types";

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
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [triangleToFace, setTriangleToFace] = useState<number[]>([]);
  const [triangleToPart, setTriangleToPart] = useState<number[]>([]);
  const [faceCount, setFaceCount] = useState<number | null>(null);
  const [partCount, setPartCount] = useState<number | null>(null);
  const [edges, setEdges] = useState<EdgeInfo[]>([]);
  const [points, setPoints] = useState<PointInfo[]>([]);
  const [mode, setMode] = useState<SelectionMode>("surface");
  const [selection, setSelection] = useState<SelectionInfo | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFileSelected(file: File) {
    setStatus("uploading");
    setErrorMessage(null);
    setFileName(file.name);
    setSelection(null);
    setMode("surface");

    try {
      const result = await uploadGeometry(file);
      setStlUrl(resolveTessellationUrl(result.tessellation_url));
      setTriangleToFace(result.triangle_to_face);
      setTriangleToPart(result.triangle_to_part);
      setFaceCount(result.face_count);
      setPartCount(result.part_count);

      // Kenar/nokta listeleri ayrı endpoint'lerden — upload ile paralel değil,
      // ardından (stored_filename gerektiği için) çekiliyor.
      const [edgeList, pointList] = await Promise.all([
        fetchEdges(result.stored_filename),
        fetchPoints(result.stored_filename),
      ]);
      setEdges(edgeList);
      setPoints(pointList);

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
    setStlUrl(null);
    setTriangleToFace([]);
    setTriangleToPart([]);
    setFaceCount(null);
    setPartCount(null);
    setEdges([]);
    setPoints([]);
    setSelection(null);
    setMode("surface");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const handleSelectionChange = useCallback((info: SelectionInfo | null) => {
    setSelection(info);
  }, []);

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
          </div>
        )}

        {status !== "idle" && (
          <button type="button" className="reset-button" onClick={handleReset}>
            Yeni dosya seç
          </button>
        )}
      </div>

      <div className="viewer-panel">
        {stlUrl ? (
          <>
            <SelectionModeBar activeMode={mode} onChange={setMode} />
            <GeometryViewer
              stlUrl={stlUrl}
              triangleToFace={triangleToFace}
              triangleToPart={triangleToPart}
              edges={edges}
              points={points}
              mode={mode}
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
