/**
 * S-N (yorulma) öğeleri 3 · Malzeme panelinde yalnız durability için anlamlı.
 * Crash (OpenRadioss) S-N okumaz; orada gizlenir (kullanıcı 2026-10-12).
 */
export type AnalysisTab = "durability" | "modal" | "crash" | "cfd" | "composite" | "mbd";

/** S-N satırı, "Tahmini S-N üret" ve "Oluştururken tahmini S-N ekle" görünür mü. */
export function snControlsVisible(tab: AnalysisTab): boolean {
  return tab !== "crash" && tab !== "mbd";
}

/** Özel malzeme oluştururken gönderilecek sn_mode — gizli seçenek sessizce S-N eklemesin. */
export function customMaterialSnMode(snEstimate: boolean, tab: AnalysisTab): "estimated" | "none" {
  return snEstimate && snControlsVisible(tab) ? "estimated" : "none";
}
