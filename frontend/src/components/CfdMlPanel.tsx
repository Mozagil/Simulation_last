/**
 * ML Stüdyo / Akış — Faz 2.9: roket CFD DOE → vekil model (RF + K-fold CV) →
 * tahmin. Crash 1.19 deseni. Değişken / aralık / çözücü / mesh ayarı
 * mühendisin; model kabul eşiği ya da öneri yok, sayılar gösterilir.
 */
import { useEffect, useRef, useState } from "react";
import type { CfdSolver } from "../api/cfd";
import {
  fetchCfdCorpus,
  fetchCfdDoe,
  fetchCfdDoes,
  fetchCfdModels,
  postCfdDoe,
  predictCfd,
  trainCfdModel,
  type CfdCorpusSummary,
  type CfdDoe,
  type CfdDoeInfo,
  type CfdModelInfo,
} from "../api/cfdMl";
import { fmtNum } from "./CrashModelPanel";

export const DOE_VARS: { key: string; label: string; unit: string; lo: string; hi: string }[] = [
  { key: "mach", label: "Mach", unit: "", lo: "0.1", hi: "0.3" },
  { key: "alpha_deg", label: "Hücum açısı α", unit: "°", lo: "0", hi: "6" },
  { key: "fin_span", label: "Kanatçık açıklığı s", unit: "mm", lo: "70", hi: "130" },
  { key: "fin_root_chord", label: "Kök veteri Cr", unit: "mm", lo: "120", hi: "180" },
  { key: "fin_tip_chord", label: "Uç veteri Ct", unit: "mm", lo: "40", hi: "80" },
  { key: "fin_sweep", label: "Ok mesafesi Xs", unit: "mm", lo: "50", hi: "110" },
  { key: "nose_length", label: "Burun boyu Ln", unit: "mm", lo: "250", hi: "400" },
  { key: "body_length", label: "Gövde boyu Lb", unit: "mm", lo: "1000", hi: "1400" },
];
const SOLVERS: CfdSolver[] = ["simpleFoam", "rhoSimpleFoam", "rhoCentralFoam"];

const num = (s: string) => Number(s.replace(",", "."));

function Num({ label, value, onChange, disabled, unit }: { label: string; value: string; onChange: (v: string) => void; disabled?: boolean; unit?: string }) {
  return (
    <label className="crash-unit-field">
      <span>{label}</span>
      <span className="crash-unit-box">
        <input aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        {unit && <em>{unit}</em>}
      </span>
    </label>
  );
}

