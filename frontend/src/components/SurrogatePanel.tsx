import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMaterials } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import { numberFieldsFromSchema, type JsonSchema } from "../templates/schemaForm";
import {
  addRunsToCorpus,
  evaluateForCorpus,
  fetchCorpusList,
  fetchSurrogateStatus,
  freezeCorpus,
  predictFromParams,
  predictSweep,
  type SweepResult,
  fetchValidation,
  type ValidationResult,
  predictSurrogate,
  trainFieldGnn,
  trainScalarRf,
  type CorpusListItem,
  type CorpusRunVerdict,
  type ParamPredictResult,
  type ScalarModelInfo,
  type ScalarModelKind,
  type SurrogatePredictResult,
  type SurrogateStatus,
} from "../api/surrogate";

/** Skaler model türlerinin okunur adı. */
const MODEL_LABEL: Record<ScalarModelKind, string> = {
  rf: "Random Forest",
  loglinear: "Log-log lineer",
  hybrid: "Hibrit (log-log + RF artık)",
};

/** Varsayılan tür: ölçülen en isabetli model (plakada u %0.29 / σ %1.30). */
const DEFAULT_MODEL: ScalarModelKind = "hybrid";

/** Süzgeç gerekçelerinin okunur karşılığı; karar kullanıcıya ait. */
const REASON_TEXT: Record<string, string> = {
  large_displacement: "u/L eşiği aşıldı (lineer varsayım dışı)",
  mesh_outlier: "mesh oranı setin medyanından uzak",
  other_template: "başka şablon ailesi",
  other_material: "başka malzeme",
  analytic_warn: "analitik sapma uyarısı var",
  wrong_analysis: "statik değil",
  rigid_body: "rijit cisim / yakınsamamış",
  not_converged: "çözücü adımı tamamlamadı (yakınsamadı)",
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
  templateId,
  onPrediction,
  onCorpusChange,
}: {
  refreshKey?: number;
  geometryId?: number | null;
  runId?: number | null;
  /** Geometri panelinde seçili şablon; tahmin formu buna geçer. */
  templateId?: string | null;
  onPrediction?: (result: SurrogatePredictResult) => void;
  onCorpusChange?: (name: string | null) => void;
}) {
  const [status, setStatus] = useState<SurrogateStatus | null>(null);
  const [busy, setBusy] = useState<
    "rf" | "gnn" | "pred" | "params" | "sweep" | "validate" | "freeze" | "evaluate" | "add" | null
  >(null);
  // Tahmin vs FEA: çözülmüş run'larda modelin sapması (tablo).
  const [validateLimit, setValidateLimit] = useState("10");
  const [validateName, setValidateName] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  // Toplu tarama: tek parametre, aralık, adım (2 · Tahmin altında).
  const [sweepParam, setSweepParam] = useState<string>("");
  const [sweepMin, setSweepMin] = useState("");
  const [sweepMax, setSweepMax] = useState("");
  const [sweepN, setSweepN] = useState("20");
  const [sweepResult, setSweepResult] = useState<SweepResult | null>(null);
  const [corpora, setCorpora] = useState<CorpusListItem[]>([]);
  const [corpus, setCorpus] = useState<string>("");
  const [newCorpusName, setNewCorpusName] = useState("kiris-v1");
  const [verdict, setVerdict] = useState<CorpusRunVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [paramResult, setParamResult] = useState<ParamPredictResult | null>(null);
  // Tahmin formu ŞABLONA göre kurulur: alanlar şemadan gelir. Eskiden
  // L/T/W sabitti; plakada height/diameter girilemiyordu.
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [predictTemplate, setPredictTemplate] = useState<string>("cantilever_beam");
  // Büyük deformasyon (NLGEOM) modeli: ayrı korpus, ayrı dosya (TODO 4).
  const [nlgeom, setNlgeom] = useState(false);
  const [params, setParams] = useState<Record<string, string>>({});
  const [elementSize, setElementSize] = useState("8");
  const [youngs, setYoungs] = useState("2.1e11");
  const [poisson, setPoisson] = useState("0.3");
  const [fx, setFx] = useState("0");
  const [fy, setFy] = useState("-500");
  // Akma kontrolü için malzeme. Boş bırakılırsa kontrol atlanır — E ve ν
  // zaten ayrı alanlarda, bu yalnız akma sınırı için.
  const [materialId, setMaterialId] = useState<string>("");
  // Akma kontrolünde hangi gerilme okunacağı mühendisin kararı (TODO 6/8).
  const [stressSource, setStressSource] = useState<"auto" | "away" | "peak">("auto");
  const [materials, setMaterials] = useState<{ id: number; name: string }[]>([]);

  useEffect(() => {
    void fetchTemplates()
      .then(setTemplates)
      .catch(() => undefined);
  }, []);

  // Geometri panelindeki şablon değişince tahmin formu da ona geçer.
  useEffect(() => {
    if (templateId) setPredictTemplate(templateId);
  }, [templateId]);

  useEffect(() => {
    const t = templates.find((x) => x.id === predictTemplate);
    if (!t) return;
    const fields = numberFieldsFromSchema(t.params_schema as JsonSchema);
    setParams(Object.fromEntries(fields.map((f) => [f.name, String(f.defaultValue)])));
    setParamResult(null);
  }, [templates, predictTemplate]);

  useEffect(() => {
    let cancelled = false;
    void fetchMaterials()
      .then((list) => {
        if (!cancelled) setMaterials(list.map((m) => ({ id: m.id, name: m.name })));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const [fz, setFz] = useState("0");
  const [compareOpenRun, setCompareOpenRun] = useState(true);
  const autoPickedCorpus = useRef(false);

  const reload = useCallback(() => {
    fetchSurrogateStatus(predictTemplate, nlgeom)
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
  }, [predictTemplate, nlgeom]);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  useEffect(() => {
    onCorpusChange?.(corpus || null);
  }, [corpus, onCorpusChange]);

  // Hangi skaler modelin egitilecegi/kullanilacagi. Arac sessizce secmez:
  // tahmin yanitindaki model_kind daima gosterilir.
  const [scalarModel, setScalarModel] = useState<ScalarModelKind>(DEFAULT_MODEL);

  async function handleTrainRf() {
    setBusy("rf");
    setError(null);
    setMessage(null);
    try {
      const r = await trainScalarRf(corpus || null, scalarModel, predictTemplate, nlgeom);
      const info = r?.corpus;
      const droppedN = Object.values(info?.dropped ?? {}).reduce((a, b) => a + b, 0);
      const flaggedN = Object.values(info?.flagged ?? {}).reduce((a, b) => a + b, 0);
      let msg = `${MODEL_LABEL[scalarModel]} eğitildi · ${r?.n_samples ?? "?"} örnek`;
      msg += corpus ? ` · set ${corpus}` : " · canlı süzgeç";
      if (info?.template_id) msg += ` · ${info.template_id}`;
      if (droppedN > 0) msg += ` · atılan ${droppedN}`;
      if (flaggedN > 0) msg += ` · eşik üstü ${flaggedN}`;
      // Holdout yoksa "test R²" YAZILMAZ. Eskiden bu satır eğitim R²'sini
      // test R²'si diye gösteriyordu (n<12'de X_te = X_tr atanıyordu).
      msg += r?.has_holdout
        ? ` · test R² disp ${fmtR2(r?.metrics?.test?.max_displacement?.r2)}`
        : ` · holdout yok (n<12) · eğitim R² disp ${fmtR2(
            r?.metrics?.train?.max_displacement?.r2,
          )}`;
      setMessage(msg);
      if (info?.youngs_modulus != null) setYoungs(String(info.youngs_modulus));
      if (info?.poisson_ratio != null) setPoisson(String(info.poisson_ratio));
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Skaler model eğitilemedi.");
    } finally {
      setBusy(null);
    }
  }

  async function handleTrainGnn() {
    setBusy("gnn");
    setError(null);
    setMessage(null);
    try {
      const r = await trainFieldGnn(corpus || null, predictTemplate);
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

  function paramPredictBody() {
    return {
      template_id: predictTemplate,
      params: Object.fromEntries(
        Object.entries(params).map(([k, v]) => [k, num(v)]),
      ),
      element_size: num(elementSize),
      youngs_modulus: num(youngs),
      poisson_ratio: num(poisson),
      load_fx: num(fx),
      load_fy: num(fy),
      load_fz: num(fz),
      pressure_mpa: 0,
      dimension: 3,
      material_id: materialId ? Number(materialId) : undefined,
      stress_source: stressSource,
    };
  }

  async function handleValidate() {
    setBusy("validate");
    setError(null);
    setMessage(null);
    setValidation(null);
    try {
      const result = await fetchValidation({
        templateId: predictTemplate,
        model: scalarModel,
        nlgeom,
        limit: Math.max(1, Math.min(200, Math.round(num(validateLimit)) || 10)),
        nameContains: validateName.trim() || null,
      });
      setValidation(result);
      const sk = Object.values(result.skipped).reduce((a, b) => a + b, 0);
      setMessage(
        `Tahmin vs FEA: ${result.n} run` +
          (result.mean_abs_dev_u_pct != null ? ` · ort |sapma| u ${result.mean_abs_dev_u_pct.toFixed(2)}%` : "") +
          (result.mean_abs_dev_vm_pct != null ? ` · σ ${result.mean_abs_dev_vm_pct.toFixed(2)}%` : "") +
          (sk > 0 ? ` · ${sk} run atlandı (kinematik/özellik)` : ""),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Doğrulama tablosu alınamadı.");
    } finally {
      setBusy(null);
    }
  }

  async function handleSweep() {
    if (!sweepParam) return;
    setBusy("sweep");
    setError(null);
    setMessage(null);
    setSweepResult(null);
    try {
      const result = await predictSweep(
        {
          ...paramPredictBody(),
          sweep_param: sweepParam,
          sweep_min: num(sweepMin),
          sweep_max: num(sweepMax),
          sweep_n: Math.max(2, Math.min(200, Math.round(num(sweepN)))),
        },
        scalarModel,
        nlgeom,
      );
      setSweepResult(result);
      setMessage(
        `Tarama: ${result.n} nokta · ${result.sweep_param}` +
          (result.n_out_of_domain > 0 ? ` · ${result.n_out_of_domain} nokta eğitim uzayı dışı` : ""),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Toplu tarama başarısız.");
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
        template_id: predictTemplate,
        params: Object.fromEntries(
          Object.entries(params).map(([k, v]) => [k, num(v)]),
        ),
        element_size: num(elementSize),
        youngs_modulus: num(youngs),
        poisson_ratio: num(poisson),
        load_fx: num(fx),
        load_fy: num(fy),
        load_fz: num(fz),
        pressure_mpa: 0,
        dimension: 3,
        compare_run_id: compareOpenRun && runId != null ? runId : undefined,
        material_id: materialId ? Number(materialId) : undefined,
        stress_source: stressSource,
      }, scalarModel, nlgeom);
      setParamResult(result);
      setMessage(result.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Parametre tahmini başarısız.");
    } finally {
      setBusy(null);
    }
  }

  const rf = status?.scalar_rf;
  const loglin = status?.scalar_loglinear;
  const hybrid = status?.scalar_hybrid;
  const byKind: Record<ScalarModelKind, ScalarModelInfo | null | undefined> = {
    rf,
    loglinear: loglin,
    hybrid,
  };
  const active = byKind[scalarModel];
  const gnn = status?.field_gnn;
  const gnnHoldoutUmax = gnn?.metrics?.holdout?.scalar_rmse?.max_displacement;
  const canRunPredict = geometryId != null || runId != null;
  // Tahmin, SEÇİLİ türün o şablonda eğitilmiş olmasını ister — başka türe
  // sessizce düşmek kullanıcıyı yanıltırdı.
  const canParamsPredict = active != null && busy === null;
  // Seçili tür bu şablonda eğitilmemişse, mevcut en iyi türe GEÇ. Sessiz
  // değil: seçici güncellenir, kullanıcı hangi modelin kullanıldığını
  // görür. Aksi halde buton gerekçesiz devre dışı kalıyordu.
  useEffect(() => {
    if (!status) return;
    if (byKind[scalarModel] != null) return;
    const fallback = (["hybrid", "loglinear", "rf"] as ScalarModelKind[]).find(
      (k) => byKind[k] != null,
    );
    if (fallback) setScalarModel(fallback);
    // byKind status'tan türetiliyor; bağımlılık olarak status yeterli.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const predictFields = numberFieldsFromSchema(
    (templates.find((t) => t.id === predictTemplate)?.params_schema ?? {}) as JsonSchema,
  );
  const pred = paramResult?.predictions;
  const fea = paramResult?.fea;
  const dev = paramResult?.deviation_pct;

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Surrogate</span>
      <h1>Hızlı tahmin</h1>
      <p className="lead">
        Eğitilmiş model, yeni bir tasarım için sonucu ccx çalıştırmadan verir.
        Tahmin tam çözüm değildir; eğitim uzayı dışında bayrakla döner.
      </p>

      {/* ── 1 · Model ─────────────────────────────────────────────── */}
      <p className="material-assignments-title">1 · Model</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>Şablon</span>
          <select value={predictTemplate} onChange={(e) => setPredictTemplate(e.target.value)}>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
                {status?.templates?.[t.id]?.length
                  ? ` · ${status.templates[t.id].length} model`
                  : " · model yok"}
              </option>
            ))}
          </select>
        </label>
        <label className="mesh-field">
          <span>Kinematik</span>
          <select
            value={nlgeom ? "nlgeom" : "linear"}
            disabled={busy !== null}
            onChange={(e) => setNlgeom(e.target.value === "nlgeom")}
            title="Lineer: küçük deformasyon (u/L < 0.10). NLGEOM: büyük deformasyon — ayrı korpus, ayrı model."
          >
            <option value="linear">Lineer (küçük deformasyon)</option>
            <option value="nlgeom">NLGEOM (büyük deformasyon)</option>
          </select>
        </label>
        <label className="mesh-field">
          <span>Model türü</span>
          <select
            value={scalarModel}
            disabled={busy !== null}
            onChange={(e) => setScalarModel(e.target.value as ScalarModelKind)}
          >
            {(["hybrid", "loglinear", "rf"] as ScalarModelKind[]).map((k) => (
              <option key={k} value={k}>
                {MODEL_LABEL[k]}
                {byKind[k] ? ` · ${byKind[k]?.n_samples} örnek` : " · eğitilmedi"}
              </option>
            ))}
          </select>
        </label>
      </div>
      {active ? (
        <p className="material-assign-hint" data-testid="model-status-line">
          {MODEL_LABEL[scalarModel]} · {active.n_samples} örnek ·{" "}
          {active.has_holdout
            ? `holdout u_max MAPE ${fmtPct((active.metrics?.test?.max_displacement?.mape ?? NaN) * 100)} · R² ${fmtR2(active.metrics?.test?.max_displacement?.r2)}`
            : `holdout yok · eğitim R² ${fmtR2(active.metrics?.train?.max_displacement?.r2)}`}
          {nlgeom ? " · NLGEOM" : " · lineer"}
        </p>
      ) : nlgeom ? (
        <p className="material-assign-hint" data-testid="nlgeom-model-missing">
          Bu şablonda NLGEOM modeli eğitilmedi — 3 · Eğitim bölümünden NLGEOM korpusuyla eğit;
          tahmin lineer modele düşmez.
        </p>
      ) : (
        <p className="material-assign-hint">Bu şablonda model eğitilmedi — 3 · Eğitim bölümüne bak.</p>
      )}

      {/* ── 2 · Tahmin ────────────────────────────────────────────── */}
      <p className="material-assignments-title">2 · Tahmin</p>
      <div className="mesh-grid">
        {predictFields.filter((f) => !f.optional).map((f) => (
          <label className="mesh-field" key={f.name}>
            <span>
              {f.symbol ? `${f.symbol} · ` : ""}
              {f.label}
              {f.unit ? ` (${f.unit})` : ""}
            </span>
            <input
              value={params[f.name] ?? String(f.defaultValue)}
              onChange={(e) => setParams((p) => ({ ...p, [f.name]: e.target.value }))}
            />
          </label>
        ))}
        <label className="mesh-field">
          <span>Fy (N)</span>
          <input value={fy} onChange={(e) => setFy(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Malzeme (akma kontrolü)</span>
          <select
            value={materialId}
            onChange={(e) => setMaterialId(e.target.value)}
            title="Tahmin edilen gerilme bu malzemenin akma sınırıyla karşılaştırılır"
          >
            <option value="">— seçilmedi —</option>
            {materials.map((m) => (
              <option key={m.id} value={String(m.id)}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <details className="surrogate-exponents">
        <summary>Diğer yük bileşenleri, isteğe bağlı geometri, malzeme sabitleri, mesh, akma ölçütü</summary>
        <div className="mesh-grid">
          {predictFields.filter((f) => f.optional).map((f) => (
            <label className="mesh-field" key={f.name}>
              <span>
                {f.symbol ? `${f.symbol} · ` : ""}
                {f.label}
                {f.unit ? ` (${f.unit})` : ""}
              </span>
              <input
                value={params[f.name] ?? String(f.defaultValue)}
                onChange={(e) => setParams((p) => ({ ...p, [f.name]: e.target.value }))}
              />
            </label>
          ))}
          <label className="mesh-field">
            <span>Fx (N)</span>
            <input value={fx} onChange={(e) => setFx(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>Fz (N)</span>
            <input value={fz} onChange={(e) => setFz(e.target.value)} />
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
            <span>Eleman (mm)</span>
            <input value={elementSize} onChange={(e) => setElementSize(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>Akma gerilmesi</span>
            <select
              value={stressSource}
              onChange={(e) => setStressSource(e.target.value as "auto" | "away" | "peak")}
              title="Maskeli: kısıttan 1×T uzakta (tekillik dışarıda, kirişte teoriye ±%1). Ham tepe: mesh'teki en yüksek değer, tekillik dahil (kirişte ~%10 yüksek)."
            >
              <option value="auto">otomatik (maskeli varsa)</option>
              <option value="away">maskeli (tekillik dışı)</option>
              <option value="peak">ham tepe (tekillik dahil)</option>
            </select>
          </label>
        </div>
      </details>
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
          {busy === "params" ? "Tahmin…" : "Tahmin et"}
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
            <div className="predict-warning predict-warning-ood">
              <strong>Eğitim uzayı dışı</strong>
              {paramResult.domain_violations && paramResult.domain_violations.length > 0 ? (
                <>
                  <table className="predict-warning-table">
                    <tbody>
                      {paramResult.domain_violations.map((v) => (
                        <tr key={v.feature}>
                          <td>{v.feature}</td>
                          <td className="predict-warning-num">{fmtNum(v.value)}</td>
                          <td className="predict-warning-range">
                            eğitim: {fmtNum(v.min)} … {fmtNum(v.max)}
                          </td>
                          <td>
                            {v.factor
                              ? `${v.factor.toFixed(1)}× ${v.side === "below" ? "küçük" : "büyük"}`
                              : v.side === "below"
                                ? "altında"
                                : "üstünde"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <span className="predict-warning-note">
                    Model bu aralıkta hiç örnek görmedi. Log-log model kuvvet
                    yasası öğrendiği için sınırın dışında da makul sonuç
                    verebilir, ama garanti yoktur — uzaklaştıkça bozulur ve
                    bozulduğunu söylemez.
                  </span>
                </>
              ) : (
                <span className="predict-warning-note">
                  Sayı gösterilir, güvenilmez.
                </span>
              )}
            </div>
          )}
          {paramResult?.yield_check?.exceeds_limit && (
            <div
              className={
                paramResult.yield_check.exceeds_yield
                  ? "predict-warning predict-warning-yield"
                  : "predict-warning"
              }
            >
              <strong>
                {paramResult.yield_check.exceeds_yield
                  ? "Akma aşılıyor — sonuç geçersiz"
                  : "Akmaya yaklaşıyor"}
              </strong>
              <span className="predict-warning-note">
                {paramResult.yield_check.material}: tahmin{" "}
                {fmtNum(paramResult.yield_check.sigma_mpa)} MPa (
                {paramResult.yield_check.source === "max_von_mises" ? "ham tepe" : "maskeli"}), akma{" "}
                {fmtNum(paramResult.yield_check.yield_mpa)} MPa
                {paramResult.yield_check.utilisation != null &&
                  ` (%${(paramResult.yield_check.utilisation * 100).toFixed(0)} kullanım)`}
                .{" "}
                {paramResult.yield_check.exceeds_yield
                  ? "Malzeme plastik davranır; hem lineer FEA hem bu tahmin gerçeği temsil etmez. Yükü azaltın, kesiti büyütün ya da daha yüksek dayanımlı malzeme seçin."
                  : "Elastik sınırın yakınında — tasarım marjı dar."}
              </span>
            </div>
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
      {/* ── Toplu tarama (2 · Tahmin'in devamı) ───────────────────── */}
      <details className="surrogate-exponents" data-testid="sweep-section">
        <summary>Toplu tarama — bir parametreyi aralıkta değiştir, N tahmin tek seferde</summary>
        <p className="material-assign-hint" data-testid="sweep-fixed-inputs">
          Taranmayan girdiler yukarıdaki 2 · Tahmin formundan alınır:{" "}
          {predictFields
            .filter((f) => !f.optional && f.name !== sweepParam)
            .map((f) => `${f.symbol ?? f.label}=${params[f.name] ?? String(f.defaultValue)}`)
            .concat(
              sweepParam !== "load_fy" ? [`Fy=${fy}`] : [],
              materialId
                ? [materials.find((m) => String(m.id) === materialId)?.name ?? `malzeme #${materialId}`]
                : ["malzeme seçilmedi"],
              [nlgeom ? "NLGEOM" : "lineer"],
            )
            .join(" · ")}
          . Eğitim aralığı dışındaki girdi her noktayı &quot;uzay dışı&quot; yapar.
        </p>
        <div className="mesh-grid">
          <label className="mesh-field">
            <span>Parametre</span>
            <select value={sweepParam} onChange={(e) => setSweepParam(e.target.value)}>
              <option value="">— seç —</option>
              {predictFields.map((f) => (
                <option key={f.name} value={f.name}>
                  {f.symbol ? `${f.symbol} · ` : ""}
                  {f.label}
                </option>
              ))}
              <option value="load_fy">Fy (N)</option>
              <option value="load_fx">Fx (N)</option>
              <option value="load_fz">Fz (N)</option>
              <option value="element_size">Eleman (mm)</option>
            </select>
          </label>
          <label className="mesh-field">
            <span>Min</span>
            <input value={sweepMin} onChange={(e) => setSweepMin(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>Max</span>
            <input value={sweepMax} onChange={(e) => setSweepMax(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>Adım sayısı (2–200)</span>
            <input value={sweepN} onChange={(e) => setSweepN(e.target.value)} />
          </label>
        </div>
        <div className="doe-actions">
          <button
            type="button"
            className="material-assign-button"
            disabled={!canParamsPredict || !sweepParam || sweepMin === "" || sweepMax === ""}
            onClick={() => void handleSweep()}
          >
            {busy === "sweep" ? "Taranıyor…" : "Tara"}
          </button>
        </div>
        {sweepResult && sweepResult.points.length > 0 && (
          <div className="surrogate-pred-table" data-testid="sweep-result">
            <SweepChart result={sweepResult} />
            <table className="doe-table">
              <thead>
                <tr>
                  <th>{sweepResult.sweep_param}</th>
                  <th>u_max (mm)</th>
                  <th>σ_max (MPa)</th>
                  <th>durum</th>
                </tr>
              </thead>
              <tbody>
                {sweepResult.points.map((p) => (
                  <tr
                    key={p.value}
                    className={p.out_of_domain || p.exceeds_yield ? "doe-table-row-flagged" : undefined}
                  >
                    <td>{fmtNum(p.value)}</td>
                    <td>{fmtNum(p.max_displacement)}</td>
                    <td>{fmtNum(p.max_von_mises)}</td>
                    <td>
                      {[
                        p.out_of_domain
                          ? `uzay dışı${p.violations?.length ? `: ${p.violations.map(violationLabel).join(", ")}` : ""}`
                          : null,
                        p.exceeds_yield ? "akıyor" : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>

      {/* ── Tahmin vs FEA ─────────────────────────────────────────── */}
      <details className="surrogate-exponents" data-testid="validate-section" open>
        <summary>Tahmin vs FEA — çözülmüş run'larda model ne kadar şaşıyor</summary>
        <div className="mesh-grid">
          <label className="mesh-field">
            <span>Son N run</span>
            <input value={validateLimit} onChange={(e) => setValidateLimit(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>Ad içerir (isteğe bağlı)</span>
            <input
              value={validateName}
              placeholder="örn. OOD deneme"
              onChange={(e) => setValidateName(e.target.value)}
            />
          </label>
          <div className="mesh-field">
            <span>&nbsp;</span>
            <button
              type="button"
              className="material-assign-button"
              disabled={!canParamsPredict}
              onClick={() => void handleValidate()}
            >
              {busy === "validate" ? "Hesaplanıyor…" : "Tabloyu oluştur"}
            </button>
          </div>
        </div>
        {validation && (
          <div className="surrogate-pred-table" data-testid="validate-result">
            <div className="dataset-stats">
              <div>
                <strong>{validation.n}</strong>
                <span>run</span>
              </div>
              <div>
                <strong>{validation.mean_abs_dev_u_pct != null ? `${validation.mean_abs_dev_u_pct.toFixed(2)}%` : "—"}</strong>
                <span>ort |sapma| u_max</span>
              </div>
              <div>
                <strong>{validation.mean_abs_dev_vm_pct != null ? `${validation.mean_abs_dev_vm_pct.toFixed(2)}%` : "—"}</strong>
                <span>ort |sapma| σ</span>
              </div>
              <div>
                <strong>{validation.max_abs_dev_u_pct != null ? `${validation.max_abs_dev_u_pct.toFixed(2)}%` : "—"}</strong>
                <span>en kötü u_max</span>
              </div>
            </div>
            <div className="validate-table-wrap">
            <table className="doe-table">
              <thead>
                <tr>
                  <th>run</th>
                  <th>tasarım</th>
                  <th>FEA u_max</th>
                  <th>tahmin</th>
                  <th>sapma</th>
                  <th>FEA σ</th>
                  <th>tahmin</th>
                  <th>sapma</th>
                  <th>durum</th>
                </tr>
              </thead>
              <tbody>
                {validation.rows.map((r) => (
                  <tr key={r.run_id} className={r.out_of_domain ? "doe-table-row-flagged" : undefined}>
                    <td>{r.run_id}{r.name ? ` · ${r.name}` : ""}</td>
                    <td>
                      {Object.entries(r.params)
                        .filter(([k]) => ["length", "thickness", "width", "height", "diameter"].includes(k))
                        .map(([k, v]) => `${violationLabel(k)}=${fmtNum(v)}`)
                        .concat([`Fy=${fmtNum(r.load_fy)}`])
                        .join(" · ")}
                    </td>
                    <td>{fmtNum(r.fea_u)} mm</td>
                    <td>{fmtNum(r.pred_u)}</td>
                    <td>{r.dev_u_pct != null ? `${r.dev_u_pct >= 0 ? "+" : ""}${r.dev_u_pct.toFixed(1)}%` : "—"}</td>
                    <td>{fmtNum(r.fea_vm)} MPa</td>
                    <td>{fmtNum(r.pred_vm)}</td>
                    <td>{r.dev_vm_pct != null ? `${r.dev_vm_pct >= 0 ? "+" : ""}${r.dev_vm_pct.toFixed(1)}%` : "—"}</td>
                    <td>
                      {[
                        r.out_of_domain ? `uzay dışı: ${r.violations.map(violationLabel).join(", ")}` : null,
                        r.u_over_l != null && r.u_over_l > 0.1 ? `u/L ${r.u_over_l.toFixed(2)}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="filename">
              σ sütunu maskeli gerilme (`{validation.rows[0]?.vm_key ?? "max_von_mises"}`). Run'lar
              zaten çözülmüş; ccx çalışmadı.
            </p>
          </div>
        )}
      </details>

      {/* ── 3 · Eğitim (gelişmiş) ─────────────────────────────────── */}
      <details className="surrogate-exponents" data-testid="training-section">
        <summary>3 · Eğitim (gelişmiş) — set, eğit, GNN, açık run</summary>
        <div className="dataset-stats">
          <div>
            <strong>{active?.n_samples ?? "—"}</strong>
            <span>{MODEL_LABEL[scalarModel]} örnek</span>
          </div>
          <div>
            <strong>
              {active?.has_holdout
                ? fmtR2(active?.metrics?.test?.max_displacement?.r2)
                : fmtR2(active?.metrics?.train?.max_displacement?.r2)}
            </strong>
            <span>{active?.has_holdout ? "test R² disp" : "eğitim R² disp (holdout yok)"}</span>
          </div>
          <div>
            <strong>{fmtPct((active?.metrics?.test?.max_displacement?.mape ?? NaN) * 100)}</strong>
            <span>test MAPE disp</span>
          </div>
          <div>
            <strong>{gnn?.n_samples ?? "—"}</strong>
            <span>GNN graf</span>
          </div>
        </div>

        {scalarModel !== "rf" && active?.exponents?.max_displacement && (
          <details className="surrogate-exponents">
            <summary>Öğrenilen üsler — deplasman (log-log modelin katsayıları)</summary>
            <table className="doe-table">
              <thead>
                <tr>
                  <th>özellik</th>
                  <th>üs</th>
                  <th>okunabilir mi</th>
                </tr>
              </thead>
              <tbody>
                {active.exponents.max_displacement.map((e) => (
                  <tr key={e.feature} className={e.identifiable ? undefined : "doe-table-row-flagged"}>
                    <td>{e.feature}</td>
                    <td>{e.exponent == null ? "—" : e.exponent.toFixed(4)}</td>
                    <td>{e.identifiable ? "evet" : (e.reason ?? "hayır")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="filename">
              Bir sütun korpus boyunca sabitse ya da başka bir sütunla eşdoğrusalsa
              katsayısı &quot;üs&quot; olarak okunamaz — tahmin bundan zarar görmez,
              yorum görür.
            </p>
          </details>
        )}

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

        <div className="doe-actions">
          <button
            type="button"
            className="material-assign-button"
            disabled={busy !== null}
            onClick={() => void handleTrainRf()}
          >
            {busy === "rf" ? "Eğitiliyor…" : `${MODEL_LABEL[scalarModel]} eğit`}
          </button>
          <button
            type="button"
            className="material-secondary-button"
            disabled={busy !== null}
            onClick={() => void handleTrainGnn()}
          >
            {busy === "gnn" ? "Eğitiliyor…" : "GNN eğit (prototip)"}
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

        {/* TODO 1.3b: başarı ölçütü (holdout u_max hatası < %5) tutmadı. */}
        <div className="predict-warning" role="note" data-testid="gnn-prototype-note">
          <strong>GNN alan modeli prototip — sonuçlar geçersiz</strong>
          <span className="predict-warning-note">
            Başarı ölçütü (holdout u_max hatası &lt; %5) karşılanmadı. Açık run
            tahmini GNN varken kontur olarak onun çıktısını gösterir.
            {gnnHoldoutUmax != null && ` Son eğitim holdout u_max RMSE: ${fmtNum(gnnHoldoutUmax)} mm.`}
          </span>
        </div>
      </details>

    </div>
  );
}

/** Tablo hücresi için kısa girdi adı (Fy, T, L…); bilinmeyen anahtar olduğu gibi. */
function violationLabel(key: string): string {
  const short: Record<string, string> = {
    length: "L", thickness: "T", width: "W", height: "H", diameter: "d",
    load_fx: "Fx", load_fy: "Fy", load_fz: "Fz", element_size: "eleman",
    youngs_modulus: "E", poisson_ratio: "ν", root_fillet: "r",
  };
  return short[key] ?? key;
}

/** u_max'ın taranan parametreye göre eğrisi; uzay dışı / akan noktalar içi boş. */
function SweepChart({ result }: { result: SweepResult }) {
  const pts = result.points.filter((p) => p.max_displacement != null && Number.isFinite(p.max_displacement));
  if (pts.length < 2) return null;
  const W = 320;
  const H = 120;
  const pad = { l: 44, r: 8, t: 8, b: 22 };
  const xs = pts.map((p) => p.value);
  const ys = pts.map((p) => p.max_displacement as number);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = 0;
  const y1 = Math.max(...ys) || 1;
  const sx = (x: number) => pad.l + ((x - x0) / (x1 - x0 || 1)) * (W - pad.l - pad.r);
  const sy = (y: number) => H - pad.b - ((y - y0) / (y1 - y0 || 1)) * (H - pad.t - pad.b);
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.value).toFixed(1)},${sy(p.max_displacement as number).toFixed(1)}`).join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`u_max – ${result.sweep_param} eğrisi, ${pts.length} nokta`}
      className="sweep-chart"
    >
      <line x1={pad.l} y1={H - pad.b} x2={W - pad.r} y2={H - pad.b} className="template-schematic-dim" />
      <line x1={pad.l} y1={pad.t} x2={pad.l} y2={H - pad.b} className="template-schematic-dim" />
      <text x={pad.l - 4} y={pad.t + 8} textAnchor="end" className="template-schematic-label">{fmtNum(y1)}</text>
      <text x={pad.l - 4} y={H - pad.b} textAnchor="end" className="template-schematic-label">0</text>
      <text x={pad.l} y={H - 6} className="template-schematic-label">{fmtNum(x0)}</text>
      <text x={W - pad.r} y={H - 6} textAnchor="end" className="template-schematic-label">{fmtNum(x1)}</text>
      <text x={(pad.l + W - pad.r) / 2} y={H - 6} textAnchor="middle" className="template-schematic-label">
        {result.sweep_param} → u_max (mm)
      </text>
      <path d={path} fill="none" className="template-schematic-load" />
      {pts.map((p) => (
        <circle
          key={p.value}
          cx={sx(p.value)}
          cy={sy(p.max_displacement as number)}
          r={3}
          className={p.out_of_domain || p.exceeds_yield ? "sweep-point-flagged" : "sweep-point"}
        />
      ))}
    </svg>
  );
}
