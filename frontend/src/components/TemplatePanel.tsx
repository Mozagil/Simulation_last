import { useEffect, useMemo, useState } from "react";
import {
  createGeometryFromTemplate,
  downloadGeometryStep,
  fetchTemplates,
  TemplateApiError,
  type CreateFromTemplateResponse,
  type GeometryTemplateInfo,
} from "../api/templates";
import {
  defaultsFromFields,
  enumFieldsFromSchema,
  numberFieldsFromSchema,
  parseParamInputs,
  type JsonSchema,
} from "../templates/schemaForm";
import TemplateLoadDialog, {
  applyLoadInputs,
  loadInputsFromBcs,
} from "./TemplateLoadDialog";
import TemplateSchematic from "./TemplateSchematic";

interface TemplatePanelProps {
  geometryId: number | null;
  geometryFilename: string | null;
  busy: boolean;
  onCreated: (result: CreateFromTemplateResponse) => Promise<void> | void;
}

export default function TemplatePanel({
  geometryId,
  geometryFilename,
  busy,
  onCreated,
}: TemplatePanelProps) {
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  // Onay penceresi: parametreler doğrulandıktan sonra açılır, kullanıcı yük
  // değerlerini girer. Geometri ancak onaydan sonra üretilir.
  const [pending, setPending] = useState<{ params: Record<string, number | string> } | null>(null);
  const [loadInputs, setLoadInputs] = useState<Record<string, string>>({});

  const selected = templates.find((t) => t.id === selectedId) ?? null;
  const fields = useMemo(
    () => (selected ? numberFieldsFromSchema(selected.params_schema as JsonSchema) : []),
    [selected],
  );
  const enums = useMemo(
    () => (selected ? enumFieldsFromSchema(selected.params_schema as JsonSchema) : []),
    [selected],
  );

  function fillDefaults(t: GeometryTemplateInfo) {
    const schema = t.params_schema as JsonSchema;
    const f = numberFieldsFromSchema(schema);
    const e = enumFieldsFromSchema(schema);
    const d = defaultsFromFields(f, e);
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(d)) next[k] = String(v);
    setInputs(next);
  }

  useEffect(() => {
    fetchTemplates()
      .then((list) => {
        setTemplates(list);
        if (list.length) {
          setSelectedId(list[0].id);
          fillDefaults(list[0]);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Şablonlar alınamadı."));
  }, []);

  function handleOpenDialog() {
    if (!selected) return;
    const parsed = parseParamInputs(inputs, enums.map((e) => e.name));
    if (typeof parsed === "string") {
      setError(parsed);
      return;
    }
    setError(null);
    setLoadInputs(loadInputsFromBcs(selected.default_bcs ?? []));
    setPending({ params: parsed });
  }

  async function handleConfirm() {
    if (!selected || !pending) return;
    // Önce girdileri doğrula: şablonun (id'siz) BC listesi üzerinde. Geometri
    // üretmeden hata vermek, yarım kayıt bırakmamak için.
    const check = applyLoadInputs(selected.default_bcs ?? [], loadInputs);
    if (typeof check === "string") {
      setError(check);
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const result = await createGeometryFromTemplate(selected.id, pending.params);
      // Sunucudan gelen BC'ler gerçek yüzey/kenar id'leriyle bağlı; kullanıcının
      // girdiği yük değerlerini bunların üzerine uygula (sıra aynı şablondan gelir).
      const bound = applyLoadInputs(result.default_bcs ?? [], loadInputs);
      await onCreated(
        typeof bound === "string" ? result : { ...result, default_bcs: bound },
      );
      setPending(null);
    } catch (e) {
      setError(e instanceof TemplateApiError ? e.message : "Şablon üretilemedi.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDownload() {
    if (geometryId == null) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadGeometryStep(geometryId, geometryFilename ?? `geometry-${geometryId}.step`);
    } catch (e) {
      setError(e instanceof TemplateApiError ? e.message : "STEP indirilemedi.");
    } finally {
      setDownloading(false);
    }
  }

  const disabled = busy || creating;

  return (
    <div className="template-panel">
      <p className="material-assignments-title">Şablondan üret</p>
      <p className="lead material-lead">Dosya yüklemeden parametrik geometri.</p>
      {selected && <TemplateSchematic templateId={selected.id} />}
      <label className="mesh-field">
        <span>Şablon</span>
        <select
          value={selectedId}
          disabled={disabled || templates.length === 0}
          onChange={(e) => {
            const id = e.target.value;
            setSelectedId(id);
            const t = templates.find((x) => x.id === id);
            if (t) fillDefaults(t);
          }}
        >
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      {selected && <p className="filename">{selected.description}</p>}
      {enums.map((f) => (
        <label key={f.name} className="mesh-field">
          <span>{f.label}</span>
          <select
            value={inputs[f.name] ?? f.defaultValue}
            disabled={disabled}
            title={f.description}
            onChange={(e) => setInputs((prev) => ({ ...prev, [f.name]: e.target.value }))}
          >
            {f.options.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </label>
      ))}
      {fields.map((f) => (
        <label key={f.name} className="mesh-field">
          <span>
            {f.label}
            {/* Şemadaki harf: kullanıcı hangi ölçü olduğunu tahmin etmesin. */}
            {f.symbol ? <em className="param-symbol">{f.symbol}</em> : null}
            {f.unit ? ` (${f.unit})` : ""}
          </span>
          <input
            type="number"
            step="any"
            value={inputs[f.name] ?? ""}
            disabled={disabled}
            title={f.description}
            onChange={(e) => setInputs((prev) => ({ ...prev, [f.name]: e.target.value }))}
          />
        </label>
      ))}
      <div className="template-panel-actions">
        <button type="button" disabled={disabled || !selected} onClick={handleOpenDialog}>
          Model üret
        </button>
        <button
          type="button"
          disabled={geometryId == null || busy || downloading}
          onClick={() => void handleDownload()}
        >
          {downloading ? "İndiriliyor…" : "STEP indir"}
        </button>
      </div>
      {error && !pending && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {selected && pending && (
        <TemplateLoadDialog
          template={selected}
          params={inputs}
          bcs={selected.default_bcs ?? []}
          inputs={loadInputs}
          busy={creating}
          error={error}
          onInputChange={(key, value) =>
            setLoadInputs((prev) => ({ ...prev, [key]: value }))
          }
          onCancel={() => {
            setPending(null);
            setError(null);
          }}
          onConfirm={() => void handleConfirm()}
        />
      )}
    </div>
  );
}
