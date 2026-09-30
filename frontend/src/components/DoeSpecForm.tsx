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
 *
 * Görsel dil: Claude Design "ML Studio 1a" — satır başına sembol + ad,
 * Aralık/Sabit anahtarı; sağda tarama bandı (açık mavi), uçlarda gösterim
 * sınırları, ▼ şablon varsayılanı. Bant salt gösterimdir; değerler kutulara
 * yazılır.
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
    // Varsayılanı 0 olan parametre (örn. kök fillet yarıçapı) ±%20 ile 0–0
    // olur; aralık geçersiz. Böyle parametre sabit başlar, kullanıcı isterse
    // aralığa çevirip sınır yazar.
    params[f.name] = {
      mode: d === 0 ? "fixed" : "range",
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

/* ------------------------------------------------------------------ */
/* Görsel yardımcılar                                                   */
/* ------------------------------------------------------------------ */

/** 2 anlamlı basamağa yuvarlanmış "temiz" sınır (80, 260, 0.2 …). */
function nice(v: number, up: boolean): number {
  if (!Number.isFinite(v) || v === 0) return v;
  const p = Math.pow(10, Math.floor(Math.log10(Math.abs(v))) - 1);
  return (up ? Math.ceil(v / p) : Math.floor(v / p)) * p;
}

/** Bant için gösterim sınırları: varsayılanın 0.4–1.6 katı, kullanıcının
 * girdiği aralığı da kapsayacak şekilde genişler. Şema üst sınır vermiyor;
 * bu yalnız gösterim ölçeğidir, doğrulama değildir. */
function displayBounds(def: number, lo: number, hi: number, floor: number | null): [number, number] {
  let a = nice(def * 0.4, false);
  let b = nice(def * 1.6, true);
  if (Number.isFinite(lo)) a = Math.min(a, nice(lo, false));
  if (Number.isFinite(hi)) b = Math.max(b, nice(hi, true));
  if (floor != null) a = Math.max(a, floor);
  if (b <= a) b = a + Math.abs(a || 1);
  return [a, b];
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return String(Number(v.toPrecision(4)));
}

function pct(v: number): string {
  return `${(Math.max(0, Math.min(1, v)) * 100).toFixed(1)}%`;
}

/** Tarama bandı: çizgi üstünde açık mavi bant (min–max), uçlarda dikey
 * çubuklar, ▼ varsayılan. Sabit modda bant yerine tek dikey işaret. */
function RangeBar({
  lo,
  hi,
  min,
  max,
  def,
  fixed,
}: {
  lo: number;
  hi: number;
  min: number;
  max: number;
  def: number;
  fixed: number | null;
}) {
  const f = (v: number) => (v - lo) / (hi - lo);
  const left = pct(f(min));
  const right = pct(f(max));
  const width = pct(Math.max(0, f(max) - f(min)));
  return (
    <span className="doe-bar" aria-hidden="true">
      <span className="doe-bar-track" />
      {fixed == null ? (
        <>
          <span className="doe-bar-band" style={{ left, width }} />
          <span className="doe-bar-end" style={{ left }} />
          <span className="doe-bar-end" style={{ left: right }} />
        </>
      ) : (
        <span className="doe-bar-fixed" style={{ left: pct(f(fixed)) }} />
      )}
      <span className="doe-bar-def" style={{ left: pct(f(def)) }}>
        ▼
      </span>
    </span>
  );
}

function ModeSwitch({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <span className="doe-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={o.value === value ? "doe-seg-opt active" : "doe-seg-opt"}
          aria-pressed={o.value === value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </span>
  );
}

/** Tek parametre satırı: sol sembol/ad/anahtar, sağ bant + kutular. */
function ParamLine({
  sym,
  name,
  unit,
  mode,
  modeLabel,
  modeOptions,
  onMode,
  bounds,
  def,
  min,
  max,
  fixed,
  onMin,
  onMax,
  onFixed,
  minLabel,
  maxLabel,
  fixedLabel,
  disabled,
  note,
}: {
  sym: string | null;
  name: string;
  unit: string | null;
  mode: string;
  modeLabel: string;
  modeOptions: { value: string; label: string }[];
  onMode: (v: string) => void;
  bounds: [number, number];
  def: number;
  min: string;
  max: string;
  fixed: string | null;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
  onFixed?: (v: string) => void;
  minLabel: string;
  maxLabel: string;
  fixedLabel?: string;
  disabled: boolean;
  note?: string;
}) {
  const [lo, hi] = bounds;
  const isFixed = fixed != null;
  return (
    <div className="doe-line">
      <span className="doe-line-head">
        <span className="doe-line-title">
          {sym ? <em className="doe-line-sym">{sym}</em> : null}
          <span className="doe-line-name">{name}</span>
        </span>
        <ModeSwitch label={modeLabel} value={mode} options={modeOptions} disabled={disabled} onChange={onMode} />
      </span>
      <span className="doe-line-body">
        <RangeBar
          lo={lo}
          hi={hi}
          min={Number(min)}
          max={Number(max)}
          def={def}
          fixed={isFixed ? Number(fixed) : null}
        />
        <span className="doe-line-inputs">
          <span className="doe-line-bound">{fmt(lo)}</span>
          {isFixed ? (
            <input
              className="doe-num"
              type="number"
              step="any"
              aria-label={fixedLabel}
              value={fixed ?? ""}
              disabled={disabled}
              onChange={(e) => onFixed?.(e.target.value)}
            />
          ) : (
            <>
              <input
                className="doe-num"
                type="number"
                step="any"
                aria-label={minLabel}
                value={min}
                disabled={disabled}
                onChange={(e) => onMin(e.target.value)}
              />
              <span className="doe-line-dash">–</span>
              <input
                className="doe-num"
                type="number"
                step="any"
                aria-label={maxLabel}
                value={max}
                disabled={disabled}
                onChange={(e) => onMax(e.target.value)}
              />
            </>
          )}
          {unit ? <span className="doe-line-unit">{unit}</span> : null}
          {note ? <span className="doe-line-note">{note}</span> : null}
          <span className="doe-line-bound doe-line-bound-hi">{fmt(hi)}</span>
        </span>
      </span>
    </div>
  );
}

interface DoeSpecFormProps {
  templates: GeometryTemplateInfo[];
  state: DoeFormState;
  busy: boolean;
  onChange: (next: DoeFormState) => void;
}

const MODE_OPTIONS = [
  { value: "range", label: "Aralık" },
  { value: "fixed", label: "Sabit" },
];

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

  const isRatio = state.elementMode === "ratio";
  const [rLo, rHi] = template?.default_element_ratio ?? [0.5, 1.2];
  const elemDef = isRatio ? Math.sqrt(rLo * rHi) : 9;
  const elemBounds: [number, number] = isRatio
    ? [Math.min(0.2, Number(state.elementMin) || 0.2), Math.max(2, Number(state.elementMax) || 2)]
    : [Math.min(2, Number(state.elementMin) || 2), Math.max(24, Number(state.elementMax) || 24)];
  const loadBounds: [number, number] = [
    Math.min(0.1, Number(state.loadMin) || 0.1),
    Math.max(3, Number(state.loadMax) || 3),
  ];

  return (
    <div className="doe-spec-form">
      <div className="doe-selects">
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
      </div>

      {fields.map((f) => {
        const row = state.params[f.name];
        if (!row) return null;
        const fixed = row.mode === "fixed";
        const bounds = displayBounds(
          f.defaultValue,
          fixed ? Number(row.fixed) : Number(row.min),
          fixed ? Number(row.fixed) : Number(row.max),
          f.exclusiveMin,
        );
        return (
          <ParamLine
            key={f.name}
            sym={f.symbol}
            name={f.label}
            unit={f.unit}
            mode={row.mode}
            modeLabel={`${f.label} tarama tipi`}
            modeOptions={MODE_OPTIONS}
            onMode={(v) => setParam(f.name, { mode: v as ParamMode })}
            bounds={bounds}
            def={f.defaultValue}
            min={row.min}
            max={row.max}
            fixed={fixed ? row.fixed : null}
            onMin={(v) => setParam(f.name, { min: v })}
            onMax={(v) => setParam(f.name, { max: v })}
            onFixed={(v) => setParam(f.name, { fixed: v })}
            minLabel={`${f.label} min`}
            maxLabel={`${f.label} maks`}
            fixedLabel={`${f.label} sabit değer`}
            disabled={busy}
          />
        );
      })}

      <ParamLine
        sym={isRatio ? "es/t" : "es"}
        name={isRatio ? "Eleman oranı" : "Eleman boyutu"}
        unit={isRatio ? "×" : "mm"}
        mode={state.elementMode}
        modeLabel="Eleman boyutu tipi"
        modeOptions={[
          { value: "ratio", label: "Oranlı" },
          { value: "mm", label: "Sabit mm" },
        ]}
        onMode={(v) => onChange({ ...state, elementMode: v as "ratio" | "mm" })}
        bounds={elemBounds}
        def={elemDef}
        min={state.elementMin}
        max={state.elementMax}
        fixed={null}
        onMin={(v) => onChange({ ...state, elementMin: v })}
        onMax={(v) => onChange({ ...state, elementMax: v })}
        minLabel="Eleman boyutu min"
        maxLabel="Eleman boyutu maks"
        disabled={busy || (template?.has_characteristic_length === false && isRatio)}
        note={isRatio ? "× karakteristik uzunluk" : undefined}
      />

      <ParamLine
        sym="k"
        name="Yük katsayısı"
        unit="×"
        mode="range"
        modeLabel="Yük katsayısı tarama tipi"
        modeOptions={[{ value: "range", label: "Aralık" }]}
        onMode={() => undefined}
        bounds={loadBounds}
        def={1}
        min={state.loadMin}
        max={state.loadMax}
        fixed={null}
        onMin={(v) => onChange({ ...state, loadMin: v })}
        onMax={(v) => onChange({ ...state, loadMax: v })}
        minLabel="Yük katsayısı min"
        maxLabel="Yük katsayısı maks"
        disabled={busy}
        note="× şablon yükü"
      />
    </div>
  );
}
