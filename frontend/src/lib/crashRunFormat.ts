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

/** Eğri anahtarından grafik başlığı / birim / eksen adı (veri: ivme g, enerji J, kuvvet kN). */
export function curveUnit(key: string): { title: string; unit: string; yLabel: string; isForce: boolean } {
  if (key.startsWith("acc_g")) return { title: "İvme · g", unit: "g", yLabel: "ivme", isForce: false };
  if (/energy|external_work/.test(key)) return { title: "Enerji · J", unit: "J", yLabel: "enerji", isForce: false };
  return { title: "Kuvvet · kN", unit: "kN", yLabel: "kuvvet", isForce: true };
}
