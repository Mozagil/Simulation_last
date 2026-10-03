import { Fragment } from "react";
import type { CrashModelPayload } from "../api/crash";
import ButtonGroup from "./ButtonGroup";

/** Malzeme kartı (1.14e): LAW1 / LAW2 (+ Johnson-Cook hız/sıcaklık) / LAW36 tablo
 * ve /FAIL kriterleri. Alanlar ham metin; sayıya gönderimde çevrilir. Öneri yok:
 * 0 = terim kapalı / Radioss varsayılanı, mühendis doldurur. */

export type CrashLaw = "elastic" | "plastic" | "tabulated";

export interface TabCurveRow {
  id: number;
  /** ε̇ (1/s) */
  rate: string;
  /** satır başına "ε_p σ(MPa)" — Excel'den yapıştırılabilir */
  points: string;
}

export interface FailJohnsonRow {
  d1: string;
  d2: string;
  d3: string;
  d4: string;
  d5: string;
  eps0: string;
  ifailSh: string;
  ifailSo: string;
  dadv: string;
}

export interface FailTensRow {
  t1: string;
  t2: string;
  f1: string;
  f2: string;
  sflag: string;
}

export interface MatCardState {
  law: CrashLaw;
  sigmaY: string;
  hardenB: string;
  hardenN: string;
  epsPMax: string;
  sigMax0: string;
  jcC: string;
  jcEps0: string;
  jcIcc: string;
  jcFsmooth: string;
  jcFcut: string;
  jcChard: string;
  jcM: string;
  jcTmelt: string;
  jcRhoCp: string;
  jcTr: string;
  tabCurves: TabCurveRow[];
  /** 1.17g — LAW36 eğrileri istekte değil, atanan malzemeden (1.14c2) */
  curvesFromMaterial: boolean;
  tabEpsT: string;
  tabEpsM: string;
  tabEpsF: string;
  tabVp: string;
  failJohnson: FailJohnsonRow | null;
  failTens: FailTensRow | null;
}

let curveSeq = 0;

function newCurve(): TabCurveRow {
  curveSeq += 1;
  return { id: curveSeq, rate: "0", points: "" };
}

export function defaultMatCard(): MatCardState {
  return {
    law: "elastic",
    sigmaY: "",
    hardenB: "0",
    hardenN: "1",
    epsPMax: "0",
    sigMax0: "0",
    jcC: "0",
    jcEps0: "0",
    jcIcc: "0",
    jcFsmooth: "0",
    jcFcut: "0",
    jcChard: "0",
    jcM: "0",
    jcTmelt: "0",
    jcRhoCp: "0",
    jcTr: "0",
    tabCurves: [newCurve()],
    curvesFromMaterial: false,
    tabEpsT: "0",
    tabEpsM: "0",
    tabEpsF: "0",
    tabVp: "0",
    failJohnson: null,
    failTens: null,
  };
}

const JOHNSON_DEFAULT: FailJohnsonRow = {
  d1: "0", d2: "0", d3: "0", d4: "0", d5: "0", eps0: "0", ifailSh: "0", ifailSo: "0", dadv: "0",
};
const TENS_DEFAULT: FailTensRow = { t1: "0", t2: "0", f1: "0", f2: "0", sflag: "0" };

function num(raw: string, what: string): number {
  const v = Number(raw.trim().replace(",", "."));
  if (!raw.trim() || !Number.isFinite(v)) throw new Error(`${what}: sayı geçersiz (${raw || "boş"})`);
  return v;
}

/** "ε_p σ" satırları → noktalar. Ayırıcı boşluk / sekme / ";"; tek başına
 * virgül ayırıcı sayılır ("0.1,250"), sekmeyle gelen ondalık virgül nokta olur. */
export function parseCurvePoints(text: string, what: string): [number, number][] {
  const out: [number, number][] = [];
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t) continue;
    let tokens = t.split(/[\s;]+/);
    if (tokens.length === 1) tokens = t.split(",");
    if (tokens.length !== 2) throw new Error(`${what}: "${t}" iki sütun olmalı (ε_p σ)`);
    out.push([num(tokens[0], what), num(tokens[1], what)]);
  }
  return out;
}

