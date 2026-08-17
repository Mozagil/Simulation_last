import { SELECTION_MODES, SelectionMode } from "../types";

interface SelectionModeBarProps {
  activeMode: SelectionMode;
  onChange: (mode: SelectionMode) => void;
}

/** Part / Surface / Edge / Point arasında geçiş yapan navbar. */
function SelectionModeBar({ activeMode, onChange }: SelectionModeBarProps) {
  return (
    <div className="selection-mode-bar" role="tablist" aria-label="Seçim modu">
      {SELECTION_MODES.map(({ mode, label }) => (
        <button
          key={mode}
          type="button"
          role="tab"
          aria-selected={activeMode === mode}
          className={`selection-mode-button${activeMode === mode ? " active" : ""}`}
          onClick={() => onChange(mode)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default SelectionModeBar;
