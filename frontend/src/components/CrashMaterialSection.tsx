/**
 * Crash malzeme modeli — global kart + parça başına kart. Kullanıcı 2026-10-07:
 * malzeme kavramları (LAW, kopma /FAIL) 3 · Material adımında olmalı; 4 · Crash
 * yalnız özet gösterir. Aynı bileşen ikisinde de kullanılır (state App'te).
 */
import type { Dispatch, SetStateAction } from "react";
import CrashMaterialCard, { type MatCardState } from "./CrashMaterialCard";
import { DynaToggle } from "./Kw";

const LAW_NAME: Record<MatCardState["law"], string> = {
  elastic: "elastik (LAW1)",
  plastic: "elasto-plastik (LAW2)",
  tabulated: "tablolu eğri (LAW36)",
};

/** "elasto-plastik (LAW2) · kopma kapalı" — 4 · Crash özeti için. */
export function matCardSummary(card: MatCardState): string {
  const fails = [card.failJohnson && "Johnson-Cook", card.failTens && "çekme gerinimi"].filter(Boolean);
  return `${LAW_NAME[card.law]} · ${fails.length ? `kopma: ${fails.join(" + ")}` : "kopma kapalı"}`;
}

export default function CrashMaterialSection({
  partIds,
  matCard,
  setMatCard,
  partCards,
  setPartCards,
  disabled = false,
  hideToggle = false,
}: {
  partIds: number[];
  matCard: MatCardState;
  setMatCard: (next: MatCardState) => void;
  partCards: Record<number, MatCardState>;
  setPartCards: Dispatch<SetStateAction<Record<number, MatCardState>>>;
  disabled?: boolean;
  /** Üst bileşen LS-DYNA düğmesini zaten gösteriyorsa. */
  hideToggle?: boolean;
}) {
  return (
    <section className="crash-mat-section-wrap" aria-label="Crash malzeme modeli">
      <p className="material-assignments-title">
        {Object.keys(partCards).length > 0 ? "Crash malzeme modeli — ortak" : "Crash malzeme modeli"}
      </p>
      <p className="crash-behavior-hint">
        Yukarıdaki kütüphane malzemesi E, ν, ρ ve akma gerilmesini verir. Burada çarpışmada malzemenin
        nasıl davranacağı seçilir: akınca ne olur, kopar mı.
      </p>
      {!hideToggle && <DynaToggle />}
      {partIds.length > 1 && (
        <div className="crash-mat-toggles">
          {partIds.map((pid) => (
            <div key={pid} className="crash-mat-toggle">
              <span>#{pid}</span>
              <span className="doe-seg" role="group" aria-label={`Parça ${pid} kartı`}>
                <button
                  type="button"
                  className={partCards[pid] ? "doe-seg-opt" : "doe-seg-opt active"}
                  aria-pressed={!partCards[pid]}
                  disabled={disabled}
                  onClick={() =>
                    setPartCards((c) => {
                      const next = { ...c };
                      delete next[pid];
                      return next;
                    })
                  }
                >
                  Global
                </button>
                <button
                  type="button"
                  className={partCards[pid] ? "doe-seg-opt active" : "doe-seg-opt"}
                  aria-pressed={Boolean(partCards[pid])}
                  disabled={disabled}
                  onClick={() => setPartCards((c) => (c[pid] ? c : { ...c, [pid]: { ...matCard } }))}
                >
                  Ayrı
                </button>
              </span>
            </div>
          ))}
          <span className="crash-behavior-hint">
            Global = ortak model; Ayrı = o parçaya kendi modeli (ör. çarpan rijit küre elastik, plaka kopmalı).
          </span>
        </div>
      )}
      <CrashMaterialCard value={matCard} onChange={setMatCard} disabled={disabled} testId="crash-mat-global" />
      {partIds
        .filter((pid) => partCards[pid])
        .map((pid) => (
          <div key={pid} className="crash-contact-card crash-mat-part">
            <div className="crash-contact-head">
              <strong>Parça #{pid} — malzeme modeli</strong>
            </div>
            <CrashMaterialCard
              value={partCards[pid]}
              onChange={(next) => setPartCards((c) => ({ ...c, [pid]: next }))}
              disabled={disabled}
              testId={`crash-mat-part-${pid}`}
            />
          </div>
        ))}
    </section>
  );
}
