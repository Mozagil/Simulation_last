import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import GeometryViewer from "./GeometryViewer";
import type { CameraState, GeometryViewerHandle } from "./GeometryViewer";
import {
  fetchMeshPreview,
  fetchResultsPreview,
  resolveTessellationUrl,
  type MeshPreviewData,
  type ResultsPreviewData,
} from "../api/geometry";
import { fetchRunDetail, type RunDetail } from "../api/runs";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

interface ComparisonViewProps {
  runIdA: number;
  runIdB: number;
  onBack: () => void;
}

interface RunPanelData {
  detail: RunDetail;
  stlUrl: string;
  triangleToFace: number[];
  triangleToPart: number[];
  meshPreview: MeshPreviewData | null;
  resultsPreview: ResultsPreviewData | null;
}

/** Bir run için karşılaştırma paneline gereken tüm veriyi çeker.
 *
 * NOT: triangle_to_face/part için AYRI bir backend endpoint YOK — bu
 * dosyalar zaten `/files/tessellations/{geometry_id}.faces.json` /
 * `.parts.json` olarak statik sunuluyor (upload/mutasyon anında yazılıyor,
 * kalıcı). Karşılaştırma modu bunları doğrudan fetch ediyor.
 */
async function loadRunPanelData(runId: number): Promise<RunPanelData> {
  const detail = await fetchRunDetail(runId);
  if (!detail.tessellation_url) {
    throw new Error(`Run #${runId}: geometri tessellation'ı bulunamadı.`);
  }

  const facesUrl = `${API_BASE_URL}/files/tessellations/${detail.geometry_id}.faces.json`;
  const partsUrl = `${API_BASE_URL}/files/tessellations/${detail.geometry_id}.parts.json`;

  const [facesResp, partsResp] = await Promise.all([fetch(facesUrl), fetch(partsUrl)]);
  const triangleToFace: number[] = facesResp.ok ? await facesResp.json() : [];
  const triangleToPart: number[] = partsResp.ok ? await partsResp.json() : [];

  const meshPreview = detail.mesh_preview_url
    ? await fetchMeshPreview(detail.mesh_preview_url)
    : null;
  const resultsPreview = detail.results_preview_url
    ? await fetchResultsPreview(detail.results_preview_url)
    : null;

  return {
    detail,
    stlUrl: resolveTessellationUrl(detail.tessellation_url),
    triangleToFace,
    triangleToPart,
    meshPreview,
    resultsPreview,
  };
}

/** Tek bir karşılaştırma panelini (salt okunur GeometryViewer + üst bilgi
 * kartı) render eder.
 */
function ComparisonPanel({
  runId,
  resultsField,
  sharedScaleMax,
  viewerRef,
  onCameraChange,
}: {
  runId: number;
  resultsField: "von_mises" | "displacement_magnitude";
  sharedScaleMax: number | null;
  viewerRef: RefObject<GeometryViewerHandle>;
  onCameraChange: (state: CameraState) => void;
}) {
  const [data, setData] = useState<RunPanelData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deformScale, setDeformScale] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    loadRunPanelData(runId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) {
    return <div className="compare-panel-error">Hata: {error}</div>;
  }
  if (!data) {
    return <div className="compare-panel-loading">Yükleniyor…</div>;
  }

  const scalarLabel = resultsField === "von_mises" ? "Max von Mises" : "Max deplasman";
  const scalarValue =
    resultsField === "von_mises"
      ? data.detail.scalars.max_von_mises
      : data.detail.scalars.max_displacement;

  return (
    <div className="compare-panel">
      <div className="compare-panel-header">
        <div className="compare-panel-title">{data.detail.name ?? `Run #${data.detail.id}`}</div>
        <div className="compare-panel-sub">
          {data.detail.geometry_filename} · {data.detail.dimension === 2 ? "2D shell" : "3D solid"} ·{" "}
          {new Date(data.detail.created_at).toLocaleString("tr-TR")}
        </div>
        <div className="compare-panel-scalar">
          {scalarLabel}: {scalarValue !== undefined ? scalarValue.toExponential(3) : "—"}
        </div>
        {data.resultsPreview && (
          <label className="compare-deform-row">
            <span>Deformasyon {deformScale.toFixed(0)}×</span>
            <input
              type="range"
              min={0}
              max={
                data.detail.scalars.max_displacement > 1e-30
                  ? (0.3 * 500) / data.detail.scalars.max_displacement
                  : 200
              }
              value={deformScale}
              onChange={(e) => setDeformScale(parseFloat(e.target.value))}
            />
          </label>
        )}
      </div>
      <div className="compare-panel-viewer">
        <GeometryViewer
          ref={viewerRef}
          onCameraChange={onCameraChange}
          stlUrl={data.stlUrl}
          triangleToFace={data.triangleToFace}
          triangleToPart={data.triangleToPart}
          edges={[]}
          points={[]}
          mode="part"
          hiddenParts={new Set()}
          showEdges={true}
          meshPreview={data.meshPreview}
          showMesh={false}
          meshWireframe={false}
          resultsPreview={data.resultsPreview}
          showResults={data.resultsPreview !== null}
          resultsField={resultsField}
          resultsDeformScale={deformScale}
          resultsScaleMin={0}
          resultsScaleMax={sharedScaleMax}
          viewerBackground="white"
          cadOpacity={1}
          selectedIds={[]}
          meshPicks={[]}
          meshGrow="element"
          externalHighlight={null}
        />
      </div>
    </div>
  );
}

