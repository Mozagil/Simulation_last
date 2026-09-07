import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import GeometryViewer from "./GeometryViewer";
import type { CameraState, GeometryViewerHandle, ResultProbeHit } from "./GeometryViewer";
import { ResultsHistogram, ResultsStatsTable } from "./ResultsCharts";
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
  /** Verilmezse tek run inceleme (geçmişten açılan case). */
  runIdB?: number;
  onBack: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}

interface RunPanelData {
  detail: RunDetail;
  stlUrl: string;
  triangleToFace: number[];
  triangleToPart: number[];
  meshPreview: MeshPreviewData | null;
  resultsPreview: ResultsPreviewData | null;
}

function jetRgb(t: number): string {
  const c = Math.min(1, Math.max(0, t));
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * c - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * c - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * c - 1)));
  return `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
}

function fmtNum(v: number | undefined, digits = 3): string {
  if (v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 1000 || (Math.abs(v) < 0.01 && v !== 0)) return v.toExponential(digits);
  return v.toFixed(digits);
}

function deltaPct(ref: number | undefined, value: number | undefined): number | null {
  if (ref === undefined || value === undefined || Math.abs(ref) < 1e-30) return null;
  return ((value - ref) / ref) * 100;
}

/** Model bbox'ının en uzun kenarı — deformasyon kaydırıcısını buna göre sınırla.
 * Sabit 500 mm varsayımı küçük parçalarda 7000× gibi çarpanlar üretiyordu;
 * bir milim kaydırınca kontur CAD'den kopup geometriyi bozuyordu.
 */
function nodesBBoxSize(nodes: number[][] | undefined): number {
  if (!nodes || nodes.length === 0) return 1;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const [x, y, z] of nodes) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
    if (z < minZ) minZ = z;
    if (z > maxZ) maxZ = z;
  }
  return Math.max(maxX - minX, maxY - minY, maxZ - minZ) || 1;
}

function adaptiveDeformMax(maxDisplacement: number, bboxSize: number): number {
  if (!(maxDisplacement > 1e-30)) return 200;
  return (0.3 * bboxSize) / maxDisplacement;
}

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

function ComparisonPanel({
  runId,
  resultsField,
  sharedScaleMax,
  viewerRef,
  onCameraChange,
  probeEnabled,
  isRef,
  refMaxStress,
}: {
  runId: number;
  resultsField: "von_mises" | "displacement_magnitude";
  sharedScaleMax: number | null;
  viewerRef: RefObject<GeometryViewerHandle>;
  onCameraChange: (state: CameraState) => void;
  probeEnabled: boolean;
  isRef: boolean;
  refMaxStress?: number;
}) {
  const [data, setData] = useState<RunPanelData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deformScale, setDeformScale] = useState(0);
  const [showCad, setShowCad] = useState(true);
  const [showResults, setShowResults] = useState(true);
  const [probes, setProbes] = useState<ResultProbeHit[]>([]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    setProbes([]);
    setDeformScale(0);
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

  const s = data.detail.scalars;
  const maxStress = s.max_von_mises;
  const sf = s.safety_factor;
  const life = s.fatigue_life_cycles;
  const dStress = isRef ? null : deltaPct(refMaxStress, maxStress);
  const risk = sf !== undefined && sf < 1;

  const fieldValues =
    data.resultsPreview == null
      ? []
      : resultsField === "von_mises"
        ? data.resultsPreview.von_mises
        : data.resultsPreview.displacement_magnitude;

  const bboxSize = nodesBBoxSize(data.meshPreview?.nodes ?? data.resultsPreview?.nodes);
  const maxDisp = data.resultsPreview?.max_displacement ?? data.detail.scalars.max_displacement ?? 0;
  const deformMax = adaptiveDeformMax(maxDisp, bboxSize);
  const clampedDeform = Math.min(deformScale, deformMax);

  return (
    <div className="compare-panel">
      <div className="compare-panel-header">
        <div className="compare-panel-title-row">
          <div className="compare-panel-title">{data.detail.name ?? `Run #${data.detail.id}`}</div>
          {isRef ? (
            <span className="compare-tag compare-tag-ref">REF</span>
          ) : dStress !== null ? (
            <span className={`compare-tag ${dStress < 0 ? "compare-tag-down" : "compare-tag-up"}`}>
              Δ {dStress >= 0 ? "+" : ""}
              {dStress.toFixed(0)}%
            </span>
          ) : null}
          {risk && <span className="compare-tag compare-tag-risk">RİSK</span>}
        </div>
        <div className="compare-panel-sub">
          {data.detail.geometry_filename} · {data.detail.dimension === 2 ? "2D shell" : "3D solid"} ·{" "}
          {new Date(data.detail.created_at).toLocaleString("tr-TR")}
        </div>
        <div className="compare-metrics">
          <div>
            <span>max σ</span>
            <strong>{fmtNum(maxStress)}</strong>
          </div>
          <div>
            <span>SF</span>
            <strong>{sf !== undefined ? sf.toFixed(2) : "—"}</strong>
          </div>
          <div>
            <span>life</span>
            <strong>{life !== undefined ? life.toExponential(1) : "—"}</strong>
          </div>
        </div>
        <div className="compare-toggles">
          <label>
            <input type="checkbox" checked={showCad} onChange={(e) => setShowCad(e.target.checked)} />
            Geometri
          </label>
          <label>
            <input
              type="checkbox"
              checked={showResults}
              disabled={!data.resultsPreview}
              onChange={(e) => setShowResults(e.target.checked)}
            />
            Sonuç
          </label>
        </div>
        {data.resultsPreview && (
          <label className="compare-deform-row">
            <span>
              Deformasyon {clampedDeform.toFixed(0)}×
              {maxDisp > 0 ? ` · kayma ≈ ${(clampedDeform * maxDisp).toFixed(2)}` : ""}
            </span>
            <input
              type="range"
              min={0}
              max={deformMax}
              step={deformMax / 200}
              value={clampedDeform}
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
          showResults={showResults && data.resultsPreview !== null}
          resultsField={resultsField}
          resultsDeformScale={clampedDeform}
          resultsScaleMin={0}
          resultsScaleMax={sharedScaleMax}
          viewerBackground="white"
          cadOpacity={clampedDeform > 0 ? 0.18 : 1}
          showCad={showCad}
          probeEnabled={probeEnabled}
          onResultProbe={(hit) => {
            setProbes((prev) => {
              if (prev.some((p) => p.nodeId === hit.nodeId)) return prev;
              return [...prev, hit];
            });
          }}
          selectedIds={[]}
          meshPicks={[]}
          meshGrow="element"
          externalHighlight={null}
        />
      </div>
      <div className="compare-panel-footer">
        {fieldValues.length > 0 && (
          <>
            <ResultsStatsTable
              label={resultsField === "von_mises" ? "von Mises" : "deplasman"}
              values={fieldValues}
            />
            <ResultsHistogram
              label="dağılım"
              values={fieldValues}
              color="var(--accent, #2a6f97)"
            />
          </>
        )}
        {probes.length > 0 && (
          <div className="compare-probes">
            <p className="results-stats-title">
              Probe ({probes.length})
              <button type="button" className="compare-probe-clear" onClick={() => setProbes([])}>
                temizle
              </button>
            </p>
            <table>
              <thead>
                <tr>
                  <th>id</th>
                  <th>σ</th>
                  <th>|U|</th>
                </tr>
              </thead>
              <tbody>
                {probes.map((p) => (
                  <tr key={p.nodeId}>
                    <td>#{p.nodeId}</td>
                    <td>{fmtNum(p.vonMises)}</td>
                    <td>{fmtNum(p.displacement)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ComparisonView({
  runIdA,
  runIdB,
  onBack,
  onEdit,
  onDelete,
}: ComparisonViewProps) {
  const single = runIdB === undefined;
  const [resultsField, setResultsField] = useState<"von_mises" | "displacement_magnitude">(
    "von_mises",
  );
  const [scalarsA, setScalarsA] = useState<Record<string, number> | null>(null);
  const [scalarsB, setScalarsB] = useState<Record<string, number> | null>(null);
  const [cameraSyncEnabled, setCameraSyncEnabled] = useState(false);
  const [probeEnabled, setProbeEnabled] = useState(false);
  const viewerRefA = useRef<GeometryViewerHandle>(null);
  const viewerRefB = useRef<GeometryViewerHandle>(null);

  useEffect(() => {
    fetchRunDetail(runIdA).then((d) => setScalarsA(d.scalars));
    if (runIdB !== undefined) {
      fetchRunDetail(runIdB).then((d) => setScalarsB(d.scalars));
    } else {
      setScalarsB(null);
    }
  }, [runIdA, runIdB]);

  const key = resultsField === "von_mises" ? "max_von_mises" : "max_displacement";
  const sharedScaleMax = single
    ? (scalarsA?.[key] ?? 0) || null
    : scalarsA && scalarsB
      ? Math.max(scalarsA[key] ?? 0, scalarsB[key] ?? 0) || null
      : null;

  const tickCount = 5;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => {
    const t = i / tickCount;
    return (sharedScaleMax ?? 1) * t;
  });
  const gradientStops = Array.from({ length: 11 }, (_, i) => {
    const t = i / 10;
    return `${jetRgb(t)} ${t * 100}%`;
  }).join(", ");

  return (
    <div className="compare-view">
      <div className="compare-toolbar">
        <button type="button" className="reset-button" onClick={onBack}>
          ← Düzenlemeye dön
        </button>
        {single && onEdit && (
          <button type="button" className="group-create-button" onClick={onEdit}>
            Düzenle
          </button>
        )}
        {single && onDelete && (
          <button
            type="button"
            className="reset-button history-action-button-danger"
            onClick={onDelete}
          >
            Sil
          </button>
        )}
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
        {!single && (
          <button
            type="button"
            className={cameraSyncEnabled ? "group-create-button" : "reset-button"}
            onClick={() => setCameraSyncEnabled((prev) => !prev)}
          >
            {cameraSyncEnabled ? "Kamera senkron (açık)" : "Kamera senkron"}
          </button>
        )}
        <button
          type="button"
          className={probeEnabled ? "group-create-button" : "reset-button"}
          onClick={() => setProbeEnabled((prev) => !prev)}
          title="Geometri veya kontura tıklayınca en yakın düğümün σ / |U| / id değeri okunur"
        >
          {probeEnabled ? "Probe (açık)" : "Probe"}
        </button>
        <a
          className="reset-button"
          href={`${API_BASE_URL}/geometry/runs/${runIdA}/report.pdf`}
          target="_blank"
          rel="noreferrer"
        >
          {single ? "PDF" : "PDF A"}
        </a>
        {!single && runIdB !== undefined && (
          <a
            className="reset-button"
            href={`${API_BASE_URL}/geometry/runs/${runIdB}/report.pdf`}
            target="_blank"
            rel="noreferrer"
          >
            PDF B
          </a>
        )}
      </div>
      <div className={single ? "compare-panels compare-panels-single" : "compare-panels"}>
        <ComparisonPanel
          runId={runIdA}
          resultsField={resultsField}
          sharedScaleMax={sharedScaleMax}
          viewerRef={viewerRefA}
          probeEnabled={probeEnabled}
          isRef={!single}
          onCameraChange={(state) => {
            if (!single && cameraSyncEnabled) viewerRefB.current?.setCameraState(state);
          }}
        />
        {!single && runIdB !== undefined && (
          <ComparisonPanel
            runId={runIdB}
            resultsField={resultsField}
            sharedScaleMax={sharedScaleMax}
            viewerRef={viewerRefB}
            probeEnabled={probeEnabled}
            isRef={false}
            refMaxStress={scalarsA?.max_von_mises}
            onCameraChange={(state) => {
              if (cameraSyncEnabled) viewerRefA.current?.setCameraState(state);
            }}
          />
        )}
      </div>
      <div className="compare-shared-bar">
        <div className="compare-shared-colorbar">
          <span className="compare-shared-label">{single ? "COLORBAR" : "ORTAK COLORBAR"}</span>
          <div
            className="compare-shared-track"
            style={{ background: `linear-gradient(to right, ${gradientStops})` }}
          />
          <div className="compare-shared-ticks">
            {ticks.map((v, i) => (
              <span key={i}>{fmtNum(v, 2)}</span>
            ))}
          </div>
        </div>
        <div className="compare-shared-note">
          {single
            ? "Bu run’ın kayıtlı geometri / mesh / sonuç anlık görüntüsü. Probe açıkken kontura veya geometriye tıklayın."
            : `İki panel aynı skalayı kullanır (max=${sharedScaleMax !== null ? fmtNum(sharedScaleMax) : "—"}). Probe açıkken kontura veya geometriye tıklayın.`}
        </div>
      </div>
    </div>
  );
}
