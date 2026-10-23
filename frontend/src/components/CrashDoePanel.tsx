/**
 * Crash DOE (1.19f-1) — ML Stüdyo / Crash / DOE aşaması.
 *
 * Durability DOE ekranının düzeni: sol pano tasarım uzayı, sağ pano çalışma
 * çipleri + örnek tablosu. Taban senaryo bir `/crash/scenario` gövdesidir
 * (JSON, şablon seçimi `template_id`'yi yazar); taranan alanlar noktalı yol +
 * [alt, üst]. Hangi alanın hangi aralıkta taranacağı mühendisin — öneri yok,
 * yol listesi yalnız yazım kolaylığı (datalist).
 */
import { useCallback, useEffect, useState } from "react";
import { fetchCrashCatalog, type CrashCatalogEntry } from "../api/crash";
import {
  createCrashDoeStudy,
  fetchCrashDoeStudies,
  fetchCrashDoeStudy,
  resumeCrashDoeStudy,
  type CrashDoeStudyInfo,
} from "../api/crashMl";
import { fetchMaterials, type Material } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import CrashDoeLive from "./CrashDoeLive";
import CrashDoeSpecForm, {
  buildCrashDoeSpecFromForm,
  initialCrashDoeState,
  type CrashDoeFormState,
} from "./CrashDoeSpecForm";

const RUNNING = new Set(["running", "pending"]);

function fmt(v: number): string {
  const a = Math.abs(v);
  return a !== 0 && (a >= 1e5 || a < 1e-2) ? v.toExponential(3) : v.toFixed(a >= 100 ? 1 : 3);
}