export default function CfdMlPanel({ pollMs = 4000 }: { pollMs?: number }) {
  // ---- DOE
  const [vars, setVars] = useState(() =>
    Object.fromEntries(DOE_VARS.map((v) => [v.key, { on: v.key === "mach" || v.key === "alpha_deg" || v.key === "fin_span", lo: v.lo, hi: v.hi }])),
  );
  const [doeForm, setDoeForm] = useState({ name: "", n: "10", mach: "0.2", alpha: "4", base_cell: "0.3", stl: "15", lmin: "2", lmax: "3", iterations: "400", relax_u: "0.5", relax_other: "0.3", cg: "900" });
  const [solver, setSolver] = useState<CfdSolver>("simpleFoam");
  const [doe, setDoe] = useState<CfdDoe | null>(null);
  const [does, setDoes] = useState<CfdDoeInfo[]>([]);
  // ---- model
  const [source, setSource] = useState<string | null>(null);
  const [corpus, setCorpus] = useState<CfdCorpusSummary | null>(null);
  const [model, setModel] = useState<CfdModelInfo | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [pred, setPred] = useState<{ prediction: Record<string, number | null>; out_of_domain: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const refreshDoes = () => fetchCfdDoes().then(setDoes).catch(() => setDoes([]));
  useEffect(() => {
    void refreshDoes();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchCfdCorpus({ application: solver, doe_id: source })
      .then((c) => !cancelled && setCorpus(c))
      .catch((e) => !cancelled && setError((e as Error).message));
    fetchCfdModels()
      .then((ms) => {
        if (cancelled) return;
        const m = ms.find((x) => x.application === solver) ?? null;
        setModel(m);
        if (m) setInputs(Object.fromEntries(m.feature_keys.map((k) => [k, String(+((m.bounds[k][0] + m.bounds[k][1]) / 2).toPrecision(4))])));
      })
      .catch(() => !cancelled && setModel(null));
    setPred(null);
    return () => {
      cancelled = true;
    };
  }, [solver, source, doe?.status]);

  function poll(id: string) {
    timer.current = window.setTimeout(async () => {
      try {
        const d = await fetchCfdDoe(id);
        setDoe(d);
        if (d.status !== "done") poll(id);
        else void refreshDoes();
      } catch (e) {
        setError((e as Error).message);
      }
    }, pollMs);
  }

  async function startDoe() {
    setError(null);
    const ranges: Record<string, [number, number]> = {};
    for (const v of DOE_VARS) if (vars[v.key].on) ranges[v.key] = [num(vars[v.key].lo), num(vars[v.key].hi)];
    try {
      const d = await postCfdDoe({
        name: doeForm.name.trim() || null,
        template_params: {},
        ranges,
        n_samples: num(doeForm.n),
        mach: num(doeForm.mach),
        alpha_deg: num(doeForm.alpha),
        mesher: "snappy",
        tunnel: { upstream: 3, downstream: 6, lateral: 3, base_cell_m: num(doeForm.base_cell) },
        snappy: { surface_level_min: num(doeForm.lmin), surface_level_max: num(doeForm.lmax), feature_level: num(doeForm.lmax), wake_level: 0, n_layers: 0, stl_size_mm: num(doeForm.stl) },
        solve: { solver, iterations: num(doeForm.iterations), relax_u: num(doeForm.relax_u), relax_other: num(doeForm.relax_other), cg_mm: num(doeForm.cg) },
      });
      setDoe(d);
      poll(d.doe_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function openDoe(id: string) {
    try {
      const d = await fetchCfdDoe(id);
      setDoe(d);
      if (d.status !== "done") poll(id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function train() {
    setBusy(true);
    setError(null);
    try {
      const m = await trainCfdModel({ application: solver, doe_id: source });
      setModel(m);
      setInputs(Object.fromEntries(m.feature_keys.map((k) => [k, String(+((m.bounds[k][0] + m.bounds[k][1]) / 2).toPrecision(4))])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function predict() {
    if (!model) return;
    setError(null);
    try {
      setPred(await predictCfd({ application: solver, inputs: Object.fromEntries(model.feature_keys.map((k) => [k, num(inputs[k] ?? "")])) }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const running = !!doe && doe.status !== "done";
  const nVars = DOE_VARS.filter((v) => vars[v.key].on).length;
  const finished = doe?.samples.filter((s) => s.status === "solved" || s.status === "failed").length ?? 0;

  return (
    <div className="crash-ml-stage" data-testid="cfd-ml-stage">
      <section className="crash-ml-card">
        <div className="crash-ml-head">
          <span className="ml-k">2.9 · DOE</span>
          <span className="ml-h">Roket CFD tasarım taraması</span>
        </div>
        <p className="crash-behavior-hint">
          Her örnek: roket şablonundan geometri, ardından tünel mesh'i (snappyHexMesh) ve roket koşusu. Örnekler sırayla koşar; değişkenler LHS ile
          örneklenir. Seçilmeyen şablon parametreleri varsayılan değerinde kalır.
        </p>
        <table className="cfd-table" aria-label="DOE değişkenleri">
          <thead>
            <tr><th /><th>Değişken</th><th>Alt</th><th>Üst</th></tr>
          </thead>
          <tbody>
            {DOE_VARS.map((v) => (
              <tr key={v.key}>
                <td>
                  <input type="checkbox" aria-label={`Tara ${v.key}`} checked={vars[v.key].on} disabled={running} onChange={(e) => setVars((s) => ({ ...s, [v.key]: { ...s[v.key], on: e.target.checked } }))} />
                </td>
                <td>{v.label}{v.unit ? ` (${v.unit})` : ""}</td>
                <td><input aria-label={`${v.key} alt`} value={vars[v.key].lo} disabled={running || !vars[v.key].on} onChange={(e) => setVars((s) => ({ ...s, [v.key]: { ...s[v.key], lo: e.target.value } }))} /></td>
                <td><input aria-label={`${v.key} üst`} value={vars[v.key].hi} disabled={running || !vars[v.key].on} onChange={(e) => setVars((s) => ({ ...s, [v.key]: { ...s[v.key], hi: e.target.value } }))} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="crash-expert-grid cols-3">
          <Num label="Örnek sayısı" value={doeForm.n} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, n: v }))} />
          {!vars.mach.on && <Num label="Sabit Mach" value={doeForm.mach} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, mach: v }))} />}
          {!vars.alpha_deg.on && <Num label="Sabit α" unit="°" value={doeForm.alpha} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, alpha: v }))} />}
          <Num label="Ağırlık merkezi" unit="mm" value={doeForm.cg} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, cg: v }))} />
          <Num label="Taban hücre" unit="m" value={doeForm.base_cell} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, base_cell: v }))} />
          <Num label="Yüzey seviyesi min" value={doeForm.lmin} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, lmin: v }))} />
          <Num label="Yüzey seviyesi max" value={doeForm.lmax} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, lmax: v }))} />
          <Num label="STL üçgen boyu" unit="mm" value={doeForm.stl} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, stl: v }))} />
          <Num label="İterasyon" value={doeForm.iterations} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, iterations: v }))} />
          <Num label="Gevşetme U" value={doeForm.relax_u} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, relax_u: v }))} />
          <Num label="Gevşetme diğer" value={doeForm.relax_other} disabled={running} onChange={(v) => setDoeForm((f) => ({ ...f, relax_other: v }))} />
        </div>
        <div className="crash-doe-field">
          <span className="ml-k">Çözücü</span>
          <span className="doe-seg" role="group" aria-label="Çözücü">
            {SOLVERS.map((s) => (
              <button key={s} type="button" className={solver === s ? "doe-seg-opt active" : "doe-seg-opt"} aria-pressed={solver === s} disabled={running} onClick={() => setSolver(s)}>
                {s}
              </button>
            ))}
          </span>
        </div>
        <label className="crash-unit-field wide">
          <span>DOE adı</span>
          <span className="crash-unit-box">
            <input aria-label="DOE adı" value={doeForm.name} disabled={running} placeholder="isteğe bağlı" onChange={(e) => setDoeForm((f) => ({ ...f, name: e.target.value }))} />
          </span>
        </label>
        <button type="button" className="doe-btn" disabled={running || nVars === 0} onClick={() => void startDoe()}>
          {running ? `Koşuyor… ${finished} / ${doe?.samples.length}` : `DOE başlat (${num(doeForm.n)} örnek × ${nVars} değişken)`}
        </button>
        {does.length > 0 && (
          <label className="crash-ml-select">
            <span className="ml-k">Önceki DOE'ler</span>
            <select aria-label="Önceki DOE" value={doe?.doe_id ?? ""} onChange={(e) => e.target.value && void openDoe(e.target.value)}>
              <option value="">—</option>
              {does.map((d) => (
                <option key={d.doe_id} value={d.doe_id}>
                  {d.name ?? d.doe_id.slice(0, 8)} · {d.solver} · {d.n_samples} örnek · {d.message ?? d.status}
                </option>
              ))}
            </select>
          </label>
        )}
        {doe && (
          <table className="cfd-table" data-testid="cfd-doe-samples">
            <thead>
              <tr><th>#</th><th>Parametreler</th><th>Mach</th><th>α</th><th>Hücre</th><th>Durum</th><th>CD</th><th>CN</th><th>x_cp (mm)</th></tr>
            </thead>
            <tbody>
              {doe.samples.map((s) => (
                <tr key={s.index}>
                  <td>{s.index + 1}</td>
                  <td>{Object.entries(s.template_params).map(([k, v]) => `${k} ${v}`).join(" · ") || "varsayılan"}</td>
                  <td>{s.mach.toFixed(3)}</td>
                  <td>{s.alpha_deg.toFixed(2)}</td>
                  <td>{s.cells ?? "—"}</td>
                  <td title={s.message}>{s.status}</td>
                  <td>{fmtNum(s.aero?.CD ?? null)}</td>
                  <td>{fmtNum(s.aero?.CN ?? null)}</td>
                  <td>{typeof s.aero?.x_cp_m === "number" ? fmtNum(s.aero.x_cp_m * 1000) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {doe?.message && <p className="crash-behavior-hint" data-testid="cfd-doe-status">{doe.message}</p>}
      </section>

      <section className="crash-ml-card">
        <div className="crash-ml-head">
          <span className="ml-k">2.9 · Model</span>
          <span className="ml-h">Vekil model (Random Forest, K-fold CV)</span>
        </div>
        <div className="crash-ml-row">
          <label className="crash-ml-select">
            <span className="ml-k">Çözücü</span>
            <select aria-label="Model çözücüsü" value={solver} onChange={(e) => setSolver(e.target.value as CfdSolver)}>
              {SOLVERS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="crash-ml-select">
            <span className="ml-k">Kaynak</span>
            <select aria-label="Kaynak" value={source ?? ""} onChange={(e) => setSource(e.target.value || null)}>
              <option value="">Tüm çözülmüş roket koşuları</option>
              {does.filter((d) => d.solver === solver).map((d) => (
                <option key={d.doe_id} value={d.doe_id}>DOE {d.name ?? d.doe_id.slice(0, 8)} · {d.n_samples} örnek</option>
              ))}
            </select>
          </label>
        </div>
        {corpus && (
          <p className="crash-behavior-hint" data-testid="cfd-corpus">
            {corpus.n_runs} koşu · girdiler: {corpus.features.join(", ") || "—"}
            {Object.keys(corpus.constant_features).length > 0 && ` · sabit: ${Object.entries(corpus.constant_features).map(([k, v]) => `${k}=${fmtNum(v)}`).join(", ")}`}
            {Object.keys(corpus.dropped).length > 0 && ` · dışarıda: ${Object.entries(corpus.dropped).map(([k, v]) => `${k} ${v}`).join(", ")}`}
          </p>
        )}
        <button type="button" className="doe-btn" disabled={busy || !corpus || corpus.n_runs === 0} onClick={() => void train()}>
          {busy ? "Eğitiliyor…" : "Modeli eğit"}
        </button>
        {model && (
          <table className="cfd-table" data-testid="cfd-model-cv">
            <thead>
              <tr><th>Hedef</th><th>n</th><th>R² (CV)</th><th>MAE</th><th>MAPE</th></tr>
            </thead>
            <tbody>
              {model.targets.map((t) => (
                <tr key={t.key}>
                  <td title={t.label}>{t.key}{t.unit !== "-" ? ` (${t.unit})` : ""}</td>
                  <td>{t.cv?.n ?? 0}</td>
                  <td>{t.cv?.skipped ? t.cv.skipped : fmtNum(t.cv?.r2)}</td>
                  <td>{fmtNum(t.cv?.mae)}</td>
                  <td>{typeof t.cv?.mape === "number" ? `%${(t.cv.mape * 100).toFixed(1)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {model && (
        <section className="crash-ml-card">
          <div className="crash-ml-head">
            <span className="ml-k">2.9 · Tahmin</span>
            <span className="ml-h">Vekil modelden katsayılar</span>
          </div>
          <div className="crash-expert-grid cols-3">
            {model.feature_keys.map((k) => (
              <Num key={k} label={`${k} [${fmtNum(model.bounds[k][0])} … ${fmtNum(model.bounds[k][1])}]`} value={inputs[k] ?? ""} onChange={(v) => setInputs((s) => ({ ...s, [k]: v }))} />
            ))}
          </div>
          <button type="button" className="doe-btn" onClick={() => void predict()}>Tahmin et</button>
          {pred && (
            <>
              <table className="cfd-table" data-testid="cfd-prediction">
                <tbody>
                  {Object.entries(pred.prediction).map(([k, v]) => (
                    <tr key={k}><th>{k}</th><td>{fmtNum(v)}</td></tr>
                  ))}
                </tbody>
              </table>
              {pred.out_of_domain.length > 0 && (
                <p className="crash-behavior-hint" data-testid="cfd-ood">Eğitim aralığı dışında: {pred.out_of_domain.join(", ")}</p>
              )}
            </>
          )}
        </section>
      )}
      {error && <p className="error-message" role="alert">{error}</p>}
    </div>
  );
}
