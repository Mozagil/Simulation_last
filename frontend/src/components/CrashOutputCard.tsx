import type { CrashEnginePayload, CrashFilterPayload, CrashSectionPayload, CrashThPayload } from "../api/crash";

/** Çıktı ve kontrol kartı (1.15d): engine aralıkları + zaman adımı (1.15a),
 * /TH grupları (1.15b), /SECT/PARAL kesitleri (1.15c). Alanlar ham metin;
 * gönderimde sayıya çevrilir. Öneri yok: boş = backend varsayılanı. */

// Backend TH_VARS ile aynı (hm_cfg OUTPUTBLOCK; yalnız sütun yazan tekil değişkenler).
export const TH_VARS = {
  rwall: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"],
  inter: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"],
  part: [
    "IE", "KE", "XMOM", "YMOM", "ZMOM", "MASS", "HE", "TURBKE", "XCG", "YCG", "ZCG",
    "XXMOM", "YYMOM", "ZZMOM", "IXX", "IYY", "IZZ", "IXY", "IYZ", "IZX", "RIE",
    "KERB", "RKERB", "RKE", "ERODED", "HEAT", "VX", "VY", "VZ", "PW",
  ],
  sect: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ", "MX", "MY", "MZ"],
  node: [
    "DX", "DY", "DZ", "VX", "VY", "VZ", "AX", "AY", "AZ", "VRX", "VRY", "VRZ",
    "ARX", "ARY", "ARZ", "REACX", "REACY", "REACZ", "REACXX", "REACYY", "REACZZ",
    "X", "Y", "Z", "DRX", "DRY", "DRZ",
  ],
} as const;

type GroupKey = "rwall" | "inter" | "part" | "sect";

const DT_KINDS = [
  { key: "", label: "Yok" },
  { key: "DT", label: "/DT" },
  { key: "NODA/0", label: "NODA/0" },
  { key: "NODA/STOP", label: "NODA/STOP" },
  { key: "NODA/CST/0", label: "NODA/CST/0" },
] as const;

export interface SectionRow {
  id: number;
  name: string;
  m: [string, string, string];
  m1: [string, string, string];
  m2: [string, string, string];
  /** boş = tüm parçalar */
  parts: number[];
  iframe: string;
}

export interface OutputState {
  thDt: string;
  animDt: string;
  dtKind: string;
  dtScale: string;
  dtMin: string;
  /** 1.17e — CFC sınıfı ("" = süzme yok) */
  forceCfc: string;
  accCfc: string;
  groups: Record<GroupKey, { enabled: boolean; vars: string[] }>;
  nodeIds: string;
  nodeVars: string[];
  sections: SectionRow[];
}

let sectionSeq = 0;

