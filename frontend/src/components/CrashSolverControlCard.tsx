/** 1.23 D2 — çözüm kontrolü tek yerde: bitiş süresi (/RUN), zaman adımı kartı (/DT…),
 * Δt ölçeği, Δt_min / kütle ölçekleme + kısa açıklama. Son koşunun Δt_min ve eklenen
 * kütle oranı veri olarak gösterilir. Öneri yok — değerleri mühendis seçer.
 */

import Kw from "./Kw";
import { DT_KINDS, type OutputState } from "./CrashOutputCard";

export function solverSummary(tEnd: string, s: Pick<OutputState, "dtKind" | "dtScale" | "dtMin">): string {
  const parts = [`${tEnd || "—"} ms`];
  if (!s.dtKind) parts.push("Δt: Radioss");
  else {
    parts.push(s.dtKind === "DT" ? "/DT" : `/DT/${s.dtKind}`);
    if (s.dtScale.trim()) parts.push(`Δt_sca ${s.dtScale}`);
    if (s.dtMin.trim()) parts.push(`Δt_min ${s.dtMin} ms`);
  }
  return parts.join(" · ");
}

function fmt(v: number): string {
  if (v === 0) return "0";
  return Math.abs(v) >= 0.01 ? String(Number(v.toPrecision(4))) : v.toExponential(3);
}

export default function CrashSolverControlCard({
  tEnd,
  onTEnd,
  value,
  onChange,
  lastScalars,
  disabled = false,
}: {
  tEnd: string;
  onTEnd: (v: string) => void;
  value: OutputState;
  onChange: (next: OutputState) => void;
  /** Son koşunun skalerleri (varsa): timestep_min, mass_added_rel, cycles… */
  lastScalars?: Record<string, number>;
  disabled?: boolean;
}) {
  const set = (patch: Partial<OutputState>) => onChange({ ...value, ...patch });
  const kind = DT_KINDS.find((d) => d.key === value.dtKind);
  const dtMinLast = lastScalars?.timestep_min;
  const massLast = lastScalars?.mass_added_rel;

  return (
    <div className="crash-solver-card" data-testid="crash-solver-card">
      <div className="crash-field-label">
        <span>Bitiş süresi</span>
        <Kw card="/RUN" text="/RUN süre" />
      </div>
      <div className="crash-unit-row">
        <label className="crash-unit-field">
          <span>Süre</span>
          <span className="crash-unit-box">
            <input aria-label="Süre" value={tEnd} disabled={disabled} onChange={(e) => onTEnd(e.target.value)} />
            <em>ms</em>
          </span>
        </label>
      </div>

      <div className="crash-field-label">
        <span>Zaman adımı</span>
        <Kw card="/DT" text="/DT · /DT/NODA" />
      </div>
      <div className="crash-var-chips" role="group" aria-label="Zaman adımı kartı">
        {DT_KINDS.map((d) => (
          <button
            key={d.key || "none"}
            type="button"
            className={value.dtKind === d.key ? "crash-var-chip active" : "crash-var-chip"}
            aria-pressed={value.dtKind === d.key}
            title={d.help}
            disabled={disabled}
            onClick={() => set({ dtKind: d.key })}
          >
            {d.label}
          </button>
        ))}
      </div>
      {kind && <p className="crash-behavior-hint">{kind.help}</p>}
      <div className="crash-expert-grid cols-2">
        <label className="crash-expert-field">
          <span>Δt_sca</span>
          <input
            aria-label="Δt_sca"
            value={value.dtScale}
            placeholder="0.9"
            disabled={disabled || !value.dtKind}
            onChange={(e) => set({ dtScale: e.target.value })}
          />
        </label>
        <label className="crash-expert-field">
          <span>Δt_min (ms)</span>
          <input
            aria-label="Δt_min (ms)"
            value={value.dtMin}
            disabled={disabled || !value.dtKind}
            onChange={(e) => set({ dtMin: e.target.value })}
          />
        </label>
      </div>

      <details className="crash-solver-help">
        <summary>Açıklama</summary>
        <ul>
          <li>
            Explicit çözümde kararlı zaman adımı en küçük elemanın karakteristik boyu / dalga hızıdır (Courant).
            Adım sayısı ≈ süre / Δt; süre ya da en küçük eleman küçüldükçe koşu uzar.
          </li>
          <li>Δt_sca bu kararlı adımı çarpar (1'in altı daha küçük, daha güvenli adım).</li>
          <li>
            /DT/NODA/CST (kütle ölçekleme): Δt'si Δt_min altına düşen düğüme kütle eklenir; adım Δt_min'de kalır.
            Eklenen kütle dinamiği değiştirir — oranı 5 · Sonuçlar'da "Eklenen kütle oranı" olarak yazılır.
          </li>
          <li>/DT/NODA/STOP: Δt, Δt_min altına düşünce koşu durur. Boş (Yok): Radioss kendi kararlı adımını kullanır.</li>
        </ul>
      </details>

      {(dtMinLast != null || massLast != null) && (
        <p className="crash-behavior-hint" data-testid="crash-solver-last">
          Son koşu: Δt_min {dtMinLast != null ? `${fmt(dtMinLast)} ms` : "—"} · eklenen kütle oranı{" "}
          {massLast != null ? fmt(massLast) : "—"}
          {dtMinLast != null && Number(tEnd) > 0 ? ` · süre / Δt_min ≈ ${Math.round(Number(tEnd) / dtMinLast)} adım (üst sınır)` : ""}
        </p>
      )}
    </div>
  );
}
