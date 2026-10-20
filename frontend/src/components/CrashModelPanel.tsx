/**
 * Crash vekil modeli (1.19f-2) — ML Stüdyo / Crash / Model aşaması.
 *
 * Şablon + senaryo + (isteğe bağlı) DOE çalışması → korpus özeti → eğit →
 * K-fold CV metrik tablosu. Model kabul eşiği / öneri yok: sayılar gösterilir.
 */
import { useEffect, useMemo, useState } from "react";
import { fetchCrashCatalog } from "../api/crash";
import type { CrashTrainKind, CrashModelKind } from "../api/crashMl";

const KINDS: CrashModelKind[] = ["hybrid", "loglinear", "rf"];
import {
  fetchCrashCorpus,
  fetchCrashDoeStudies,
  fetchCrashModels,
  trainCrashModel,
  CRASH_KIND_LABEL,
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
  // 1.22f: ham kartlı koşular varsayılan dışarıda (ham kart taranamaz; parametre değil).
  const [includeRaw, setIncludeRaw] = useState(false);
  const [kind, setKind] = useState<CrashTrainKind>("auto");
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
    fetchCrashCorpus({ template_id: templateId, scenario, study_id: studyId, include_raw_cards: includeRaw })
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
  }, [templateId, scenario, studyId, includeRaw]);

  function selectTemplate(tid: string) {
    setTemplateId(tid);
    setScenario(scenarioFor(tid));
    setStudyId(null);
  }

  async function handleTrain(k: CrashTrainKind = kind) {
    setBusy(true);
    setError(null);
    try {
      setModel(
        await trainCrashModel({ template_id: templateId, scenario, study_id: studyId, include_raw_cards: includeRaw, kind: k }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eğitim başarısız.");
    } finally {
      setBusy(false);
    }
  }

  const sameSource = model !== null && model.study_id === studyId;

  const kindRows = (model?.targets ?? []).filter((t) => t.cv?.kinds && Object.keys(t.cv.kinds).length > 1);
  /** Tür → hedef başına CV MAPE (%); auto modelde `cv.kinds`, tek türlü modelde `cv`. */
  const mapeOf = (k: CrashModelKind, key: string): number | null => {
    const t = model?.targets.find((x) => x.key === key);
    const m = t?.cv?.kinds?.[k] ?? ((t?.kind ?? t?.cv?.kind) === k ? t?.cv : undefined);
    return m && typeof m.mape === "number" && Number.isFinite(m.mape) ? m.mape * 100 : null;
  };
  const chosenCount = (k: CrashModelKind) => (model?.targets ?? []).filter((t) => t.trained && (t.kind ?? t.cv?.kind) === k).length;
  const trainedKinds = new Set<CrashModelKind>(
    (model?.targets ?? []).flatMap((t) => [
      ...(Object.keys(t.cv?.kinds ?? {}) as CrashModelKind[]),
      ...((t.kind ?? t.cv?.kind) ? [(t.kind ?? t.cv?.kind) as CrashModelKind] : []),
    ]),
  );
  const barTargets: { key: string; label: string }[] = (
    model ? model.targets.map((t) => ({ key: t.key, label: t.label })) : Object.keys(corpus?.targets ?? {}).map((key) => ({ key, label: key }))
  ).slice(0, 4);
  const bar = (v: number | null) => `${Math.min(100, (v ?? 0) * 5)}%`;
  const kindName = (k: CrashModelKind) => (k === "rf" ? "RF" : k);

  async function trainKind(k: CrashTrainKind) {
    setKind(k);
    await handleTrain(k);
  }

  return (
    <div className="doe-stage sg-stage crash-ml-stage" data-testid="crash-model-stage">
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">1.19d RF · 1.27 loglinear · hybrid · auto</span>
            <span className="ml-h">Vekil model</span>
          </span>
        </div>
        <div className="doe-pane-body ds-body">
          <span className="cv-row">
            <span className="ml-k cv-k-90">Şablon</span>
            <span className="doe-chips" role="group" aria-label="Crash şablonu">
              {templateIds.map((tid) => (
                <button
                  key={tid}
                  type="button"
                  className={tid === templateId ? "doe-chip active" : "doe-chip"}
                  aria-pressed={tid === templateId}
                  disabled={busy}
                  onClick={() => selectTemplate(tid)}
                >
                  {tid.replace(/_shell$/, "")}
                </button>
              ))}
            </span>
          </span>
          <span className="cv-row">
            <span className="ml-k cv-k-90">Senaryo</span>
            <select value={scenario} aria-label="Senaryo" disabled={busy} onChange={(e) => setScenario(e.target.value)}>
              {CRASH_SCENARIOS.map((sc) => (
                <option key={sc} value={sc}>
                  {sc}
                </option>
              ))}
            </select>
          </span>
          <span className="cv-row">
            <span className="ml-k cv-k-90">Korpus</span>
            <select
              value={studyId ?? ""}
              aria-label="Kaynak"
              disabled={busy}
              onChange={(e) => setStudyId(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">Tüm çözülmüş koşular (elle dahil)</option>
              {templateStudies.map((st) => (
                <option key={st.id} value={st.id}>
                  DOE #{st.id} · {st.name ?? st.template_id} · {st.n_cases} örnek
                </option>
              ))}
            </select>
            <label className="doe-pfoot-check sg-nlgeom" title="1.22f: ham kartlı koşular da korpusa girsin">
              <input type="checkbox" checked={includeRaw} disabled={busy} onChange={(e) => setIncludeRaw(e.target.checked)} />
              ham kartlı
            </label>
          </span>
          {corpus && (
            <div className="ds-stats" aria-label="Korpus özeti">
              <span>
                <span className="ml-k sg-k-keep">Koşu</span>
                <strong>{corpus.n_runs}</strong>
              </span>
              <span>
                <span className="ml-k sg-k-keep">Değişen girdi</span>
                <strong>{corpus.features.length}</strong>
              </span>
              <span>
                <span className="ml-k sg-k-keep">Sabit</span>
                <strong>{Object.keys(corpus.constant_features).length}</strong>
              </span>
              {Object.entries(corpus.dropped).map(([k, v]) => (
                <span key={k}>
                  <span className="ml-k sg-k-keep">düşen · {k}</span>
                  <strong>{v}</strong>
                </span>
              ))}
            </div>
          )}
          {corpus && (
            <div className="crash-ml-features">
              {corpus.features.slice(0, 40).map((fk) => (
                <code key={fk}>{fk}</code>
              ))}
              {corpus.features.length > 40 && <span className="crash-doe-sub">+{corpus.features.length - 40}</span>}
            </div>
          )}

          <div className="ds-section">
            <span className="ml-k">Skaler modeller · 5-fold CV MAPE · hedef başına seçim</span>
            {KINDS.map((k) => {
              const n = chosenCount(k);
              const trained = trainedKinds.has(k);
              return (
                <div key={k} className={n > 0 ? "sg-model active" : "sg-model"} data-testid={`crash-model-card-${k}`}>
                  <span className="sg-model-main">
                    <span className="sg-model-title">
                      <strong className="ml-h sg-model-name">{kindName(k)}</strong>
                      <span className={`doe-st ${n > 0 ? "doe-st-ok" : ""}`}>
                        {n > 0 ? `seçildi · ${n} hedef` : trained ? "eğitildi" : "eğitilmedi"}
                      </span>
                    </span>
                    <span className="ds-sb">{CRASH_KIND_LABEL[k]}</span>
                  </span>
                  <span className="sg-model-bars">
                    {barTargets.map((t) => {
                      const v = mapeOf(k, t.key);
                      return (
                        <span key={t.key} className="sg-bar-row" title={t.label}>
                          <span className="ml-k sg-bar-k sg-k-keep">{t.key.replace(/_(kn|j|mm|g)$/, "")}</span>
                          <span className="sg-bar">
                            <span style={{ width: bar(v) }} />
                          </span>
                          <span className="sg-bar-v">{v == null ? "—" : `%${v.toFixed(1)}`}</span>
                        </span>
                      );
                    })}
                  </span>
                  <span className="sg-model-actions">
                    <button
                      type="button"
                      className="doe-btn sg-btn-sm"
                      disabled={busy || !corpus || corpus.n_runs === 0}
                      onClick={() => void trainKind(k)}
                    >
                      {busy && kind === k ? "Eğitiliyor…" : `${CRASH_KIND_LABEL[k]} eğit`}
                    </button>
                  </span>
                </div>
              );
            })}
            <span className="ds-sb">
              Hedef başına ayrı model; en az 8 dolu satır. Log türleri ≤ 0 hedefli satırı atar. "Üçünü de eğit"
              hedef başına CV MAPE'si en düşük türü seçer.
            </span>
          </div>
          {error && <p className="dataset-error">{error}</p>}
        </div>
        <div className="doe-pfoot">
          <span className="ds-sb">Eğitim tek şablon + tek senaryo + tek korpus ile çalışır</span>
          <button
            type="button"
            className="doe-btn doe-btn-primary sg-right"
            disabled={busy || !corpus || corpus.n_runs === 0}
            onClick={() => void trainKind("auto")}
          >
            {busy && kind === "auto" ? "Eğitiliyor…" : "Üçünü de eğit"}
          </button>
        </div>
      </div>

      <div className="doe-pane-r">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">
              CV metrikleri
              {model && ` · ${model.template_id} / ${model.scenario} · ${model.study_id ? `DOE #${model.study_id}` : "tüm koşular"} · ${model.n_runs} koşu`}
              {model && !sameSource ? " · seçili kaynaktan farklı" : ""}
            </span>
            <span className="ml-h">Hedef başına doğruluk</span>
          </span>
        </div>
        <div className="doe-pane-body">
          {!model && <p className="doe-empty">Bu şablon / senaryo için kayıtlı model yok.</p>}
          {model && (
            <>
              <div className="doe-table-scroll crash-doe-table">
                <table className="doe-table crash-ml-metrics">
                  <thead>
                    <tr>
                      <th className="l">hedef</th>
                      <th>birim</th>
                      <th>tür</th>
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
                        <td>{t.trained ? kindName((t.kind ?? t.cv?.kind ?? "rf") as CrashModelKind) : "—"}</td>
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
              {kindRows.length > 0 && (
                <div className="doe-table-scroll crash-doe-table">
                  <table className="doe-table crash-ml-metrics" aria-label="Tür karşılaştırması">
                    <thead>
                      <tr>
                        <th className="l">hedef</th>
                        {KINDS.map((k) => (
                          <th key={k}>{kindName(k)} · MAPE</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {kindRows.map((t) => (
                        <tr key={t.key}>
                          <td className="l">{t.label}</td>
                          {KINDS.map((k) => {
                            const m = t.cv?.kinds?.[k];
                            const chosen = (t.kind ?? t.cv?.kind) === k;
                            return (
                              <td key={k} className={chosen ? "crash-ml-chosen" : undefined}>
                                {!m ? "—" : m.skipped ? m.skipped : `${(100 * (m.mape ?? NaN)).toFixed(1)}%`}
                                {m?.dropped_nonpositive ? ` (−${m.dropped_nonpositive})` : ""}
                                {chosen ? " ✓" : ""}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="ds-stats">
                <span>
                  <span className="ml-k sg-k-keep">Girdi</span>
                  <strong>{model.feature_keys.length}</strong>
                  <span className="ds-sb">{model.feature_keys.join(", ")}</span>
                </span>
                {model.dropped_features.length > 0 && (
                  <span>
                    <span className="ml-k sg-k-keep">eksik değerli, alınmadı</span>
                    <strong>{model.dropped_features.length}</strong>
                  </span>
                )}
                {model.design_spec && model.design_spec.raw_keys.length > 0 && (
                  <span>
                    <span className="ml-k sg-k-keep">log'a girmeyen</span>
                    <span className="ds-sb">{model.design_spec.raw_keys.join(", ")}</span>
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
