/**
 * Crash DOE (1.19f-1) — ML Stüdyo / Crash / DOE aşaması.
 *
 * Durability DOE ekranının düzeni: sol pano tasarım uzayı, sağ pano çalışma
 * çipleri + örnek tablosu. Taban senaryo bir `/crash/scenario` gövdesidir
 * (JSON, şablon seçimi `template_id`'yi yazar); taranan alanlar noktalı yol +
 * [alt, üst]. Hangi alanın hangi aralıkta taranacağı mühendisin — öneri yok,
 * yol listesi yalnız yazım kolaylığı (datalist).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchCrashCatalog, type CrashCatalogEntry } from "../api/crash";
import {
  createCrashDoeStudy,
  fetchCrashDoeStudies,
  fetchCrashDoeStudy,
  resumeCrashDoeStudy,
  type CrashDoeStudyInfo,
} from "../api/crashMl";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import CrashDoeLive from "./CrashDoeLive";

/** Senaryo isteğinin sık taranan sayısal alanları (yazım kolaylığı). */
export const COMMON_PATHS = [
  "speed_m_s",
  "angle_deg",
  "t_end_ms",
  "thickness_mm",
  "element_size_mm",
  "drop_height_mm",
  "ball_total_mass_kg",
  "end_mass_kg",
  "model.sigma_y_pa",
  "model.harden_b_mpa",
  "model.harden_n",
];

interface VaryRow {
  path: string;
  lo: string;
  hi: string;
}

const RUNNING = new Set(["running", "pending"]);

function baseFor(templateId: string, prev: string): string {
  let obj: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(prev);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) obj = parsed;
  } catch {
    /* bozuk JSON: sıfırdan */
  }
  // Şablon değişince eski şablonun geometri parametreleri anlamsız.
  const { geometry: _g, ...rest } = obj;
  return JSON.stringify({ ...rest, template_id: templateId }, null, 2);
}

export function buildCrashDoeSpec(
  baseText: string,
  rows: VaryRow[],
  nSamples: string,
  seed: string,
  name: string,
) {
  let base: Record<string, unknown>;
  try {
    base = JSON.parse(baseText);
  } catch {
    throw new Error("Taban senaryo geçerli JSON değil.");
  }
  const vary: Record<string, [number, number]> = {};
  for (const r of rows) {
    const path = r.path.trim();
    if (!path) continue;
    const lo = Number(r.lo);
    const hi = Number(r.hi);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) throw new Error(`'${path}': sınırlar sayı olmalı.`);
    if (!(hi > lo)) throw new Error(`'${path}': üst sınır alttan büyük olmalı.`);
    vary[path] = [lo, hi];
  }
  if (Object.keys(vary).length === 0) throw new Error("En az bir taranan alan gerekli.");
  const n = Number(nSamples);
  if (!Number.isInteger(n) || n < 1 || n > 500) throw new Error("Örnek sayısı 1–500 tam sayı olmalı.");
  const s = Number(seed);
  if (!Number.isInteger(s)) throw new Error("Tohum tam sayı olmalı.");
  return { ...(name.trim() ? { name: name.trim() } : {}), base, vary, n_samples: n, seed: s };
}

function fmt(v: number): string {
  const a = Math.abs(v);
  return a !== 0 && (a >= 1e5 || a < 1e-2) ? v.toExponential(3) : v.toFixed(a >= 100 ? 1 : 3);
}

