import { useCallback, useEffect, useState } from "react";
import {
  fetchSurrogateStatus,
  predictSurrogate,
  trainFieldGnn,
  trainScalarRf,
  type SurrogatePredictResult,
  type SurrogateStatus,
} from "../api/surrogate";

function fmtR2(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

export default function SurrogatePanel({
  refreshKey,
  geometryId,
  runId,
  onPrediction,
}: {
  refreshKey?: number;
  geometryId?: number | null;
  runId?: number | null;
  onPrediction?: (result: SurrogatePredictResult) => void;
}) {
  const [status, setStatus] = useState<SurrogateStatus | null>(null);
  const [busy, setBusy] = useState<"rf" | "gnn" | "pred" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchSurrogateStatus()
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Durum alınamadı."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  async function handleTrainRf() {
    setBusy("rf");
    setError(null);
    setMessage(null);
    try {
      const r = await trainScalarRf();
      setMessage(
        `RF eğitildi · ${r?.n_samples ?? "?"} örnek · test R² disp ${fmtR2(r?.metrics?.test?.max_displacement?.r2)}`,
      );
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "RF eğitilemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handleTrainGnn() {
    setBusy("gnn");
    setError(null);
    setMessage(null);
    try {
      const r = await trainFieldGnn();
      const rmse = r?.metrics?.node_rmse?.von_mises_mpa;
      setMessage(
        `GNN eğitildi · ${r?.n_samples ?? "?"} graf` +
          (rmse != null ? ` · von Mises RMSE ${rmse.toFixed(2)}` : ""),
      );
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "GNN eğitilemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handlePredict() {
    setBusy("pred");
    setError(null);
    setMessage(null);
    try {
      const result = await predictSurrogate({
        runId: runId ?? undefined,
        geometryId: geometryId ?? undefined,
      });
      setMessage(result.message);
      onPrediction?.(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tahmin başarısız.");
    } finally {
      setBusy(null);
    }
  }

  const rf = status?.scalar_rf;
  const gnn = status?.field_gnn;
  const canPredict = geometryId != null || runId != null;

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.5 · Surrogate</span>
      <h1>Hızlı tahmin</h1>
      <p className="lead">
        Skaler RF boru hattı testidir; kontur GNN alan modelinden gelir. Tahmin
        tam çözüm değildir — hata payı sayılır, uzay dışı sorgular işaretlenir.
      </p>

      <div className="dataset-stats">
        <div>
          <strong>{rf?.n_samples ?? "—"}</strong>
          <span>RF örnek</span>
        </div>
        <div>
          <strong>{fmtR2(rf?.metrics?.test?.max_displacement?.r2)}</strong>
          <span>test R² disp</span>
        </div>
        <div>
          <strong>{gnn?.n_samples ?? "—"}</strong>
          <span>GNN graf</span>
        </div>
      </div>

      <div className="doe-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={busy !== null}
          onClick={() => void handleTrainRf()}
        >
          {busy === "rf" ? "Eğitiliyor…" : "RF eğit"}
        </button>
        <button
          type="button"
          className="material-secondary-button"
          disabled={busy !== null}
          onClick={() => void handleTrainGnn()}
        >
          {busy === "gnn" ? "Eğitiliyor…" : "GNN eğit"}
        </button>
        <button
          type="button"
          className="material-secondary-button"
          disabled={busy !== null || !canPredict}
          onClick={() => void handlePredict()}
        >
          {busy === "pred" ? "Tahmin…" : "Hızlı tahmin"}
        </button>
      </div>

      {message && <p className="dataset-message">{message}</p>}
      {error && <p className="dataset-error">{error}</p>}
    </div>
  );
}
