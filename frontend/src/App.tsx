import { useRef, useState } from "react";
import { GeometryUploadError, resolveTessellationUrl, uploadGeometry } from "./api/geometry";
import GeometryViewer from "./components/GeometryViewer";

type Status = "idle" | "uploading" | "error" | "success";

const ACCEPTED_EXTENSIONS = ".step,.stp,.igs,.iges";

function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFileSelected(file: File) {
    setStatus("uploading");
    setErrorMessage(null);
    setFileName(file.name);

    try {
      const result = await uploadGeometry(file);
      setStlUrl(resolveTessellationUrl(result.tessellation_url));
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
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <main className="page">
      <div className="panel">
        <span className="eyebrow">Faz 0 · Geometri önizleme</span>
        <h1>Geometri yükle</h1>
        <p className="lead">
          STEP ya da IGES dosyanızı seçin, sunucu Gmsh ile tessellation üretsin —
          sonucu aşağıda döndürerek inceleyebilirsiniz.
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

        {status !== "idle" && (
          <button type="button" className="reset-button" onClick={handleReset}>
            Yeni dosya seç
          </button>
        )}
      </div>

      <div className="viewer-panel">
        {stlUrl ? (
          <GeometryViewer stlUrl={stlUrl} />
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
