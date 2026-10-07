/**
 * Crash vekil modeli (1.19f-2) — ML Stüdyo / Crash / Model aşaması.
 *
 * Şablon + senaryo + (isteğe bağlı) DOE çalışması → korpus özeti → eğit →
 * K-fold CV metrik tablosu. Model kabul eşiği / öneri yok: sayılar gösterilir.
 */
import { useEffect, useMemo, useState } from "react";
import { fetchCrashCatalog } from "../api/crash";
import {
  fetchCrashCorpus,
  fetchCrashDoeStudies,
  fetchCrashModels,
  trainCrashModel,
  type CrashCorpusSummary,
  type CrashDoeStudyInfo,
  type CrashModelInfo,
} from "../api/crashMl";

export const CRASH_SCENARIOS = ["rigid_wall", "plate_ball"] as const;

/** Şablonun `/crash/scenario` kurulumundaki senaryo adı. */
export function scenarioFor(templateId: string): string {
  return templateId === "plate_ball_shell" || templateId === "bucket_rock_shell" ? "plate_ball" : "rigid_wall";
}

export function fmtNum(v: number | undefined | null, digits = 3): string {
  if (v === undefined || v === null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(2);
  return v.toFixed(a >= 100 ? 1 : digits);
}

export default function CrashModelPanel() {
  const [templateIds, setTemplateIds] = useState<string[]>([]);
  const [templateId, setTemplateId] = useState("crash_box_shell");
  const [scenario, setScenario] = useState("rigid_wall");
  const [studies, setStudies] = useState<CrashDoeStudyInfo[]>([]);
  const [studyId, setStudyId] = useState<number | null>(null);
  const [corpus, setCorpus] = useState<CrashCorpusSummary | null>(null);
  const [model, setModel] = useState<CrashModelInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCrashCatalog()
      .then((c) => setTemplateIds(Object.keys(c.scenario_templates).sort()))
      .catch((e) => setError(e instanceof Error ? e.message : "Crash kataloğu alınamadı."));
    fetchCrashDoeStudies()
      .then(setStudies)
      .catch(() => setStudies([]));
  }, []);

  const templateStudies = useMemo(
    () => studies.filter((s) => s.template_id === templateId),
    [studies, templateId],
  );

  // Seçim değişince: korpus özeti + kayıtlı model (varsa).
  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchCrashCorpus({ template_id: templateId, scenario, study_id: studyId })
      .then((c) => !cancelled && setCorpus(c))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Korpus alınamadı."));
    fetchCrashModels()
      .then((ms) => {
        if (!cancelled) setModel(ms.find((m) => m.template_id === templateId && m.scenario === scenario) ?? null);
      })
      .catch(() => !cancelled && setModel(null));
    return () => {
      cancelled = true;
    };
  }, [templateId, scenario, studyId]);

  function selectTemplate(tid: string) {
    setTemplateId(tid);
    setScenario(scenarioFor(tid));
    setStudyId(null);
  }

  async function handleTrain() {
    setBusy(true);
    setError(null);
    try {
      setModel(await trainCrashModel({ template_id: templateId, scenario, study_id: studyId }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eğitim başarısız.");
    } finally {
      setBusy(false);
    }
  }

  const sameSource = model !== null && model.study_id === studyId;

  return (
    <div className="crash-ml-stage" data-testid="crash-model-stage">
      <section className="crash-ml-card">
        <div className="crash-ml-head">
          <span className="ml-k">1.19 · Korpus</span>
          <span className="ml-h">Eğitim verisi</span>
        </div>
        <div className="crash-doe-field">
          <span className="ml-k">Şablon</span>
          <span className="doe-chips" role="group" aria-label="Crash şablonu">
            {templateIds.map((tid) => (
              <button
                key={tid}
                type="button"
                className={tid === templateId ? "doe-chip active" : "doe-chip"}
                aria-pressed={tid === templateId}
                onClick={() => selectTemplate(tid)}
              >
                {tid.replace(/_shell$/, "")}
              </button>
            ))}
          </span>
        </div>
        <div className="crash-ml-row">
          <label className="crash-ml-select">
            <span className="ml-k">Senaryo</span>
            <select value={scenario} aria-label="Senaryo" onChange={(e) => setScenario(e.target.value)}>
              {CRASH_SCENARIOS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="crash-ml-select">
            <span className="ml-k">Kaynak</span>
            <select
              value={studyId ?? ""}
              aria-label="Kaynak"
              onChange={(e) => setStudyId(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">Tüm çözülmüş koşular (elle dahil)</option>
              {templateStudies.map((s) => (
                <option key={s.id} value={s.id}>
                  DOE #{s.id} · {s.name ?? s.template_id} · {s.n_cases} örnek
                </option>
              ))}
            </select>
          </label>
        </div>

        {corpus && (
          <div className="crash-ml-corpus" aria-label="Korpus özeti">
            <div className="crash-doe-kv">
              <span>
                <span className="ml-k">Koşu</span> {corpus.n_runs}
              </span>
              <span>
                <span className="ml-k">Değişen girdi</span> {corpus.features.length}
              </span>
              <span>
                <span className="ml-k">Sabit</span> {Object.keys(corpus.constant_features).length}
              </span>
              {Object.entries(corpus.dropped).map(([k, v]) => (
                <span key={k} className="crash-doe-sub">
                  düşen · {k}: {v}
                </span>
              ))}
            </div>
            <div className="crash-ml-features">
              {corpus.features.slice(0, 40).map((f) => (
                <code key={f}>{f}</code>
              ))}
              {corpus.features.length > 40 && <span className="crash-doe-sub">+{corpus.features.length - 40}</span>}
            </div>
            <div className="crash-doe-kv">
              {Object.entries(corpus.targets).map(([k, v]) => (
                <span key={k}>
                  <span className="ml-k">{k}</span> {v}/{corpus.n_runs}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="crash-ml-actions">
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy || !corpus || corpus.n_runs === 0}
            onClick={() => void handleTrain()}
          >
            {busy ? "Eğitiliyor…" : "Eğit · 5-fold CV"}
          </button>
          <span className="crash-doe-sub">Hedef başına Random Forest; en az 8 dolu satır.</span>
        </div>
      </section>

      <section className="crash-ml-card" aria-label="Model metrikleri">
        <div className="crash-ml-head">
          <span className="ml-k">1.19 · Model</span>
          <span className="ml-h">CV metrikleri</span>
          {model && (
            <span className="crash-doe-sub">
              {model.template_id} / {model.scenario} · {model.study_id ? `DOE #${model.study_id}` : "tüm koşular"} ·{" "}
              {model.n_runs} koşu
              {!sameSource && " · seçili kaynaktan farklı"}
            </span>
          )}
        </div>
        {!model && <p className="doe-empty">Bu şablon / senaryo için kayıtlı model yok.</p>}
        {model && (
          <>
            <div className="doe-table-scroll crash-doe-table">
              <table className="doe-table crash-ml-metrics">
                <thead>
                  <tr>
                    <th className="l">hedef</th>
                    <th>birim</th>
                    <th>n</th>
                    <th>R²</th>
                    <th>MAE</th>
                    <th>MAPE</th>
                    <th>fold</th>
                  </tr>
                </thead>
                <tbody>
                  {model.targets.map((t) => (
                    <tr key={t.key} title={t.definition}>
                      <td className="l">{t.label}</td>
                      <td>{t.unit}</td>
                      <td>{t.cv?.n ?? 0}</td>
                      {t.trained && t.cv ? (
                        <>
                          <td>{fmtNum(t.cv.r2)}</td>
                          <td>{fmtNum(t.cv.mae)}</td>
                          <td>{t.cv.mape !== undefined ? `${(100 * t.cv.mape).toFixed(1)}%` : "—"}</td>
                          <td>{t.cv.folds ?? "—"}</td>
                        </>
                      ) : (
                        <td colSpan={4} className="crash-doe-msg">
                          {t.cv?.skipped ?? "eğitilmedi"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="crash-doe-kv">
              <span>
                <span className="ml-k">Girdi</span> {model.feature_keys.join(", ")}
              </span>
              {model.dropped_features.length > 0 && (
                <span className="crash-doe-sub">eksik değerli, alınmadı: {model.dropped_features.length}</span>
              )}
            </div>
          </>
        )}
        {error && <p className="dataset-error">{error}</p>}
      </section>
    </div>
  );
}
