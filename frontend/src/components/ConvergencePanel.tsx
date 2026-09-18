/** Mesh yakınsama paneli (0.6.1).
 *
 * Tek geometri, artan çözünürlük: hedef skalerlerin düğüm sayısıyla nasıl
 * değiştiğini gösterir. DOE'den farkı geometrinin SABİT olması — DOE
 * geometriyi de tarar, orada ölçülen şey mesh hatası olmaz.
 *
 * Panel yorum/öneri yazmaz: ardışık sapma, en-inceye göre sapma ve (şablonda
 * varsa) analitik referans gösterilir. Hangi mesh'in yeterli olduğuna mühendis
 * bakar.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchMaterials, type Material } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import {
  parseNumberList,
  runConvergence,
  type ConvergenceReport,
} from "../api/convergence";
import { numberFieldsFromSchema, type JsonSchema } from "../templates/schemaForm";
import ConvergenceChart, { fmtCount, type ConvergencePoint } from "./ConvergenceChart";

/** Hedef anahtarı → başlık + birim. Backend `CONVERGENCE_TARGETS` ile aynı. */
const TARGET_META: Record<string, { label: string; unit: string }> = {
  max_displacement: { label: "Maks deplasman", unit: "mm" },
  max_von_mises: { label: "Maks von Mises", unit: "MPa" },
};

/** Kabadan inceye, her basamak bir öncekinin ~yarısı kadar eleman hacmi. */
const DEFAULT_RATIOS = "1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3";
const DEFAULT_SIZES = "15, 12, 10, 8, 6, 5, 4, 3";

function fmt(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
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
  const [steps, setSteps] = useState<string>(DEFAULT_RATIOS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ConvergenceReport | null>(null);

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

  // Şablon listesi geldiğinde / geometri panelinde şablon değiştiğinde seçimi
  // ona al ve parametreleri şablonun varsayılanlarına sıfırla.
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

  const parsedSteps = parseNumberList(steps);
  const canRatio = template?.has_characteristic_length !== false;
  const ready =
    !!template && materialId != null && parsedSteps.length >= 2 && !busy;

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
        ...(mode === "ratio"
          ? { element_ratios: parsedSteps }
          : { element_sizes: parsedSteps }),
        name: `yakinsama ${template.id}`,
      });
      setReport(result);
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

  const numberFields = template
    ? numberFieldsFromSchema(template.params_schema as JsonSchema)
    : [];

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.6 · Mesh</span>
      <h1>Yakınsama taraması</h1>
      <p className="lead">
        Geometri sabit, mesh incelir. Aynı katıyı verdiğin her eleman boyutunda
        yeniden mesh&apos;ler ve çözer; hedeflerin düğüm sayısıyla nasıl
        değiştiğini gösterir. DOE aralığını seçmeden önce hangi çözünürlük
        bandının kararlı olduğunu burada ölçersin — <code>element_size</code>{" "}
        surrogate&apos;in girdi vektöründe, yakınsamamış bir bantta toplanan veri
        modele ayrıklaştırma hatasını fizik diye öğretir.
      </p>
      <p className="lead">
        Tarama solver&apos;ı gerçekten çalıştırır ve senkron bekler; 8 basamaklı
        bir kiriş taraması referans makinede ~100 saniye sürdü. Bir basamak
        patlarsa tarama durmaz, o satır <code>failed</code> kalır.
      </p>

      <div className="doe-fields">
        <label className="mesh-field">
          <span>Şablon</span>
          <select
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
        </label>

        <label className="mesh-field">
          <span>Malzeme</span>
          <select
            value={materialId ?? ""}
            disabled={busy}
            onChange={(e) => setMaterialId(Number(e.target.value))}
          >
            {materials.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>

        {numberFields.map((f) => (
          <label className="mesh-field" key={f.name}>
            <span>
              {f.symbol ? `${f.symbol} · ` : ""}
              {f.label}
              {f.unit ? ` (${f.unit})` : ""}
            </span>
            <input
              type="number"
              step="any"
              /* Şablon seçimi ile `params`'ı dolduran efekt arasında bir kare
                 fark var; fallback olmadan alanlar o karede boş görünüyor. */
              value={params[f.name] ?? String(f.defaultValue)}
              disabled={busy}
              onChange={(e) => setParams((p) => ({ ...p, [f.name]: e.target.value }))}
            />
          </label>
        ))}

        <label className="mesh-field">
          <span>Basamak tipi</span>
          <select
            value={mode}
            disabled={busy || !canRatio}
            onChange={(e) => {
              const next = e.target.value as "ratio" | "mm";
              setMode(next);
              setSteps(next === "ratio" ? DEFAULT_RATIOS : DEFAULT_SIZES);
            }}
          >
            <option value="ratio">oran (es / karakteristik uzunluk)</option>
            <option value="mm">mutlak (mm)</option>
          </select>
        </label>

        <label className="mesh-field convergence-steps">
          <span>Basamaklar {mode === "ratio" ? "(oran)" : "(mm)"}</span>
          <input
            type="text"
            value={steps}
            disabled={busy}
            onChange={(e) => setSteps(e.target.value)}
          />
        </label>
      </div>

      <div className="doe-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={!ready}
          onClick={() => void handleRun()}
        >
          {busy ? `Taranıyor… (${parsedSteps.length} basamak)` : "Taramayı başlat"}
        </button>
        <span className="filename">
          {parsedSteps.length >= 2
            ? `${parsedSteps.length} basamak · kabadan inceye`
            : "En az 2 basamak gerekir."}
        </span>
      </div>

      {error && <p className="dataset-error">{error}</p>}

      {report && (
        <div className="convergence-results">
          <p className="filename">
            {report.n_solved}/{report.n_steps} basamak çözüldü · geometri #
            {report.geometry_id} · {report.material.name}
          </p>

          <div className="convergence-charts">
            {targetKeys.map((key) => (
              <ConvergenceChart
                key={key}
                title={TARGET_META[key]?.label ?? key}
                unit={TARGET_META[key]?.unit ?? ""}
                points={pointsFor(key)}
                analytic={analyticByKey[key] ?? null}
              />
            ))}
          </div>

          <ul className="convergence-summary">
            {targetKeys.map((key) => {
              const s = report.summary[key];
              const meta = TARGET_META[key] ?? { label: key, unit: "" };
              return (
                <li key={key}>
                  <strong>{meta.label}:</strong> en ince mesh {fmt(s?.finest)} {meta.unit}
                  {s?.finest_node_count != null &&
                    ` (${fmtCount(s.finest_node_count)} düğüm)`}{" "}
                  · son iki basamak arası {fmtPct(s?.last_step_delta_pct)}
                  {analyticByKey[key] != null &&
                    ` · analitik ${fmt(analyticByKey[key])} ${meta.unit}`}
                </li>
              );
            })}
          </ul>

          <div className="doe-table-scroll">
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
        </div>
      )}
    </div>
  );
}
