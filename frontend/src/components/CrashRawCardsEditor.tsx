/**
 * 1.22d — crash ham kart editörü (Mod A: ek kart). Kullanıcı OpenRadioss
 * kartlarını mesh düğüm/eleman ID'leriyle yazar; backend metni starter
 * deck'ine /END'den önce aynen ekler. Editör içeriği yorumlamaz.
 * 3 · Malzeme ve 4 · Crash'ten açılır; içerik App'te ortak.
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  postRawCardsCheck,
  postRawCardsInventory,
  type CrashSolveRequest,
  type RawCardIdRow,
  type RawCardsCheckResponse,
  type RawCardsInventoryResponse,
} from "../api/crash";
import {
  USER_ID_MIN,
  cursorInfo,
  formatIdLines,
  insertBlockAt,
  rawCardLineCount,
  rulerLines,
  spacesToNextField,
} from "../lib/rawCards";

const [RULER_NUMS, RULER_TICKS] = rulerLines(100);

interface CheckState {
  /** Kontrol edilen metin — değişirse sonuç "eski" işaretlenir. */
  text: string;
  check?: RawCardsCheckResponse;
  checkError?: string;
  inventory?: RawCardsInventoryResponse;
  inventoryError?: string;
}

const errText = (r: PromiseSettledResult<unknown>) =>
  r.status === "rejected" ? (r.reason instanceof Error ? r.reason.message : String(r.reason)) : undefined;

/** Ad alanında kullanılan ID'ler: en çok 6 değer, fazlası "… son". */
function idSummary(ids: number[]): string {
  const shown = ids.slice(0, 6).join(", ");
  return ids.length > 6 ? `${shown}, … ${ids[ids.length - 1]}` : shown;
}

/** 3 · Malzeme ve 4 · Crash'teki giriş satırı: özet + editörü aç. */
export function RawCardsOpenRow({
  rawCards,
  onOpen,
  disabled = false,
}: {
  rawCards: string;
  onOpen: () => void;
  disabled?: boolean;
}) {
  const n = rawCardLineCount(rawCards);
  return (
    <div className="raw-cards-open" data-testid="raw-cards-open">
      <button type="button" className="material-secondary-button" disabled={disabled} onClick={onOpen}>
        Ham kart editörü
      </button>
      <span className="crash-behavior-hint">
        {n ? `${n} satır ham kart — deck'e /END'den önce eklenecek` : "Ham kart yok"}
      </span>
    </div>
  );
}

