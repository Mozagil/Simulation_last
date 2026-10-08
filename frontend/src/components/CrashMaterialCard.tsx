import { Fragment, useState, type ReactNode } from "react";
import type { CrashModelPayload } from "../api/crash";
import ButtonGroup from "./ButtonGroup";
import { KwRef } from "./Kw";

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
    // Kullanıcı 2026-10-08: elle kurulan crash koşusu LAW2 (elasto-plastik) ile
    // başlar — hızlı senaryo / DOE ile aynı. LAW1 elastikte kutu ezilmez, seker.
    law: "plastic",
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

/** Kullanıcı 2026-10-07: "kopma / FAIL nedir, hangi senaryoda" — düz Türkçe açıklamalar. */
const LAW_HINT: Record<CrashLaw, string> = {
  elastic:
    "Elastik: malzeme yalnız yaylanır, yük kalkınca eski haline döner; kalıcı ezilme olmaz. Doğrulama koşuları ya da gerçekten esnek kalan parçalar (ör. rijit sayılan çarpıcı) için.",
  plastic:
    "Elasto-plastik: akma gerilmesini (σy) aşınca kalıcı şekil değiştirir, ezilir; pekleştikçe sertleşir (σ = σy + b·εpⁿ). Metal çarpışmalarının olağan seçimi.",
  tabulated:
    "Tablolu eğri: ölçülmüş gerilme–plastik gerinim eğrilerini (farklı hızlarda) doğrudan kullanır. Elinde test eğrisi varsa.",
};

/** Aç / kapa bölüm (kullanıcı 2026-10-08: yer kaplamasın). Kapalıyken
 * değiştirilen alanlar başlıkta özetlenir. İçerik DOM'da kalır (gizli). */
