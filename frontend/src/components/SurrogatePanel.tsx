import { useCallback, useEffect, useState } from "react";
import { fetchMaterials } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import { numberFieldsFromSchema, type JsonSchema } from "../templates/schemaForm";
import {
  addRunsToCorpus,
  evaluateForCorpus,
  fetchCorpusList,
  fetchCorpusMembership,
  fetchSurrogateBounds,
  type SurrogateBounds,
  fetchSurrogateStatus,
  freezeCorpus,
  predictFromParams,
  predictSweep,
  type SweepPoint,
  type SweepResult,
  fetchValidation,
  type ValidationResult,
  type ValidationRow,
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
  view = "all",
}: {
  /** ML Stüdyo aşaması: "model" → 1·Model + 3·Eğitim, "predict" → 2·Tahmin
   * (toplu tarama, Tahmin vs FEA dahil). "all" tek panelde hepsi. */
  view?: "all" | "model" | "predict";
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
  const [validateTarget, setValidateTarget] = useState<"u" | "vm">("vm");
  // Doğrulamayı seçili korpusun run'larıyla sınırla: son N run'a plastisite /
  // deplasman kontrolü koşuları da girer, lineer model onları tahmin edemez.
  const [validateCorpusOnly, setValidateCorpusOnly] = useState(true);
  // Otomatik (sessiz) doğrulamanın hatası; mesaj/hata alanına yazılmaz ki
  // eğitim/dondurma bildirimlerini silmesin.
  const [validateError, setValidateError] = useState<string | null>(null);
  // Sessiz doğrulama `busy`'yi kilitlemez: eğitim/dondurma düğmeleri o
  // sırada tıklanabilir kalmalı.
  const [validating, setValidating] = useState(false);
  // Aktif modelin eğitim kutusu: bantlar tahminden önce çizilir.
  const [bounds, setBounds] = useState<SurrogateBounds | null>(null);
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

  const reload = useCallback(() => {
    fetchSurrogateStatus(predictTemplate, nlgeom)
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Durum alınamadı."));
    fetchCorpusList()
      .then((list) => {
        setCorpora(list);
        // Bu şablonun en yeni seti seçilir; başka şablonun seti seçiliyse
        // düşer (eğitim/doğrulama şablon + korpus uyumu ister). Kullanıcının
        // bu şablon için seçtiği set korunur.
        setCorpus((prev) => {
          const mine = list.filter((c) => !c.template_id || c.template_id === predictTemplate);
          if (prev && mine.some((c) => c.name === prev)) return prev;
          return mine.length > 0 ? mine[mine.length - 1].name : "";
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

  async function handleTrainRf(kind: ScalarModelKind = scalarModel) {
    setBusy("rf");
    setError(null);
    setMessage(null);
    try {
      const r = await trainScalarRf(corpus || null, kind, predictTemplate, nlgeom);
      const info = r?.corpus;
      const droppedN = Object.values(info?.dropped ?? {}).reduce((a, b) => a + b, 0);
      const flaggedN = Object.values(info?.flagged ?? {}).reduce((a, b) => a + b, 0);
      let msg = `${MODEL_LABEL[kind]} eğitildi · ${r?.n_samples ?? "?"} örnek`;
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

  /** Tahmin vs FEA. `silent`: aşama açılınca/ayar değişince kendiliğinden;
   * mesaj alanına dokunmaz, hatayı kendi satırına yazar. */
  async function handleValidate(silent = false) {
    setValidating(true);
    if (!silent) {
      setBusy("validate");
      setError(null);
      setMessage(null);
    }
    setValidateError(null);
    setValidation(null);
    try {
      const corpusOnly = validateCorpusOnly && corpus !== "";
      let runIds: number[] | null = null;
      if (corpusOnly) {
        const m = await fetchCorpusMembership(corpus);
        runIds = [...m.auto, ...m.manual_pass, ...m.manual_override];
      }
      const result = await fetchValidation({
        templateId: predictTemplate,
        model: scalarModel,
        nlgeom,
        limit: corpusOnly
          ? Math.max(1, Math.min(200, runIds?.length ?? 1))
          : Math.max(1, Math.min(200, Math.round(num(validateLimit)) || 10)),
        nameContains: validateName.trim() || null,
        runIds,
      });
      setValidation(result);
      const sk = Object.values(result.skipped).reduce((a, b) => a + b, 0);
      if (!silent) {
        setMessage(
          `Tahmin vs FEA: ${result.n} run` +
            (result.mean_abs_dev_u_pct != null ? ` · ort |sapma| u ${result.mean_abs_dev_u_pct.toFixed(2)}%` : "") +
            (result.mean_abs_dev_vm_pct != null ? ` · σ ${result.mean_abs_dev_vm_pct.toFixed(2)}%` : "") +
            (sk > 0 ? ` · ${sk} run atlandı (kinematik/özellik)` : ""),
        );
      }
    } catch (e) {
      const m = e instanceof Error ? e.message : "Doğrulama tablosu alınamadı.";
      if (silent) setValidateError(m);
      else setError(m);
    } finally {
      setValidating(false);
      if (!silent) setBusy(null);
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

  // Model aşaması açıkken doğrulama kendiliğinden gelir: ccx çalışmaz,
  // ucuz. Model / şablon / kinematik / korpus değişince yenilenir; "Tabloyu
  // oluştur" N ve ad süzgeciyle elle yenilemek için kalır.
  const activeReady = active != null;
  useEffect(() => {
    let cancelled = false;
    if (!activeReady) {
      setBounds(null);
      return;
    }
    // Promise.resolve: çağrı senkron patlarsa (örn. mock) efekt render'ı düşürmesin.
    Promise.resolve()
      .then(() => fetchSurrogateBounds(predictTemplate, scalarModel, nlgeom))
      .then((b) => {
        if (!cancelled) setBounds(b ?? null);
      })
      .catch(() => {
        if (!cancelled) setBounds(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeReady, predictTemplate, scalarModel, nlgeom, status]);

  useEffect(() => {
    if (view === "predict" || !activeReady) return;
    // Açılışta durum, korpus ve model türü arka arkaya oturur; kısa bekleme
    // ile tek istek atılır.
    const t = window.setTimeout(() => void handleValidate(true), 150);
    return () => window.clearTimeout(t);
    // handleValidate her render'da yeni; tetikleyiciler açıkça listeleniyor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, activeReady, predictTemplate, nlgeom, scalarModel, corpus, validateCorpusOnly]);

  const predictFields = numberFieldsFromSchema(
    (templates.find((t) => t.id === predictTemplate)?.params_schema ?? {}) as JsonSchema,
  );
  const pred = paramResult?.predictions;
  const fea = paramResult?.fea;
  const dev = paramResult?.deviation_pct;
  const showModel = view !== "predict";
  const showPredict = view !== "model";
  const kinds: ScalarModelKind[] = ["hybrid", "loglinear", "rf"];
  const mapePct = (info: ScalarModelInfo | null | undefined, key: string): number | null => {
    const v = info?.metrics?.test?.[key]?.mape;
    return typeof v === "number" && Number.isFinite(v) ? v * 100 : null;
  };
  const materialName = materialId
    ? materials.find((m) => String(m.id) === materialId)?.name ?? `malzeme #${materialId}`
    : null;
  const violationByFeature = new Map(
    (paramResult?.domain_violations ?? []).map((v) => [v.feature, v] as const),
  );
  const boundsByFeature = new Map(
    (bounds?.features ?? []).map((b) => [b.feature, { min: b.min, max: b.max }] as const),
  );

  async function handleTrainAll() {
    for (const k of kinds) {
      // Sırayla; biri patlarsa handleTrainRf hatayı gösterir, döngü durur.
      // eslint-disable-next-line no-await-in-loop
      await handleTrainRf(k);
      if (error) break;
    }
  }

  /** Uzay dışı bir girdiyi eğitim sınırına çeker — kullanıcı tıklar, araç
   * kendiliğinden değiştirmez. */
  function clampToBound(feature: string, bound: number, side: "below" | "above") {
    // Sınırın İÇİNE yuvarla (6 anlamlı basamak): dışa yuvarlanırsa nokta
    // yine uzay dışı kalır ve düğme boşa basılmış olur.
    const scale = Math.pow(10, Math.floor(Math.log10(Math.abs(bound) || 1)) - 5);
    const inward = side === "below" ? Math.ceil(bound / scale) * scale : Math.floor(bound / scale) * scale;
    const v = String(Number(inward.toPrecision(6)));
    if (feature === "load_fy") setFy(v);
    else if (feature === "load_fx") setFx(v);
    else if (feature === "load_fz") setFz(v);
    else if (feature === "element_size") setElementSize(v);
    else if (feature === "youngs_modulus") setYoungs(v);
    else if (feature === "poisson_ratio") setPoisson(v);
    else setParams((p) => ({ ...p, [feature]: v }));
  }

  const templateSelect = (
    <span className="cv-row">
      <span className="ml-k cv-k-90">Şablon</span>
      <select
        className="cv-template"
        aria-label="Şablon"
        value={predictTemplate}
        onChange={(e) => setPredictTemplate(e.target.value)}
      >
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
            {status?.templates?.[t.id]?.length ? ` · ${status.templates[t.id].length} model` : " · model yok"}
          </option>
        ))}
      </select>
    </span>
  );

  const nlgeomMissingNote =
    nlgeom && !active ? (
      <p className="sg-note sg-note-warn" data-testid="nlgeom-model-missing">
        Bu şablonda NLGEOM modeli eğitilmedi — NLGEOM korpusuyla eğit; tahmin lineer modele düşmez.
      </p>
    ) : null;

  const feedback = (
    <>
      {message && <p className="dataset-message">{message}</p>}
      {error && <p className="dataset-error">{error}</p>}
    </>
  );

  /* ================= MODEL AŞAMASI ================= */
  const modelStage = (
    <div className="doe-stage sg-stage" data-testid="model-stage">
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">0.5.6 RF · 0.6.3 loglinear · 0.6.4 hybrid</span>
            <span className="ml-h">Vekil model</span>
          </span>
        </div>
        <div className="doe-pane-body ds-body">
          {templateSelect}
          <span className="cv-row">
            <span className="ml-k cv-k-90">Korpus</span>
            <span className="doe-chips" role="group" aria-label="Kullanılan set">
              <button
                type="button"
                className={corpus === "" ? "doe-chip active" : "doe-chip"}
                aria-pressed={corpus === ""}
                disabled={busy !== null}
                onClick={() => setCorpus("")}
                title="Dondurulmamış: eğitim anında süzgeçten geçen run'lar"
              >
                canlı süzgeç
              </button>
              {corpora.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  className={corpus === c.name ? "doe-chip active" : "doe-chip"}
                  aria-pressed={corpus === c.name}
                  disabled={busy !== null}
                  onClick={() => setCorpus(c.name)}
                  title={c.template_id ?? undefined}
                >
                  {c.name} · {c.n_runs} run{c.n_manual > 0 ? ` (+${c.n_manual})` : ""}
                </button>
              ))}
            </span>
            <label className="doe-pfoot-check sg-nlgeom" title="Lineer: küçük deformasyon (u/L < 0.10). NLGEOM: büyük deformasyon — ayrı korpus, ayrı model.">
              <input
                type="checkbox"
                checked={nlgeom}
                disabled={busy !== null}
                onChange={(e) => setNlgeom(e.target.checked)}
              />
              NLGEOM
            </label>
          </span>

          <div className="ds-section">
            <span className="ml-k">Skaler modeller · test MAPE{nlgeom ? " · NLGEOM" : " · lineer"}</span>
            {kinds.map((k) => {
              const info = byKind[k];
              const isActive = k === scalarModel;
              const u = mapePct(info, "max_displacement");
              const s = mapePct(info, "max_von_mises");
              const bar = (v: number | null) => `${Math.min(100, (v ?? 0) * 5)}%`;
              return (
                <div
                  key={k}
                  className={isActive ? "sg-model active" : "sg-model"}
                  data-testid={`model-card-${k}`}
                >
                  <span className="sg-model-main">
                    <span className="sg-model-title">
                      <strong className="ml-h sg-model-name">{k === "rf" ? "RF" : k}</strong>
                      <span className={`doe-st ${isActive && info ? "doe-st-ok" : ""}`}>
                        {info ? (isActive ? "aktif" : "eğitildi") : "eğitilmedi"}
                      </span>
                    </span>
                    <span className="ds-sb">
                      {MODEL_LABEL[k]}
                      {info ? ` · ${info.n_samples ?? "?"} örnek` : ""}
                      {info && !info.has_holdout ? " · holdout yok" : ""}
                    </span>
                  </span>
                  <span className="sg-model-bars">
                    <span className="sg-bar-row">
                      <span className="ml-k sg-bar-k sg-k-keep">u</span>
                      <span className="sg-bar"><span style={{ width: bar(u) }} /></span>
                      <span className="sg-bar-v">{u == null ? "—" : `%${u.toFixed(2)}`}</span>
                    </span>
                    <span className="sg-bar-row">
                      <span className="ml-k sg-bar-k sg-k-keep">σ</span>
                      <span className="sg-bar"><span style={{ width: bar(s) }} /></span>
                      <span className="sg-bar-v">{s == null ? "—" : `%${s.toFixed(2)}`}</span>
                    </span>
                  </span>
                  <span className="sg-model-actions">
                    <button
                      type="button"
                      className="doe-btn sg-btn-sm"
                      disabled={busy !== null}
                      onClick={() => {
                        setScalarModel(k);
                        void handleTrainRf(k);
                      }}
                    >
                      {busy === "rf" && scalarModel === k ? "Eğitiliyor…" : `${MODEL_LABEL[k]} eğit`}
                    </button>
                    <button
                      type="button"
                      className="doe-btn doe-btn-ghost sg-btn-xs"
                      aria-pressed={isActive}
                      disabled={busy !== null || !info || isActive}
                      onClick={() => setScalarModel(k)}
                    >
                      {isActive ? "Aktif" : "Aktif yap"}
                    </button>
                  </span>
                </div>
              );
            })}
            {nlgeomMissingNote}
          </div>

          <div className="ds-section">
            <span className="ds-legend-row">
              <span className="ml-k">Alan modeli · GNN</span>
              <span className="doe-st sg-right">prototip</span>
            </span>
            <div className="ds-stats sg-gnn">
              <span>
                <span className="ml-k sg-k-keep">Düğüm RMSE · u</span>
                <strong>
                  {gnn?.metrics?.node_rmse?.displacement_mm != null
                    ? `${fmtNum(gnn.metrics.node_rmse.displacement_mm)} mm`
                    : "—"}
                </strong>
              </span>
              <span>
                <span className="ml-k sg-k-keep">Düğüm RMSE · σ</span>
                <strong>
                  {gnn?.metrics?.node_rmse?.von_mises_mpa != null
                    ? `${fmtNum(gnn.metrics.node_rmse.von_mises_mpa)} MPa`
                    : "—"}
                </strong>
              </span>
              <span>
                <span className="ml-k sg-k-keep">Holdout u_max</span>
                <strong>{gnnHoldoutUmax != null ? `${fmtNum(gnnHoldoutUmax)} mm` : "yok"}</strong>
                <span className="ds-sb">{gnn ? `${gnn.n_samples ?? "?"} graf` : "eğitilmedi"}</span>
              </span>
            </div>
            {/* TODO 1.3b: başarı ölçütü (holdout u_max hatası < %5) tutmadı. */}
            <div className="predict-warning" role="note" data-testid="gnn-prototype-note">
              <strong>GNN alan modeli prototip — sonuçlar geçersiz</strong>
              <span className="predict-warning-note">
                Başarı ölçütü (holdout u_max hatası &lt; %5) karşılanmadı. Açık run tahmini GNN varken
                kontur olarak onun çıktısını gösterir.
                {gnnHoldoutUmax != null && ` Son eğitim holdout u_max RMSE: ${fmtNum(gnnHoldoutUmax)} mm.`}
              </span>
            </div>
          </div>

          <div className="ds-section">
            <span className="ml-k">Eğitim seti · dondur, açık run'ı karneyle ekle</span>
            <span className="cv-row">
              <input
                className="doe-num ds-freeze-input"
                aria-label="Yeni set adı"
                value={newCorpusName}
                onChange={(e) => setNewCorpusName(e.target.value)}
              />
              <button
                type="button"
                className="doe-btn sg-btn-sm"
                disabled={busy !== null || newCorpusName.trim() === ""}
                onClick={() => void handleFreeze()}
              >
                {busy === "freeze" ? "Donduruluyor…" : "Seti dondur"}
              </button>
              {corpus && (
                <button
                  type="button"
                  className="doe-btn sg-btn-sm"
                  disabled={busy !== null || runId == null}
                  onClick={() => void handleEvaluate()}
                >
                  {busy === "evaluate" ? "Bakılıyor…" : runId == null ? "Açık run yok" : `Run ${runId} karnesi`}
                </button>
              )}
            </span>
            {verdict && (
              <div className="sg-verdict">
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
                  <strong>{verdict.mesh_deviation != null ? fmtPct(verdict.mesh_deviation * 100) : "—"}</strong>
                </div>
                <button
                  type="button"
                  className="doe-btn doe-btn-primary sg-btn-sm"
                  disabled={busy !== null}
                  onClick={() => void handleAddToCorpus(!verdict.ok)}
                >
                  {busy === "add" ? "Ekleniyor…" : verdict.ok ? "Sete ekle" : "Yine de ekle (override)"}
                </button>
              </div>
            )}
          </div>
          {!showPredict && feedback}
        </div>
        <div className="doe-pfoot">
          <span className="ds-sb">Eğitim tek şablon + tek korpus ile çalışır</span>
          <button
            type="button"
            className="doe-btn doe-btn-ghost sg-right"
            disabled={busy !== null || !canRunPredict}
            onClick={() => void handlePredict()}
            title="Tezgahta açık run/geometri için tahmin; GNN varken kontur"
          >
            {busy === "pred" ? "Tahmin…" : "Açık run tahmini"}
          </button>
          <button
            type="button"
            className="doe-btn"
            disabled={busy !== null}
            onClick={() => void handleTrainGnn()}
          >
            {busy === "gnn" ? "Eğitiliyor…" : "GNN eğit (prototip)"}
          </button>
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy !== null}
            onClick={() => void handleTrainAll()}
          >
            Üçünü de eğit
          </button>
        </div>
      </div>

      <div className="doe-pane-r cv-right">
        <div className="doe-phead-r">
          <span className="doe-phead-title">
            <span className="ml-k">
              Doğrulama · {MODEL_LABEL[scalarModel]} ·{" "}
              {validation ? `${validation.n} çözülmüş run` : "çözülmüş run'lar"}
              {validateCorpusOnly && corpus ? ` · ${corpus}` : ""} · ccx çalışmaz
            </span>
            <span className="ml-h">Tahmin ↔ FEA</span>
          </span>
          <span className="doe-seg cv-seg" role="group" aria-label="Doğrulama hedefi">
            <button
              type="button"
              className={validateTarget === "u" ? "doe-seg-opt active" : "doe-seg-opt"}
              aria-pressed={validateTarget === "u"}
              onClick={() => setValidateTarget("u")}
            >
              u
            </button>
            <button
              type="button"
              className={validateTarget === "vm" ? "doe-seg-opt active" : "doe-seg-opt"}
              aria-pressed={validateTarget === "vm"}
              onClick={() => setValidateTarget("vm")}
            >
              σ
            </button>
          </span>
        </div>
        <span className="cv-row">
          <label className="doe-pfoot-check" title="Kapalıyken şablonun son N çözülmüş run'ı — plastisite/deplasman kontrolü koşuları da girer.">
            <input
              type="checkbox"
              checked={validateCorpusOnly && corpus !== ""}
              disabled={corpus === "" || busy !== null}
              onChange={(e) => setValidateCorpusOnly(e.target.checked)}
            />
            {corpus ? `yalnız ${corpus}` : "korpus seçilmedi"}
          </label>
          <label className="doe-pfoot-field">
            <span className="ml-k">Son N run</span>
            <input
              className="doe-num"
              aria-label="Son N run"
              value={validateLimit}
              disabled={validateCorpusOnly && corpus !== ""}
              onChange={(e) => setValidateLimit(e.target.value)}
            />
          </label>
          <label className="doe-pfoot-field">
            <span className="ml-k">Ad içerir</span>
            <input
              className="doe-num ds-freeze-input"
              aria-label="Ad içerir (isteğe bağlı)"
              value={validateName}
              placeholder="örn. OOD deneme"
              onChange={(e) => setValidateName(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="doe-btn doe-btn-primary sg-right"
            disabled={!canParamsPredict}
            onClick={() => void handleValidate(false)}
          >
            {validating ? "Hesaplanıyor…" : "Tabloyu oluştur"}
          </button>
        </span>

        {validateError && <p className="dataset-error">{validateError}</p>}
        {!validation && !validateError && (
          <p className="doe-empty">
            {validating
              ? "Hesaplanıyor — çözülmüş run'lar modelden geçiriliyor, ccx çalışmıyor."
              : "Çözülmüş run'larda aktif modelin sapması. Run'lar zaten çözülmüş; ccx çalışmaz."}
          </p>
        )}

        {validation && (
          <div data-testid="validate-result" className="ds-section">
            <div className="sg-val-grid">
              <div className="cv-card">
                <ValidationScatter rows={validation.rows} target={validateTarget} />
                <span className="ds-sb">Açık bant ±%5 · kahverengi = uzay dışı run</span>
              </div>
              <div className="sg-val-stats">
                <span><span className="ml-k">Örnek</span><strong className="ml-h">{validation.n}</strong></span>
                <span>
                  <span className="ml-k sg-k-keep">Ort. |Δσ|</span>
                  <strong className="ml-h">
                    {validation.mean_abs_dev_vm_pct != null ? `%${validation.mean_abs_dev_vm_pct.toFixed(2)}` : "—"}
                  </strong>
                </span>
                <span>
                  <span className="ml-k sg-k-keep">Ort. |Δu|</span>
                  <strong className="ml-h">
                    {validation.mean_abs_dev_u_pct != null ? `%${validation.mean_abs_dev_u_pct.toFixed(2)}` : "—"}
                  </strong>
                </span>
                <span>
                  <span className="ml-k sg-k-keep">Maks |Δu|</span>
                  <strong className="ml-h">
                    {validation.max_abs_dev_u_pct != null ? `%${validation.max_abs_dev_u_pct.toFixed(2)}` : "—"}
                  </strong>
                </span>
              </div>
            </div>
            <details className="surrogate-exponents">
              <summary>Satırlar · {validation.rows.length} run</summary>
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
              <p className="ds-sb">
                σ sütunu maskeli gerilme (`{validation.rows[0]?.vm_key ?? "max_von_mises"}`). Run'lar zaten
                çözülmüş; ccx çalışmadı.
              </p>
            </details>
          </div>
        )}

        {scalarModel !== "rf" && active?.exponents?.max_displacement && (
          <div className="ds-section" data-testid="exponents-section">
            <span className="ds-legend-row">
              <span className="ml-k">Öğrenilen üsler · {scalarModel} · u ∝ Π xᵢ^aᵢ</span>
              <span className="ds-sb sg-right">
                bir sütun sabitse ya da eşdoğrusalsa katsayı üs olarak okunamaz — tahmin bundan zarar görmez, yorum görür
              </span>
            </span>
            <div className="sg-exps">
              {active.exponents.max_displacement.map((e) => {
                const v = e.exponent;
                const h = v == null ? 0 : Math.min(1, Math.abs(v) / 3) * 50;
                return (
                  <span key={e.feature} className={e.identifiable ? "sg-exp" : "sg-exp sg-exp-dim"}>
                    <em className="doe-line-sym cv-sym">{violationLabel(e.feature)}</em>
                    <span className="sg-exp-bar" aria-hidden="true">
                      <span className="sg-exp-zero" />
                      <span
                        className="sg-exp-fill"
                        style={{ top: v != null && v >= 0 ? `${50 - h}%` : "50%", height: `${h}%` }}
                      />
                    </span>
                    <strong>{v == null ? "—" : v.toFixed(4)}</strong>
                    <span className="ds-sb sg-exp-note">{e.identifiable ? "okunabilir" : (e.reason ?? "okunamaz")}</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  /* ================= TAHMİN AŞAMASI ================= */
  const yc = paramResult?.yield_check ?? null;
  const predictStage = (
    <div className="doe-stage sg-stage" data-testid="predict-stage">
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">Surrogate · ccx yok</span>
            <span className="ml-h">Parametreden tahmin</span>
          </span>
          <span className="doe-phead-hint">
            Bant = eğitim kutusu{bounds ? ` · ${bounds.model_kind}` : ""}
            <br />■ = girilen değer
          </span>
        </div>
        <div className="doe-pane-body sg-pred-body">
          {!showModel && templateSelect}
          {[
            ...predictFields
              .filter((f) => !f.optional)
              .map((f) => ({
                key: f.name,
                sym: f.symbol ?? "",
                name: f.label,
                unit: f.unit ?? "",
                ariaLabel: `${f.symbol ? `${f.symbol} · ` : ""}${f.label}`,
                value: params[f.name] ?? String(f.defaultValue),
                set: (v: string) => setParams((p) => ({ ...p, [f.name]: v })),
              })),
            {
              key: "load_fy",
              sym: "Fy",
              name: "Kuvvet",
              unit: "N",
              ariaLabel: "Fy (N)",
              value: fy,
              set: setFy,
            },
          ].map((row) => {
            const val = Number(row.value);
            // Bant kaynağı: eğitim kutusu (tahminden önce de var); yoksa son
            // tahminin ihlal satırı. Uzay dışı = değer kutunun dışında.
            const bb = boundsByFeature.get(row.key);
            const vv = violationByFeature.get(row.key);
            const box = bb ?? (vv ? { min: vv.min, max: vv.max } : null);
            const outside = box != null && Number.isFinite(val) && (val < box.min || val > box.max);
            const viol = outside;
            let lo = box ? Math.min(box.min, Number.isFinite(val) ? val : box.min) : NaN;
            let hi = box ? Math.max(box.max, Number.isFinite(val) ? val : box.max) : NaN;
            if (box) {
              const span = hi - lo || Math.abs(hi) || 1;
              lo -= span * 0.08;
              hi += span * 0.08;
            }
            const pct = (v: number) => `${Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1))) * 100}%`;
            const factor =
              outside && box ? (val < box.min ? box.min / (val || 1e-12) : val / (box.max || 1e-12)) : null;
            return (
              <div className="sg-pred-row" key={row.key}>
                <span className="doe-line-title">
                  {row.sym ? <em className="doe-line-sym">{row.sym}</em> : null}
                  <span className="doe-line-name">{row.name}</span>
                </span>
                <span className="sg-pred-bar-wrap">
                  <span className="sg-pred-bar" aria-hidden="true">
                    <span className="doe-bar-track" />
                    {box && (
                      <span
                        className="sg-pred-band"
                        style={{ left: pct(box.min), width: `calc(${pct(box.max)} - ${pct(box.min)})` }}
                      />
                    )}
                    <span
                      className={outside ? "sg-pred-knob sg-pred-knob-ood" : "sg-pred-knob"}
                      style={{ left: box ? pct(val) : "50%" }}
                    />
                  </span>
                  <span className={outside ? "ds-sb sg-ood-text" : "ds-sb"} data-testid={`band-${row.key}`}>
                    {box
                      ? `eğitim ${fmtNum(box.min)} – ${fmtNum(box.max)}${
                          outside && factor != null && Number.isFinite(factor)
                            ? ` · ${factor.toFixed(2)}× ${val < box.min ? "altında" : "üstünde"}`
                            : ""
                        }`
                      : "eğitim kutusu bilinmiyor"}
                  </span>
                </span>
                <span className="sg-pred-input">
                  <input
                    className={viol ? "doe-num sg-num-ood" : "doe-num"}
                    aria-label={row.ariaLabel}
                    value={row.value}
                    onChange={(e) => row.set(e.target.value)}
                  />
                  <span className="ds-sb">{row.unit}</span>
                </span>
              </div>
            );
          })}

          <div className="sg-pred-opts">
            <span className="cv-row">
              <span className="ml-k sg-k-150">Malzeme</span>
              <span className="doe-chips" role="group" aria-label="Malzeme (akma kontrolü)">
                <button
                  type="button"
                  className={materialId === "" ? "doe-chip active" : "doe-chip"}
                  aria-pressed={materialId === ""}
                  onClick={() => setMaterialId("")}
                  title="Akma kontrolü atlanır; E ve ν ayrı alanlarda"
                >
                  yok
                </button>
                {materials.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={materialId === String(m.id) ? "doe-chip active" : "doe-chip"}
                    aria-pressed={materialId === String(m.id)}
                    onClick={() => setMaterialId(String(m.id))}
                  >
                    {m.name}
                  </button>
                ))}
              </span>
            </span>
            <span className="cv-row">
              <span className="ml-k sg-k-150">Model</span>
              <span className="doe-chips" role="group" aria-label="Model türü">
                {kinds.map((k) => (
                  <button
                    key={k}
                    type="button"
                    className={scalarModel === k ? "doe-chip active" : "doe-chip"}
                    aria-pressed={scalarModel === k}
                    disabled={!byKind[k] || busy !== null}
                    title={byKind[k] ? MODEL_LABEL[k] : `${MODEL_LABEL[k]} · bu şablonda eğitilmedi`}
                    onClick={() => setScalarModel(k)}
                  >
                    {k === "rf" ? "RF" : k}
                  </button>
                ))}
              </span>
              <span className="ds-sb">{nlgeom ? "NLGEOM" : "lineer"}</span>
            </span>
            <span className="cv-row">
              <span className="ml-k sg-k-150">Akma gerilmesi</span>
              <span className="doe-seg" role="group" aria-label="Akma gerilmesi">
                {(
                  [
                    ["auto", "auto"],
                    ["away", "maskeli"],
                    ["peak", "ham tepe"],
                  ] as const
                ).map(([v, l]) => (
                  <button
                    key={v}
                    type="button"
                    className={stressSource === v ? "doe-seg-opt active" : "doe-seg-opt"}
                    aria-pressed={stressSource === v}
                    onClick={() => setStressSource(v)}
                    title="Maskeli: kısıttan 1×T uzakta (tekillik dışarıda). Ham tepe: mesh'teki en yüksek değer, tekillik dahil."
                  >
                    {l}
                  </button>
                ))}
              </span>
            </span>
          </div>

          <details className="surrogate-exponents">
            <summary>Diğer yük bileşenleri, isteğe bağlı geometri, malzeme sabitleri, mesh</summary>
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
            </div>
          </details>
          {!showModel && nlgeomMissingNote}
        </div>
        <div className="doe-pfoot">
          <label className="doe-pfoot-check">
            <input
              type="checkbox"
              checked={compareOpenRun}
              disabled={runId == null}
              onChange={(e) => setCompareOpenRun(e.target.checked)}
            />
            {runId == null ? "Açık run yok — FEA kıyası kapalı" : `Run #${runId} ile karşılaştır`}
          </label>
          <button
            type="button"
            className="doe-btn doe-btn-primary sg-right"
            disabled={!canParamsPredict}
            onClick={() => void handleParamsPredict()}
          >
            {busy === "params" ? "Tahmin…" : "Tahmin et"}
          </button>
        </div>
      </div>

      <div className="doe-pane-r cv-right">
        {!pred && (
          <p className="doe-empty">
            {active
              ? `${MODEL_LABEL[scalarModel]} hazır · ${active.n_samples ?? "?"} örnek. Soldan girdileri verip "Tahmin et".`
              : "Bu şablonda model yok — Model aşamasından eğit."}
          </p>
        )}
        {pred && (
          <>
            <div className="sg-res-grid">
              <div className="cv-card sg-res">
                <span className="ml-k">Maks deplasman</span>
                <span className="ds-big">
                  {fmtNum(pred.max_displacement)} <span className="sg-unit">mm</span>
                </span>
                <span className="ds-sb">
                  {paramResult?.model_kind ?? scalarModel} · {paramResult?.out_of_domain ? "uzay dışı" : "uzay içi"}
                </span>
              </div>
              <div className="cv-card sg-res">
                <span className="ml-k">Maks von Mises</span>
                <span className="ds-big">
                  {fmtNum(pred.max_von_mises)} <span className="sg-unit">MPa</span>
                </span>
                <span className="ds-sb">
                  {yc
                    ? yc.source === "max_von_mises"
                      ? "ham tepe · tekillik dahil"
                      : "maskeli · tekillik hariç"
                    : "ham tepe · tekillik dahil"}
                </span>
              </div>
              {yc ? (
                <div
                  className={`cv-card sg-res ${yc.exceeds_yield ? "sg-yield-over" : yc.exceeds_limit ? "sg-yield-near" : ""}`}
                  data-testid="yield-card"
                >
                  <span className="sg-yield-head">
                    <span className="ml-k">Akma kullanımı · {yc.material}</span>
                    <strong>{yc.utilisation != null ? `%${(yc.utilisation * 100).toFixed(0)}` : "—"}</strong>
                  </span>
                  <span className="sg-yield-bar" aria-hidden="true">
                    <span style={{ width: `${Math.min(100, (yc.utilisation ?? 0) * 100)}%` }} />
                    <span className="sg-yield-limit" />
                  </span>
                  <span className="ds-sb">
                    {fmtNum(yc.sigma_mpa)} / {fmtNum(yc.yield_mpa)} MPa ·{" "}
                    {yc.exceeds_yield
                      ? "akma aşılıyor — malzeme plastik, tahmin geçersiz"
                      : yc.exceeds_limit
                        ? "limit aşılmadı ama sınırda"
                        : "elastik bölgede"}
                  </span>
                </div>
              ) : (
                <div className="cv-card sg-res">
                  <span className="ml-k">Akma kullanımı</span>
                  <span className="ds-sb">Malzeme seçilmedi; akma kontrolü atlandı.</span>
                </div>
              )}
            </div>

            {paramResult?.out_of_domain && (
              <div className="ds-section" data-testid="ood-section">
                <span className="ml-k">Neden uzay dışı · eğitim kutusu ihlali</span>
                {(paramResult.domain_violations ?? []).length === 0 && (
                  <p className="ds-sb">Sayı gösterilir, güvenilmez. Model bu noktayı hiç görmedi.</p>
                )}
                {(paramResult.domain_violations ?? []).map((v) => {
                  const bound = v.side === "below" ? v.min : v.max;
                  return (
                    <div className="sg-ood" key={v.feature}>
                      <span className="sg-ood-main">
                        <strong>
                          {violationLabel(v.feature)} = {fmtNum(v.value)} ·{" "}
                          {v.side === "below" ? "alt sınırın altında" : "üst sınırın üstünde"}
                        </strong>
                        <span>
                          eğitim aralığı {fmtNum(v.min)} – {fmtNum(v.max)}
                          {v.factor ? ` · ${v.factor.toFixed(2)}×` : ""}
                        </span>
                      </span>
                      <button
                        type="button"
                        className="doe-btn sg-btn-sm"
                        onClick={() => clampToBound(v.feature, bound, v.side)}
                      >
                        {violationLabel(v.feature)}&apos;yi {fmtNum(bound)}&apos;e çek
                      </button>
                    </div>
                  );
                })}
                <span className="ds-sb">
                  Log-log model kuvvet yasası öğrendiği için sınırın dışında da makul sonuç verebilir, ama
                  garanti yoktur — uzaklaştıkça bozulur ve bozulduğunu söylemez.
                </span>
              </div>
            )}

            {fea && (
              <div className="cv-card sg-fea" data-testid="fea-compare">
                <span className="ml-k">FEA kıyası · run {fea.run_id} · çözülmüş</span>
                <div className="sg-fea-grid">
                  <span><span className="ds-sb">FEA u_max (run {fea.run_id})</span><strong>{fmtNum(fea.max_displacement)} mm</strong></span>
                  <span><span className="ds-sb">Sapma u</span><strong>{fmtPct(dev?.max_displacement_pct)}</strong></span>
                  <span><span className="ds-sb">FEA VM_max</span><strong>{fmtNum(fea.max_von_mises)} MPa</strong></span>
                  <span><span className="ds-sb">Sapma VM</span><strong>{fmtPct(dev?.max_von_mises_pct)}</strong></span>
                </div>
              </div>
            )}
          </>
        )}

        <div className="cv-card sg-sweep" data-testid="sweep-section">
          <span className="ds-legend-row">
            <span className="doe-phead-title">
              <span className="ml-k">Tek parametre tarama · {sweepN} adım · tek istek</span>
              <strong className="sg-sweep-title">
                {sweepResult
                  ? `σ max, ${violationLabel(sweepResult.sweep_param)}'e göre`
                  : "bir parametreyi aralıkta değiştir, N tahmin tek seferde"}
              </strong>
            </span>
            <span className="ds-sb sg-right sg-legend">
              <span className="cv-ref-swatch sg-yield-swatch" />
              akma{yc ? ` ${fmtNum(yc.yield_mpa)} MPa` : ""}
            </span>
            <span className="ds-sb sg-legend">
              <span className="sg-ood-swatch" />
              uzay dışı
            </span>
          </span>
          <p className="ds-sb" data-testid="sweep-fixed-inputs">
            Taranmayan girdiler soldaki formdan alınır:{" "}
            {predictFields
              .filter((f) => !f.optional && f.name !== sweepParam)
              .map((f) => `${f.symbol ?? f.label}=${params[f.name] ?? String(f.defaultValue)}`)
              .concat(
                sweepParam !== "load_fy" ? [`Fy=${fy}`] : [],
                materialName ? [materialName] : ["malzeme seçilmedi"],
                [nlgeom ? "NLGEOM" : "lineer"],
              )
              .join(" · ")}
            . Eğitim aralığı dışındaki girdi her noktayı &quot;uzay dışı&quot; yapar.
          </p>
          <span className="cv-row sg-sweep-form">
            <label className="doe-pfoot-field">
              <span className="ml-k">Parametre</span>
              <select
                className="cv-template sg-sweep-select"
                aria-label="Parametre"
                value={sweepParam}
                onChange={(e) => setSweepParam(e.target.value)}
              >
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
            <label className="doe-pfoot-field">
              <span className="ml-k">Min</span>
              <input className="doe-num" aria-label="Min" value={sweepMin} onChange={(e) => setSweepMin(e.target.value)} />
            </label>
            <label className="doe-pfoot-field">
              <span className="ml-k">Max</span>
              <input className="doe-num" aria-label="Max" value={sweepMax} onChange={(e) => setSweepMax(e.target.value)} />
            </label>
            <label className="doe-pfoot-field">
              <span className="ml-k">Adım</span>
              <input
                className="doe-num"
                aria-label="Adım sayısı (2–200)"
                value={sweepN}
                onChange={(e) => setSweepN(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="doe-btn doe-btn-primary sg-right"
              disabled={!canParamsPredict || !sweepParam || sweepMin === "" || sweepMax === ""}
              onClick={() => void handleSweep()}
            >
              {busy === "sweep" ? "Taranıyor…" : "Tara"}
            </button>
          </span>
          {sweepResult && sweepResult.points.length > 0 && (
            <div data-testid="sweep-result" className="ds-section">
              <SweepChart result={sweepResult} yieldMpa={yc?.yield_mpa ?? null} />
              <details className="surrogate-exponents">
                <summary>Noktalar · {sweepResult.points.length}</summary>
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
              </details>
            </div>
          )}
        </div>
        {showPredict && feedback}
      </div>
    </div>
  );

  if (view === "model") return modelStage;
  if (view === "predict") return predictStage;
  return (
    <div className="sg-all">
      {modelStage}
      {predictStage}
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

/** Tahmin ↔ FEA saçılımı: x FEA, y tahmin; ±%5 bant; uzay dışı run kahverengi. */
function ValidationScatter({ rows, target }: { rows: ValidationRow[]; target: "u" | "vm" }) {
  const pts = rows
    .map((r) => ({
      x: target === "u" ? r.fea_u : r.fea_vm,
      y: target === "u" ? r.pred_u : r.pred_vm,
      ood: r.out_of_domain,
      id: r.run_id,
    }))
    .filter((p): p is { x: number; y: number; ood: boolean; id: number } =>
      p.x != null && p.y != null && Number.isFinite(p.x) && Number.isFinite(p.y),
    );
  const W = 400;
  const H = 260;
  const L = 30;
  const B = 240;
  if (pts.length === 0) {
    return <p className="ds-sb">Bu hedef için karşılaştırılacak satır yok.</p>;
  }
  const all = pts.flatMap((p) => [p.x, p.y]);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const span = hi - lo || Math.abs(hi) || 1;
  const a = lo - span * 0.05;
  const b = hi + span * 0.05;
  const sx = (v: number) => L + ((v - a) / (b - a)) * (W - L);
  const sy = (v: number) => B - ((v - a) / (b - a)) * B;
  const band = (k: number) => `${sx(a)},${sy(a * k)} ${sx(b)},${sy(b * k)}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="sg-scatter" role="img" aria-label={`Tahmin ↔ FEA saçılımı, ${pts.length} run`}>
      <rect x={L + 0.5} y="0.5" width={W - L - 1} height={B - 1} className="cv-frame" />
      <polygon points={`${band(0.95)} ${sx(b)},${sy(b * 1.05)} ${sx(a)},${sy(a * 1.05)}`} className="sg-band" />
      <line x1={sx(a)} y1={sy(a)} x2={sx(b)} y2={sy(b)} className="sg-diag" />
      {pts.map((p) => (
        <circle key={p.id} cx={sx(p.x)} cy={sy(p.y)} r="3" className={p.ood ? "sg-pt sg-pt-ood" : "sg-pt"}>
          <title>{`run ${p.id} · FEA ${fmtNum(p.x)} · tahmin ${fmtNum(p.y)}`}</title>
        </circle>
      ))}
      <text x={L + 4} y={H - 4} className="sg-axis-text">FEA {target === "u" ? "u (mm)" : "σ (MPa)"} →</text>
      <text x="2" y="12" className="sg-axis-text">tahmin</text>
    </svg>
  );
}

/** Taranan parametreye göre σ_max (yoksa u_max) eğrisi; akma çizgisi kesikli,
 * uzay dışı noktalar kahverengi. */
function SweepChart({ result, yieldMpa }: { result: SweepResult; yieldMpa: number | null }) {
  const useSigma = result.points.some((p) => p.max_von_mises != null);
  const pick = (p: SweepPoint) => (useSigma ? p.max_von_mises : p.max_displacement);
  const pts = result.points.filter((p) => pick(p) != null && Number.isFinite(pick(p) as number));
  if (pts.length < 2) return null;
  const W = 700;
  const H = 220;
  const xs = pts.map((p) => p.value);
  const ys = pts.map((p) => pick(p) as number);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const yTop = Math.max(...ys, useSigma && yieldMpa != null ? yieldMpa : 0) * 1.08 || 1;
  const sx = (x: number) => ((x - x0) / (x1 - x0 || 1)) * W;
  const sy = (y: number) => H - (y / yTop) * H;
  const path = pts.map((p) => `${sx(p.value).toFixed(1)},${sy(pick(p) as number).toFixed(1)}`).join(" ");
  // Uzay dışı bölgeler: ardışık OOD noktaların x aralığı
  const oodRects: { x: number; w: number }[] = [];
  let start: number | null = null;
  pts.forEach((p, i) => {
    if (p.out_of_domain && start == null) start = i;
    const end = !p.out_of_domain || i === pts.length - 1;
    if (start != null && end) {
      const last = p.out_of_domain ? i : i - 1;
      const xa = sx(pts[start].value) - (start > 0 ? (sx(pts[start].value) - sx(pts[start - 1].value)) / 2 : 0);
      const xb = sx(pts[last].value) + (last < pts.length - 1 ? (sx(pts[last + 1].value) - sx(pts[last].value)) / 2 : 0);
      oodRects.push({ x: xa, w: Math.max(0, xb - xa) });
      start = null;
    }
  });
  return (
    <>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${useSigma ? "σ_max" : "u_max"} – ${result.sweep_param} eğrisi, ${pts.length} nokta`}
        className="sweep-chart sg-sweep-svg"
        preserveAspectRatio="none"
      >
        <rect x="0.5" y="0.5" width={W - 1} height={H - 1} className="cv-frame" />
        {oodRects.map((r, i) => (
          <rect key={i} x={r.x} y="1" width={r.w} height={H - 2} className="sg-ood-rect" />
        ))}
        {useSigma && yieldMpa != null && (
          <line x1="0" y1={sy(yieldMpa)} x2={W} y2={sy(yieldMpa)} className="sg-yield-line" />
        )}
        <polyline points={path} className="cv-line" />
        {pts.map((p) => (
          <circle
            key={p.value}
            cx={sx(p.value)}
            cy={sy(pick(p) as number)}
            r="3.4"
            className={p.out_of_domain ? "sg-pt sg-pt-ood" : p.exceeds_yield ? "sg-pt sg-pt-yield" : "sg-pt"}
          >
            <title>{`${result.sweep_param}=${fmtNum(p.value)} · ${useSigma ? "σ" : "u"} ${fmtNum(pick(p))}${p.out_of_domain ? " · uzay dışı" : ""}${p.exceeds_yield ? " · akıyor" : ""}`}</title>
          </circle>
        ))}
      </svg>
      <span className="cv-axis ds-sb">
        <span>{violationLabel(result.sweep_param)} {fmtNum(x0)}</span>
        <span>{useSigma ? "σ_max (MPa)" : "u_max (mm)"} · {pts.length} nokta{result.n_out_of_domain > 0 ? ` · ${result.n_out_of_domain} uzay dışı` : ""}</span>
        <span>{violationLabel(result.sweep_param)} {fmtNum(x1)}</span>
      </span>
    </>
  );
}