export default function CrashRawCardsEditor({
  value,
  onChange,
  onClose,
  nodePicks = [],
  elementPicks = [],
  buildRequest,
}: {
  value: string;
  onChange: (next: string) => void;
  onClose: () => void;
  /** Viewport'ta "mesh düğüm" modunda seçili düğümler — deck no'su (Gmsh tag). */
  nodePicks?: number[];
  /** Viewport'ta "mesh eleman" modunda seçili elemanlar — deck no'su (Gmsh tag). */
  elementPicks?: number[];
  /** 1.22e: güncel /crash/solve gövdesi (4 · Crash kurulumu); yoksa "Kontrol et" pasif. */
  buildRequest?: () => CrashSolveRequest | null;
}) {
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const rulerRef = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState(0);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckState | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);

  useEffect(() => {
    areaRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const setTextAndCursor = (text: string, pos: number) => {
    onChange(text);
    setCursor(pos);
    requestAnimationFrame(() => {
      const el = areaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(pos, pos);
      }
    });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Tab" || e.shiftKey) return;
    e.preventDefault();
    const el = e.currentTarget;
    const { selectionStart: s, selectionEnd: t } = el;
    const col0 = s - (value.lastIndexOf("\n", s - 1) + 1);
    const pad = " ".repeat(spacesToNextField(col0));
    setTextAndCursor(value.slice(0, s) + pad + value.slice(t), s + pad.length);
  };

  const insertIds = (ids: number[]) => {
    const pos = areaRef.current?.selectionStart ?? value.length;
    const res = insertBlockAt(value, pos, formatIdLines(ids));
    setTextAndCursor(res.text, res.cursor);
  };

  const runCheck = async () => {
    let request: CrashSolveRequest | null = null;
    try {
      request = buildRequest?.() ?? null;
    } catch (e) {
      // Kurulumdaki geçersiz alan (ör. eğri) — koşudaki mesajın aynısı.
      setSetupError(e instanceof Error ? e.message : String(e));
      return;
    }
    if (!request) {
      setSetupError("Kontrol için 4 · Crash kurulumu (geometri + mesh) gerekir.");
      return;
    }
    setSetupError(null);
    setChecking(true);
    const text = value;
    const body = { ...request, raw_cards: text };
    const [inv, chk] = await Promise.allSettled([postRawCardsInventory(body), postRawCardsCheck(body)]);
    setResult({
      text,
      inventory: inv.status === "fulfilled" ? inv.value : undefined,
      inventoryError: errText(inv),
      check: chk.status === "fulfilled" ? chk.value : undefined,
      checkError: errText(chk),
    });
    setChecking(false);
  };

  /** Sonuç satırına tıklanınca imleç ham metindeki o satırın başına. */
  const jumpToLine = (line: number) => {
    const lines = value.split("\n");
    const pos = lines.slice(0, Math.max(0, line - 1)).reduce((n, l) => n + l.length + 1, 0);
    setTextAndCursor(value, Math.min(pos, value.length));
  };

  const idRows = (rows: RawCardIdRow[], what: (r: RawCardIdRow) => string) =>
    rows.map((r) => (
      <li key={`${r.line}-${r.namespace}-${r.id}-${what(r)}`}>
        <button type="button" className="crash-link-btn" onClick={() => jumpToLine(r.line)}>
          Satır {r.line}
        </button>{" "}
        <code>{r.keyword}</code> · {r.namespace} {r.id} — {what(r)}
      </li>
    ));

  const syncScroll = () => {
    const el = areaRef.current;
    if (!el) return;
    if (gutterRef.current) gutterRef.current.scrollTop = el.scrollTop;
    if (rulerRef.current) rulerRef.current.scrollLeft = el.scrollLeft;
  };

  const lineCount = Math.max(1, value.split("\n").length);
  const info = cursorInfo(value, cursor);
  const updateCursor = () => setCursor(areaRef.current?.selectionStart ?? 0);

  return (
    <div className="crash-newcase-backdrop" role="presentation" onClick={onClose}>
      <div
        className="raw-cards-dialog"
        role="dialog"
        aria-label="Ham kart editörü"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="crash-newcase-head">
          <strong>Ham kartlar · OpenRadioss</strong>
          <span className="crash-behavior-hint">
            Starter deck'ine /END'den önce aynen eklenir. ID'ler ≥ {USER_ID_MIN.toLocaleString("tr-TR")};
            /BEGIN ve /END yazılmaz.
          </span>
          <button type="button" className="crash-doe-x" aria-label="Kapat" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="raw-cards-toolbar">
          <span className="raw-cards-picks">
            Seçili düğüm: <strong data-testid="raw-cards-pick-count">{nodePicks.length}</strong>
          </span>
          <button
            type="button"
            className="material-secondary-button"
            disabled={nodePicks.length === 0}
            // Odak metin alanında kalsın: imleç konumu ekleme yeri.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => insertIds(nodePicks)}
            title="Viewport'ta Mesh düğüm modunda seçilenler; 10'luk alanlara, satır başına 10"
          >
            Düğüm ID'lerini imlece ekle
          </button>
          <span className="raw-cards-picks">
            Seçili eleman: <strong data-testid="raw-cards-elem-count">{elementPicks.length}</strong>
          </span>
          <button
            type="button"
            className="material-secondary-button"
            disabled={elementPicks.length === 0}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => insertIds(elementPicks)}
            title="Viewport'ta Mesh eleman modunda seçilenler (deck eleman no'su); 10'luk alanlara, satır başına 10"
          >
            Eleman ID'lerini imlece ekle
          </button>
          <span className="raw-cards-pos" data-testid="raw-cards-pos">
            Satır {info.line} · Kolon {info.col} · Alan {info.field}
          </span>
        </div>

        <div className="raw-cards-editor">
          <div className="raw-cards-corner" aria-hidden="true" />
          <div className="raw-cards-ruler" ref={rulerRef} aria-hidden="true">
            <pre>{RULER_NUMS}</pre>
            <pre>{RULER_TICKS}</pre>
          </div>
          <div className="raw-cards-gutter" ref={gutterRef} aria-hidden="true">
            {Array.from({ length: lineCount }, (_, i) => (
              <div key={i} className={i + 1 === info.line ? "active" : undefined}>
                {i + 1}
              </div>
            ))}
          </div>
          <textarea
              ref={areaRef}
              className="raw-cards-area"
              aria-label="Ham kart metni"
              value={value}
              wrap="off"
              spellCheck={false}
              placeholder={"/GRNOD/NODE/900001\nmesnet_dugumleri\n       101       102       103"}
              onChange={(e) => {
                onChange(e.target.value);
                setCursor(e.target.selectionStart);
              }}
              onKeyDown={onKeyDown}
              onKeyUp={updateCursor}
              onClick={updateCursor}
              onSelect={updateCursor}
              onScroll={syncScroll}
            />
        </div>

        {(result || setupError) && (
          <div className="raw-cards-result" data-testid="raw-cards-result">
            {setupError && <p className="raw-cards-err">{setupError}</p>}
            {result && (
              <>
                {result.text !== value && (
                  <p className="raw-cards-stale">Metin kontrolden sonra değişti — sonuç eski metne ait.</p>
                )}
                <p className="raw-cards-result-title">Starter</p>
                {result.checkError && <p className="raw-cards-err">{result.checkError}</p>}
                {result.check && (
                  <>
                    <p data-testid="raw-cards-starter-summary">
                      Çıkış kodu {result.check.exit_code} · {result.check.errors.length} hata ·{" "}
                      {result.check.warnings.length} uyarı
                      {result.check.raw_cards_deck_line != null &&
                        ` · ham kartlar deck'te ${result.check.raw_cards_deck_line}. satırdan`}
                    </p>
                    {[...result.check.errors, ...result.check.warnings].map((b, i) => (
                      <pre key={i} className={b.kind === "error" ? "raw-cards-msg error" : "raw-cards-msg"}>
                        {b.lines.join("\n")}
                      </pre>
                    ))}
                    {result.check.console_tail && <pre className="raw-cards-msg">{result.check.console_tail}</pre>}
                  </>
                )}
                <p className="raw-cards-result-title">ID'ler</p>
                {result.inventoryError && <p className="raw-cards-err">{result.inventoryError}</p>}
                {result.inventory && (
                  <InventoryView inv={result.inventory} idRows={idRows} />
                )}
              </>
            )}
          </div>
        )}

        <div className="raw-cards-foot">
          <span className="crash-behavior-hint">
            {rawCardLineCount(value)} satır · Tab = sonraki 10'luk alan · Esc = kapat
          </span>
          <button
            type="button"
            className="material-secondary-button"
            disabled={checking || !buildRequest || !value.trim()}
            onClick={() => void runCheck()}
            title="Ham kartlı deck'i yalnız starter ile okutur (koşu yok) ve ID çakışmalarını listeler"
          >
            {checking ? "Kontrol ediliyor…" : "Kontrol et"}
          </button>
          <button type="button" className="material-assign-button" onClick={onClose}>
            Tamam
          </button>
        </div>
      </div>
    </div>
  );
}