function Fold({
  title,
  formula,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  formula?: string;
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={open ? "crash-fold open" : "crash-fold"}>
      <button type="button" className="crash-fold-head" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="crash-fold-chev" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <strong>{title}</strong>
        {formula && <span className="crash-formula">{formula}</span>}
        <span className="crash-fold-summary">{summary}</span>
      </button>
      <div className="crash-fold-body" hidden={!open}>
        {children}
      </div>
    </div>
  );
}

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
  /** Varsayılandan farklı alanlar: "c 0.014 · ε̇₀ 1"; hiçbiri yoksa "varsayılan". */
  const changed = (pairs: [ScalarKey, string][]) => {
    const d = defaultMatCard();
    const out = pairs.filter(([k]) => value[k].trim() !== "" && value[k] !== d[k]).map(([k, l]) => `${l} ${value[k]}`);
    return out.length ? out.join(" · ") : "varsayılan";
  };
  const field = (key: ScalarKey, label: string) => (
    <label className="mesh-field">
      <span>{label}</span>
      <input value={value[key]} disabled={disabled} onChange={(e) => set({ [key]: e.target.value })} />
    </label>
  );
  /** Uzman düzeni alanı: kısa etiket + birim; erişilebilir ad eski etiket (testler / ekran okuyucu). */
  const xf = (key: ScalarKey, aria: string, label: string, unit?: string, placeholder = "boş") => (
    <label className="crash-expert-field" key={key}>
      <span>{label}</span>
      <span className="crash-card-input">
        <input aria-label={aria} value={value[key]} placeholder={placeholder} disabled={disabled} onChange={(e) => set({ [key]: e.target.value })} />
        {unit && <span className="crash-card-unit">{unit}</span>}
      </span>
    </label>
  );
  const xfail = <R extends FailJohnsonRow | FailTensRow>(
    row: R,
    key: keyof R & string,
    aria: string,
    label: string,
    apply: (next: R) => void,
    unit?: string,
  ) => (
    <label className="crash-expert-field" key={key}>
      <span>{label}</span>
      <span className="crash-card-input">
        <input aria-label={aria} value={row[key] as string} placeholder="boş" disabled={disabled} onChange={(e) => apply({ ...row, [key]: e.target.value })} />
        {unit && <span className="crash-card-unit">{unit}</span>}
      </span>
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
      <p className="crash-behavior-hint" data-testid="crash-law-hint">{LAW_HINT[law]}</p>
      <KwRef card={law === "elastic" ? "/MAT/LAW1" : law === "plastic" ? "/MAT/LAW2" : "/MAT/LAW36"} />

      {law === "plastic" && (
        <div className="crash-law-sections">
          <Fold
            title="Akma ve pekleşme"
            formula="σ = a + b·εₚⁿ"
            summary={changed([["sigmaY", "a"], ["hardenB", "b"], ["hardenN", "n"], ["sigMax0", "SIG_max0"]])}
            defaultOpen
          >
          <p className="crash-behavior-hint">
            a = akma (boşsa kütüphane malzemesinin Rp0.2'si); b, n pekleşme — b büyüdükçe ezildikçe daha çok
            sertleşir. SIG_max0: gerilme tavanı (boş = yok).
          </p>
          <div className="crash-expert-grid cols-2">
            {xf("sigmaY", "σy (Pa) — boşsa atanan malzeme", "a · akma σy", "Pa", "kütüphane")}
            {xf("sigMax0", "SIG_max0 (MPa)", "SIG_max0 · tavan", "MPa")}
            {xf("hardenB", "LAW2 b (MPa)", "b · pekleşme", "MPa")}
            {xf("hardenN", "LAW2 n", "n · üs")}
          </div>
          </Fold>

          <Fold
            title="Hız etkisi"
            formula="σ·(1 + c·ln(ε̇/ε̇₀))"
            summary={changed([["jcC", "c"], ["jcEps0", "ε̇₀"], ["jcIcc", "ICC"], ["jcFsmooth", "Fsmooth"], ["jcFcut", "F_cut"], ["jcChard", "Chard"]])}
          >
          <p className="crash-behavior-hint">
            Metaller hızlı yüklemede sertleşir: σ × (1 + c·ln(ε̇/ε̇₀)). c = 0 → hız etkisi yok. Fsmooth / F_cut
            şekil değiştirme hızını süzer.
          </p>
          <div className="crash-expert-grid cols-3">
            {xf("jcC", "c", "c · hız katsayısı")}
            {xf("jcEps0", "ε̇₀ (1/s)", "ε̇₀ · referans", "1/s")}
            {xf("jcIcc", "ICC", "ICC")}
            {xf("jcFsmooth", "Fsmooth", "Fsmooth")}
            {xf("jcFcut", "F_cut (Hz)", "F_cut", "Hz")}
            {xf("jcChard", "Chard", "Chard")}
          </div>
          </Fold>

          <Fold title="Sıcaklık etkisi" summary={changed([["jcM", "m"], ["jcTmelt", "T_melt"], ["jcTr", "T_r"], ["jcRhoCp", "ρCp"]])}>
          <p className="crash-behavior-hint">
            Plastik iş ısıya döner, malzeme yumuşar: m üssü, erime ve referans sıcaklığı, ρ·Cp. Boş = sıcaklık
            etkisi yok.
          </p>
          <div className="crash-expert-grid cols-2">
            {xf("jcM", "m", "m · yumuşama üssü")}
            {xf("jcTmelt", "T_melt (K)", "T_melt · erime", "K")}
            {xf("jcTr", "T_r (K)", "T_r · referans", "K")}
            {xf("jcRhoCp", "ρCp (J/m³K)", "ρ·Cp", "J/m³K")}
          </div>
          </Fold>

          <Fold title="Basit kopma sınırı" summary={changed([["epsPMax", "EPS_p_max"]])}>
          <p className="crash-behavior-hint">
            Bu plastik gerinime ulaşan eleman silinir (boş = kapalı). Daha ayrıntılı kopma için aşağıdaki /FAIL kartları.
          </p>
          <div className="crash-expert-grid cols-2">
            {xf("epsPMax", "EPS_p_max", "EPS_p_max · kopma gerinimi")}
          </div>
          </Fold>
        </div>
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

      <div className="crash-law-sections">
        <Fold
          title="Kopma / hasar · /FAIL"
          summary={failCount > 0 ? `${failCount} kriter: ${[j && "Johnson–Cook", t && "çekme gerinimi"].filter(Boolean).join(" + ")}` : "kapalı"}
          defaultOpen={failCount > 0}
        >
        <p className="crash-behavior-hint" data-testid="crash-fail-intro">
          Kapalıyken malzeme ne kadar uzarsa uzasın kopmaz — sac yırtılmaz, mermi delmez; yalnız ezilir ve
          bükülür. Açıkken kriteri sağlayan eleman silinir; silinen eleman sayısı sonuçlarda yazar. Tipik:
          delinme (plaka–küre, kuş), kırılgan parça, yırtılan sac. Yalnız ezilme incelenen koşularda (crash box)
          çoğunlukla kapalı.
        </p>
        <div className={j ? "crash-fail-tile active" : "crash-fail-tile"}>
          <label className="crash-fail-head">
            <input
              type="checkbox"
              aria-label="/FAIL/JOHNSON"
              checked={j != null}
              disabled={disabled}
              onChange={(e) => set({ failJohnson: e.target.checked ? { ...JOHNSON_DEFAULT } : null })}
            />
            <span className="crash-fail-text">
              <strong>Johnson–Cook hasarı</strong>
              <span>Kopma gerinimi gerilme durumuna, hıza, sıcaklığa bağlı (D1–D5). En gerçekçi, en çok veri isteyen.</span>
            </span>
            <code>/FAIL/JOHNSON</code>
          </label>
          <KwRef card="/FAIL/JOHNSON" />
          {j && (
            <div className="crash-expert-grid cols-5">
              {(["d1", "d2", "d3", "d4", "d5"] as const).map((k) => (
                <Fragment key={k}>{xfail(j, k, k.toUpperCase(), k.toUpperCase(), (n) => set({ failJohnson: n }))}</Fragment>
              ))}
            </div>
          )}
          {j && (
            <div className="crash-expert-grid cols-4">
              {xfail(j, "eps0", "ε̇₀ (1/s)", "ε̇₀", (n) => set({ failJohnson: n }), "1/s")}
              {xfail(j, "ifailSh", "Ifail_sh", "Ifail_sh", (n) => set({ failJohnson: n }))}
              {xfail(j, "ifailSo", "Ifail_so", "Ifail_so", (n) => set({ failJohnson: n }))}
              {xfail(j, "dadv", "Dadv", "Dadv", (n) => set({ failJohnson: n }))}
            </div>
          )}
        </div>
        <div className={t ? "crash-fail-tile active" : "crash-fail-tile"}>
          <label className="crash-fail-head">
            <input
              type="checkbox"
              aria-label="/FAIL/TENSSTRAIN"
              checked={t != null}
              disabled={disabled}
              onChange={(e) => set({ failTens: e.target.checked ? { ...TENS_DEFAULT } : null })}
            />
            <span className="crash-fail-text">
              <strong>Çekme gerinimi</strong>
              <span>ε_t1'de hasar başlar, ε_f1'de eleman silinir (çekme deneyindeki kopma uzaması). Basit, az veri.</span>
            </span>
            <code>/FAIL/TENSSTRAIN</code>
          </label>
          <KwRef card="/FAIL/TENSSTRAIN" />
          {t && (
            <div className="crash-expert-grid cols-5">
              {xfail(t, "t1", "ε_t1", "ε_t1", (n) => set({ failTens: n }))}
              {xfail(t, "t2", "ε_t2", "ε_t2", (n) => set({ failTens: n }))}
              {xfail(t, "f1", "ε_f1", "ε_f1", (n) => set({ failTens: n }))}
              {xfail(t, "f2", "ε_f2", "ε_f2", (n) => set({ failTens: n }))}
              {xfail(t, "sflag", "S_Flag", "S_Flag", (n) => set({ failTens: n }))}
            </div>
          )}
        </div>
        <p className="material-assign-hint">S_Flag: 0, 1, 11, 21 · Ifail: 0, 1, 2 (Radioss bayrakları; boş = varsayılan).</p>
        </Fold>
      </div>
    </div>
  );
}
