/**
 * 1.23 D1 — üretilen deck'i görüntüle / dışa aktar (ham kart Mod B'nin ilk yarısı:
 * salt okunur). Koşudaki gibi üretilir (ham kartlar dahil, solver koşmaz). Sol: kart
 * listesi (aranır), sağ: seçili kartın bloğu satır numaralı. Starter / engine ayrı;
 * ikisi de .rad olarak indirilir. Düzenleme yok — ek kart için ham kart editörü.
 */

import { useEffect, useMemo, useState } from "react";

import { postDeckPreview, type CrashSolveRequest, type DeckCard, type DeckPreviewResponse } from "../api/crash";
import { useBackdropClose } from "../lib/useBackdropClose";
import { downloadBlob } from "./CrashForceChart";

/** Arama: kart başlığında büyük/küçük harf duyarsız. */
export function filterCards(cards: DeckCard[], q: string): DeckCard[] {
  const s = q.trim().toUpperCase();
  return s ? cards.filter((c) => c.card.toUpperCase().includes(s)) : cards;
}

/** Bir kart bloğu (başlık + gövde); çok uzunsa ilk `max` satır. */
export function cardBlock(text: string, c: DeckCard, max = 400): { lines: string[]; cut: number } {
  const all = text.split("\n").slice(c.line - 1, c.line - 1 + c.lines);
  return { lines: all.slice(0, max), cut: Math.max(0, all.length - max) };
}

export default function CrashDeckViewer({
  request,
  onClose,
}: {
  /** /crash/solve gövdesi (ham kartlar dahil) */
  request: CrashSolveRequest;
  onClose: () => void;
}) {
  const [data, setData] = useState<DeckPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [which, setWhich] = useState<"starter" | "engine">("starter");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  useEffect(() => {
    let alive = true;
    postDeckPreview(request)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Deck üretilemedi."));
    return () => {
      alive = false;
    };
    // istek açılışta bir kez (panel değişirse pencere yeniden açılır)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const text = data ? data[which] : "";
  const outline = data ? (which === "starter" ? data.starter_outline : data.engine_outline) : [];
  const shown = useMemo(() => filterCards(outline, q), [outline, q]);
  const current = shown[Math.min(sel, shown.length - 1)];
  const block = current ? cardBlock(text, current) : null;
  const nLines = text ? text.split("\n").length : 0;
  const backdrop = useBackdropClose(onClose);

  const download = (kind: "starter" | "engine") =>
    data && downloadBlob(new Blob([data[kind]], { type: "text/plain" }), kind === "starter" ? "crash_0000.rad" : "crash_0001.rad");

  return (
    <div className="crash-newcase-backdrop" role="presentation" {...backdrop}>
      <div className="raw-cards-dialog crash-deck-dialog" role="dialog" aria-label="Üretilen deck" onClick={(e) => e.stopPropagation()}>
        <div className="crash-newcase-head">
          <strong>Üretilen deck · OpenRadioss</strong>
          <span className="crash-behavior-hint">
            Koşudaki gibi üretilir (ham kartlar dahil); solver koşmaz. Salt okunur — ek kart için ham kart editörü.
          </span>
          <button type="button" className="crash-doe-x" aria-label="Kapat" onClick={onClose}>
            ×
          </button>
        </div>
        {error && <p className="material-assign-hint crash-run-failed">{error}</p>}
        {!data && !error && <p className="doe-empty">Deck üretiliyor…</p>}
        {data && (
          <>
            <div className="raw-cards-toolbar">
              <span className="crash-var-chips" role="group" aria-label="Deck dosyası">
                {(["starter", "engine"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    className={which === k ? "crash-var-chip active" : "crash-var-chip"}
                    aria-pressed={which === k}
                    onClick={() => {
                      setWhich(k);
                      setSel(0);
                    }}
                  >
                    {k === "starter" ? "Starter · _0000.rad (model)" : "Engine · _0001.rad (çözüm kontrolü)"}
                  </button>
                ))}
              </span>
              <span className="ds-sb" data-testid="crash-deck-stats">
                {nLines} satır · {outline.length} kart
              </span>
              <button type="button" className="material-secondary-button" onClick={() => download("starter")}>
                ⤓ Starter .rad
              </button>
              <button type="button" className="material-secondary-button" onClick={() => download("engine")}>
                ⤓ Engine .rad
              </button>
            </div>
            <div className="crash-deck-body">
              <div className="crash-deck-list">
                <input
                  aria-label="Kart ara"
                  placeholder="kart ara (ör. /MAT, /RWALL)"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setSel(0);
                  }}
                />
                <ul aria-label="Kartlar">
                  {shown.map((c, i) => (
                    <li key={`${c.line}`}>
                      <button
                        type="button"
                        className={c === current ? "crash-deck-card active" : "crash-deck-card"}
                        onClick={() => setSel(i)}
                      >
                        <span>{c.card}</span>
                        <em>
                          s.{c.line} · {c.lines}
                        </em>
                      </button>
                    </li>
                  ))}
                  {shown.length === 0 && <li className="doe-empty">Eşleşen kart yok.</li>}
                </ul>
              </div>
              <pre className="crash-deck-text" data-testid="crash-deck-text">
                {block?.lines.map((ln, i) => (
                  <span key={i} className="crash-deck-line">
                    <i>{current!.line + i}</i>
                    {ln || " "}
                    {"\n"}
                  </span>
                ))}
                {block && block.cut > 0 && (
                  <span className="crash-deck-cut">… {block.cut} satır daha (tamamı için .rad indir)</span>
                )}
              </pre>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
