/**
 * Crash malzeme modeli — global kart + parça başına kart. Kullanıcı 2026-10-07:
 * malzeme kavramları (LAW, kopma /FAIL) 3 · Material adımında olmalı; 4 · Crash
 * yalnız özet gösterir. Aynı bileşen ikisinde de kullanılır (state App'te).
 */
import { useState, type Dispatch, type SetStateAction } from "react";
import CrashMaterialCard, { type MatCardState } from "./CrashMaterialCard";
import { DynaToggle } from "./Kw";

const LAW_NAME: Record<MatCardState["law"], string> = {
  elastic: "elastik (LAW1)",
  plastic: "elasto-plastik (LAW2)",
  tabulated: "tablolu eğri (LAW36)",
};

export const LAW_SHORT: Record<MatCardState["law"], string> = {
  elastic: "LAW1 elastik",
  plastic: "LAW2 elasto-plastik",
  tabulated: "LAW36 tablolu",
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
  materialOf,
}: {
  partIds: number[];
  matCard: MatCardState;
  setMatCard: (next: MatCardState) => void;
  partCards: Record<number, MatCardState>;
  setPartCards: Dispatch<SetStateAction<Record<number, MatCardState>>>;
  disabled?: boolean;
  /** Üst bileşen LS-DYNA düğmesini zaten gösteriyorsa. */
  hideToggle?: boolean;
  /** 1.23 A2: parçaya atanmış kütüphane malzemesinin adı (tabloda gösterilir). */
  materialOf?: (pid: number) => string | null;
}) {
  // 1.23 A2: parça başına model seçimi tek tabloda. "Varsayılan" = varsayılan kart; LAW
  // seçilince o parçaya kendi kartı açılır (varsayılan karttan kopya, LAW değiştirilmiş).
  const choose = (pid: number, v: string) =>
    setPartCards((c) => {
      const next = { ...c };
      if (v === "common") delete next[pid];
      else next[pid] = { ...(c[pid] ?? matCard), law: v as MatCardState["law"] };
      return next;
    });

  // Kullanıcı 2026-10-13: varsayılan kartta LAW değişince, kendi modeli olan parça varsa
  // küçük onay: "Tüm parçalar LAW1 olsun mu?" — Tamam = parça kartları kalkar, hepsi
  // varsayılanı izler; Hayır = yalnız varsayılan değişir.
  const [askAll, setAskAll] = useState<MatCardState["law"] | null>(null);
  const ownCount = Object.keys(partCards).length;
  const setDefault = (next: MatCardState) => {
    if (next.law !== matCard.law && ownCount > 0) setAskAll(next.law);
    setMatCard(next);
  };
  return (
    <section className="crash-mat-section-wrap" aria-label="Crash malzeme modeli">
      {!hideToggle && (
        <>
        <p className="material-assignments-title">
          {Object.keys(partCards).length > 0 ? "Crash malzeme modeli — varsayılan" : "Crash malzeme modeli"}
        </p>
        <p className="crash-behavior-hint">
          Yukarıdaki kütüphane malzemesi E, ν, ρ ve akma gerilmesini verir. Burada çarpışmada malzemenin
          nasıl davranacağı seçilir: akınca ne olur, kopar mı.
        </p>
          </>
      )}
      {!hideToggle && <DynaToggle />}
      {partIds.length > 1 && (
        <div className="crash-mat-table" role="table" aria-label="Parça başına malzeme modeli">
          <div className="crash-mat-row crash-mat-row-head" role="row">
            <span role="columnheader">Parça</span>
            <span role="columnheader">Kütüphane malzemesi</span>
            <span role="columnheader">Model (LAW) · kopma</span>
          </div>
          {partIds.map((pid) => (
            <div key={pid} className="crash-mat-row" role="row" data-testid={`crash-mat-row-${pid}`}>
              <code role="cell">#{pid}</code>
              <span role="cell">{materialOf?.(pid) ?? "—"}</span>
              <span role="cell" className="crash-mat-row-model">
                <select
                  aria-label={`Parça ${pid} modeli`}
                  value={partCards[pid] ? partCards[pid].law : "common"}
                  disabled={disabled}
                  onChange={(e) => choose(pid, e.target.value)}
                >
                  <option value="common">Varsayılan</option>
                  <option value="elastic">{LAW_SHORT.elastic}</option>
                  <option value="plastic">{LAW_SHORT.plastic}</option>
                  <option value="tabulated">{LAW_SHORT.tabulated}</option>
                </select>
                <span className="crash-behavior-hint">{matCardSummary(partCards[pid] ?? matCard).split(" · ")[1]}</span>
              </span>
            </div>
          ))}
          <span className="crash-behavior-hint">
            Varsayılan = aşağıdaki varsayılan kart. LAW seçilen parçanın kendi kartı açılır (kopma ayarları dahil) — ör.
            çarpan rijit küre LAW1 elastik, plaka LAW2 + kopma.
          </span>
        </div>
      )}
      {partIds.length > 1 && <p className="crash-expert-title">Varsayılan model (kendi modeli seçilmeyen parçalar)</p>}
      {askAll && (
        <div className="crash-mat-ask" role="alertdialog" aria-label="Tüm parçalar">
          <span>Hepsi {LAW_SHORT[askAll]} olsun mu?</span>
          <button
            type="button"
            className="material-assign-button"
            onClick={() => {
              setPartCards({});
              setAskAll(null);
            }}
          >
            Evet
          </button>
          <button type="button" className="material-secondary-button" onClick={() => setAskAll(null)}>
            Hayır
          </button>
        </div>
      )}
      <CrashMaterialCard value={matCard} onChange={setDefault} disabled={disabled} testId="crash-mat-global" />
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
