/** DOE tarama formu: şablon, parametre aralıkları, yük ve mesh ayarları.
 *
 * Her parametre için kullanıcı ikisinden birini seçer:
 *   - **Sabit**: tek değer, tüm örneklerde aynı
 *   - **Aralık**: min–max, Latin Hypercube bu aralığı tarar
 * Varsayılan olarak şablonun kendi varsayılanı ±%20 bir aralıktır — yani
 * "hiçbir şeye dokunmadan başlat" makul bir tarama verir, ama kritik
 * parametrede kullanıcı kendi sınırlarını yazar ya da sabitler.
 *
 * BC senaryosu şablonun `default_bcs`'inden gelir; yük büyüklüğü `load_scale`
 * ile taranır (yönü ve tipi korur, basınçta da çalışır).
 */

import { useMemo } from "react";
import type { DoeSpecPayload } from "../api/doe";
import type { GeometryTemplateInfo } from "../api/templates";
import {
  enumFieldsFromSchema,
  numberFieldsFromSchema,
  type JsonSchema,
} from "../templates/schemaForm";

export type ParamMode = "fixed" | "range";

export interface ParamRow {
  mode: ParamMode;
  fixed: string;
  min: string;
  max: string;
}

export interface DoeFormState {
  templateId: string;
  params: Record<string, ParamRow>;
  enums: Record<string, string>;
  /** "ratio": eleman = oran × karakteristik uzunluk. "mm": mutlak boyut. */
  elementMode: "ratio" | "mm";
  elementMin: string;
  elementMax: string;
  loadMin: string;
  loadMax: string;
  nSamples: string;
  seed: string;
}

/** Şablon varsayılanının çevresinde makul bir başlangıç aralığı. */
const SPREAD = 0.2;

export function initialStateFor(template: GeometryTemplateInfo): DoeFormState {
  const schema = template.params_schema as JsonSchema;
  const params: Record<string, ParamRow> = {};
  for (const f of numberFieldsFromSchema(schema)) {
    const d = f.defaultValue;
    params[f.name] = {
      mode: "range",
      fixed: String(d),
      min: String(Number((d * (1 - SPREAD)).toFixed(4))),
      max: String(Number((d * (1 + SPREAD)).toFixed(4))),
    };
  }
  const enums: Record<string, string> = {};
  for (const f of enumFieldsFromSchema(schema)) enums[f.name] = f.defaultValue;
  // Oranlı mod varsayılan: geometri tarandıkça mesh çözünürlüğü sabit kalır.
  // Mutlak mm'de aynı fizik, sırf mesh yüzünden %9.6–%21.8 gerilme sapması
  // veriyor ve bazı örnekler yanlışlıkla uyarı tetikliyor.
  const canRatio = template.has_characteristic_length !== false;
  const [rLo, rHi] = template.default_element_ratio ?? [0.5, 1.2];
  return {
    templateId: template.id,
    params,
    enums,
    elementMode: canRatio ? "ratio" : "mm",
    elementMin: canRatio ? String(rLo) : "6",
    elementMax: canRatio ? String(rHi) : "12",
    loadMin: "0.5",
    loadMax: "2",
    nSamples: "8",
    seed: "42",
  };
}

function num(raw: string, label: string): number {
  const v = Number(raw.trim());
  if (raw.trim() === "" || !Number.isFinite(v)) throw new Error(`${label} geçerli bir sayı olmalı.`);
  return v;
}

