import { useState, type MouseEvent as ReactMouseEvent } from "react";
import type { RunSummary } from "../api/runs";
import {
  summarizeTemplateParams,
  type SymbolMap,
} from "../templates/paramSummary";

const EXPANDED_DEFAULT_H = 220;
const EXPANDED_MIN_H = 120;
const EXPANDED_MAX_H = 640;

/** Donmuş eğitim setine göre run'ın durumu (manifest'ten gelir). */
export type CorpusRole = "auto" | "manual_pass" | "manual_override" | "outside";

const CORPUS_BADGE: Record<CorpusRole, { text: string; title: string }> = {
  auto: { text: "eğitim", title: "Süzgeç dondurulurken sete alındı" },
  manual_pass: { text: "manuel ✓", title: "Elle eklendi, süzgeci geçti" },
  manual_override: {
    text: "manuel ⚠",
    title: "Elle eklendi, süzgeci geçmedi (override)",
  },
  outside: { text: "sette değil", title: "Eğitim setinde yok — deneme çözümü" },
};

interface HistoryFooterProps {
  runs: RunSummary[];
  compareSelection: number[];
  busy: boolean;
  editBusy?: boolean;
  paramSymbols: SymbolMap;
  corpusName?: string | null;
  corpusRoles?: Record<number, CorpusRole>;
  onToggleCompare: (id: number) => void;
  onReview: (id: number) => void;
  onEdit: (id: number) => void;
  onDelete: (id: number, name: string) => void;
  onCompare: () => void;
}

export default function HistoryFooter({
  runs,
  compareSelection,
  busy,
  editBusy = false,
  paramSymbols,
  corpusName = null,
  corpusRoles,
  onToggleCompare,
  onReview,
  onEdit,
  onDelete,
  onCompare,
}: HistoryFooterProps) {
  const [expanded, setExpanded] = useState(false);
  const [height, setHeight] = useState(EXPANDED_DEFAULT_H);

  function startResize(e: ReactMouseEvent<HTMLDivElement>) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    // window dinleyicisi native MouseEvent alır, React'in sarmalayıcısını değil.
    function onMove(ev: globalThis.MouseEvent) {
      const next = startH - (ev.clientY - startY);
      setHeight(Math.min(EXPANDED_MAX_H, Math.max(EXPANDED_MIN_H, next)));
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }

  return (
    <div
      className={expanded ? "history-footer" : "history-footer history-footer-collapsed"}
      style={expanded ? { height: `${height}px` } : undefined}
    >
      {expanded && (
        <div
          className="resize-handle resize-handle-top"
          role="separator"
          aria-orientation="horizontal"
          title="Sürükleyerek yüksekliği ayarla"
          onMouseDown={startResize}
        />
      )}
      <div className="history-footer-bar">
        <button
          type="button"
          className="history-footer-title"
          aria-expanded={expanded}
          onClick={() => setExpanded((prev) => !prev)}
        >
          Analiz geçmişi
          <span className="history-footer-count">{runs.length}</span>
        </button>
        {corpusName && (
          <span className="history-footer-hint" title="Rozetler bu donmuş eğitim setine göre">
            set: {corpusName}
          </span>
        )}
        {compareSelection.length > 0 && (
          <span className="history-footer-hint">{compareSelection.length}/2 seçili</span>
        )}
        {compareSelection.length === 2 && (
          <button type="button" className="history-footer-compare" onClick={onCompare}>
            Karşılaştır
          </button>
        )}
        <button
          type="button"
          className="history-footer-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? "Gizle" : "Aç"}
        </button>
      </div>
      {expanded && (
        runs.length === 0 ? (
          <p className="history-footer-empty">Henüz kayıtlı analiz yok.</p>
        ) : (
          <ul className="history-list">
            {runs.map((r) => {
              const label = r.name ?? `Run #${r.id}`;
              // Set dondurulmuşsa üye olmayan run "sette değil" olarak işaretlenir.
              const role: CorpusRole | null = corpusName
                ? (corpusRoles?.[r.id] ?? "outside")
                : null;
              const badge = role ? CORPUS_BADGE[role] : null;
              return (
                <li key={r.id} className="history-item">
                  <label className="history-item-checkbox">
                    <input
                      type="checkbox"
                      checked={compareSelection.includes(r.id)}
                      onChange={() => onToggleCompare(r.id)}
                    />
                  </label>
                  <button
                    type="button"
                    className="history-item-body"
                    onClick={() => onReview(r.id)}
                  >
                    <div className="history-item-title">
                      {label}{" "}
                      <span className={`history-status history-status-${r.status}`}>
                        {r.status}
                      </span>
                      {badge && (
                        <>
                          {" "}
                          <span className={`history-corpus history-corpus-${role}`} title={badge.title}>
                            {badge.text}
                          </span>
                        </>
                      )}
                    </div>
                    <div className="history-item-sub">
                      {r.geometry_filename} · {r.dimension === 2 ? "2D" : "3D"} ·{" "}
                      {new Date(r.created_at).toLocaleString("tr-TR")}
                    </div>
                    {r.template_params && (
                      <div className="history-item-params">
                        {summarizeTemplateParams(r.template_id, r.template_params, paramSymbols)}
                      </div>
                    )}
                    {r.scalars.max_von_mises !== undefined && (
                      <div className="history-item-scalar">
                        VM max: {r.scalars.max_von_mises.toExponential(2)} · Deplasman max:{" "}
                        {r.scalars.max_displacement?.toExponential(2) ?? "—"}
                      </div>
                    )}
                  </button>
                  <div className="history-item-actions">
                    <button
                      type="button"
                      className="history-action-button"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        onEdit(r.id);
                      }}
                    >
                      {editBusy ? "Yükleniyor…" : "Düzenle"}
                    </button>
                    <button
                      type="button"
                      className="history-action-button history-action-button-danger"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(r.id, label);
                      }}
                    >
                      Sil
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )
      )}
    </div>
  );
}