export function defaultOutput(): OutputState {
  return {
    thDt: "",
    animDt: "",
    dtKind: "",
    dtScale: "0",
    dtMin: "0",
    forceCfc: "",
    accCfc: "",
    groups: {
      rwall: { enabled: true, vars: ["FNX", "FNY", "FNZ"] },
      inter: { enabled: true, vars: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"] },
      part: { enabled: true, vars: ["IE", "KE"] },
      sect: { enabled: true, vars: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"] },
    },
    nodeIds: "",
    nodeVars: ["AX", "AY", "AZ"],
    sections: [],
  };
}

function num(raw: string, what: string): number {
  const v = Number(raw.trim().replace(",", "."));
  if (!raw.trim() || !Number.isFinite(v)) throw new Error(`${what}: sayı geçersiz (${raw || "boş"})`);
  return v;
}

function optNum(raw: string, what: string): number | null {
  return raw.trim() ? num(raw, what) : null;
}

export function parseNodeIds(raw: string): number[] {
  const out: number[] = [];
  for (const tok of raw.split(/[\s,;]+/)) {
    if (!tok) continue;
    const v = Number(tok);
    if (!Number.isInteger(v) || v <= 0) throw new Error(`TH düğüm kimliği geçersiz: ${tok}`);
    if (!out.includes(v)) out.push(v);
  }
  return out;
}

export function outputPayload(s: OutputState): {
  engine: CrashEnginePayload;
  th: CrashThPayload;
  sections: CrashSectionPayload[];
  filters: CrashFilterPayload;
} {
  const vec = (v: [string, string, string], what: string) =>
    v.map((c, i) => num(c, `${what} ${"xyz"[i]}`)) as [number, number, number];
  return {
    engine: {
      th_dt_ms: optNum(s.thDt, "TH aralığı"),
      anim_dt_ms: optNum(s.animDt, "Animasyon aralığı"),
      dt_kind: s.dtKind,
      dt_scale: s.dtKind ? num(s.dtScale, "Δt_sca") : 0,
      dt_min_ms: s.dtKind ? num(s.dtMin, "Δt_min") : 0,
    },
    th: {
      rwall: s.groups.rwall,
      inter: s.groups.inter,
      part: s.groups.part,
      sect: s.groups.sect,
      node_ids: parseNodeIds(s.nodeIds),
      node_vars: s.nodeVars,
    },
    filters: {
      force_cfc: s.forceCfc ? Number(s.forceCfc) : null,
      acc_cfc: s.accCfc ? Number(s.accCfc) : null,
    },
    sections: s.sections.map((r, i) => ({
      name: r.name.trim() || `section_${i + 1}`,
      origin: vec(r.m, `Kesit ${i + 1} M`),
      corner1: vec(r.m1, `Kesit ${i + 1} M1`),
      corner2: vec(r.m2, `Kesit ${i + 1} M2`),
      parts: r.parts,
      iframe: num(r.iframe, `Kesit ${i + 1} Iframe`),
    })),
  };
}

function VarChips({
  vars,
  selected,
  onChange,
  disabled,
  label,
}: {
  vars: readonly string[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <div className="crash-var-chips" role="group" aria-label={label}>
      {vars.map((v) => {
        const on = selected.includes(v);
        return (
          <button
            key={v}
            type="button"
            className={on ? "crash-var-chip active" : "crash-var-chip"}
            aria-pressed={on}
            disabled={disabled}
            onClick={() => onChange(on ? selected.filter((x) => x !== v) : [...selected, v])}
          >
            {v}
          </button>
        );
      })}
    </div>
  );
}

const GROUP_LABELS: Record<GroupKey, string> = {
  rwall: "Rijit duvar — /TH/RWALL",
  inter: "Temas — /TH/INTER",
  part: "Parça — /TH/PART",
  sect: "Kesit — /TH/SECTIO",
};

export default function CrashOutputCard({
  value,
  onChange,
  partOptions,
  disabled = false,
}: {
  value: OutputState;
  onChange: (next: OutputState) => void;
  partOptions: number[];
  disabled?: boolean;
}) {
  const set = (patch: Partial<OutputState>) => onChange({ ...value, ...patch });
  const setGroup = (k: GroupKey, patch: Partial<{ enabled: boolean; vars: string[] }>) =>
    set({ groups: { ...value.groups, [k]: { ...value.groups[k], ...patch } } });
  const setSection = (id: number, patch: Partial<SectionRow>) =>
    set({ sections: value.sections.map((r) => (r.id === id ? { ...r, ...patch } : r)) });
  const text = (label: string, v: string, apply: (s: string) => void, placeholder?: string, off = false) => (
    <label className="mesh-field">
      <span>{label}</span>
      <input value={v} placeholder={placeholder} disabled={disabled || off} onChange={(e) => apply(e.target.value)} />
    </label>
  );
  const nSel = (Object.keys(value.groups) as GroupKey[]).filter((k) => value.groups[k].enabled).length;

  return (
    <div className="crash-mat-card" data-testid="crash-output">
      <details className="crash-mat-section">
        <summary>
          Çıktı ve zaman adımı{value.dtKind ? ` · /DT${value.dtKind === "DT" ? "" : `/${value.dtKind}`}` : ""}
        </summary>
        <div className="mesh-grid">
          {text("TH aralığı (ms)", value.thDt, (v) => set({ thDt: v }), "t_end/200")}
          {text("Animasyon (ms)", value.animDt, (v) => set({ animDt: v }), "t_end/20")}
        </div>
        <div className="crash-var-chips" role="group" aria-label="Zaman adımı kartı">
          {DT_KINDS.map((d) => (
            <button
              key={d.key || "none"}
              type="button"
              className={value.dtKind === d.key ? "crash-var-chip active" : "crash-var-chip"}
              aria-pressed={value.dtKind === d.key}
              disabled={disabled}
              onClick={() => set({ dtKind: d.key })}
            >
              {d.label}
            </button>
          ))}
        </div>
        <div className="mesh-grid">
          {text("Δt_sca", value.dtScale, (v) => set({ dtScale: v }), undefined, !value.dtKind)}
          {text("Δt_min (ms)", value.dtMin, (v) => set({ dtMin: v }), undefined, !value.dtKind)}
        </div>
        <div className="mesh-grid">
          {(
            [
              ["forceCfc", "Kuvvet CFC"],
              ["accCfc", "İvme CFC"],
            ] as const
          ).map(([key, lab]) => (
            <label key={key} className="mesh-field">
              <span>{lab}</span>
              <select
                aria-label={lab}
                value={value[key]}
                disabled={disabled}
                onChange={(e) => set({ [key]: e.target.value })}
              >
                <option value="">Yok (ham)</option>
                {[60, 180, 600, 1000].map((c) => (
                  <option key={c} value={String(c)}>
                    CFC {c}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <p className="material-assign-hint">
          CFC (SAE J211): ham eğri korunur, süzülmüş ayrıca eklenir; ivme bileşen bazında
          süzülür, HIC süzülmüşten de hesaplanır.
        </p>
        <p className="material-assign-hint">
          Boş aralık = varsayılan. Δt_sca 0 = Radioss 0.9. NODA/CST/0 Δt_min'i tutmak için kütle
          ekler; eklenen kütle sonuçta.
        </p>
      </details>

      <details className="crash-mat-section">
        <summary>Zaman geçmişi — /TH · {nSel} grup</summary>
        {(Object.keys(GROUP_LABELS) as GroupKey[]).map((k) => (
          <div key={k} className="crash-th-group">
            <label className="material-check">
              <input
                type="checkbox"
                checked={value.groups[k].enabled}
                disabled={disabled}
                onChange={(e) => setGroup(k, { enabled: e.target.checked })}
              />
              {GROUP_LABELS[k]}
            </label>
            {value.groups[k].enabled && (
              <VarChips
                vars={TH_VARS[k]}
                selected={value.groups[k].vars}
                onChange={(vars) => setGroup(k, { vars })}
                disabled={disabled}
                label={`${GROUP_LABELS[k]} değişkenleri`}
              />
            )}
          </div>
        ))}
        <div className="crash-th-group">
          {text("Düğüm — /TH/NODE (kimlikler)", value.nodeIds, (v) => set({ nodeIds: v }), "ör. 12, 480")}
          <VarChips
            vars={TH_VARS.node}
            selected={value.nodeVars}
            onChange={(nodeVars) => set({ nodeVars })}
            disabled={disabled}
            label="Düğüm değişkenleri"
          />
        </div>
        <p className="material-assign-hint">
          Sütunlar Radioss sırasıyla yazılır. İvme mm/ms²; HIC ilk düğümden, filtresiz.
        </p>
      </details>

      <details className="crash-mat-section" open={value.sections.length > 0 || undefined}>
        <summary>
          Kesitler — /SECT/PARAL{value.sections.length > 0 ? ` · ${value.sections.length}` : ""}
        </summary>
        {value.sections.map((r, i) => {
          const k = i + 1;
          const vecRow = (key: "m" | "m1" | "m2", label: string) => (
            <div className="mesh-grid">
              {(["x", "y", "z"] as const).map((ax, j) => (
                <label key={ax} className="mesh-field">
                  <span>
                    {label} {ax}
                  </span>
                  <input
                    aria-label={`Kesit ${k} ${label} ${ax}`}
                    value={r[key][j]}
                    disabled={disabled}
                    onChange={(e) => {
                      const next = [...r[key]] as [string, string, string];
                      next[j] = e.target.value;
                      setSection(r.id, { [key]: next });
                    }}
                  />
                </label>
              ))}
            </div>
          );
          return (
            <div key={r.id} className="crash-contact-card" data-testid={`crash-section-${k}`}>
              <div className="crash-contact-head">
                <strong>Kesit {k}</strong>
                <input
                  className="crash-section-name"
                  aria-label={`Kesit ${k} adı`}
                  value={r.name}
                  disabled={disabled}
                  onChange={(e) => setSection(r.id, { name: e.target.value })}
                />
                <button
                  type="button"
                  className="crash-contact-remove"
                  aria-label={`Kesit ${k} sil`}
                  disabled={disabled}
                  onClick={() => set({ sections: value.sections.filter((x) => x.id !== r.id) })}
                >
                  ×
                </button>
              </div>
              {vecRow("m", "M")}
              {vecRow("m1", "M1")}
              {vecRow("m2", "M2")}
              <div className="crash-var-chips" role="group" aria-label={`Kesit ${k} parçaları`}>
                {partOptions.map((pid) => {
                  const on = r.parts.includes(pid);
                  return (
                    <button
                      key={pid}
                      type="button"
                      className={on ? "crash-var-chip active" : "crash-var-chip"}
                      aria-pressed={on}
                      disabled={disabled}
                      onClick={() =>
                        setSection(r.id, { parts: on ? r.parts.filter((p) => p !== pid) : [...r.parts, pid] })
                      }
                    >
                      #{pid}
                    </button>
                  );
                })}
                <span className="crash-var-note">{r.parts.length === 0 ? "seçim yok = tümü" : ""}</span>
              </div>
              <label className="mesh-field">
                <span>Iframe (moment merkezi)</span>
                <select
                  aria-label={`Kesit ${k} Iframe`}
                  value={r.iframe}
                  disabled={disabled}
                  onChange={(e) => setSection(r.id, { iframe: e.target.value })}
                >
                  <option value="10">10 · global eksen C0</option>
                  <option value="11">11 · kesit geometrik merkezi</option>
                  <option value="12">12 · kesit ağırlık merkezi</option>
                  <option value="13">13 · (0, 0, 0)</option>
                </select>
              </label>
            </div>
          );
        })}
        <button
          type="button"
          className="doe-btn doe-btn-ghost crash-contact-add"
          disabled={disabled}
          onClick={() => {
            sectionSeq += 1;
            set({
              sections: [
                ...value.sections,
                {
                  id: sectionSeq,
                  name: `section_${value.sections.length + 1}`,
                  m: ["0", "0", "0"],
                  m1: ["0", "0", "0"],
                  m2: ["0", "0", "0"],
                  parts: [],
                  iframe: "10",
                },
              ],
            });
          }}
        >
          + Kesit ekle
        </button>
        <p className="material-assign-hint">
          Paralelkenar M, M1, M2 (mm); kesitten geçen elemanlar. Kuvvet = FN + FT (global); FN/FT
          ayrımı Radioss'un kesit normaline bağlı.
        </p>
      </details>
    </div>
  );
}
