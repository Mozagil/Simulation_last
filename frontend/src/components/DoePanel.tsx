import { useCallback, useEffect, useState } from "react";
import { fetchMaterials, type Material } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import {
  createDoeStudy,
  fetchDoeQuality,
  fetchDoeResults,
  fetchDoeStudies,
  startQualitySet,
  type DoeQualityInfo,
  type DoeResults,
  type DoeStudyInfo,
} from "../api/doe";
import DoeResultsTable from "./DoeResultsTable";
import DoeSpecForm, {
  buildSpec,
  initialStateFor,
  type DoeFormState,
} from "./DoeSpecForm";

function formatCounts(counts: Record<string, number> | undefined): string {
  if (!counts) return "";
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}:${v}`)
    .join(" · ");
}

interface DoePanelProps {
  refreshKey?: number;
  /** Tablodaki satıra tıklanınca o run'ı aç (Analiz Geçmişi ile aynı yol). */
  onOpenRun?: (runId: number) => void;
}

export default function DoePanel({ refreshKey, onOpenRun }: DoePanelProps) {
  const [studies, setStudies] = useState<DoeStudyInfo[]>([]);
  const [qualityById, setQualityById] = useState<Record<number, DoeQualityInfo>>({});
  // Açık tablo: aynı anda tek çalışma; 200 satırlık tabloyu ikinci kez açmak
  // gereksiz yer kaplar.
  const [openResults, setOpenResults] = useState<DoeResults | null>(null);
  const [resultsBusy, setResultsBusy] = useState<number | null>(null);
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [form, setForm] = useState<DoeFormState | null>(null);
  const [materialId, setMaterialId] = useState<number | "">("");
  const [runSolver, setRunSolver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchDoeStudies()
      .then(setStudies)
      .catch((e) => setError(e instanceof Error ? e.message : "DOE listesi alınamadı."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  useEffect(() => {
    fetchTemplates()
      .then((list) => {
        setTemplates(list);
        if (list.length) setForm(initialStateFor(list[0]));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Şablonlar alınamadı."));
    fetchMaterials()
      .then((list) => {
        setMaterials(list);
        if (list.length) setMaterialId(list[0].id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Malzemeler alınamadı."));
  }, []);

  useEffect(() => {
    const running = studies.some((s) => s.status === "running" || s.status === "pending");
    if (!running) return;
    const t = window.setInterval(reload, 5000);
    return () => window.clearInterval(t);
  }, [studies, reload]);

  useEffect(() => {
    let cancelled = false;
    const ids = studies.slice(0, 5).map((s) => s.id);
    Promise.all(
      ids.map(async (id) => {
        try {
          const q = await fetchDoeQuality(id);
          return [id, q] as const;
        } catch {
          return null;
        }
      }),
    ).then((rows) => {
      if (cancelled) return;
      const next: Record<number, DoeQualityInfo> = {};
      for (const row of rows) {
        if (row) next[row[0]] = row[1];
      }
      setQualityById(next);
    });
    return () => {
      cancelled = true;
    };
  }, [studies]);

  async function handleStart() {
    const template = templates.find((t) => t.id === form?.templateId);
    if (!form || !template) return;
    if (materialId === "") {
      setError("Malzeme seçilmeli.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const spec = buildSpec(form, template, [materialId], runSolver);
      const study = await createDoeStudy(spec, true);
      // Örnekleme, şablonun geometrik kısıtlarını ihlal eden kombinasyonları
      // eler; istenenden az örnek çıkabilir — kullanıcı sessiz kalmasın.
      if (study.n_cases < spec.n_samples) {
        setError(
          `${spec.n_samples} örnek istendi, ${study.n_cases} üretildi — ` +
            "aralıklar şablonun geometrik kısıtlarıyla çelişiyor olabilir.",
        );
      }
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "DOE başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleResults(studyId: number) {
    if (openResults?.study_id === studyId) {
      setOpenResults(null);
      return;
    }
    setResultsBusy(studyId);
    setError(null);
    try {
      setOpenResults(await fetchDoeResults(studyId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sonuç tablosu alınamadı.");
    } finally {
      setResultsBusy(null);
    }
  }

  async function handleQualitySet() {
    setBusy(true);
    setError(null);
    try {
      if (materialId === "") {
        throw new Error("Malzeme seçilmeli.");
      }
      await startQualitySet({
        material_ids: [materialId],
        run_solver: runSolver,
        wait: false,
      });
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kalite seti başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.5 · DOE</span>
      <h1>Toplu tarama</h1>
      <p className="lead">
        Seçtiğin şablondan Latin Hypercube örnekler. Her parametreyi sabit
        tutabilir ya da aralık verip taratabilirsin. BC&apos;ler şablonun
        varsayılanlarından gelir ve isimli bölgelere bağlanır; bir örnek
        patlarsa diğerleri durmaz.
      </p>
      <p className="lead">
        Kalite seti: 200 ankastre kiriş, tohum 2026. L 450–700 mm, T 8–12 mm, W
        35–70 mm, eleman 6–14 mm, uç yükü −800…−200 N (−y). Tek malzeme, tek BC
        (ankastre + uç CLOAD). Kapalı form sapması ve kaba aykırı değerler
        sayılır; mesh/BC önerisi yok.
      </p>

      {form && (
        <DoeSpecForm templates={templates} state={form} busy={busy} onChange={setForm} />
      )}

      <div className="doe-fields">
        <label className="mesh-field">
          <span>Malzeme</span>
          <select
            value={materialId}
            disabled={busy || materials.length === 0}
            onChange={(e) => setMaterialId(e.target.value === "" ? "" : Number(e.target.value))}
          >
            {materials.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label className="mesh-field">
          <span>Örnek</span>
          <input
            value={form?.nSamples ?? ""}
            disabled={busy || !form}
            onChange={(e) => form && setForm({ ...form, nSamples: e.target.value })}
          />
        </label>
        <label className="mesh-field">
          <span>Tohum</span>
          <input
            value={form?.seed ?? ""}
            disabled={busy || !form}
            onChange={(e) => form && setForm({ ...form, seed: e.target.value })}
          />
        </label>
        <label className="dataset-filter">
          <input
            type="checkbox"
            checked={runSolver}
            onChange={(e) => setRunSolver(e.target.checked)}
          />
          ccx çalıştır
        </label>
      </div>

      <div className="doe-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={busy}
          onClick={() => void handleStart()}
        >
          {busy ? "Çalışıyor…" : "DOE başlat"}
        </button>
        <button
          type="button"
          className="material-assign-button"
          disabled={busy}
          onClick={() => void handleQualitySet()}
        >
          200&apos;lük kalite seti
        </button>
      </div>

      {studies.length > 0 && (
        <ul className="doe-study-list">
          {studies.slice(0, 5).map((st) => {
            const q = qualityById[st.id];
            return (
              <li key={st.id}>
                <strong>#{st.id}</strong> {st.status} · {st.n_cases} örnek
                {st.message ? ` · ${st.message}` : ""}
                {q ? (
                  <span className="doe-quality">
                    {" "}
                    · kalite ok:{q.n_ok}
                    {formatCounts(q.counts) ? ` · ${formatCounts(q.counts)}` : ""}
                  </span>
                ) : null}
                <button
                  type="button"
                  className="doe-results-toggle"
                  disabled={resultsBusy !== null}
                  onClick={() => void handleToggleResults(st.id)}
                >
                  {openResults?.study_id === st.id
                    ? "Tabloyu kapat"
                    : resultsBusy === st.id
                      ? "Yükleniyor…"
                      : "Sonuç tablosu"}
                </button>
                {openResults?.study_id === st.id && (
                  <DoeResultsTable results={openResults} onOpenRun={onOpenRun} />
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && <p className="dataset-error">{error}</p>}
    </div>
  );
}
