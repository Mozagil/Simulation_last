/**
 * Crash koşu geçmişi — alttaki "Analiz geçmişi" dock'unun crash karşılığı
 * (Claude Design adım 3: "Koşu geçmişi → alt dock"). Crash sekmesinde
 * durability geçmişinin yerini alır.
 */
import { useState } from "react";
import CrashHistory from "./CrashHistory";

export default function CrashHistoryDock({
  geometryId,
  refreshKey,
  activeAnimId,
  onAnimate,
}: {
  geometryId: number | null;
  refreshKey: string;
  activeAnimId: number | null;
  onAnimate: (run: { id: number; title: string } | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className={expanded ? "history-footer crash-history-dock" : "history-footer history-footer-collapsed"}
      data-testid="crash-history-dock"
    >
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
