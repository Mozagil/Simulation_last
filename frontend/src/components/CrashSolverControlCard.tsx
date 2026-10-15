/** 1.23 D2 — çözüm kontrolü tek yerde: bitiş süresi (/RUN), zaman adımı kartı (/DT…),
 * Δt ölçeği, Δt_min / kütle ölçekleme + kısa açıklama. Son koşunun Δt_min ve eklenen
 * kütle oranı veri olarak gösterilir. Öneri yok — değerleri mühendis seçer.
 */

import Kw from "./Kw";
import { DT_KINDS, dampingSummary, type OutputState } from "./CrashOutputCard";

export function solverSummary(
  tEnd: string,
  s: Pick<OutputState, "dtKind" | "dtScale" | "dtMin"> & Partial<Pick<OutputState, "dampOn" | "dampAlpha" | "dampBeta" | "dampParts">>,
): string {
  const parts = [`${tEnd || "—"} ms`];
  if (!s.dtKind) parts.push("Δt: Radioss");
  else {
    parts.push(s.dtKind === "DT" ? "/DT" : `/DT/${s.dtKind}`);
    if (s.dtScale.trim()) parts.push(`Δt_sca ${s.dtScale}`);
    if (s.dtMin.trim()) parts.push(`Δt_min ${s.dtMin} ms`);
  }
  if (s.dampOn) parts.push(dampingSummary({ dampOn: true, dampAlpha: s.dampAlpha ?? "0", dampBeta: s.dampBeta ?? "0", dampParts: s.dampParts ?? [] }));
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
  partOptions = [],
  disabled = false,
}: {
  tEnd: string;
  onTEnd: (v: string) => void;
  value: OutputState;
  onChange: (next: OutputState) => void;
  /** Son koşunun skalerleri (varsa): timestep_min, mass_added_rel, cycles… */
  lastScalars?: Record<string, number>;
  /** 1.24c2 — sönüm kapsamı için parça no'ları */
  partOptions?: number[];
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

      <div className="crash-field-label">
        <span>Sönüm (Rayleigh)</span>
        <Kw card="/DAMP" text="/DAMP" />
      </div>
      <label className="material-check">
        <input
          type="checkbox"
          aria-label="Sönüm ekle"
          checked={value.dampOn}
          disabled={disabled}
          onChange={(e) => set({ dampOn: e.target.checked })}
        />
        Sönüm ekle · C = α·M + β·K
      </label>
      {value.dampOn && (
        <div className="crash-damp" data-testid="crash-damp">
          <div className="crash-expert-grid cols-2">
            {(
              [
                ["dampAlpha", "α (kütle orantılı)", "1/s"],
                ["dampBeta", "β (rijitlik orantılı)", "s"],
                ["dampT0", "Başlangıç", "ms"],
                ["dampT1", "Bitiş (0 = koşu sonu)", "ms"],
              ] as const
            ).map(([key, lab, unit]) => (
              <label key={key} className="crash-expert-field">
                <span>
                  {lab} · {unit}
                </span>
                <input aria-label={`Sönüm ${lab}`} value={value[key]} disabled={disabled} onChange={(e) => set({ [key]: e.target.value })} />
              </label>
            ))}
          </div>
          {partOptions.length > 1 && (
            <div className="crash-var-chips" role="group" aria-label="Sönüm parçaları">
              {partOptions.map((pid) => {
                const on = value.dampParts.includes(pid);
                return (
                  <button
                    key={pid}
                    type="button"
                    className={on ? "crash-var-chip active" : "crash-var-chip"}
                    aria-pressed={on}
                    disabled={disabled}
                    onClick={() => set({ dampParts: on ? value.dampParts.filter((p) => p !== pid) : [...value.dampParts, pid] })}
                  >
                    #{pid}
                  </button>
                );
              })}
              <span className="crash-var-note">{value.dampParts.length === 0 ? "seçim yok = tüm parçalar" : ""}</span>
            </div>
          )}
          <details className="crash-solver-help">
            <summary>Açıklama</summary>
            <ul>
              <li>
                Düğüm grubuna Rayleigh sönümü: C = α·M + β·K. α kütleyle orantılı (mutlak hızı söndürür; rijit
                hareket de yavaşlar), β rijitlikle orantılı (yüksek frekanslı titreşimi söndürür; kararlı Δt küçülür).
              </li>
              <li>Deck'e model birimiyle yazılır: α / 1000 (1/ms), β · 1000 (ms). α ve β ikisi birden 0 olamaz.</li>
              <li>Sönüm kullanmak ve değerleri mühendisin kararı; varsayılan yok.</li>
            </ul>
          </details>
        </div>
      )}

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
