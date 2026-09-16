/** "Model üret" onay penceresi: şema + yük değerleri.
 *
 * Şablon, sınır koşullarını hazır getirir ama yükün BÜYÜKLÜĞÜ tasarıma özgüdür —
 * kullanıcı burada girer. Kısıtlar (fixed/displacement) salt okunur gösterilir;
 * bunlar şablonun tanımı gereği sabittir, geometri üretildikten sonra BC
 * listesinden değiştirilebilir.
 */

import type { SolveBC } from "../api/materials";
import type { GeometryTemplateInfo } from "../api/templates";
import TemplateSchematic from "./TemplateSchematic";

/** Kullanıcının düzenleyebildiği yük alanları: BC tipine göre. */
const LOAD_FIELDS: Record<string, { key: string; label: string; unit: string }[]> = {
  cload: [
    { key: "fx", label: "Fx", unit: "N" },
    { key: "fy", label: "Fy", unit: "N" },
    { key: "fz", label: "Fz", unit: "N" },
  ],
  pressure: [{ key: "magnitude", label: "Basınç", unit: "MPa" }],
  bearing: [{ key: "magnitude", label: "Yatak kuvveti", unit: "N" }],
  gravity: [
    { key: "gx", label: "gx", unit: "mm/s²" },
    { key: "gy", label: "gy", unit: "mm/s²" },
    { key: "gz", label: "gz", unit: "mm/s²" },
  ],
};

export function isLoadBc(bc: SolveBC): boolean {
  return bc.type in LOAD_FIELDS;
}

/** BC listesindeki her yük alanı için `${index}.${key}` anahtarlı metin girdileri. */
export function loadInputsFromBcs(bcs: SolveBC[]): Record<string, string> {
  const out: Record<string, string> = {};
  bcs.forEach((bc, index) => {
    for (const f of LOAD_FIELDS[bc.type] ?? []) {
      const value = (bc as Record<string, unknown>)[f.key];
      out[`${index}.${f.key}`] = typeof value === "number" ? String(value) : "0";
    }
  });
  return out;
}

/** Girdileri BC listesine uygular. Hatalı sayı varsa hata metni döner. */
export function applyLoadInputs(
  bcs: SolveBC[],
  inputs: Record<string, string>,
): SolveBC[] | string {
  const out: SolveBC[] = [];
  for (const [index, bc] of bcs.entries()) {
    const fields = LOAD_FIELDS[bc.type];
    if (!fields) {
      out.push(bc);
      continue;
    }
    const next: SolveBC = { ...bc };
    for (const f of fields) {
      const raw = (inputs[`${index}.${f.key}`] ?? "").trim();
      const value = Number(raw);
      if (raw === "" || !Number.isFinite(value)) {
        return `${f.label} geçerli bir sayı olmalı.`;
      }
      (next as Record<string, unknown>)[f.key] = value;
    }
    out.push(next);
  }
  return out;
}

function describeTarget(bc: SolveBC, regions: GeometryTemplateInfo["regions"]): string {
  if (!bc.region) return "";
  const info = regions.find((r) => r.name === bc.region);
  return info?.description ? `${bc.region} — ${info.description}` : bc.region;
}

interface TemplateLoadDialogProps {
  template: GeometryTemplateInfo;
  /** Parametre adı -> kullanıcı girdisi (üst panelden, salt okunur özet). */
  params: Record<string, string>;
  bcs: SolveBC[];
  inputs: Record<string, string>;
  busy: boolean;
  error: string | null;
  onInputChange: (key: string, value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function TemplateLoadDialog({
  template,
  params,
  bcs,
  inputs,
  busy,
  error,
  onInputChange,
  onCancel,
  onConfirm,
}: TemplateLoadDialogProps) {
  const loads = bcs.map((bc, index) => ({ bc, index })).filter((x) => isLoadBc(x.bc));
  const constraints = bcs.filter((bc) => !isLoadBc(bc));

  return (
    <div className="template-dialog-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="template-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`${template.name} — model üret`}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="material-assignments-title">{template.name}</p>
        <TemplateSchematic templateId={template.id} />

        <p className="template-dialog-params">
          {Object.entries(params)
            .map(([k, v]) => `${k} = ${v}`)
            .join(" · ")}
        </p>

        {constraints.length > 0 && (
          <div className="template-dialog-section">
            <span className="template-dialog-section-title">Kısıtlar</span>
            <ul className="template-dialog-list">
              {constraints.map((bc, i) => (
                <li key={`${bc.type}-${i}`}>
                  <strong>{bc.type}</strong> · {describeTarget(bc, template.regions)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {loads.length === 0 ? (
          <p className="filename">Bu şablonda düzenlenecek yük yok.</p>
        ) : (
          <div className="template-dialog-section">
            <span className="template-dialog-section-title">Yük</span>
            {loads.map(({ bc, index }) => (
              <div key={`${bc.type}-${index}`} className="template-dialog-load">
                <p className="filename">{describeTarget(bc, template.regions)}</p>
                <div className="template-dialog-load-fields">
                  {(LOAD_FIELDS[bc.type] ?? []).map((f) => (
                    <label key={f.key} className="mesh-field">
                      <span>{`${f.label} (${f.unit})`}</span>
                      <input
                        type="number"
                        step="any"
                        disabled={busy}
                        value={inputs[`${index}.${f.key}`] ?? ""}
                        onChange={(e) => onInputChange(`${index}.${f.key}`, e.target.value)}
                      />
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}

        <div className="template-panel-actions">
          <button type="button" disabled={busy} onClick={onConfirm}>
            {busy ? "Üretiliyor…" : "Modeli üret"}
          </button>
          <button type="button" disabled={busy} onClick={onCancel}>
            Vazgeç
          </button>
        </div>
      </div>
    </div>
  );
}