/** Kart → CrashModelPayload'ın malzeme kısmı (eleman bayrakları hariç). */
export function matCardPayload(s: MatCardState, label = "Malzeme"): Partial<CrashModelPayload> {
  const sy = s.sigmaY.trim() ? num(s.sigmaY, `${label} σy`) : null;
  const out: Partial<CrashModelPayload> = {
    law: s.law,
    sigma_y_pa: sy,
    harden_b_mpa: num(s.hardenB, `${label} b`),
    harden_n: num(s.hardenN, `${label} n`),
  };
  if (s.law === "plastic") {
    Object.assign(out, {
      eps_p_max: num(s.epsPMax, `${label} EPS_p_max`),
      sig_max0_mpa: num(s.sigMax0, `${label} SIG_max0`),
      jc_c: num(s.jcC, `${label} c`),
      jc_eps_dot0_per_s: num(s.jcEps0, `${label} ε̇₀`),
      jc_icc: num(s.jcIcc, `${label} ICC`),
      jc_fsmooth: num(s.jcFsmooth, `${label} Fsmooth`),
      jc_fcut_hz: num(s.jcFcut, `${label} F_cut`),
      jc_chard: num(s.jcChard, `${label} Chard`),
      jc_m: num(s.jcM, `${label} m`),
      jc_t_melt_k: num(s.jcTmelt, `${label} T_melt`),
      jc_rho_cp: num(s.jcRhoCp, `${label} ρCp`),
      jc_t_r_k: num(s.jcTr, `${label} T_r`),
    });
  } else if (s.law === "tabulated") {
    Object.assign(out, {
      eps_p_max: num(s.epsPMax, `${label} EPS_p_max`),
      jc_fsmooth: num(s.jcFsmooth, `${label} Fsmooth`),
      jc_fcut_hz: num(s.jcFcut, `${label} F_cut`),
      jc_chard: num(s.jcChard, `${label} Chard`),
      // boş liste → backend parçaya atanmış malzemenin crash_curves'ünü kullanır
      tab_curves: s.curvesFromMaterial ? [] : s.tabCurves.map((c, i) => ({
        eps_dot_per_s: num(c.rate, `${label} eğri ${i + 1} ε̇`),
        points: parseCurvePoints(c.points, `${label} eğri ${i + 1}`),
      })),
      tab_eps_t: num(s.tabEpsT, `${label} Eps_t`),
      tab_eps_m: num(s.tabEpsM, `${label} Eps_m`),
      tab_eps_f: num(s.tabEpsF, `${label} Eps_f`),
      tab_vp: num(s.tabVp, `${label} VP`),
    });
  }
  const j = s.failJohnson;
  const t = s.failTens;
  if (j || t) {
    out.fail = {
      ...(j
        ? {
            johnson: {
              d1: num(j.d1, `${label} D1`),
              d2: num(j.d2, `${label} D2`),
              d3: num(j.d3, `${label} D3`),
              d4: num(j.d4, `${label} D4`),
              d5: num(j.d5, `${label} D5`),
              eps_dot0_per_s: num(j.eps0, `${label} FAIL ε̇₀`),
              ifail_sh: num(j.ifailSh, `${label} Ifail_sh`),
              ifail_so: num(j.ifailSo, `${label} Ifail_so`),
              dadv: num(j.dadv, `${label} Dadv`),
            },
          }
        : {}),
      ...(t
        ? {
            tensstrain: {
              eps_t1: num(t.t1, `${label} ε_t1`),
              eps_t2: num(t.t2, `${label} ε_t2`),
              eps_f1: num(t.f1, `${label} ε_f1`),
              eps_f2: num(t.f2, `${label} ε_f2`),
              s_flag: num(t.sflag, `${label} S_Flag`),
            },
          }
        : {}),
    };
  }
  return out;
}

