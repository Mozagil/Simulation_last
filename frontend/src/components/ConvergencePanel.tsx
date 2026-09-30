/** Mesh yakınsama aşaması (0.6.1) — Claude Design "ML Studio 1a".
 *
 * Tek geometri, artan çözünürlük: hedef skalerlerin düğüm sayısıyla nasıl
 * değiştiğini gösterir. DOE'den farkı geometrinin SABİT olması — DOE
 * geometriyi de tarar, orada ölçülen şey mesh hatası olmaz.
 *
 * Sol pano: sabit geometri kartları, malzeme çipleri, basamak karoları
 * (Oran / Mutlak mm anahtarı, + Basamak, Varsayılana dön), alt şerit.
 * Sağ pano: iki yakınsama kartı (en ince / son iki basamak / analitiğe göre),
 * basamak başına Δ karoları, ayrıntı tablosu.
 *
 * Panel yorum/öneri yazmaz: ardışık sapma, en-inceye göre sapma ve (şablonda
 * varsa) analitik referans gösterilir. "Kararlı bant" gibi bir eşik çizmez;
 * hangi mesh'in yeterli olduğuna mühendis bakar.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchMaterials, type Material } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import { runConvergence, type ConvergenceReport } from "../api/convergence";
import { numberFieldsFromSchema, type JsonSchema } from "../templates/schemaForm";
import ConvergenceChart, {
  fmtCount,
  fmtCountShort,
  fmtSignedPct,
  niceValue,
  type ConvergencePoint,
} from "./ConvergenceChart";

/** Hedef anahtarı → başlık + birim. Backend `CONVERGENCE_TARGETS` ile aynı. */
const TARGET_META: Record<string, { label: string; unit: string }> = {
  max_displacement: { label: "Maks deplasman", unit: "mm" },
  max_von_mises: { label: "Maks von Mises", unit: "MPa" },
};

/** Kabadan inceye, her basamak bir öncekinin ~yarısı kadar eleman hacmi. */
const DEFAULT_RATIOS = ["1.5", "1.2", "1.0", "0.8", "0.6", "0.5", "0.4", "0.3"];
const DEFAULT_SIZES = ["15", "12", "10", "8", "6", "5", "4", "3"];

