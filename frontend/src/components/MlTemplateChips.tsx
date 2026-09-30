import type { GeometryTemplateInfo } from "../api/templates";

/**
 * Üst şerit şablon çipleri (ML Studio 1a). Veri ya da modeli olan şablonlar
 * çip olur; aktif şablon verisi olmasa da listede kalır. Tıklama stüdyonun
 * şablonunu değiştirir (DOE, yakınsama, model, tahmin hepsi ona geçer);
 * tezgahtaki geometri seçimine dokunmaz.
 */
export default function MlTemplateChips({
  templates,
  withData,
  activeId,
  onSelect,
}: {
  templates: GeometryTemplateInfo[];
  withData: string[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const ids = [...withData];
  if (activeId && !ids.includes(activeId)) ids.unshift(activeId);
  if (ids.length === 0) {
    return <span className="ml-studio-chip">seçilmedi — tezgahta şablon üret</span>;
  }
  return (
    <span className="ml-template-chips" role="group" aria-label="Şablon">
      {ids.map((id) => {
        const t = templates.find((x) => x.id === id);
        const on = id === activeId;
        return (
          <button
            key={id}
            type="button"
            className={on ? "doe-chip active" : "doe-chip"}
            aria-pressed={on}
            title={id}
            onClick={() => onSelect(id)}
          >
            {t?.name ?? id}
          </button>
        );
      })}
    </span>
  );
}
