/** 1.24g — kütüphane Johnson–Cook seti → LAW2 kartı alanları; σ–εₚ eğrileri (önizleme).
 * Boş (null) alan karta yazılmaz — kartın mevcut değeri kalır; tahmin yok. */

import type { CrashJcSet } from "../api/materials";
import type { MatCardState } from "../components/CrashMaterialCard";

export interface JcSource {
  /** Malzeme adı (ör. "7075-T6") */
  label: string;
  jc: CrashJcSet;
}

const s = (v: number) => String(Number(v.toPrecision(6)));

/** JC seti → LAW2 kart yaması (A MPa → σy Pa; B MPa; ε̇₀, m, T_m, T_r yalnız doluysa; D → /FAIL/JOHNSON). */
export function jcToCard(jc: CrashJcSet, card: MatCardState): Partial<MatCardState> {
  const patch: Partial<MatCardState> = {
    law: "plastic",
    sigmaY: s(jc.a_mpa * 1e6),
    hardenB: s(jc.b_mpa),
    hardenN: s(jc.n),
    jcC: s(jc.c),
  };
  if (jc.eps_dot0_per_s != null) patch.jcEps0 = s(jc.eps_dot0_per_s);
  if (jc.m != null) patch.jcM = s(jc.m);
  if (jc.t_melt_k != null) patch.jcTmelt = s(jc.t_melt_k);
  if (jc.t_ref_k != null) patch.jcTr = s(jc.t_ref_k);
  if (jc.d && jc.d.length === 5) {
    const [d1, d2, d3, d4, d5] = jc.d.map(s);
    patch.failJohnson = { ...(card.failJohnson ?? { eps0: "0", ifailSh: "0", ifailSo: "0", dadv: "0" }), d1, d2, d3, d4, d5 } as MatCardState["failJohnson"];
  }
  return patch;
}

/** σ = A + B·εₚⁿ (MPa), εₚ ∈ [0, epsMax] — referans hız ve sıcaklıkta (C ve m terimleri 1). */
export function jcStressCurve(aMpa: number, bMpa: number, n: number, epsMax = 0.5, steps = 50): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const e = (epsMax * i) / steps;
    out.push([e, aMpa + bMpa * (e === 0 ? 0 : Math.pow(e, n))]);
  }
  return out;
}
