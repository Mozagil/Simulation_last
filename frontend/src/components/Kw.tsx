/**
 * OpenRadioss kart adı + (tercih açıksa) LS-DYNA karşılığı (bilgi amaçlı).
 * `KwRef` yalnız karşılığı yazar; `DynaToggle` tercihi değiştirir.
 */
import { dynaFor, setDynaRefs, useDynaRefs } from "../lib/dynaKeywords";

export function KwRef({ card }: { card: string }) {
  const on = useDynaRefs();
  const eq = dynaFor(card);
  if (!on || !eq) return null;
  return (
    <span className="kw-dyna" title="LS-DYNA karşılığı (yaklaşık, bilgi amaçlı)">
      ≈{" "}
      {eq.split("_").map((part, i) => (
        <span key={i}>
          {i > 0 && "_"}
          {i > 0 && <wbr />}
          {part}
        </span>
      ))}
    </span>
  );
}

/** `<code>text</code>` + karşılık. `card` verilmezse `text` kart adı sayılır. */
export default function Kw({ card, text }: { card?: string; text?: string }) {
  const c = card ?? text ?? "";
  return (
    <span className="kw">
      <code>{text ?? c}</code>
      <KwRef card={c} />
    </span>
  );
}

/** Açık/kapalı düğme: iki kart arasında eşdeğer (⇄) simgesi + "LS-DYNA". */
export function DynaToggle() {
  const on = useDynaRefs();
  return (
    <div className="kw-toggle-row">
      <button
        type="button"
        className={on ? "kw-toggle active" : "kw-toggle"}
        aria-pressed={on}
        title={on ? "LS-DYNA karşılıklarını gizle" : "LS-DYNA karşılıklarını göster (yaklaşık, bilgi amaçlı)"}
        onClick={() => setDynaRefs(!on)}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="1.5" y="2.5" width="5" height="4" rx="1" />
          <rect x="9.5" y="9.5" width="5" height="4" rx="1" />
          <path d="M9 4.5h4.5l-1.5-1.5M7 11.5H2.5L4 13" />
        </svg>
        <span>LS-DYNA karşılıkları</span>
        <span className="kw-toggle-state">{on ? "açık" : "kapalı"}</span>
      </button>
    </div>
  );
}
