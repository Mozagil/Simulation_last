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
      ≈ {eq}
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

export function DynaToggle() {
  const on = useDynaRefs();
  return (
    <label className="material-check kw-toggle">
      <input type="checkbox" checked={on} onChange={(e) => setDynaRefs(e.target.checked)} />
      LS-DYNA karşılıklarını göster
    </label>
  );
}