/** Form durumundan API gövdesi; hata varsa `Error` fırlatır. */
export function buildSpec(
  state: DoeFormState,
  template: GeometryTemplateInfo,
  materialIds: number[],
  runSolver: boolean,
): DoeSpecPayload {
  const geometry: Record<string, [number, number]> = {};
  const fixed: Record<string, number | string> = { ...state.enums };
  const labels = new Map(
    numberFieldsFromSchema(template.params_schema as JsonSchema).map((f) => [
      f.name,
      f.symbol ? `${f.label} (${f.symbol})` : f.label,
    ]),
  );
  for (const [name, row] of Object.entries(state.params)) {
    const label = labels.get(name) ?? name;
    if (row.mode === "fixed") {
      fixed[name] = num(row.fixed, label);
      continue;
    }
    const lo = num(row.min, `${label} min`);
    const hi = num(row.max, `${label} maks`);
    if (hi <= lo) throw new Error(`${label}: maks değer min değerden büyük olmalı.`);
    geometry[name] = [lo, hi];
  }
  if (Object.keys(geometry).length === 0) {
    throw new Error("En az bir parametre aralık olarak taranmalı.");
  }

  const isRatio = state.elementMode === "ratio";
  const eLabel = isRatio ? "Eleman oranı" : "Eleman boyutu";
  const eLo = num(state.elementMin, `${eLabel} min`);
  const eHi = num(state.elementMax, `${eLabel} maks`);
  if (eLo <= 0) throw new Error(`${eLabel} pozitif olmalı.`);
  if (eHi <= eLo) throw new Error(`${eLabel}: maks değer min değerden büyük olmalı.`);
  const lLo = num(state.loadMin, "Yük katsayısı min");
  const lHi = num(state.loadMax, "Yük katsayısı maks");
  if (lLo <= 0) throw new Error("Yük katsayısı pozitif olmalı.");
  if (lHi <= lLo) throw new Error("Yük katsayısı: maks değer min değerden büyük olmalı.");
  const n = num(state.nSamples, "Örnek sayısı");
  if (!Number.isInteger(n) || n < 1) throw new Error("Örnek sayısı 1 veya daha büyük tam sayı olmalı.");

  const bcs = template.default_bcs ?? [];
  if (bcs.length === 0) {
    throw new Error(`'${template.name}' şablonunda varsayılan sınır koşulu yok.`);
  }

  return {
    name: `${template.id} LHS`,
    template_id: template.id,
    seed: num(state.seed, "Tohum"),
    n_samples: n,
    geometry,
    fixed_params: fixed,
    // Oranlı modda backend element_size'ı yok sayar; yine de geçerli bir
    // aralık göndermek gerekiyor (şablon karakteristik uzunluk vermezse
    // geri düşülen değer bu).
    element_size: isRatio ? [6, 12] : [eLo, eHi],
    ...(isRatio ? { element_ratio: [eLo, eHi] as [number, number] } : {}),
    load_scale: [lLo, lHi],
    material_ids: materialIds,
    bc_scenarios: [{ name: "varsayilan", bcs: bcs as unknown as Record<string, unknown>[] }],
    dimension: 3,
    element_scheme: "tet",
    run_solver: runSolver,
  };
}

interface DoeSpecFormProps {
  templates: GeometryTemplateInfo[];
  state: DoeFormState;
  busy: boolean;
  onChange: (next: DoeFormState) => void;
}

