/**
 * 1.23 B1c — "Kurulumu yükle": /crash/scenario (setup_only) yanıtındaki
 * /crash/solve gövdesini arayüz durumuna çevirir (malzeme kartı, ek tanım
 * kartları). Yalnız ters eşleme; değer yorumlamaz.
 */
import { defaultMatCard, type MatCardState } from "../components/CrashMaterialCard";
import { newCard, railDofs, type Axis, type LoadCard } from "../components/CrashLoadCards";
import type { CrashModelPayload } from "../api/crash";

type Rec = Record<string, unknown>;

const str = (v: unknown, fallback: string): string => (typeof v === "number" && Number.isFinite(v) ? String(v) : fallback);

/** /crash/solve `model` → malzeme kartı (LAW, sertleşme, /FAIL, LAW36 eğrileri). */
export function matCardFromModel(model: Partial<CrashModelPayload> | Rec | null | undefined): MatCardState {
  const d = defaultMatCard();
  if (!model) return d;
  const m = model as Rec;
  const law = m.law === "elastic" || m.law === "tabulated" || m.law === "plastic" ? m.law : d.law;
  const out: MatCardState = {
    ...d,
    law,
    sigmaY: str(m.sigma_y_pa, d.sigmaY),
    hardenB: str(m.harden_b_mpa, d.hardenB),
    hardenN: str(m.harden_n, d.hardenN),
    epsPMax: str(m.eps_p_max, d.epsPMax),
    sigMax0: str(m.sig_max0_mpa, d.sigMax0),
    jcC: str(m.jc_c, d.jcC),
    jcEps0: str(m.jc_eps_dot0_per_s, d.jcEps0),
    jcIcc: str(m.jc_icc, d.jcIcc),
    jcFsmooth: str(m.jc_fsmooth, d.jcFsmooth),
    jcFcut: str(m.jc_fcut_hz, d.jcFcut),
    jcChard: str(m.jc_chard, d.jcChard),
    jcM: str(m.jc_m, d.jcM),
    jcTmelt: str(m.jc_t_melt_k, d.jcTmelt),
    jcRhoCp: str(m.jc_rho_cp, d.jcRhoCp),
    jcTr: str(m.jc_t_r_k, d.jcTr),
    tabEpsT: str(m.tab_eps_t, d.tabEpsT),
    tabEpsM: str(m.tab_eps_m, d.tabEpsM),
    tabEpsF: str(m.tab_eps_f, d.tabEpsF),
    tabVp: str(m.tab_vp, d.tabVp),
  };
  if (Array.isArray(m.tab_curves)) {
    const curves = m.tab_curves as { eps_dot_per_s?: number; points?: number[][] }[];
    out.curvesFromMaterial = curves.length === 0;
    if (curves.length) {
      out.tabCurves = curves.map((c, i) => ({
        id: i + 1,
        rate: str(c.eps_dot_per_s, "0"),
        points: (c.points ?? []).map((p) => p.join(" ")).join("\n"),
      }));
    }
  }
  const fail = (m.fail ?? null) as Rec | null;
  const j = fail?.johnson as Rec | undefined;
  const t = fail?.tensstrain as Rec | undefined;
  out.failJohnson = j
    ? {
        d1: str(j.d1, "0"), d2: str(j.d2, "0"), d3: str(j.d3, "0"), d4: str(j.d4, "0"), d5: str(j.d5, "0"),
        eps0: str(j.eps_dot0_per_s, "1"), ifailSh: str(j.ifail_sh, "1"), ifailSo: str(j.ifail_so, "1"),
        dadv: str(j.dadv, "0"),
      }
    : null;
  out.failTens = t
    ? { t1: str(t.eps_t1, "0"), t2: str(t.eps_t2, "0"), f1: str(t.eps_f1, "0"), f2: str(t.eps_f2, "0"), sflag: str(t.s_flag, "1") }
    : null;
  return out;
}

function targetString(r: Rec): string {
  if (typeof r.part_id === "number") return `part:${r.part_id}`;
  if (typeof r.region === "string") return `region:${r.region}`;
  return "";
}

/** /crash/solve kart listeleri → Ek tanımlar kartları (ilk hız, kilit, sabit hız, kütle/kızak). */
export function cardsFromRequest(req: Rec, impactAxis: Axis): LoadCard[] {
  const cards: LoadCard[] = [];
  let id = 0;
  const next = (kind: LoadCard["kind"], r: Rec) => newCard(++id, kind, targetString(r));
  const list = (k: string) => (Array.isArray(req[k]) ? (req[k] as Rec[]) : []);

  for (const r of list("initial_velocities")) {
    const c = next("inivel", r);
    c.speed = str(r.speed_m_s, c.speed);
    if (Array.isArray(r.direction)) c.dir = (r.direction as number[]).map(String) as [string, string, string];
    cards.push(c);
  }
  const rbBcs = new Map<string, string>();
  for (const r of list("boundary_conditions")) {
    if (typeof r.rigid_body === "string") {
      rbBcs.set(r.rigid_body, String(r.dofs ?? ""));
      continue;
    }
    const c = next("bcs", r);
    c.dofs = String(r.dofs ?? c.dofs);
    cards.push(c);
  }
  for (const r of list("imposed_velocities")) {
    const c = next("impvel", r);
    if (r.direction === "X" || r.direction === "Y" || r.direction === "Z") c.axis = r.direction;
    c.velocity = str(r.velocity_m_s, c.velocity);
    c.tStart = str(r.t_start_ms, c.tStart);
    c.tStop = str(r.t_stop_ms, c.tStop);
    cards.push(c);
  }
  for (const r of list("rigid_bodies")) {
    const c = next("rbody", r);
    c.mass = str(r.mass_kg, "");
    c.hic = r.th_accel === true;
    c.keepWall = r.ikrem === 1;
    const dofs = typeof r.name === "string" ? rbBcs.get(r.name) : undefined;
    if (dofs) {
      if (dofs === railDofs(impactAxis)) c.rbMotion = "rail";
      else {
        c.rbMotion = "custom";
        c.dofs = dofs;
      }
    }
    cards.push(c);
  }
  // 1.23 C4 — /ADMAS ek kütle
  for (const r of list("added_masses")) {
    const c = next("admas", r);
    c.mass = str(r.mass_kg, "");
    c.massDist = r.distribution === "per_node" ? "per_node" : "total";
    cards.push(c);
  }
  return cards;
}
