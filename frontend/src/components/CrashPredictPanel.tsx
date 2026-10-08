/**
 * Crash vekil model tahmini (1.19f-3) — ML Stüdyo / Crash / Tahmin aşaması.
 *
 * Kayıtlı model seçilir; modelin girdi sütunları için form (başlangıç değeri
 * eğitim aralığının ortası, aralık yanında). Tahmin her hedef için CV MAE ile
 * birlikte gösterilir. Eğitim aralığı dışındaki girdi engellenmez, listelenir.
 */
import { useEffect, useState } from "react";
import { fetchCrashModels, predictCrash, type CrashModelInfo, type CrashPrediction } from "../api/crashMl";
import { fmtNum } from "./CrashModelPanel";

const keyOf = (m: CrashModelInfo) => `${m.template_id}/${m.scenario}`;

export function midInputs(model: CrashModelInfo): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of model.feature_keys) {
    const [lo, hi] = model.bounds[k] ?? [0, 0];
    out[k] = String(Number(((lo + hi) / 2).toPrecision(6)));
  }
  return out;
}

export default function CrashPredictPanel() {
  const [models, setModels] = useState<CrashModelInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [result, setResult] = useState<CrashPrediction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCrashModels()
      .then((ms) => {
        const ok = ms.filter((m) => Array.isArray(m.feature_keys));
        setModels(ok);
        if (ok.length) {
          setSelected(keyOf(ok[0]));
          setInputs(midInputs(ok[0]));
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Modeller alınamadı."));
  }, []);

  const model = models.find((m) => keyOf(m) === selected) ?? null;

  function selectModel(key: string) {
    setSelected(key);
    setResult(null);
    const m = models.find((x) => keyOf(x) === key);
    if (m) setInputs(midInputs(m));
  }

  async function handlePredict() {
    if (!model) return;
    setError(null);
    const values: Record<string, number> = {};
    for (const k of model.feature_keys) {
      const v = Number(inputs[k]);
      if (inputs[k]?.trim() === "" || !Number.isFinite(v)) {
        setError(`'${k}' sayı olmalı.`);
        return;
      }
      values[k] = v;
    }
    setBusy(true);
    try {
      setResult(await predictCrash({ template_id: model.template_id, scenario: model.scenario, inputs: values }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tahmin başarısız.");
    } finally {
      setBusy(false);
    }
  }

  if (!model) {
    return (
      <div className="crash-ml-stage" data-testid="crash-predict-stage">
        <section className="crash-ml-card">
          <p className="doe-empty">Kayıtlı crash modeli yok. Önce Model aşamasında eğit.</p>
          {error && <p className="dataset-error">{error}</p>}
        </section>
      </div>
    );
  }

  const ood = new Set(result?.out_of_domain ?? []);

  return (
    <div className="crash-ml-stage" data-testid="crash-predict-stage">
      <section className="crash-ml-card">
        <div className="crash-ml-head">
          <span className="ml-k">1.19 · Tahmin</span>
          <span className="ml-h">Girdi</span>
        </div>
        <label className="crash-ml-select">
          <span className="ml-k">Model</span>
          <select value={selected} aria-label="Model" onChange={(e) => selectModel(e.target.value)}>
            {models.map((m) => (
              <option key={keyOf(m)} value={keyOf(m)}>
                {m.template_id} / {m.scenario} · {m.study_id ? `DOE #${m.study_id}` : "tüm koşular"} · {m.n_runs} koşu
              </option>
            ))}
          </select>
        </label>
        <div className="crash-pred-inputs">
          <span className="crash-doe-vh">girdi</span>
          <span className="crash-doe-vh">değer</span>
          <span className="crash-doe-vh">eğitim aralığı</span>
          {model.feature_keys.map((k) => {
            const [lo, hi] = model.bounds[k] ?? [NaN, NaN];
            return (
              <div key={k} className={ood.has(k) ? "crash-pred-row ood" : "crash-pred-row"}>
                <code>{k}</code>
                <input
                  className="doe-num"
                  aria-label={k}
                  value={inputs[k] ?? ""}
                  onChange={(e) => setInputs((prev) => ({ ...prev, [k]: e.target.value }))}
                />
                <span className="crash-doe-sub">
                  {fmtNum(lo)} – {fmtNum(hi)}
                </span>
              </div>
            );
          })}
        </div>
        <div className="crash-ml-actions">
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy}
            onClick={() => void handlePredict()}
          >
            {busy ? "Hesaplanıyor…" : "Tahmin et"}
          </button>
          <button
            type="button"
            className="doe-btn doe-btn-secondary"
            disabled={busy}
            onClick={() => setInputs(midInputs(model))}
          >
            Aralık ortası
          </button>
        </div>
        {error && <p className="dataset-error">{error}</p>}
      </section>

      <section className="crash-ml-card" aria-label="Tahmin sonucu">
        <div className="crash-ml-head">
          <span className="ml-k">1.19 · Tahmin</span>
          <span className="ml-h">Hedefler</span>
          <span className="crash-doe-sub">± = 5-fold CV MAE</span>
        </div>
        {!result && <p className="doe-empty">Girdileri verip &quot;Tahmin et&quot;.</p>}
        {result && (
          <>
            {result.out_of_domain.length > 0 && (
              <p className="crash-pred-ood" role="status">
                Eğitim aralığı dışında: {result.out_of_domain.join(", ")}
              </p>
            )}
            <div className="crash-pred-grid">
              {model.targets.map((t) => {
                const v = result.prediction[t.key];
                return (
                  <div key={t.key} className="crash-pred-tile" title={t.definition}>
                    <span className="ml-k">{t.label}</span>
                    <span className="crash-pred-value">
                      {v === null || v === undefined ? "—" : fmtNum(v)}
                      <span className="crash-pred-unit">{t.unit}</span>
                    </span>
                    <span className="crash-doe-sub">
                      {t.trained && t.cv
                        ? `± ${fmtNum(t.cv.mae)} · R² ${fmtNum(t.cv.r2)}`
                        : (t.cv?.skipped ?? "model yok")}
                    </span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
