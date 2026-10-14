/**
 * Crash koşu geçmişi — alttaki "Analiz geçmişi" dock'unun crash karşılığı
 * (Claude Design adım 3: "Koşu geçmişi → alt dock"). Crash sekmesinde
 * durability geçmişinin yerini alır.
 */
import { useState, type MouseEvent as ReactMouseEvent } from "react";
import CrashHistory, { type CrashAnimTarget } from "./CrashHistory";

// Açık dock viewport'u kapatmasın (kullanıcı 2026-10-07): varsayılan alçak,
// üst kenardan sürüklenir, pencerenin %60'ını geçmez; yükseklik hatırlanır.
const DEFAULT_H = 200;
const MIN_H = 120;
const STORE_KEY = "crashHistoryDockH";
const maxH = () => Math.max(MIN_H, Math.round(window.innerHeight * 0.6));
const clampH = (h: number) => Math.min(maxH(), Math.max(MIN_H, h));

function readStoredH(): number {
  try {
    const v = Number(window.localStorage.getItem(STORE_KEY));
    return Number.isFinite(v) && v > 0 ? clampH(v) : DEFAULT_H;
  } catch {
    return DEFAULT_H;
  }
}

export default function CrashHistoryDock({
  geometryId,
  refreshKey,
  activeAnimId,
  onAnimate,
}: {
  geometryId: number | null;
  refreshKey: string;
  activeAnimId: number | null;
  onAnimate: (run: CrashAnimTarget | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [height, setHeight] = useState(readStoredH);

  function startResize(e: ReactMouseEvent<HTMLDivElement>) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    let last = startH;
    function onMove(ev: globalThis.MouseEvent) {
      last = clampH(startH - (ev.clientY - startY));
      setHeight(last);
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try {
        window.localStorage.setItem(STORE_KEY, String(last));
      } catch {
        /* depolama yoksa yalnız bu oturum */
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  }

  return (
    <div
      className={expanded ? "history-footer crash-history-dock" : "history-footer history-footer-collapsed"}
      style={expanded ? { height: `${height}px` } : undefined}
      data-testid="crash-history-dock"
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
          onClick={() => setExpanded((v) => !v)}
        >
          Crash geçmişi
          <span className="history-footer-hint">{geometryId != null ? "bu geometri" : "tüm geometriler"}</span>
        </button>
        <button type="button" className="history-footer-toggle" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Kapat" : "Aç"}
        </button>
      </div>
      {expanded && (
        <div className="crash-history-dock-body">
          <CrashHistory geometryId={geometryId} refreshKey={refreshKey} activeAnimId={activeAnimId} onAnimate={onAnimate} />
        </div>
      )}
    </div>
  );
}
