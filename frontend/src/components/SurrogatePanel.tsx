import { useCallback, useEffect, useRef, useState } from "react";
import {
  addRunsToCorpus,
  evaluateForCorpus,
  fetchCorpusList,
  fetchSurrogateStatus,
  freezeCorpus,
  predictFromParams,
  predictSurrogate,
  trainFieldGnn,
  trainScalarRf,
  type CorpusListItem,
  type CorpusRunVerdict,
  type ParamPredictResult,
  type SurrogatePredictResult,
  type SurrogateStatus,
} from "../api/surrogate";

/** Süzgeç gerekçelerinin okunur karşılığı; karar kullanıcıya ait. */
const REASON_TEXT: Record<string, string> = {
  large_displacement: "u/L eşiği aşıldı (lineer varsayım dışı)",
  mesh_outlier: "mesh oranı setin medyanından uzak",
  other_template: "başka şablon ailesi",
  other_material: "başka malzeme",
  analytic_warn: "analitik sapma uyarısı var",
  wrong_analysis: "statik değil",
  rigid_body: "rijit cisim / yakınsamamış",
  degenerate_mesh: "dejenere mesh",
  missing_features: "özellik veya hedef eksik",
  no_template: "şablon parametresi yok",
  not_solved: "çözülmemiş run",
  missing_run: "run bulunamadı",
};

function reasonText(reason: string | null): string {
  if (!reason) return "süzgeci geçti";
  return REASON_TEXT[reason] ?? reason;
}

