/**
 * ML Stüdyo aşama çubuğu — Claude Design "ML Studio 1a" (pipeline yönü).
 * Beş aşama soldan sağa veri akışı sırasında: DOE → Veri seti → Yakınsama →
 * Model → Tahmin. Tek seferde bir aşama görünür; çubuk sadece seçimi
 * taşır, içerik App'te aşamaya göre render edilir.
 */
export type MlStage = "doe" | "data" | "conv" | "model" | "pred";

export const ML_STAGES: { id: MlStage; phase: string; name: string }[] = [
  { id: "doe", phase: "0.5", name: "DOE" },
  { id: "data", phase: "0.5", name: "Veri seti" },
  { id: "conv", phase: "0.6.1", name: "Yakınsama" },
  { id: "model", phase: "0.5.6–0.6.4", name: "Model" },
  { id: "pred", phase: "surrogate", name: "Tahmin" },
];

export default function MlStudioNav({
  stage,
  onSelect,
  meta,
}: {
  stage: MlStage;
  onSelect: (stage: MlStage) => void;
  /** Aşama altındaki kısa durum satırı (örn. "412 run"); yoksa boş kalır. */
  meta?: Partial<Record<MlStage, string>>;
}) {
  return (
    <nav className="ml-stage-nav" aria-label="ML Stüdyo aşamaları">
      {ML_STAGES.map((s) => {
        const active = s.id === stage;
        const m = meta?.[s.id];
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
            <span className="ml-stage-meta">
              {m ? <span className="ml-stage-dot" /> : null}
              {m ?? " "}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
