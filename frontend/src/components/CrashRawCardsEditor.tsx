/**
 * 1.22d — crash ham kart editörü (Mod A: ek kart). Kullanıcı OpenRadioss
 * kartlarını mesh düğüm/eleman ID'leriyle yazar; backend metni starter
 * deck'ine /END'den önce aynen ekler. Editör içeriği yorumlamaz.
 * 3 · Malzeme ve 4 · Crash'ten açılır; içerik App'te ortak.
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
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
}: {
  value: string;
  onChange: (next: string) => void;
  onClose: () => void;
  /** Viewport'ta "mesh düğüm" modunda seçili düğümler (gmsh no = deck no). */
  nodePicks?: number[];
}) {
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const rulerRef = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState(0);

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

  const insertNodes = () => {
    const pos = areaRef.current?.selectionStart ?? value.length;
    const res = insertBlockAt(value, pos, formatIdLines(nodePicks));
    setTextAndCursor(res.text, res.cursor);
  };

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
            onClick={insertNodes}
            title="Viewport'ta Mesh düğüm modunda seçilenler; 10'luk alanlara, satır başına 10"
          >
            Düğüm ID'lerini imlece ekle
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

        <div className="raw-cards-foot">
          <span className="crash-behavior-hint">
            {rawCardLineCount(value)} satır · Tab = sonraki 10'luk alan · Esc = kapat
          </span>
          <button type="button" className="material-assign-button" onClick={onClose}>
            Tamam
          </button>
        </div>
      </div>
    </div>
  );
}
