/**
 * Crash DOE formu (1.28a) — Durability `DoeSpecForm` deseni: şablon parametreleri
 * ve senaryo alanları satır satır, Aralık / Sabit; bant = taranan aralık,
 * ▼ = şablon varsayılanı. Çıktı: `/crash/doe/studies` gövdesi (`base` + `vary`).
 * Öneri yok: varsayılan aralık ±%20, mühendis değiştirir.
 */
import { useMemo } from "react";
import type { Material } from "../api/materials";
import type { GeometryTemplateInfo } from "../api/templates";
import { numberFieldsFromSchema, type JsonSchema } from "../templates/schemaForm";
import { ParamLine, displayBounds, type ParamRow } from "./DoeSpecForm";

export interface CrashScenarioField {
  key: string;
  label: string;
  sym: string | null;
  unit: string | null;
  def: number;
  floor: number | null;
}

/** Her şablonda olan senaryo alanları (CrashScenarioRequest). */
export const SCENARIO_FIELDS: CrashScenarioField[] = [
  { key: "speed_m_s", label: "Çarpma hızı", sym: "v", unit: "m/s", def: 10, floor: 0 },
  { key: "t_end_ms", label: "Süre", sym: "t_end", unit: "ms", def: 20, floor: 0 },
  { key: "element_size_mm", label: "Eleman boyutu", sym: "es", unit: "mm", def: 5, floor: 0 },
];

export interface CrashDoeFormState {
  templateId: string;
  geometry: Record<string, ParamRow>;
  scenario: Record<string, ParamRow>;
  materialName: string;
  nSamples: string;
  seed: string;
  name: string;
  /** Gelişmiş: taban isteğe eklenen ham JSON (boş = yok) */
  extraJson: string;
}

const SPREAD = 0.2;

function rowFor(d: number, range: boolean): ParamRow {
  return {
    mode: range && d !== 0 ? "range" : "fixed",
    fixed: String(d),
    min: String(Number((d * (1 - SPREAD)).toFixed(4))),
    max: String(Number((d * (1 + SPREAD)).toFixed(4))),
  };
}

export function initialCrashDoeState(template: GeometryTemplateInfo, prev?: CrashDoeFormState): CrashDoeFormState {
  const geometry: Record<string, ParamRow> = {};
  for (const f of numberFieldsFromSchema(template.params_schema as JsonSchema)) {
    geometry[f.name] = rowFor(f.defaultValue, !f.optional);
  }
  const scenario: Record<string, ParamRow> = {};
  for (const f of SCENARIO_FIELDS) scenario[f.key] = prev?.scenario[f.key] ?? rowFor(f.def, f.key === "speed_m_s");
  return {
    templateId: template.id,
    geometry,
    scenario,
    materialName: prev?.materialName ?? "S235",
    nSamples: prev?.nSamples ?? "20",
    seed: prev?.seed ?? "1",
    name: "",
    extraJson: prev?.extraJson ?? "",
  };
}

function num(raw: string, label: string): number {
  const v = Number(raw);
  if (raw.trim() === "" || !Number.isFinite(v)) throw new Error(`${label}: sayı gerekli.`);
  return v;
}

/** Form → `/crash/doe/studies` gövdesi. Aralık satırları `vary`, sabitler `base`. */
export function buildCrashDoeSpecFromForm(state: CrashDoeFormState) {
  const base: Record<string, unknown> = { template_id: state.templateId, material_name: state.materialName };
  const vary: Record<string, [number, number]> = {};
  const geometry: Record<string, number> = {};
  const add = (path: string, label: string, row: ParamRow, into?: Record<string, number>, key?: string) => {
    if (row.mode === "range") {
      const lo = num(row.min, `${label} alt`);
      const hi = num(row.max, `${label} üst`);
      if (!(hi > lo)) throw new Error(`${label}: üst sınır alttan büyük olmalı.`);
      vary[path] = [lo, hi];
    } else if (into && key) {
      into[key] = num(row.fixed, label);
    } else {
      base[path] = num(row.fixed, label);
    }
  };
  for (const [name, row] of Object.entries(state.geometry)) add(`geometry.${name}`, name, row, geometry, name);
  for (const f of SCENARIO_FIELDS) {
    const row = state.scenario[f.key];
    if (row) add(f.key, f.label, row);
  }
  if (Object.keys(geometry).length) base.geometry = geometry;
  if (state.extraJson.trim()) {
    let extra: unknown;
    try {
      extra = JSON.parse(state.extraJson);
    } catch {
      throw new Error("Gelişmiş JSON geçerli değil.");
    }
    if (!extra || typeof extra !== "object" || Array.isArray(extra)) throw new Error("Gelişmiş JSON bir nesne olmalı.");
    Object.assign(base, extra as Record<string, unknown>);
  }
  if (Object.keys(vary).length === 0) throw new Error("En az bir parametre Aralık olmalı.");
  const n = Number(state.nSamples);
  if (!Number.isInteger(n) || n < 1 || n > 500) throw new Error("Örnek sayısı 1–500 tam sayı olmalı.");
  const s = Number(state.seed);
  if (!Number.isInteger(s)) throw new Error("Tohum tam sayı olmalı.");
  return { ...(state.name.trim() ? { name: state.name.trim() } : {}), base, vary, n_samples: n, seed: s };
}

