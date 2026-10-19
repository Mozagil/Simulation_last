/** 1.23 C8b — ezilme mesafesi referansı (istek) ve F–δ (sonuç).
 * Referans: Kütle / kızak kartı (ana düğüm; istekte `rbody_<sıra>`) ya da bölge (düğüm ortalaması).
 * Seçim mühendisin; yok = ezilme skalerleri yazılmaz. */

import { rbodyName, type LoadCard } from "../components/CrashLoadCards";

export interface CrushRefState {
  mode: "" | "rbody" | "region";
  /** Kütle / kızak kartının kimliği (mode "rbody") */
  cardId: number | null;
  region: string;
}

export interface CrushRefPayload {
  rigid_body?: string;
  region?: string;
}

/** Durum → istek alanı; eksik seçimde null (deck'e yazılmaz). */
export function crushRefPayload(s: CrushRefState, cards: LoadCard[]): CrushRefPayload | null {
  if (s.mode === "rbody") {
    const nm = s.cardId != null ? rbodyName(cards, s.cardId) : null;
    return nm ? { rigid_body: nm } : null;
  }
  if (s.mode === "region" && s.region.trim()) return { region: s.region.trim() };
  return null;
}

/** Kayıtlı istek → durum. Arayüz koşusunda ad `rbody_<sıra>` (kart sırası); API / senaryo koşusunda
 * özgün ad (ör. "kizak") → isteğin `rigid_bodies` sırasındaki yeri → aynı sıradaki kızak kartı. */
export function crushRefFromRequest(
  ref: CrushRefPayload | null | undefined,
  cards: LoadCard[],
  rigidBodies: { name?: string }[] = [],
): CrushRefState {
  if (ref?.rigid_body) {
    const k = Number(/^rbody_(\d+)$/.exec(ref.rigid_body)?.[1]);
    let card = Number.isFinite(k) && k >= 1 ? cards[k - 1] : undefined;
    if (!card || card.kind !== "rbody") {
      const j = rigidBodies.findIndex((rb) => rb.name === ref.rigid_body);
      card = j >= 0 ? cards.filter((c) => c.kind === "rbody")[j] : undefined;
    }
    return { mode: "rbody", cardId: card && card.kind === "rbody" ? card.id : null, region: "" };
  }
  if (ref?.region) return { mode: "region", cardId: null, region: ref.region };
  return { mode: "", cardId: null, region: "" };
}

/** F–δ: δ_maks örneğine kadar (yükleme kolu; geri sekme dışarıda — iş tanımıyla aynı). */
export function forceVsCrush(crush: number[] | undefined, force: number[] | undefined): { x: number[]; f: number[] } | null {
  if (!crush || !force || crush.length < 2 || crush.length !== force.length) return null;
  let iMax = 0;
  crush.forEach((v, i) => {
    if (v > crush[iMax]) iMax = i;
  });
  if (crush[iMax] <= 0) return null;
  return { x: crush.slice(0, iMax + 1), f: force.slice(0, iMax + 1).map((v) => Math.abs(v)) };
}