function fmtR2(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

function fmtNum(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function num(raw: string): number {
  const v = Number(raw);
  if (!Number.isFinite(v)) throw new Error(`Sayı geçersiz: ${raw}`);
  return v;
}

export default function SurrogatePanel({
  refreshKey,
  geometryId,
  runId,
  onPrediction,
  onCorpusChange,
}: {
  refreshKey?: number;
  geometryId?: number | null;
  runId?: number | null;
  onPrediction?: (result: SurrogatePredictResult) => void;
  onCorpusChange?: (name: string | null) => void;
}) {
  const [status, setStatus] = useState<SurrogateStatus | null>(null);
  const [busy, setBusy] = useState<
    "rf" | "gnn" | "pred" | "params" | "freeze" | "evaluate" | "add" | null
  >(null);
  const [corpora, setCorpora] = useState<CorpusListItem[]>([]);
  const [corpus, setCorpus] = useState<string>("");
  const [newCorpusName, setNewCorpusName] = useState("kiris-v1");
  const [verdict, setVerdict] = useState<CorpusRunVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [paramResult, setParamResult] = useState<ParamPredictResult | null>(null);
  const [length, setLength] = useState("500");
  const [thickness, setThickness] = useState("10");
  const [width, setWidth] = useState("50");
  const [elementSize, setElementSize] = useState("8");
  const [youngs, setYoungs] = useState("2.1e11");
  const [poisson, setPoisson] = useState("0.3");
  const [fx, setFx] = useState("0");
  const [fy, setFy] = useState("-500");
  const [fz, setFz] = useState("0");
  const [compareOpenRun, setCompareOpenRun] = useState(true);
  const autoPickedCorpus = useRef(false);

  const reload = useCallback(() => {
    fetchSurrogateStatus()
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Durum alınamadı."));
    fetchCorpusList()
      .then((list) => {
        setCorpora(list);
        setCorpus((prev) => {
          if (prev) return prev;
          if (!autoPickedCorpus.current && list.length > 0) {
            autoPickedCorpus.current = true;
            return list[list.length - 1].name;
          }
          return prev;
        });
      })
      .catch(() => setCorpora([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  useEffect(() => {
    onCorpusChange?.(corpus || null);
  }, [corpus, onCorpusChange]);

  async function handleTrainRf() {
    setBusy("rf");
    setError(null);
    setMessage(null);
    try {
      const r = await trainScalarRf(corpus || null);
      const info = r?.corpus;
      const droppedN = Object.values(info?.dropped ?? {}).reduce((a, b) => a + b, 0);
      const flaggedN = Object.values(info?.flagged ?? {}).reduce((a, b) => a + b, 0);
      let msg = `RF eğitildi · ${r?.n_samples ?? "?"} örnek`;
      msg += corpus ? ` · set ${corpus}` : " · canlı süzgeç";
      if (info?.template_id) msg += ` · ${info.template_id}`;
      if (droppedN > 0) msg += ` · atılan ${droppedN}`;
      if (flaggedN > 0) msg += ` · eşik üstü ${flaggedN}`;
      msg += ` · test R² disp ${fmtR2(r?.metrics?.test?.max_displacement?.r2)}`;
      setMessage(msg);
      if (info?.youngs_modulus != null) setYoungs(String(info.youngs_modulus));
      if (info?.poisson_ratio != null) setPoisson(String(info.poisson_ratio));
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
      const r = await trainFieldGnn(corpus || null);
      const rmse = r?.metrics?.node_rmse?.von_mises_mpa;
      const info = r?.corpus;
      const droppedN = Object.values(info?.dropped ?? {}).reduce((a, b) => a + b, 0);
      let msg = `GNN eğitildi · ${r?.n_samples ?? "?"} graf`;
      msg += corpus ? ` · set ${corpus}` : " · canlı süzgeç";
      if (info?.template_id) msg += ` · ${info.template_id}`;
      if (droppedN > 0) msg += ` · atılan ${droppedN}`;
      if (rmse != null) msg += ` · von Mises RMSE ${rmse.toFixed(2)}`;
      setMessage(msg);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "GNN eğitilemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handleFreeze() {
    setBusy("freeze");
    setError(null);
    setMessage(null);
    try {
      const name = newCorpusName.trim();
      const r = await freezeCorpus(name);
      const n = r.manifest.run_ids.length;
      setCorpus(name);
      setMessage(`Set donduruldu: ${name} · ${n} run`);
      reload();
      onCorpusChange?.(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Set dondurulamadı.");
    } finally {
      setBusy(null);
    }
  }

  async function handleEvaluate() {
    if (!corpus || runId == null) return;
    setBusy("evaluate");
    setError(null);
    setMessage(null);
    setVerdict(null);
    try {
      const r = await evaluateForCorpus(corpus, [runId]);
      setVerdict(r.verdicts[0] ?? null);
      if (r.already_present.includes(runId)) setMessage(`Run ${runId} bu sette zaten var.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karne alınamadı.");
    } finally {
      setBusy(null);
    }
  }

  async function handleAddToCorpus(override: boolean) {
    if (!corpus || runId == null) return;
    setBusy("add");
    setError(null);
    setMessage(null);
    try {
      const r = await addRunsToCorpus(corpus, [runId], override);
      if (r.added.length > 0) {
        setMessage(
          `Run ${runId} sete eklendi${override ? " (override)" : ""} · set ${r.n_runs} run`,
        );
        setVerdict(null);
        onCorpusChange?.(corpus);
      } else if (r.already_present.length > 0) {
        setMessage(`Run ${runId} bu sette zaten var.`);
      } else {
        const why = r.rejected[0]?.reason ?? null;
        setMessage(`Run ${runId} eklenmedi — ${reasonText(why)}.`);
      }
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sete eklenemedi.");
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

  async function handleParamsPredict() {
    setBusy("params");
    setError(null);
    setMessage(null);
    setParamResult(null);
    try {
      const result = await predictFromParams({
        length: num(length),
        thickness: num(thickness),
        width: num(width),
        element_size: num(elementSize),
        youngs_modulus: num(youngs),
        poisson_ratio: num(poisson),
        load_fx: num(fx),
        load_fy: num(fy),
        load_fz: num(fz),
        pressure_mpa: 0,
        dimension: 3,
        compare_run_id: compareOpenRun && runId != null ? runId : undefined,
      });
      setParamResult(result);
      setMessage(result.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Parametre tahmini başarısız.");
    } finally {
      setBusy(null);
    }
  }

  const rf = status?.scalar_rf;
  const gnn = status?.field_gnn;
  const canRunPredict = geometryId != null || runId != null;
  const canParamsPredict = rf != null && busy === null;
  const pred = paramResult?.predictions;
  const fea = paramResult?.fea;
  const dev = paramResult?.deviation_pct;

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.5 · Surrogate</span>
      <h1>Hızlı tahmin</h1>
      <p className="lead">
        Çözülmüş run&apos;lar modeli eğitir. Aşağıdaki L/T/W ve yük <em>yeni</em>{" "}
        bir tasarım içindir — ccx çalışmaz. Skaler RF kontur üretmez; GNN alan
        modeli ayrı. Tahmin tam çözüm değildir.
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

      <p className="material-assignments-title">Eğitim seti</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>Kullanılan set</span>
          <select value={corpus} onChange={(e) => setCorpus(e.target.value)}>
            <option value="">Canlı süzgeç (dondurulmamış)</option>
            {corpora.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} · {c.n_runs} run{c.n_manual > 0 ? ` (+${c.n_manual} manuel)` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="mesh-field">
          <span>Yeni set adı</span>
          <input value={newCorpusName} onChange={(e) => setNewCorpusName(e.target.value)} />
        </label>
        <div className="mesh-field">
          <span>&nbsp;</span>
          <button
            type="button"
            className="material-secondary-button"
            disabled={busy !== null || newCorpusName.trim() === ""}
            onClick={() => void handleFreeze()}
          >
            {busy === "freeze" ? "Donduruluyor…" : "Seti dondur"}
          </button>
        </div>
      </div>

      {corpus && (
        <div className="doe-actions">
          <button
            type="button"
            className="material-secondary-button"
            disabled={busy !== null || runId == null}
            onClick={() => void handleEvaluate()}
          >
            {busy === "evaluate"
              ? "Bakılıyor…"
              : runId == null
                ? "Açık run yok"
                : `Run ${runId} karnesi`}
          </button>
        </div>
      )}

      {verdict && (
        <div className="surrogate-pred-table">
          <div className="results-stats-row">
            <span>Run {verdict.run_id}</span>
            <strong>{verdict.ok ? "süzgeci geçti" : reasonText(verdict.reason)}</strong>
          </div>
          <div className="results-stats-row">
            <span>u / L</span>
            <strong>{verdict.u_over_L != null ? verdict.u_over_L.toFixed(3) : "—"}</strong>
          </div>
          <div className="results-stats-row">
            <span>Mesh sapması</span>
            <strong>
              {verdict.mesh_deviation != null ? fmtPct(verdict.mesh_deviation * 100) : "—"}
            </strong>
          </div>
          <div className="doe-actions">
            <button
              type="button"
              className="material-assign-button"
              disabled={busy !== null}
              onClick={() => void handleAddToCorpus(!verdict.ok)}
            >
              {busy === "add"
                ? "Ekleniyor…"
                : verdict.ok
                  ? "Sete ekle"
                  : "Yine de ekle (override)"}
            </button>
          </div>
        </div>
      )}

      <p className="material-assignments-title">Yeni tasarım (ccx yok)</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>L (mm)</span>
          <input value={length} onChange={(e) => setLength(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>T (mm)</span>
          <input value={thickness} onChange={(e) => setThickness(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>W (mm)</span>
          <input value={width} onChange={(e) => setWidth(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Eleman (mm)</span>
          <input value={elementSize} onChange={(e) => setElementSize(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>E (Pa)</span>
          <input value={youngs} onChange={(e) => setYoungs(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>ν</span>
          <input value={poisson} onChange={(e) => setPoisson(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Fx (N)</span>
          <input value={fx} onChange={(e) => setFx(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Fy (N)</span>
          <input value={fy} onChange={(e) => setFy(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Fz (N)</span>
          <input value={fz} onChange={(e) => setFz(e.target.value)} />
        </label>
      </div>
      <label className="dataset-filter">
        <input
          type="checkbox"
          checked={compareOpenRun}
          disabled={runId == null}
          onChange={(e) => setCompareOpenRun(e.target.checked)}
        />
        Açık run ile FEA kıyasla{runId == null ? " (run yok)" : ` (run ${runId})`}
      </label>

      <div className="doe-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={!canParamsPredict}
          onClick={() => void handleParamsPredict()}
        >
          {busy === "params" ? "Tahmin…" : "Parametreyle tahmin"}
        </button>
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
          disabled={busy !== null || !canRunPredict}
          onClick={() => void handlePredict()}
        >
          {busy === "pred" ? "Tahmin…" : "Açık run tahmini"}
        </button>
      </div>

      {pred && (
        <div className="surrogate-pred-table">
          <div className="results-stats-row">
            <span>Tahmin u_max</span>
            <strong>{fmtNum(pred.max_displacement)} mm</strong>
          </div>
          <div className="results-stats-row">
            <span>Tahmin VM_max</span>
            <strong>{fmtNum(pred.max_von_mises)} MPa</strong>
          </div>
          {paramResult?.out_of_domain && (
            <p className="dataset-error">Eğitim uzayı dışı — sayı gösterilir, güvenilmez.</p>
          )}
          {fea && (
            <>
              <div className="results-stats-row">
                <span>FEA u_max (run {fea.run_id})</span>
                <strong>{fmtNum(fea.max_displacement)} mm</strong>
              </div>
              <div className="results-stats-row">
                <span>Sapma u</span>
                <strong>{fmtPct(dev?.max_displacement_pct)}</strong>
              </div>
              <div className="results-stats-row">
                <span>FEA VM_max</span>
                <strong>{fmtNum(fea.max_von_mises)} MPa</strong>
              </div>
              <div className="results-stats-row">
                <span>Sapma VM</span>
                <strong>{fmtPct(dev?.max_von_mises_pct)}</strong>
              </div>
            </>
          )}
        </div>
      )}

      {message && <p className="dataset-message">{message}</p>}
      {error && <p className="dataset-error">{error}</p>}
    </div>
  );
}
