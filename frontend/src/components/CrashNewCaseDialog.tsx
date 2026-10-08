/**
 * "+ Yeni crash vakası" — katalog + hızlı senaryo (Claude Design adım 3:
 * "Katalog + hızlı senaryo → + Yeni vaka"). Senaryo geometrisi üretilince
 * App viewport'a yükler; koşu geçmişi dock'ta görünür.
 */
import type { CrashScenarioResponse } from "../api/crash";
import CrashCatalog from "./CrashCatalog";
import CrashScenarioCard from "./CrashScenarioCard";

export default function CrashNewCaseDialog({
  onClose,
  onGeometry,
  onDone,
  onJobStarted,
}: {
  onClose: () => void;
  onGeometry: (geometryId: number, name: string) => void;
  onDone: () => void;
  onJobStarted?: (res: CrashScenarioResponse) => void;
}) {
  return (
    <div className="crash-newcase-backdrop" role="presentation" onClick={onClose}>
      <div
        className="crash-newcase-dialog"
        role="dialog"
        aria-label="Yeni crash vakası"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="crash-newcase-head">
          <strong>Yeni crash vakası</strong>
          <span className="crash-behavior-hint">Hazır bir örnekten başla: geometri + kurulum tek seferde.</span>
          <button type="button" className="crash-doe-x" aria-label="Kapat" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="crash-newcase-body">
          <div>
            <CrashScenarioCard
              showSchematic onDone={onDone} onGeometry={onGeometry} onJobStarted={onJobStarted} />
          </div>
          <div>
            <CrashCatalog />
          </div>
        </div>
      </div>
    </div>
  );
}
