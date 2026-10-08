import { useState } from "react";
import { downloadGeometryStep, TemplateApiError } from "../api/templates";

/**
 * Yüklü geometrinin güncel STEP'ini indirir (TODO 11.6). Önceden şablon
 * panelindeydi — o panel yalnız geometri YOKKEN görünür, düğme hep kapalı
 * kalıyordu. Artık Geometri adımında, geometri yüklüyken.
 */
export default function GeometryStepDownload({
  geometryId,
  filename,
  disabled = false,
}: {
  geometryId: number;
  filename: string | null;
  disabled?: boolean;
}) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadGeometryStep(geometryId, filename ?? `geometry-${geometryId}.step`);
    } catch (e) {
      setError(e instanceof TemplateApiError ? e.message : "STEP indirilemedi.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="geometry-step-download">
      <button
        type="button"
        className="material-secondary-button"
        disabled={disabled || downloading}
        onClick={() => void handleDownload()}
      >
        {downloading ? "İndiriliyor…" : "STEP indir"}
      </button>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