/** ID çakışma listesi + üretilen deck envanteri (aynen; değerlendirme yok). */
function InventoryView({
  inv,
  idRows,
}: {
  inv: RawCardsInventoryResponse;
  idRows: (rows: RawCardIdRow[], what: (r: RawCardIdRow) => string) => JSX.Element[];
}) {
  const n = inv.collisions.length + inv.duplicates.length + inv.below_user_range.length;
  const userMin = inv.user_id_min.toLocaleString("tr-TR");
  return (
    <>
      {n > 0 ? (
        <ul className="raw-cards-idlist" data-testid="raw-cards-collisions">
          {idRows(inv.collisions, () => "üretilen deck'te de var")}
          {idRows(inv.duplicates, (r) => `ham metinde ${r.first_line}. satırda da var`)}
          {idRows(inv.below_user_range, () => `kullanıcı aralığının (≥ ${userMin}) altında`)}
        </ul>
      ) : (
        <p data-testid="raw-cards-collisions">Çakışma yok.</p>
      )}
      <p className="crash-behavior-hint" data-testid="raw-cards-inventory">
        Üretilen deck: {inv.nodes.count} düğüm ({inv.nodes.min}–{inv.nodes.max}), {inv.elements.count} eleman (
        {inv.elements.min}–{inv.elements.max})
        {Object.entries(inv.ids).map(([ns, ids]) => ` · ${ns}: ${idSummary(ids)}`)}
      </p>
    </>
  );
}