export default function CrashDoePanel() {
  const [entries, setEntries] = useState<CrashCatalogEntry[]>([]);
  const [templateIds, setTemplateIds] = useState<string[]>([]);
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState("crash_box_shell");
  const [materials, setMaterials] = useState<Material[]>([]);
  const [form, setForm] = useState<CrashDoeFormState | null>(null);
  const [studies, setStudies] = useState<CrashDoeStudyInfo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CrashDoeStudyInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchCrashDoeStudies()
      .then(setStudies)
      .catch((e) => setError(e instanceof Error ? e.message : "Crash DOE listesi alınamadı."));
  }, []);

  useEffect(() => {
    reload();
    fetchCrashCatalog()
      .then((c) => {
        setEntries(c.entries);
        setTemplateIds(Object.keys(c.scenario_templates).sort());
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Crash kataloğu alınamadı."));
    fetchTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
    fetchMaterials()
      .then(setMaterials)
      .catch(() => setMaterials([]));
  }, [reload]);

  // Şablon (ya da şablon listesi) değişince form o şablonun parametrelerinden kurulur;
  // senaryo alanları, malzeme ve örnek/tohum korunur.
  const template = templates.find((t) => t.id === templateId) ?? null;
  useEffect(() => {
    if (template) setForm((prev) => initialCrashDoeState(template, prev ?? undefined));
  }, [template]);

  const selected = studies.find((s) => s.id === selectedId) ?? studies[0] ?? null;

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetchCrashDoeStudy(selected.id)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Çalışma alınamadı."));
    return () => {
      cancelled = true;
    };
  }, [selected?.id, selected?.status, selected?.counts]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!studies.some((s) => RUNNING.has(s.status))) return;
    const t = window.setInterval(reload, 5000);
    return () => window.clearInterval(t);
  }, [studies, reload]);

  const titleOf = useCallback(
    (tid: string) => entries.find((e) => e.template_id === tid && e.status === "ready")?.title ?? tid,
    [entries],
  );

  function selectTemplate(tid: string) {
    setTemplateId(tid);
  }

  async function handleStart() {
    setError(null);
    setBusy(true);
    try {
      if (!form) throw new Error("Şablon parametreleri henüz yüklenmedi.");
      const st = await createCrashDoeStudy(buildCrashDoeSpecFromForm(form));
      setSelectedId(st.id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "DOE başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResume(id: number) {
    setError(null);
    try {
      await resumeCrashDoeStudy(id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Devam ettirilemedi.");
    }
  }

  const paths = detail?.vary ? Object.keys(detail.vary) : [];
  const done = detail ? (detail.counts.solved ?? 0) + (detail.counts.rad_only ?? 0) : 0;
  const failed = detail?.counts.failed ?? 0;

  return (
    <div className="doe-stage" data-testid="crash-doe-stage">
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">1.19 · Crash DOE</span>
            <span className="ml-h">Tasarım uzayı</span>
          </span>
          <span className="doe-phead-hint">
            Açık bant = taranan aralık
            <br />
            ▼ = şablon varsayılanı
          </span>
        </div>
        <div className="doe-pane-body crash-doe-body">
          <div className="crash-doe-field">
            <span className="ml-k">Şablon</span>
            <span className="doe-chips" role="group" aria-label="Crash şablonu">
              {templateIds.map((tid) => (
                <button
                  key={tid}
                  type="button"
                  className={tid === templateId ? "doe-chip active" : "doe-chip"}
                  aria-pressed={tid === templateId}
                  title={titleOf(tid)}
                  disabled={busy}
                  onClick={() => selectTemplate(tid)}
                >
                  {tid.replace(/_shell$/, "")}
                </button>
              ))}
            </span>
            <span className="crash-doe-sub">{titleOf(templateId)}</span>
          </div>

          {form ? (
            <CrashDoeSpecForm template={template} materials={materials} state={form} busy={busy} onChange={setForm} />
          ) : (
            <p className="doe-empty">Şablon parametreleri yükleniyor…</p>
          )}
        </div>
        <div className="doe-pfoot">
          <label className="doe-pfoot-field">
            <span className="ml-k">Ad</span>
            <input
              className="doe-num crash-doe-name"
              aria-label="Çalışma adı"
              value={form?.name ?? ""}
              placeholder={templateId}
              disabled={busy || !form}
              onChange={(e) => form && setForm({ ...form, name: e.target.value })}
            />
          </label>
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
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy || !form}
            onClick={() => void handleStart()}
          >
            {busy ? "Örnekleniyor…" : "DOE başlat"}
          </button>
        </div>
      </div>

      <div className="doe-pane-r">
        {studies.length > 0 && (
          <div className="doe-study-chips" role="group" aria-label="Çalışma seç">
            <span className="ml-k">Çalışma</span>
            {studies.slice(0, 8).map((st) => (
              <button
                key={st.id}
                type="button"
                className={selected?.id === st.id ? "doe-chip active" : "doe-chip"}
                aria-pressed={selected?.id === st.id}
                title={`${st.name ?? st.template_id} · ${st.status} · ${st.n_cases} örnek`}
                onClick={() => setSelectedId(st.id)}
              >
                #{st.id}
                {RUNNING.has(st.status) ? " ●" : ""}
              </button>
            ))}
          </div>
        )}
        {studies.length === 0 && !error && (
          <p className="doe-empty">Henüz crash DOE çalışması yok. Soldan şablon ve aralıkları verip &quot;DOE başlat&quot;.</p>
        )}
        {detail && (
          <section className="crash-doe-study" aria-label="Çalışma ilerlemesi">
            <div className="crash-doe-shead">
              <span className="ml-h">
                #{detail.id} · {detail.name ?? detail.template_id}
              </span>
              <span className={`crash-doe-status s-${detail.status}`}>{detail.status}</span>
              {!RUNNING.has(detail.status) && done < detail.n_cases && (
                <button type="button" className="doe-btn doe-btn-secondary" onClick={() => void handleResume(detail.id)}>
                  Devam ettir ({detail.n_cases - done})
                </button>
              )}
            </div>
            <div className="crash-doe-progress" aria-label="İlerleme">
              <span style={{ width: `${(100 * done) / Math.max(detail.n_cases, 1)}%` }} />
              <span className="fail" style={{ width: `${(100 * failed) / Math.max(detail.n_cases, 1)}%` }} />
            </div>
            {/* 1.25a2 — çalışan örneğin canlı ilerlemesi (liste 5 s'de bir yenilenir; daha taze) */}
            <CrashDoeLive
              studyId={detail.id}
              jobId={(selected?.id === detail.id ? selected.current_job_id : detail.current_job_id) ?? null}
              caseIndex={(selected?.id === detail.id ? selected.current_case_index : detail.current_case_index) ?? null}
              nCases={detail.n_cases}
              studyRunning={RUNNING.has(detail.status)}
            />
            <div className="crash-doe-kv">
              <span>
                <span className="ml-k">Şablon</span> {detail.template_id}
              </span>
              <span>
                <span className="ml-k">Tohum</span> {detail.seed}
              </span>
              <span>
                <span className="ml-k">Biten</span> {done}/{detail.n_cases}
              </span>
              <span>
                <span className="ml-k">Hata</span> {failed}
              </span>
              {detail.message && <span className="crash-doe-sub">{detail.message}</span>}
            </div>
            <div className="doe-table-scroll crash-doe-table">
              <table className="doe-table">
                <thead>
                  <tr>
                    <th>#</th>
                    {paths.map((p) => (
                      <th key={p} title={`[${detail.vary?.[p].join(", ")}]`}>
                        {p}
                      </th>
                    ))}
                    <th>durum</th>
                    <th>koşu</th>
                    <th className="crash-doe-msg">mesaj</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.cases ?? []).map((c) => (
                    <tr key={c.id} className={c.status === "failed" ? "doe-table-row-flagged" : undefined}>
                      <td>{c.index}</td>
                      {paths.map((p) => (
                        <td key={p}>{c.values[p] !== undefined ? fmt(c.values[p]) : "—"}</td>
                      ))}
                      <td>{c.status}</td>
                      <td>{c.run_id ?? "—"}</td>
                      <td className="crash-doe-msg" title={c.message ?? ""}>
                        {c.message ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {error && <p className="dataset-error">{error}</p>}
      </div>
    </div>
  );
}