/** İki analiz run'ını aynı ekranda, yan yana (split-screen) gösterir — AYNI
 * renk skalasını paylaşırlar (ikisinin de max_von_mises'inin büyüğü) ki
 * renkler doğrudan karşılaştırılabilir olsun.
 */
export default function ComparisonView({ runIdA, runIdB, onBack }: ComparisonViewProps) {
  const [resultsField, setResultsField] = useState<"von_mises" | "displacement_magnitude">(
    "von_mises",
  );
  const [scalarsA, setScalarsA] = useState<Record<string, number> | null>(null);
  const [scalarsB, setScalarsB] = useState<Record<string, number> | null>(null);
  const [cameraSyncEnabled, setCameraSyncEnabled] = useState(false);
  const viewerRefA = useRef<GeometryViewerHandle>(null);
  const viewerRefB = useRef<GeometryViewerHandle>(null);

  useEffect(() => {
    fetchRunDetail(runIdA).then((d) => setScalarsA(d.scalars));
    fetchRunDetail(runIdB).then((d) => setScalarsB(d.scalars));
  }, [runIdA, runIdB]);

  const key = resultsField === "von_mises" ? "max_von_mises" : "max_displacement";
  const sharedScaleMax =
    scalarsA && scalarsB ? Math.max(scalarsA[key] ?? 0, scalarsB[key] ?? 0) || null : null;

  return (
    <div className="compare-view">
      <div className="compare-toolbar">
        <button type="button" className="reset-button" onClick={onBack}>
          ← Düzenlemeye dön
        </button>
        <div className="results-field-toggle">
          <button
            type="button"
            className={resultsField === "von_mises" ? "group-create-button" : "reset-button"}
            onClick={() => setResultsField("von_mises")}
          >
            Von Mises
          </button>
          <button
            type="button"
            className={
              resultsField === "displacement_magnitude" ? "group-create-button" : "reset-button"
            }
            onClick={() => setResultsField("displacement_magnitude")}
          >
            Deplasman
          </button>
        </div>
        <button
          type="button"
          className={cameraSyncEnabled ? "group-create-button" : "reset-button"}
          onClick={() => setCameraSyncEnabled((prev) => !prev)}
          title="Bir paneli döndürünce diğeri de aynı şekilde dönsün"
        >
          {cameraSyncEnabled ? "🔗 Kamera Senkron (açık)" : "🔗 Kamera Senkron"}
        </button>
        <span className="compare-hint">
          İki panel de aynı renk skalasını paylaşıyor (max=
          {sharedScaleMax?.toExponential(2) ?? "—"})
        </span>
      </div>
      <div className="compare-panels">
        <ComparisonPanel
          runId={runIdA}
          resultsField={resultsField}
          sharedScaleMax={sharedScaleMax}
          viewerRef={viewerRefA}
          onCameraChange={(state) => {
            if (cameraSyncEnabled) viewerRefB.current?.setCameraState(state);
          }}
        />
        <ComparisonPanel
          runId={runIdB}
          resultsField={resultsField}
          sharedScaleMax={sharedScaleMax}
          viewerRef={viewerRefB}
          onCameraChange={(state) => {
            if (cameraSyncEnabled) viewerRefA.current?.setCameraState(state);
          }}
        />
      </div>
    </div>
  );
}
