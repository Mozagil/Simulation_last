/**
 * OpenRadioss kartı → LS-DYNA keyword karşılığı — yalnız bilgi amaçlı ad
 * (kullanıcı kararı 2026-10-08, CLAUDE.md kural 2 istisnası). Hiçbir kod
 * LS-DYNA çağırmaz ya da onun formatında dosya yazmaz. Eşlemeler birebir
 * değil, yaklaşık ("≈").
 *
 * Gösterim kişisel tercih: localStorage (yoksa kapalı).
 */
import { useSyncExternalStore } from "react";

export const DYNA_EQUIV: Record<string, string> = {
  "/MAT/LAW1": "*MAT_ELASTIC (001)",
  "/MAT/LAW2": "*MAT_JOHNSON_COOK (015) / *MAT_PIECEWISE_LINEAR_PLASTICITY (024)",
  "/MAT/LAW36": "*MAT_PIECEWISE_LINEAR_PLASTICITY (024) + LCSS tablo",
  "/FAIL/JOHNSON": "*MAT_015 hasar (D1–D5)",
  "/FAIL/TENSSTRAIN": "*MAT_ADD_EROSION (MXEPS)",
  "/RWALL": "*RIGIDWALL_PLANAR",
  "/RWALL/CYL": "*RIGIDWALL_GEOMETRIC_CYLINDER",
  "/INIVEL": "*INITIAL_VELOCITY_GENERATION",
  "/BCS": "*BOUNDARY_SPC_SET",
  "/IMPVEL": "*BOUNDARY_PRESCRIBED_MOTION_SET",
  "/RBODY": "*CONSTRAINED_NODAL_RIGID_BODY (+ *ELEMENT_MASS)",
  "/ADMAS": "*ELEMENT_MASS_PART",
  "/GRAV": "*LOAD_BODY_X / _Y / _Z",
  "/INTER/TYPE7": "*CONTACT_AUTOMATIC_NODES_TO_SURFACE (öz temas: _SINGLE_SURFACE)",
  "/INTER/TYPE24": "*CONTACT_AUTOMATIC_SURFACE_TO_SURFACE (SOFT=2; tüm model: _SINGLE_SURFACE)",
  "/PROP/TYPE1": "*SECTION_SHELL (+ *HOURGLASS)",
  "/PROP/TYPE14": "*SECTION_SOLID (+ *HOURGLASS)",
  "/TH/RWALL": "*DATABASE_RWFORC",
  "/TH/INTER": "*DATABASE_RCFORC",
  "/TH/PART": "*DATABASE_MATSUM",
  "/TH/SECTIO": "*DATABASE_SECFORC + *DATABASE_CROSS_SECTION",
  "/TH/NODE": "*DATABASE_NODOUT",
  "/PLOAD": "*LOAD_SEGMENT_SET",
  "/LOAD/PBLAST": "*LOAD_BLAST_ENHANCED",
  "/SPHCEL": "*ELEMENT_SPH (+ *SECTION_SPH)",
  "/RUN": "*CONTROL_TERMINATION",
  "/ANIM/DT": "*DATABASE_BINARY_D3PLOT",
};

export function dynaFor(card: string): string | null {
  return DYNA_EQUIV[card] ?? null;
}

const KEY = "showDynaRefs";
const EVENT = "dyna-refs-change";

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setDynaRefs(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* depolama yoksa yalnız bu sayfa */
  }
  memo = on;
  window.dispatchEvent(new Event(EVENT));
}

let memo: boolean | null = null;

function subscribe(cb: () => void): () => void {
  const h = () => {
    memo = read();
    cb();
  };
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", h);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", h);
  };
}

/** LS-DYNA karşılıkları gösterilsin mi (kişisel tercih). */
export function useDynaRefs(): boolean {
  return useSyncExternalStore(subscribe, () => (memo ??= read()), () => false);
}