export default function DoeSpecForm({ templates, state, busy, onChange }: DoeSpecFormProps) {
  const template = templates.find((t) => t.id === state.templateId) ?? null;
  const fields = useMemo(
    () => (template ? numberFieldsFromSchema(template.params_schema as JsonSchema) : []),
    [template],
  );
  const enumFields = useMemo(
    () => (template ? enumFieldsFromSchema(template.params_schema as JsonSchema) : []),
    [template],
  );

  function setParam(name: string, patch: Partial<ParamRow>) {
    onChange({
      ...state,
      params: { ...state.params, [name]: { ...state.params[name], ...patch } },
    });
  }

  return (
    <div className="doe-spec-form">
      <label className="mesh-field">
        <span>Şablon</span>
        <select
          value={state.templateId}
          disabled={busy || templates.length === 0}
          onChange={(e) => {
            const t = templates.find((x) => x.id === e.target.value);
            if (t) onChange({ ...initialStateFor(t), nSamples: state.nSamples, seed: state.seed });
          }}
        >
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      {enumFields.map((f) => (
        <label key={f.name} className="mesh-field">
          <span>{f.label}</span>
          <select
            value={state.enums[f.name] ?? f.defaultValue}
            disabled={busy}
            onChange={(e) => onChange({ ...state, enums: { ...state.enums, [f.name]: e.target.value } })}
          >
            {f.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      ))}

      {fields.map((f) => {
        const row = state.params[f.name];
        if (!row) return null;
        return (
          <div key={f.name} className="doe-param-row">
            <div className="doe-param-head">
              <span className="doe-param-name">
                {f.label}
                {f.symbol ? <em className="param-symbol">{f.symbol}</em> : null}
                {f.unit ? ` (${f.unit})` : ""}
              </span>
              <select
                aria-label={`${f.label} tarama tipi`}
                value={row.mode}
                disabled={busy}
                onChange={(e) => setParam(f.name, { mode: e.target.value as ParamMode })}
              >
                <option value="range">Aralık</option>
                <option value="fixed">Sabit</option>
              </select>
            </div>
            {row.mode === "fixed" ? (
              <input
                type="number"
                step="any"
                aria-label={`${f.label} sabit değer`}
                value={row.fixed}
                disabled={busy}
                onChange={(e) => setParam(f.name, { fixed: e.target.value })}
              />
            ) : (
              <div className="doe-param-range">
                <input
                  type="number"
                  step="any"
                  aria-label={`${f.label} min`}
                  value={row.min}
                  disabled={busy}
                  onChange={(e) => setParam(f.name, { min: e.target.value })}
                />
                <span>–</span>
                <input
                  type="number"
                  step="any"
                  aria-label={`${f.label} maks`}
                  value={row.max}
                  disabled={busy}
                  onChange={(e) => setParam(f.name, { max: e.target.value })}
                />
              </div>
            )}
          </div>
        );
      })}

      <div className="doe-param-row">
        <div className="doe-param-head">
          <span className="doe-param-name">
            {state.elementMode === "ratio" ? "Eleman oranı (×)" : "Eleman boyutu (mm)"}
          </span>
          <select
            aria-label="Eleman boyutu tipi"
            value={state.elementMode}
            disabled={busy || template?.has_characteristic_length === false}
            onChange={(e) =>
              onChange({ ...state, elementMode: e.target.value as "ratio" | "mm" })
            }
          >
            <option value="ratio">Oranlı</option>
            <option value="mm">Sabit mm</option>
          </select>
        </div>
        <div className="doe-param-range">
          <input
            type="number"
            step="any"
            aria-label="Eleman boyutu min"
            value={state.elementMin}
            disabled={busy}
            onChange={(e) => onChange({ ...state, elementMin: e.target.value })}
          />
          <span>–</span>
          <input
            type="number"
            step="any"
            aria-label="Eleman boyutu maks"
            value={state.elementMax}
            disabled={busy}
            onChange={(e) => onChange({ ...state, elementMax: e.target.value })}
          />
        </div>
        {state.elementMode === "ratio" && (
          <p className="filename">
            Eleman boyutu = oran × şablonun karakteristik uzunluğu (kirişte kesit
            kalınlığı, delikli plakada delik çapı). Geometri değişirken mesh
            çözünürlüğü sabit kalır.
          </p>
        )}
      </div>

      <div className="doe-param-row">
        <div className="doe-param-head">
          <span className="doe-param-name">Yük katsayısı (×)</span>
        </div>
        <div className="doe-param-range">
          <input
            type="number"
            step="any"
            aria-label="Yük katsayısı min"
            value={state.loadMin}
            disabled={busy}
            onChange={(e) => onChange({ ...state, loadMin: e.target.value })}
          />
          <span>–</span>
          <input
            type="number"
            step="any"
            aria-label="Yük katsayısı maks"
            value={state.loadMax}
            disabled={busy}
            onChange={(e) => onChange({ ...state, loadMax: e.target.value })}
          />
        </div>
        <p className="filename">
          Şablonun varsayılan yükü bu katsayıyla çarpılır; yön ve tip korunur.
        </p>
      </div>
    </div>
  );
}
