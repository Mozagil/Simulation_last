/**
 * Crash malzeme modeli — global kart + parça başına kart. Kullanıcı 2026-10-07:
 * malzeme kavramları (LAW, kopma /FAIL) 3 · Material adımında olmalı; 4 · Crash
 * yalnız özet gösterir. Aynı bileşen ikisinde de kullanılır (state App'te).
 */
import { useState, type Dispatch, type SetStateAction } from "react";
import CrashMaterialCard, { type MatCardState } from "./CrashMaterialCard";
import type { JcSource } from "../lib/crashJc";
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
  jcOf,
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
  /** 1.24g: parçaya atanmış kütüphane malzemesinin Johnson–Cook seti (varsa). */
  jcOf?: (pid: number) => JcSource | null;
}) {
  // 1.23 A2 (kullanıcı 2026-10-13): tabloda yalnız LAW adları — her parçanın geçerli
  // modeli seçili. Alttaki kartın LAW'ından farklı seçilen parçaya kendi kartı açılır
  // (alttaki karttan kopya); aynısı seçilirse kendi kartı kalkar.
  // 1.24g — alttaki (ortak) kart: parçalara atanmış malzemelerin JC setleri, ada göre tekil
  const allJc = [
    ...new Map(
      partIds.map((pid) => jcOf?.(pid)).filter((s): s is JcSource => s != null).map((s) => [s.label, s] as const),
    ).values(),
  ];
  const choose = (pid: number, law: MatCardState["law"]) =>
    setPartCards((c) => {
      const next = { ...c };
      if (law === matCard.law) delete next[pid];
      else next[pid] = { ...(c[pid] ?? matCard), law };
      return next;
    });

  // Alttaki kartta model seçilince (2+ parça) sor: "Hepsi LAW1 olsun mu?" Evet = tüm
  // parçalar bu model (kendi kartları kalkar); Hayır = değişiklik uygulanmaz.
  const [pending, setPending] = useState<MatCardState | null>(null);
  const setDefault = (next: MatCardState) => {
    if (next.law !== matCard.law && partIds.length > 1) {
      setPending(next);
      return;
    }
    setMatCard(next);
  };
  return (
    <section className="crash-mat-section-wrap" aria-label="Crash malzeme modeli">
      {!hideToggle && (
        <>
        <p className="material-assignments-title">
          Crash malzeme modeli
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
                  value={(partCards[pid] ?? matCard).law}
                  disabled={disabled}
                  onChange={(e) => choose(pid, e.target.value as MatCardState["law"])}
                >
                  <option value="elastic">{LAW_SHORT.elastic}</option>
                  <option value="plastic">{LAW_SHORT.plastic}</option>
                  <option value="tabulated">{LAW_SHORT.tabulated}</option>
                </select>
                <span className="crash-behavior-hint">{matCardSummary(partCards[pid] ?? matCard).split(" · ")[1]}</span>
              </span>
            </div>
          ))}
          <span className="crash-behavior-hint">
            Parçaya farklı model seçilince o parçanın kendi kartı açılır (kopma ayarları dahil) — ör. çarpan rijit küre
            LAW1 elastik, plaka LAW2 + kopma.
          </span>
        </div>
      )}
      {partIds.length > 1 && <p className="crash-expert-title">Model (kendi kartı olmayan parçalar)</p>}
      {pending && (
        <div className="crash-mat-ask" role="alertdialog" aria-label="Tüm parçalar">
          <span>Hepsi {LAW_SHORT[pending.law]} olsun mu?</span>
          <button
            type="button"
            className="material-assign-button"
            onClick={() => {
              setMatCard(pending);
              setPartCards({});
              setPending(null);
            }}
          >
            Evet
          </button>
          <button type="button" className="material-secondary-button" onClick={() => setPending(null)}>
            Hayır
          </button>
        </div>
      )}
      <CrashMaterialCard value={matCard} onChange={setDefault} disabled={disabled} testId="crash-mat-global" jcSources={allJc} />
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
              jcSources={jcOf?.(pid) ? [jcOf(pid)!] : []}
            />
          </div>
        ))}
    </section>
  );
}
