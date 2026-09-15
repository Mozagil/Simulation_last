/** Şablon parametrelerini tek satırda özetler: "L 512 · T 9.4 · W 48".
 *
 * Şemadaki harf (symbol) varsa o kullanılır — kullanıcı geçmiş satırında
 * gördüğü değeri şemadaki ölçüyle eşleştirebilsin. Yoksa parametre adı.
 */

import type { GeometryTemplateInfo } from "../api/templates";
import { numberFieldsFromSchema, type JsonSchema } from "./schemaForm";

export type SymbolMap = Record<string, Record<string, string>>;

/** template_id -> (parametre adı -> harf) */
export function symbolMapFromTemplates(templates: GeometryTemplateInfo[]): SymbolMap {
  const out: SymbolMap = {};
  for (const t of templates) {
    const fields = numberFieldsFromSchema(t.params_schema as JsonSchema);
    out[t.id] = Object.fromEntries(
      fields.filter((f) => f.symbol).map((f) => [f.name, f.symbol as string]),
    );
  }
  return out;
}

function fmt(value: number | string): string {
  if (typeof value !== "number") return String(value);
  // 512.4999 → 512.5, 48 → 48; sabit basamak sayısı gereksiz gürültü yapıyor.
  return String(Number(value.toFixed(2)));
}

export function summarizeTemplateParams(
  templateId: string | null,
  params: Record<string, number | string> | null,
  symbols: SymbolMap,
): string {
  if (!params || Object.keys(params).length === 0) return "";
  const map = (templateId && symbols[templateId]) || {};
  return Object.entries(params)
    .map(([name, value]) => `${map[name] ?? name} ${fmt(value)}`)
    .join(" · ");
}
