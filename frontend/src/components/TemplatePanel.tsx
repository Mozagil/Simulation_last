import { useEffect, useMemo, useState } from "react";
import {
  createGeometryFromTemplate,
  downloadTemplateStep,
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
import { postRocketOrk } from "../api/cfd";
import { fetchCrashCatalog } from "../api/crash";

interface TemplatePanelProps {
  busy: boolean;
  onCreated: (result: CreateFromTemplateResponse) => Promise<void> | void;
  /** Seçili şablon değişince haber ver — DOE paneli bunu izliyor, böylece
   * kullanıcı tek yerden şablon seçiyor. */
  onTemplateSelected?: (templateId: string) => void;
  /** Analiz sekmesi: crash → yalnız `crash` etiketli şablonlar, durability /
   * modal → crash olmayanlar (kullanıcı 2026-10-04: crash'te durability
   * şablonları görünüyordu). */
  kind?: TemplateKind;
  /** 1.23 B1 (crash): hazır senaryosu olan şablonda "Model üret" yeni vaka penceresini
   * (crash kurulum alanlarıyla) açar; geometri değerleri oraya taşınır. */
  onCrashModel?: (templateId: string, geometry: Record<string, string>) => void;
}

export type TemplateKind = "durability" | "crash" | "cfd";

/** Sekmeye göre şablonlar: crash ve cfd (akış, ör. roket — R1) kendi etiketleriyle;
 * durability ikisini de görmez. */
export function templatesForKind(list: GeometryTemplateInfo[], kind: TemplateKind): GeometryTemplateInfo[] {
  return list.filter((t) => {
    const tags = t.tags ?? [];
    if (kind === "crash") return tags.includes("crash");
    if (kind === "cfd") return tags.includes("cfd");
    return !tags.includes("crash") && !tags.includes("cfd");
  });
}

export default function TemplatePanel({
  busy,
  onCreated,
  onTemplateSelected,
  kind = "durability",
  onCrashModel,
}: TemplatePanelProps) {
  const [allTemplates, setAllTemplates] = useState<GeometryTemplateInfo[]>([]);
  const templates = useMemo(() => templatesForKind(allTemplates, kind), [allTemplates, kind]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // Onay penceresi: parametreler doğrulandıktan sonra açılır, kullanıcı yük
  // değerlerini girer. Geometri ancak onaydan sonra üretilir.
  const [pending, setPending] = useState<{ params: Record<string, number | string> } | null>(null);
  const [loadInputs, setLoadInputs] = useState<Record<string, string>>({});
  // R6: OpenRocket .ork → roket formu (eşlenemeyenler not olarak)
  const [orkNotes, setOrkNotes] = useState<string[] | null>(null);

  async function importOrk(file: File) {
    setError(null);
    try {
      const r = await postRocketOrk(file);
      setInputs((prev) => {
        const next = { ...prev };
        for (const [k, v] of Object.entries(r.params)) next[k] = String(v);
        return next;
      });
      setOrkNotes([`${file.name}${r.name ? ` (${r.name})` : ""}: ${Object.keys(r.params).length} parametre dolduruldu.`, ...r.notes]);
    } catch (e) {
      setOrkNotes(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const selected = templates.find((t) => t.id === selectedId) ?? null;
  // 1.23 A6: şablon BC'leri yalnız durability'de (crash / akışta kendi kurulumları var).
  const templateBcs = kind === "durability" ? (selected?.default_bcs ?? []) : [];
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
      .then(setAllTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : "Şablonlar alınamadı."));
  }, []);

  // 1.23 B1: hazır crash senaryosu olan şablonlar (katalog).
  const [scenarioTemplates, setScenarioTemplates] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (kind !== "crash" || !onCrashModel) return;
    fetchCrashCatalog()
      .then((c) => setScenarioTemplates(new Set(Object.keys(c.scenario_templates))))
      .catch(() => setScenarioTemplates(new Set()));
  }, [kind, onCrashModel]);

  // Liste (ya da sekme) değişince seçim listede değilse ilk şablona geç.
  useEffect(() => {
    if (!templates.length || templates.some((t) => t.id === selectedId)) return;
    setSelectedId(templates[0].id);
    onTemplateSelected?.(templates[0].id);
    fillDefaults(templates[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates]);

  function handleOpenDialog() {
    if (!selected) return;
    const parsed = parseParamInputs(inputs, enums.map((e) => e.name));
    if (typeof parsed === "string") {
      setError(parsed);
      return;
    }
    setError(null);
    if (kind === "crash" && onCrashModel && scenarioTemplates.has(selected.id)) {
      onCrashModel(selected.id, inputs);
      return;
    }
    setLoadInputs(loadInputsFromBcs(templateBcs));
    setPending({ params: parsed });
  }

  async function handleConfirm() {
    if (!selected || !pending) return;
    // Sade panelde ölçüler pop-up'ta düzenlenir — onayda yeniden okunur.
    let params = pending.params;
    if (compact) {
      const parsed = parseParamInputs(inputs, enums.map((e) => e.name));
      if (typeof parsed === "string") {
        setError(parsed);
        return;
      }
      params = parsed;
    }
    // Önce girdileri doğrula: şablonun (id'siz) BC listesi üzerinde. Geometri
    // üretmeden hata vermek, yarım kayıt bırakmamak için.
    const check = applyLoadInputs(templateBcs, loadInputs);
    if (typeof check === "string") {
      setError(check);
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const result = await createGeometryFromTemplate(selected.id, params);
      // Sunucudan gelen BC'ler gerçek yüzey/kenar id'leriyle bağlı; kullanıcının
      // girdiği yük değerlerini bunların üzerine uygula (sıra aynı şablondan gelir).
      // 1.23 A6: şablonun BC'leri durability'ye ait (ör. Taylor basıncı);
      // crash / akış sekmesinde yüklenmez — kurulum o sekmenin kendi panelinde.
      if (kind !== "durability") {
        await onCreated({ ...result, default_bcs: [] });
      } else {
        const bound = applyLoadInputs(result.default_bcs ?? [], loadInputs);
        await onCreated(typeof bound === "string" ? result : { ...result, default_bcs: bound });
      }
      setPending(null);
    } catch (e) {
      setError(e instanceof TemplateApiError ? e.message : "Şablon üretilemedi.");
    } finally {
      setCreating(false);
    }
  }

  const disabled = busy || creating;
  // 1.23 B1b: crash'te panel sade — görsel, şablon, Model üret, STEP indir. Ölçüler
  // pop-up'ta: hazır senaryolu şablonda "Yeni crash vakası", diğerinde Model üret penceresi.
  const compact = kind === "crash";
  const [stepBusy, setStepBusy] = useState(false);

  async function handleStep() {
    if (!selected) return;
    const parsed = parseParamInputs(inputs, enums.map((e) => e.name));
    if (typeof parsed === "string") {
      setError(parsed);
      return;
    }
    setStepBusy(true);
    setError(null);
    try {
      await downloadTemplateStep(selected.id, parsed);
    } catch (e) {
      setError(e instanceof TemplateApiError ? e.message : "STEP indirilemedi.");
    } finally {
      setStepBusy(false);
    }
  }

  const paramFields = (
      <div className="template-panel-fields">
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
      </div>
  );

  return (
    <div className={compact ? "template-panel template-panel-compact" : "template-panel"}>
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
            onTemplateSelected?.(id);
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
      {selected && !compact && (
        <p className="template-panel-desc" title={selected.description}>
          {selected.description}
        </p>
      )}
      {selected?.id === "rocket" && (
        <div className="template-ork">
          <label className="doe-btn doe-btn-ghost">
            OpenRocket .ork içe aktar
            <input
              type="file"
              accept=".ork,.xml"
              aria-label="OpenRocket dosyası"
              hidden
              disabled={disabled}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importOrk(f);
                e.target.value = "";
              }}
            />
          </label>
          {orkNotes && (
            <ul className="crash-behavior-hint" data-testid="ork-notes">
              {orkNotes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!compact && paramFields}
      <div className="template-panel-actions">
        <button type="button" disabled={disabled || !selected} onClick={handleOpenDialog}>
          Model üret
        </button>
        <button
          type="button"
          disabled={disabled || !selected || stepBusy}
          onClick={() => void handleStep()}
          title="Şablonun STEP dosyası (geçerli parametrelerle); geometri kaydı açılmaz"
        >
          {stepBusy ? "İndiriliyor…" : "STEP indir"}
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
          paramFields={compact ? paramFields : undefined}
          bcs={templateBcs}
          note={
            kind === "crash"
              ? "Şablonun durability yükü/kısıtları crash'te kullanılmaz; çarpma (ilk hız, duvar, roller) 4 · Crash'te kurulur."
              : kind === "cfd"
                ? "Şablonun durability yükü/kısıtları akışta kullanılmaz; akış koşulları 3 · Akış'ta kurulur."
                : undefined
          }
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