type ScalarKey = {
  [K in keyof MatCardState]: MatCardState[K] extends string ? K : never;
}[keyof MatCardState];

export default function CrashMaterialCard({
  value,
  onChange,
  disabled = false,
  testId,
}: {
  value: MatCardState;
  onChange: (next: MatCardState) => void;
  disabled?: boolean;
  testId?: string;
}) {
  const set = (patch: Partial<MatCardState>) => onChange({ ...value, ...patch });
  const field = (key: ScalarKey, label: string) => (
    <label className="mesh-field">
      <span>{label}</span>
      <input value={value[key]} disabled={disabled} onChange={(e) => set({ [key]: e.target.value })} />
    </label>
  );
  const failField = <R extends FailJohnsonRow | FailTensRow>(
    row: R,
    key: keyof R & string,
    label: string,
    apply: (next: R) => void,
  ) => (
    <label className="mesh-field">
      <span>{label}</span>
      <input
        value={row[key] as string}
        disabled={disabled}
        onChange={(e) => apply({ ...row, [key]: e.target.value })}
      />
    </label>
  );
  const law = value.law;
  const j = value.failJohnson;
  const t = value.failTens;
  const failCount = (j ? 1 : 0) + (t ? 1 : 0);

  return (
    <div className="crash-mat-card" data-testid={testId}>
      <ButtonGroup
        title="LAW"
        items={[
          { key: "elastic", label: "LAW1 elastik", active: law === "elastic", disabled, onClick: () => set({ law: "elastic" }) },
          { key: "plastic", label: "LAW2 plastik", active: law === "plastic", disabled, onClick: () => set({ law: "plastic" }) },
          { key: "tabulated", label: "LAW36 tablo", active: law === "tabulated", disabled, onClick: () => set({ law: "tabulated" }) },
        ]}
      />

      {law === "plastic" && (
        <>
          <div className="mesh-grid">
            {field("sigmaY", "σy (Pa) — boşsa atanan malzeme")}
            {field("hardenB", "LAW2 b (MPa)")}
            {field("hardenN", "LAW2 n")}
            {field("epsPMax", "EPS_p_max")}
            {field("sigMax0", "SIG_max0 (MPa)")}
          </div>
          <details className="crash-mat-section">
            <summary>Johnson-Cook hız / sıcaklık</summary>
            <div className="mesh-grid">
              {field("jcC", "c")}
              {field("jcEps0", "ε̇₀ (1/s)")}
              {field("jcIcc", "ICC")}
              {field("jcFsmooth", "Fsmooth")}
              {field("jcFcut", "F_cut (Hz)")}
              {field("jcChard", "Chard")}
              {field("jcM", "m")}
              {field("jcTmelt", "T_melt (K)")}
              {field("jcRhoCp", "ρCp (J/m³K)")}
              {field("jcTr", "T_r (K)")}
            </div>
          </details>
        </>
      )}

      {law === "tabulated" && (
        <>
          <label className="material-check">
            <input
              type="checkbox"
              checked={value.curvesFromMaterial}
              disabled={disabled}
              onChange={(e) => set({ curvesFromMaterial: e.target.checked })}
            />
            Eğriler malzemeden (3 · Material → Crash LAW36 eğrileri)
          </label>
          {!value.curvesFromMaterial && (
          <>
          <div className="crash-mat-curves">
            {value.tabCurves.map((c, i) => (
              <div key={c.id} className="crash-mat-curve">
                <div className="crash-contact-head">
                  <strong>Eğri {i + 1}</strong>
                  <label className="crash-mat-rate">
                    <span>ε̇ (1/s)</span>
                    <input
                      aria-label={`Eğri ${i + 1} ε̇`}
                      value={c.rate}
                      disabled={disabled}
                      onChange={(e) =>
                        set({ tabCurves: value.tabCurves.map((r) => (r.id === c.id ? { ...r, rate: e.target.value } : r)) })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="crash-contact-remove"
                    aria-label={`Eğri ${i + 1} sil`}
                    disabled={disabled || value.tabCurves.length === 1}
                    onClick={() => set({ tabCurves: value.tabCurves.filter((r) => r.id !== c.id) })}
                  >
                    ×
                  </button>
                </div>
                <textarea
                  aria-label={`Eğri ${i + 1} noktaları`}
                  className="crash-mat-points"
                  rows={4}
                  placeholder={"ε_p  σ (MPa)\n0     235\n0.2   320"}
                  value={c.points}
                  disabled={disabled}
                  onChange={(e) =>
                    set({ tabCurves: value.tabCurves.map((r) => (r.id === c.id ? { ...r, points: e.target.value } : r)) })
                  }
                />
              </div>
            ))}
          </div>
          <button
            type="button"
            className="doe-btn doe-btn-ghost crash-contact-add"
            disabled={disabled}
            onClick={() => set({ tabCurves: [...value.tabCurves, newCurve()] })}
          >
            + Eğri ekle
          </button>
          <p className="material-assign-hint">
            Satır başına ε_p ve gerçek gerilme σ (MPa); ε_p kesin artan, eğriler ε̇ artan
            sırada. Excel'den iki sütun yapıştırılabilir.
          </p>
          </>
          )}
          <div className="mesh-grid">
            {field("tabEpsT", "Eps_t")}
            {field("tabEpsM", "Eps_m")}
            {field("tabEpsF", "Eps_f")}
            {field("tabVp", "VP")}
            {field("epsPMax", "EPS_p_max")}
            {field("jcFsmooth", "Fsmooth")}
            {field("jcFcut", "F_cut (Hz)")}
            {field("jcChard", "Chard")}
          </div>
        </>
      )}

      <details className="crash-mat-section" open={failCount > 0 || undefined}>
        <summary>
          Kopma — /FAIL{failCount > 0 ? ` · ${failCount} kriter` : ""}
        </summary>
        <label className="material-check">
          <input
            type="checkbox"
            checked={j != null}
            disabled={disabled}
            onChange={(e) => set({ failJohnson: e.target.checked ? { ...JOHNSON_DEFAULT } : null })}
          />
          /FAIL/JOHNSON
        </label>
        {j && (
          <div className="mesh-grid">
            {(["d1", "d2", "d3", "d4", "d5"] as const).map((k) => (
              <Fragment key={k}>
                {failField(j, k, k.toUpperCase(), (n) => set({ failJohnson: n }))}
              </Fragment>
            ))}
            {failField(j, "eps0", "ε̇₀ (1/s)", (n) => set({ failJohnson: n }))}
            {failField(j, "ifailSh", "Ifail_sh", (n) => set({ failJohnson: n }))}
            {failField(j, "ifailSo", "Ifail_so", (n) => set({ failJohnson: n }))}
            {failField(j, "dadv", "Dadv", (n) => set({ failJohnson: n }))}
          </div>
        )}
        <label className="material-check">
          <input
            type="checkbox"
            checked={t != null}
            disabled={disabled}
            onChange={(e) => set({ failTens: e.target.checked ? { ...TENS_DEFAULT } : null })}
          />
          /FAIL/TENSSTRAIN
        </label>
        {t && (
          <div className="mesh-grid">
            {failField(t, "t1", "ε_t1", (n) => set({ failTens: n }))}
            {failField(t, "t2", "ε_t2", (n) => set({ failTens: n }))}
            {failField(t, "f1", "ε_f1", (n) => set({ failTens: n }))}
            {failField(t, "f2", "ε_f2", (n) => set({ failTens: n }))}
            {failField(t, "sflag", "S_Flag", (n) => set({ failTens: n }))}
          </div>
        )}
        <p className="material-assign-hint">
          Kriter sağlanınca eleman silinir; silinen eleman sayısı iş sonucunda. S_Flag: 0, 1,
          11, 21. Ifail: 0, 1, 2.
        </p>
      </details>
    </div>
  );
}