const MODE_OPTIONS = [
  { value: "range", label: "Aralık" },
  { value: "fixed", label: "Sabit" },
];

interface Props {
  template: GeometryTemplateInfo | null;
  materials: Material[];
  state: CrashDoeFormState;
  busy: boolean;
  onChange: (next: CrashDoeFormState) => void;
}

export default function CrashDoeSpecForm({ template, materials, state, busy, onChange }: Props) {
  const fields = useMemo(
    () => (template ? numberFieldsFromSchema(template.params_schema as JsonSchema) : []),
    [template],
  );
  const setRow = (group: "geometry" | "scenario", key: string, patch: Partial<ParamRow>) =>
    onChange({ ...state, [group]: { ...state[group], [key]: { ...state[group][key], ...patch } } });

  const line = (group: "geometry" | "scenario", key: string, label: string, sym: string | null, unit: string | null, def: number, floor: number | null) => {
    const row = state[group][key];
    if (!row) return null;
    const isFixed = row.mode === "fixed";
    return (
      <ParamLine
        key={`${group}.${key}`}
        sym={sym}
        name={label}
        unit={unit}
        mode={row.mode}
        modeLabel={`${label} modu`}
        modeOptions={MODE_OPTIONS}
        onMode={(m) => setRow(group, key, { mode: m as ParamRow["mode"] })}
        bounds={displayBounds(def, Number(row.min), Number(row.max), floor)}
        def={def}
        min={row.min}
        max={row.max}
        fixed={isFixed ? row.fixed : null}
        onMin={(v) => setRow(group, key, { min: v })}
        onMax={(v) => setRow(group, key, { max: v })}
        onFixed={(v) => setRow(group, key, { fixed: v })}
        minLabel={`${label} alt`}
        maxLabel={`${label} üst`}
        fixedLabel={`${label} sabit`}
        disabled={busy}
      />
    );
  };

  return (
    <>
      {fields.map((f) => line("geometry", f.name, f.label, f.symbol, f.unit, f.defaultValue, f.exclusiveMin))}
      <span className="ml-k crash-doe-group">Senaryo</span>
      {SCENARIO_FIELDS.map((f) => line("scenario", f.key, f.label, f.sym, f.unit, f.def, f.floor))}
      <div className="doe-material-row">
        <span className="ml-k">Malzeme</span>
        <span className="doe-chips" role="group" aria-label="Malzeme">
          {materials.map((m) => (
            <button
              key={m.id}
              type="button"
              className={state.materialName === m.name ? "doe-chip active" : "doe-chip"}
              aria-pressed={state.materialName === m.name}
              disabled={busy}
              onClick={() => onChange({ ...state, materialName: m.name })}
            >
              {m.name}
            </button>
          ))}
        </span>
        <span className="doe-material-hint">tek malzeme; σy taraması için Gelişmiş'te model.sigma_y_pa</span>
      </div>
      <details className="crash-doe-advanced">
        <summary className="ml-k">Gelişmiş · taban isteğe ek JSON</summary>
        <textarea
          className="crash-doe-json"
          aria-label="Gelişmiş JSON"
          spellCheck={false}
          rows={5}
          placeholder={'{ "model": { "sigma_y_pa": 2.35e8 }, "contacts": [] }'}
          value={state.extraJson}
          disabled={busy}
          onChange={(e) => onChange({ ...state, extraJson: e.target.value })}
        />
        <span className="crash-doe-sub">
          CrashScenarioRequest alanları buradan eklenir (contacts, rigid_bodies, model…). Kutunun durması için
          t_end_ms yeterli olmalı, yoksa ezilme boş kalır.
        </span>
      </details>
    </>
  );
}