function fmt(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function parseSteps(steps: string[]): number[] {
  return steps.map((s) => Number(s.trim())).filter((n) => Number.isFinite(n) && n > 0);
}

interface Props {
  /** Geometri panelinde seçili şablon; panel açılırken ona geçer. */
  templateId?: string | null;
}

export default function ConvergencePanel({ templateId }: Props) {
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [materialId, setMaterialId] = useState<number | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"ratio" | "mm">("ratio");
  const [steps, setSteps] = useState<string[]>(DEFAULT_RATIOS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ConvergenceReport | null>(null);
  const [tableOpen, setTableOpen] = useState(false);

  const template = useMemo(
    () => templates.find((t) => t.id === selectedTemplate) ?? null,
    [templates, selectedTemplate],
  );

  useEffect(() => {
    fetchTemplates()
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : "Şablonlar alınamadı."));
    fetchMaterials()
      .then((list) => {
        setMaterials(list);
        if (list.length) setMaterialId(list[0].id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Malzemeler alınamadı."));
  }, []);

  // Şablon listesi geldiğinde / stüdyoda şablon değiştiğinde seçimi ona al
  // ve parametreleri şablonun varsayılanlarına sıfırla.
  useEffect(() => {
    if (!templates.length) return;
    const wanted = templates.find((t) => t.id === templateId) ?? templates[0];
    setSelectedTemplate(wanted.id);
  }, [templates, templateId]);

  useEffect(() => {
    if (!template) return;
    const fields = numberFieldsFromSchema(template.params_schema as JsonSchema);
    setParams(Object.fromEntries(fields.map((f) => [f.name, String(f.defaultValue)])));
    const canRatio = template.has_characteristic_length !== false;
    setMode(canRatio ? "ratio" : "mm");
    setSteps(canRatio ? DEFAULT_RATIOS : DEFAULT_SIZES);
    setReport(null);
  }, [template]);

  const parsedSteps = parseSteps(steps);
  const canRatio = template?.has_characteristic_length !== false;
  const ready = !!template && materialId != null && parsedSteps.length >= 2 && !busy;

  function switchMode(next: "ratio" | "mm") {
    if (next === mode) return;
    setMode(next);
    setSteps(next === "ratio" ? DEFAULT_RATIOS : DEFAULT_SIZES);
  }

  function addStep() {
    const last = Number(steps[steps.length - 1]);
    const next = Number.isFinite(last) && last > 0 ? Number((last * 0.8).toPrecision(2)) : 1;
    setSteps((s) => [...s, String(next)]);
  }

  async function handleRun() {
    if (!template || materialId == null) return;
    setBusy(true);
    setError(null);
    try {
      const numericParams: Record<string, number> = {};
      for (const [k, v] of Object.entries(params)) {
        const n = Number(v);
        if (Number.isFinite(n)) numericParams[k] = n;
      }
      const result = await runConvergence({
        template_id: template.id,
        params: numericParams,
        material_id: materialId,
        ...(mode === "ratio" ? { element_ratios: parsedSteps } : { element_sizes: parsedSteps }),
        name: `yakinsama ${template.id}`,
      });
      setReport(result);
      setTableOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yakınsama taraması başarısız.");
    } finally {
      setBusy(false);
    }
  }

  /** Analitik referansı ilk çözülen satırdan al — geometri sabit olduğu için
   * tüm basamaklarda aynı. */
  const analyticByKey = useMemo(() => {
    const out: Record<string, number> = {};
    for (const row of report?.rows ?? []) {
      if (!row.analytic || row.analytic.skipped) continue;
      for (const m of row.analytic.metrics) out[m.key] = m.analytic;
      break;
    }
    return out;
  }, [report]);

  const targetKeys = report?.targets ?? [];
  // Karolarda gösterilecek hedef: von Mises varsa o (mesh'e en duyarlı), yoksa ilki.
  const tileKey = targetKeys.includes("max_von_mises") ? "max_von_mises" : targetKeys[0];

  function pointsFor(key: string): ConvergencePoint[] {
    return (report?.rows ?? [])
      .filter((r) => r.status === "solved" && r.node_count != null)
      .map((r) => ({
        nodeCount: Number(r.node_count),
        value: Number(r.targets[key]?.value),
        elementSize: r.element_size,
      }))
      .filter((p) => Number.isFinite(p.value));
  }

  const numberFields = template ? numberFieldsFromSchema(template.params_schema as JsonSchema) : [];
  const maxAbsDelta = Math.max(
    1e-9,
    ...(report?.rows ?? []).map((r) => Math.abs(r.targets[tileKey]?.delta_prev_pct ?? 0)),
  );

  return (
    <div className="doe-stage cv-stage" data-testid="convergence-stage">
      {/* ── Sol pano ─────────────────────────────────────────────── */}
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">0.6.1 · Mesh</span>
            <span className="ml-h">Yakınsama taraması</span>
          </span>
          <span className="doe-phead-hint">
            Geometri sabit
            <br />
            mesh incelir
          </span>
        </div>
        <div className="doe-pane-body cv-body">
          <div className="ds-section">
            <span className="cv-row">
              <span className="ml-k">Sabit geometri</span>
              <select
                className="cv-template"
                aria-label="Şablon"
                value={selectedTemplate}
                disabled={busy}
                onChange={(e) => setSelectedTemplate(e.target.value)}
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </span>
            <div className="cv-params">
              {numberFields.map((f) => (
                <label className="cv-param" key={f.name}>
                  <span className="cv-param-head">
                    {f.symbol ? <em className="doe-line-sym cv-sym">{f.symbol}</em> : null}
                    <span className="ds-sb">{f.label}</span>
                  </span>
                  <span className="cv-param-val">
                    <input
                      type="number"
                      step="any"
                      aria-label={`${f.symbol ? `${f.symbol} · ` : ""}${f.label}`}
                      /* Şablon seçimi ile `params`'ı dolduran efekt arasında bir kare
                         fark var; fallback olmadan alanlar o karede boş görünüyor. */
                      value={params[f.name] ?? String(f.defaultValue)}
                      disabled={busy}
                      onChange={(e) => setParams((p) => ({ ...p, [f.name]: e.target.value }))}
                    />
                    {f.unit ? <span className="ds-sb">{f.unit}</span> : null}
                  </span>
                </label>
              ))}
            </div>
            <span className="cv-row">
              <span className="ml-k cv-k-70">Malzeme</span>
              <span className="doe-chips" role="group" aria-label="Malzeme">
                {materials.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={m.id === materialId ? "doe-chip active" : "doe-chip"}
                    aria-pressed={m.id === materialId}
                    disabled={busy}
                    onClick={() => setMaterialId(m.id)}
                  >
                    {m.name}
                  </button>
                ))}
              </span>
            </span>
          </div>

          <div className="ds-section">
            <span className="cv-row">
              <span className="ml-k">Basamaklar</span>
              <span className="doe-seg cv-seg" role="group" aria-label="Basamak tipi">
                <button
                  type="button"
                  className={mode === "ratio" ? "doe-seg-opt active" : "doe-seg-opt"}
                  aria-pressed={mode === "ratio"}
                  disabled={busy || !canRatio}
                  onClick={() => switchMode("ratio")}
                >
                  Oran · es/t
                </button>
                <button
                  type="button"
                  className={mode === "mm" ? "doe-seg-opt active" : "doe-seg-opt"}
                  aria-pressed={mode === "mm"}
                  disabled={busy}
                  onClick={() => switchMode("mm")}
                >
                  Mutlak mm
                </button>
              </span>
            </span>
            <div className="cv-steps" role="group" aria-label="Basamaklar">
              {steps.map((s, i) => {
                const n = Number(s);
                const ok = Number.isFinite(n) && n > 0;
                const rel = ok ? Math.min(1, n / Math.max(...parsedSteps, 1e-9)) : 0;
                const rowRes = report?.rows[i];
                return (
                  <span className={ok ? "cv-step" : "cv-step cv-step-bad"} key={i}>
                    <span
                      className="cv-step-box"
                      style={{ width: `${6 + rel * 12}px`, height: `${6 + rel * 12}px` }}
                      aria-hidden="true"
                    />
                    <input
                      className="cv-step-input"
                      aria-label={`Basamak ${i + 1}`}
                      value={s}
                      disabled={busy}
                      onChange={(e) => setSteps((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                    />
                    <span className="ds-sb cv-step-sub">
                      {rowRes && rowRes.status === "solved"
                        ? `${niceValue(rowRes.element_size)} mm`
                        : mode === "ratio"
                          ? "× t"
                          : "mm"}
                    </span>
                    <button
                      type="button"
                      className="cv-step-x"
                      aria-label={`Basamak ${i + 1} sil`}
                      disabled={busy || steps.length <= 2}
                      onClick={() => setSteps((prev) => prev.filter((_, j) => j !== i))}
                    >
                      ×
                    </button>
                  </span>
                );
              })}
            </div>
            <span className="cv-axis ds-sb">
              <span>← kaba</span>
              <span>
                {parsedSteps.length >= 2
                  ? `${parsedSteps.length} basamak · ${mode === "ratio" ? "eleman = oran × karakteristik uzunluk" : "eleman boyutu mm"}`
                  : "En az 2 basamak gerekir."}
              </span>
              <span>ince →</span>
            </span>
            <span className="cv-row cv-row-tight">
              <button type="button" className="doe-btn doe-btn-ghost ds-ghost cv-ghost" disabled={busy} onClick={addStep}>
                + Basamak
              </button>
              <button
                type="button"
                className="doe-btn doe-btn-ghost ds-ghost cv-ghost"
                disabled={busy}
                onClick={() => setSteps(mode === "ratio" ? DEFAULT_RATIOS : DEFAULT_SIZES)}
              >
                Varsayılana dön
              </button>
            </span>
          </div>

          <div className="cv-note">
            <span className="ds-sb ds-note">
              DOE aralığını seçmeden önce hangi çözünürlük bandının kararlı olduğunu burada ölçün.
              Eleman boyutu surrogate&apos;in girdisinde; yakınsamamış bantta toplanan veri modele
              ayrıklaştırma hatasını fizik diye öğretir.
            </span>
          </div>
        </div>
        <div className="doe-pfoot">
          <span className="ds-sb">Solver gerçekten çalışır · 8 basamak ≈ 100 s · patlayan basamak atlanır</span>
          <button
            type="button"
            className="doe-btn doe-btn-primary cv-run"
            disabled={!ready}
            onClick={() => void handleRun()}
          >
            {busy ? `Taranıyor… (${parsedSteps.length} basamak)` : "Taramayı başlat"}
          </button>
        </div>
      </div>

      {/* ── Sağ pano ─────────────────────────────────────────────── */}
      <div className="doe-pane-r cv-right">
        {error && <p className="dataset-error">{error}</p>}
        {!report && !error && (
          <>
            <span className="doe-phead-title">
              <span className="ml-k">Tarama yok</span>
              <span className="ml-h">Hedefler düğüm sayısıyla</span>
            </span>
            <p className="doe-empty">
              {busy
                ? "Taranıyor — her basamak yeniden mesh'lenip çözülüyor."
                : "Soldan geometriyi ve basamakları verip \"Taramayı başlat\"."}
            </p>
          </>
        )}
        {report && (
          <>
            <div className="doe-phead-r">
              <span className="doe-phead-title">
                <span className="ml-k">
                  {report.n_solved}/{report.n_steps} basamak çözüldü · geometri #{report.geometry_id} ·{" "}
                  {report.material.name}
                </span>
                <span className="ml-h">Hedefler düğüm sayısıyla</span>
              </span>
              <button
                type="button"
                className="doe-btn doe-btn-ghost"
                onClick={() => setTableOpen((v) => !v)}
              >
                {tableOpen ? "Tabloyu kapat" : "Tabloyu aç"}
              </button>
            </div>

            <div className="cv-cards">
              {targetKeys.map((key) => (
                <ConvergenceChart
                  key={key}
                  title={TARGET_META[key]?.label ?? key}
                  unit={TARGET_META[key]?.unit ?? ""}
                  points={pointsFor(key)}
                  analytic={analyticByKey[key] ?? null}
                  lastStepDeltaPct={report.summary[key]?.last_step_delta_pct}
                />
              ))}
            </div>

            {tileKey && (
              <div className="ds-section">
                <span className="ml-k">
                  Basamak başına · {TARGET_META[tileKey]?.label ?? tileKey} · Δ önceki basamağa göre
                </span>
                <div className="cv-tiles" data-testid="step-tiles">
                  {report.rows.map((row) => {
                    const t = row.targets[tileKey];
                    const d = t?.delta_prev_pct ?? null;
                    const w = d == null ? 0 : (Math.abs(d) / maxAbsDelta) * 100;
                    return (
                      <span className={row.status === "solved" ? "cv-tile" : "cv-tile cv-tile-failed"} key={row.index}>
                        <span className="cv-tile-head">
                          <strong>{row.ratio == null ? niceValue(row.element_size) : row.ratio.toFixed(1)}</strong>
                          <span className="ds-sb">{fmtCountShort(row.node_count)}</span>
                        </span>
                        <span className="cv-tile-val">
                          {row.status === "solved" && t?.value != null
                            ? `${niceValue(t.value)} ${TARGET_META[tileKey]?.unit ?? ""}`
                            : row.status}
                        </span>
                        <span className="cv-tile-bar" aria-hidden="true">
                          <span style={{ width: `${w}%` }} />
                        </span>
                        <span className="cv-tile-delta">{fmtSignedPct(d)}</span>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {tableOpen && (
              <div className="doe-table-scroll convergence-results">
                <table className="doe-table">
                  <thead>
                    <tr>
                      <th>es (mm)</th>
                      <th>oran</th>
                      <th>düğüm</th>
                      {targetKeys.map((key) => (
                        <th key={key} colSpan={3}>
                          {TARGET_META[key]?.label ?? key}
                        </th>
                      ))}
                      <th>durum</th>
                    </tr>
                    <tr>
                      <th />
                      <th />
                      <th />
                      {targetKeys.flatMap((key) => [
                        <th key={`${key}-v`}>değer</th>,
                        <th key={`${key}-p`}>Δönceki</th>,
                        <th key={`${key}-f`}>Δen ince</th>,
                      ])}
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((row) => (
                      <tr
                        key={row.index}
                        className={row.status === "solved" ? undefined : "doe-table-row-flagged"}
                      >
                        <td>{fmt(row.element_size, 2)}</td>
                        <td>{row.ratio == null ? "—" : fmt(row.ratio, 2)}</td>
                        <td>{fmtCount(row.node_count)}</td>
                        {targetKeys.flatMap((key) => {
                          const t = row.targets[key];
                          return [
                            <td key={`${key}-v`}>{fmt(t?.value)}</td>,
                            <td key={`${key}-p`}>{fmtPct(t?.delta_prev_pct)}</td>,
                            <td key={`${key}-f`}>{fmtPct(t?.delta_finest_pct)}</td>,
                          ];
                        })}
                        <td title={row.message ?? undefined}>{row.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
