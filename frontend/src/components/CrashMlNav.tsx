/**
 * ML Stüdyo / Crash aşama çubuğu (1.19f) — durability `MlStudioNav` ile aynı
 * görünüm (`ml-stage-*` sınıfları), crash'in kendi aşamaları.
 */
export type CrashMlStage = "doe" | "model" | "pred";

export const CRASH_ML_STAGES: { id: CrashMlStage; phase: string; name: string }[] = [
  { id: "doe", phase: "1.19c", name: "DOE" },
  { id: "model", phase: "1.19d", name: "Model" },
  { id: "pred", phase: "1.19e", name: "Tahmin" },
];

export default function CrashMlNav({
  stage,
  onSelect,
}: {
  stage: CrashMlStage;
  onSelect: (stage: CrashMlStage) => void;
}) {
  return (
    <nav className="ml-stage-nav" aria-label="Crash ML aşamaları">
      {CRASH_ML_STAGES.map((s) => {
        const active = s.id === stage;
        return (
          <button
            key={s.id}
            type="button"
            className={active ? "ml-stage active" : "ml-stage"}
            aria-current={active ? "step" : undefined}
            onClick={() => onSelect(s.id)}
          >
            <span className="ml-stage-title">
              <span className="ml-stage-phase">{s.phase}</span>
              <span className="ml-stage-name">{s.name}</span>
            </span>
            <span className="ml-stage-meta"> </span>
          </button>
        );
      })}
    </nav>
  );
}