export default function CrashDoePanel() {
  const [entries, setEntries] = useState<CrashCatalogEntry[]>([]);
  const [templateIds, setTemplateIds] = useState<string[]>([]);
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [templateId, setTemplateId] = useState("crash_box_shell");
  const [baseText, setBaseText] = useState(baseFor("crash_box_shell", "{}"));
  const [rows, setRows] = useState<VaryRow[]>([{ path: "speed_m_s", lo: "5", hi: "15" }]);
  const [nSamples, setNSamples] = useState("20");
  const [seed, setSeed] = useState("1");
  const [name, setName] = useState("");
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
  }, [reload]);

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

  const pathOptions = useMemo(() => {
    const props = templates.find((t) => t.id === templateId)?.params_schema.properties ?? {};
    return [...Object.keys(props).map((k) => `geometry.${k}`), ...COMMON_PATHS];
  }, [templates, templateId]);

  function selectTemplate(tid: string) {
    setTemplateId(tid);
    setBaseText((prev) => baseFor(tid, prev));
    setRows((prev) => prev.filter((r) => !r.path.startsWith("geometry.")));
  }

  async function handleStart() {
    setError(null);
    setBusy(true);
    try {
      const st = await createCrashDoeStudy(buildCrashDoeSpec(baseText, rows, nSamples, seed, name));
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
            Taban senaryo sabit
            <br />
            taranan alan = LHS [alt, üst]
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

          <div className="crash-doe-field">
            <span className="ml-k">Taranan alanlar</span>
            <datalist id="crash-doe-paths">
              {pathOptions.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
            <div className="crash-doe-vary">
              <span className="crash-doe-vh">yol</span>
              <span className="crash-doe-vh">alt</span>
              <span className="crash-doe-vh">üst</span>
              <span />
              {rows.map((r, i) => (
                <VaryRowInputs
                  key={i}
                  row={r}
                  index={i}
                  disabled={busy}
                  onChange={(nr) => setRows((prev) => prev.map((x, j) => (j === i ? nr : x)))}
                  onRemove={() => setRows((prev) => prev.filter((_, j) => j !== i))}
                />
              ))}
            </div>
            <button
              type="button"
              className="doe-chip crash-doe-add"
              disabled={busy}
              onClick={() => setRows((prev) => [...prev, { path: "", lo: "", hi: "" }])}
            >
              + alan ekle
            </button>
          </div>

          <label className="crash-doe-field">
            <span className="ml-k">Taban senaryo · /crash/scenario gövdesi (JSON)</span>
            <textarea
              className="crash-doe-json"
              aria-label="Taban senaryo"
              spellCheck={false}
              value={baseText}
              disabled={busy}
              onChange={(e) => setBaseText(e.target.value)}
              rows={9}
            />
            <span className="crash-doe-sub">
              Boş alanlar senaryo varsayılanı. Kutunun durması için t_end_ms yeterli olmalı (aksi halde ezilme boş).
            </span>
          </label>
        </div>
        <div className="doe-pfoot">
          <label className="doe-pfoot-field">
            <span className="ml-k">Ad</span>
            <input
              className="doe-num crash-doe-name"
              aria-label="Çalışma adı"
              value={name}
              placeholder={templateId}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="doe-pfoot-field">
            <span className="ml-k">Örnek</span>
            <input
              className="doe-num"
              aria-label="Örnek sayısı"
              value={nSamples}
              disabled={busy}
              onChange={(e) => setNSamples(e.target.value)}
            />
          </label>
          <label className="doe-pfoot-field">
            <span className="ml-k">Tohum</span>
            <input
              className="doe-num"
              aria-label="Tohum"
              value={seed}
              disabled={busy}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="doe-btn doe-btn-primary"
            disabled={busy}
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

function VaryRowInputs({
  row,
  index,
  disabled,
  onChange,
  onRemove,
}: {
  row: VaryRow;
  index: number;
  disabled: boolean;
  onChange: (r: VaryRow) => void;
  onRemove: () => void;
}) {
  return (
    <>
      <input
        className="doe-num crash-doe-path"
        list="crash-doe-paths"
        aria-label={`Alan ${index + 1} yolu`}
        value={row.path}
        placeholder="geometry.wall"
        disabled={disabled}
        onChange={(e) => onChange({ ...row, path: e.target.value })}
      />
      <input
        className="doe-num"
        aria-label={`Alan ${index + 1} alt`}
        value={row.lo}
        disabled={disabled}
        onChange={(e) => onChange({ ...row, lo: e.target.value })}
      />
      <input
        className="doe-num"
        aria-label={`Alan ${index + 1} üst`}
        value={row.hi}
        disabled={disabled}
        onChange={(e) => onChange({ ...row, hi: e.target.value })}
      />
      <button
        type="button"
        className="crash-doe-x"
        aria-label={`Alan ${index + 1} sil`}
        disabled={disabled}
        onClick={onRemove}
      >
        ×
      </button>
    </>
  );
}
