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
import DoeDistribution from "./DoeDistribution";
import DoeSpecForm, {
  buildSpec,
  initialStateFor,
  type DoeFormState,
} from "./DoeSpecForm";

interface DoePanelProps {
  refreshKey?: number;
  /** Geometri panelinde seçilen şablon. Değişince DOE formu da ona geçer
   * (kullanıcı yine DOE tarafından değiştirebilir). Aralıklar sıfırlanır:
   * eski şablonun aralıkları yenisinde anlamsız. */
  templateId?: string | null;
  /** Tablodaki satıra tıklanınca o run'ı aç (Analiz Geçmişi ile aynı yol). */
  onOpenRun?: (runId: number) => void;
}

export default function DoePanel({ refreshKey, templateId, onOpenRun }: DoePanelProps) {
  const [studies, setStudies] = useState<DoeStudyInfo[]>([]);
  const [qualityById, setQualityById] = useState<Record<number, DoeQualityInfo>>({});
  // Sağ panoda tek çalışma görünür (varsayılan: en yeni). Sonuçları seçilince
  // çekilir; tablo ayrıca açılır — 200 satır varsayılan olarak kapalı.
  const [selectedStudyId, setSelectedStudyId] = useState<number | null>(null);
  const [openResults, setOpenResults] = useState<DoeResults | null>(null);
  const [resultsBusy, setResultsBusy] = useState<number | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [form, setForm] = useState<DoeFormState | null>(null);
  // Çoklu seçim: örnekler malzemelere dengeli dağılır (200 örnek + 2 malzeme
  // = 100/100). E model girdisinde olduğu için tek malzemeyle eğitilen
  // surrogate başka malzemeye genelleyemez.
  const [materialIds, setMaterialIds] = useState<number[]>([]);
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
        if (list.length) setMaterialIds([list[0].id]);
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
    if (materialIds.length === 0) {
      setError("En az bir malzeme seçilmeli.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const spec = buildSpec(form, template, materialIds, runSolver);
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

  // Dışarıdan gelen şablon seçimini izle. Kullanıcı DOE formundan başka bir
  // şablon seçerse ve dışarısı değişmezse ona dokunulmaz — `templateId`
  // değiştiği anda senkronlanır.
  useEffect(() => {
    if (!templateId || templates.length === 0) return;
    setForm((prev) => {
      if (prev?.templateId === templateId) return prev;
      const t = templates.find((x) => x.id === templateId);
      if (!t) return prev;
      return prev
        ? { ...initialStateFor(t), nSamples: prev.nSamples, seed: prev.seed }
        : initialStateFor(t);
    });
  }, [templateId, templates]);

  const templateName = templates.find((t) => t.id === form?.templateId)?.name ?? null;

  // Seçim yoksa en yeni çalışma; liste boşalırsa seçim düşer.
  const selectedStudy =
    studies.find((s) => s.id === selectedStudyId) ?? (studies.length > 0 ? studies[0] : null);

  useEffect(() => {
    if (!selectedStudy) {
      setOpenResults(null);
      return;
    }
    const id = selectedStudy.id;
    const status = selectedStudy.status;
    if (openResults?.study_id === id && status !== "running" && status !== "pending") return;
    let cancelled = false;
    setResultsBusy(id);
    fetchDoeResults(id)
      .then((r) => {
        if (!cancelled) setOpenResults(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Sonuç tablosu alınamadı.");
      })
      .finally(() => {
        if (!cancelled) setResultsBusy(null);
      });
    return () => {
      cancelled = true;
    };
    // openResults kasıtlı dışarıda: yeni sonucu set etmek efekti tekrar
    // tetiklememeli; koşullar id/status üzerinden.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStudy?.id, selectedStudy?.status]);

  async function handleQualitySet() {
    setBusy(true);
    setError(null);
    try {
      if (materialIds.length === 0) {
        throw new Error("En az bir malzeme seçilmeli.");
      }
      await startQualitySet({
        // Formda seçili şablonun referans seti — aralıklar şablona özgü ve
        // sabittir (formdaki aralıklar KULLANILMAZ; set karşılaştırılabilir
        // bir referans olmalı).
        template_id: form?.templateId,
        material_ids: materialIds,
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
    <div className="doe-stage" data-testid="doe-stage">
      {/* ── Sol pano: tasarım uzayı (ML Studio 1a) ─────────────────── */}
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">0.5 · DOE</span>
            <span className="ml-h">Tasarım uzayı</span>
          </span>
          <span className="doe-phead-hint">
            Açık bant = taranan aralık
            <br />▼ = şablon varsayılanı
          </span>
        </div>
        <div className="doe-pane-body">
          {form && (
            <DoeSpecForm templates={templates} state={form} busy={busy} onChange={setForm} />
          )}
          <div className="doe-material-row">
            <span className="ml-k">Malzeme</span>
            <span className="doe-chips">
              {materials.map((m) => {
                const on = materialIds.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    className={on ? "doe-chip active" : "doe-chip"}
                    aria-pressed={on}
                    disabled={busy}
                    onClick={() =>
                      setMaterialIds((prev) =>
                        on ? prev.filter((x) => x !== m.id) : [...prev, m.id],
                      )
                    }
                  >
                    {m.name}
                  </button>
                );
              })}
            </span>
            <span className="doe-material-hint">örnekler dengeli dağılır</span>
          </div>
        </div>
        <div className="doe-pfoot">
          <label className="doe-pfoot-field">
            <span className="ml-k">Örnek</span>
            <input
              className="doe-num"
              aria-label="Örnek sayısı"
              value={form?.nSamples ?? ""}
              disabled={busy || !form}
              onChange={(e) => form && setForm({ ...form, nSamples: e.target.value })}
            />
          </label>
          <label className="doe-pfoot-field">
            <span className="ml-k">Tohum</span>
            <input
              className="doe-num"
              aria-label="Tohum"
              value={form?.seed ?? ""}
              disabled={busy || !form}
              onChange={(e) => form && setForm({ ...form, seed: e.target.value })}
            />
          </label>
          <label className="doe-pfoot-check">
            <input
              type="checkbox"
              checked={runSolver}
              onChange={(e) => setRunSolver(e.target.checked)}
            />
            ccx çalıştır
          </label>
          <button
            type="button"
            className="doe-btn doe-btn-secondary"
            disabled={busy}
            title="Şablona özgü sabit aralıklarla 200 örnek, tohum 2026 — referans set; formdaki aralıklar kullanılmaz."
            onClick={() => void handleQualitySet()}
          >
            {templateName ? `200'lük kalite seti · ${templateName}` : "200'lük kalite seti"}
          </button>
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy}
            onClick={() => void handleStart()}
          >
            {busy ? "Çalışıyor…" : "DOE başlat"}
          </button>
        </div>
      </div>

      {/* ── Sağ pano: sonuç dağılımı (ML Studio 1a) ───────────────── */}
      <div className="doe-pane-r">
        {studies.length > 0 && (
          <div className="doe-study-chips" role="group" aria-label="Çalışma seç">
            <span className="ml-k">Çalışma</span>
            {studies.slice(0, 5).map((st) => {
              const on = selectedStudy?.id === st.id;
              return (
                <button
                  key={st.id}
                  type="button"
                  className={on ? "doe-chip active" : "doe-chip"}
                  aria-pressed={on}
                  title={`${st.template_id} · ${st.status} · ${st.n_cases} örnek`}
                  onClick={() => {
                    setSelectedStudyId(st.id);
                    setTableOpen(false);
                  }}
                >
                  #{st.id}
                  {st.status === "running" || st.status === "pending" ? " ●" : ""}
                </button>
              );
            })}
          </div>
        )}
        {studies.length === 0 && !error && (
          <p className="doe-empty">Henüz DOE çalışması yok. Soldan aralıkları verip &quot;DOE başlat&quot; ile başla.</p>
        )}
        {selectedStudy && (
          <DoeDistribution
            study={selectedStudy}
            quality={qualityById[selectedStudy.id] ?? null}
            results={openResults?.study_id === selectedStudy.id ? openResults : null}
            loading={resultsBusy === selectedStudy.id}
            tableOpen={tableOpen}
            onToggleTable={() => setTableOpen((v) => !v)}
            onOpenRun={onOpenRun}
          />
        )}
        {error && <p className="dataset-error">{error}</p>}
      </div>
    </div>
  );
}
