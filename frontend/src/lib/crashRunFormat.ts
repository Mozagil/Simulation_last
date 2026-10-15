/** Crash koşu listesi / karşılaştırma ortak biçim yardımcıları. */

import type { CrashRunSummary } from "../api/crash";

export function fmtScalar(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v === 0) return "0";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

export const runLabel = (r: CrashRunSummary) => r.name?.trim() || `#${r.id}`;

/** "#325" (adsız) ya da "#321 kizak 100 kg" — no tekrarlanmaz. */
export const runTitle = (r: CrashRunSummary) => (r.name?.trim() ? `#${r.id} ${r.name.trim()}` : `#${r.id}`);

/** Iraksayan koşu (Hata #1) failed ama eğri / animasyon ıraksama anına kadar incelenir. */
export const runHasResults = (r: CrashRunSummary) => r.status === "solved" || r.scalars.diverged_at_ms != null;

/** Eğri anahtarından grafik başlığı / birim / eksen adı (veri: ivme g, enerji J, impuls N·s, kuvvet kN). */
export function curveUnit(key: string): { title: string; unit: string; yLabel: string; isForce: boolean } {
  if (key.startsWith("acc_g")) return { title: "İvme · g", unit: "g", yLabel: "ivme", isForce: false };
  if (/energy|external_work/.test(key)) return { title: "Enerji · J", unit: "J", yLabel: "enerji", isForce: false };
  if (/_impulse/.test(key)) return { title: "İmpuls · N·s", unit: "N·s", yLabel: "impuls", isForce: false };
  if (key.startsWith("th_")) return { title: "TH kanalı", unit: "", yLabel: key, isForce: false };
  return { title: "Kuvvet · kN", unit: "kN", yLabel: "kuvvet", isForce: true };
}

/** 1.25c2 — eğri seçici grupları (sıra = gösterim sırası). */
export const CURVE_GROUPS = ["Kuvvet", "Enerji", "Temas", "Kesit", "İvme", "İmpuls", "TH kanalları"] as const;
export type CurveGroup = (typeof CURVE_GROUPS)[number];

export function curveGroup(key: string): CurveGroup {
  if (key.startsWith("th_")) return "TH kanalları";
  if (key.startsWith("acc_g")) return "İvme";
  if (/energy|external_work/.test(key)) return "Enerji";
  if (key.startsWith("contact_")) return "Temas";
  if (key.startsWith("section_")) return "Kesit";
  if (/_impulse/.test(key)) return "İmpuls";
  return "Kuvvet";
}

const CURVE_NAMES: Record<string, string> = {
  rwall_force: "Duvar kuvveti",
  rwall_impulse: "Duvar impulsu",
  internal_energy: "İç enerji (IE)",
  kinetic_energy: "Kinetik enerji (KE)",
  hourglass_energy: "Hourglass enerjisi (HG)",
  contact_energy: "Temas enerjisi",
  external_work: "Dış iş",
  total_energy: "Toplam enerji",
  acc_g: "İvme bileşkesi",
};

/** Okunur eğri adı: "Duvar kuvveti (kN)", "Temas 2 kuvveti (kN)", "Duvar kuvveti · CFC 600 (kN)", th_* ham. */
export function curveLabel(key: string): string {
  const cfc = /_cfc(\d+)$/.exec(key);
  const base = cfc ? key.slice(0, cfc.index) : key;
  let name = CURVE_NAMES[base];
  if (!name) {
    const m = /^(contact|section)_(\d+)_(force|impulse)$/.exec(base);
    if (m) name = `${m[1] === "contact" ? "Temas" : "Kesit"} ${m[2]} ${m[3] === "force" ? "kuvveti" : "impulsu"}`;
  }
  if (!name) return key;
  const u = curveUnit(base).unit;
  return `${name}${cfc ? ` · CFC ${cfc[1]}` : ""}${u ? ` (${u})` : ""}`;
}
