/** Pydantic JSON şemasından sayı alanı listesi — şablon formu / test. */

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: number;
  exclusiveMinimum?: number;
  minimum?: number;
  unit?: string;
}

export interface JsonSchema {
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

export interface SchemaNumberField {
  name: string;
  label: string;
  description: string;
  unit: string | null;
  defaultValue: number;
  exclusiveMin: number | null;
}

export function numberFieldsFromSchema(schema: JsonSchema): SchemaNumberField[] {
  const props = schema.properties ?? {};
  return Object.entries(props)
    .filter(([, p]) => p.type === "number" || p.type === "integer")
    .map(([name, p]) => ({
      name,
      label: p.title ?? name,
      description: p.description ?? "",
      unit: p.unit ?? null,
      defaultValue: typeof p.default === "number" ? p.default : 0,
      exclusiveMin: typeof p.exclusiveMinimum === "number" ? p.exclusiveMinimum : null,
    }));
}

export function defaultsFromFields(fields: SchemaNumberField[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const f of fields) out[f.name] = f.defaultValue;
  return out;
}

export function parseParamInputs(raw: Record<string, string>): Record<string, number> | string {
  const out: Record<string, number> = {};
  for (const [key, text] of Object.entries(raw)) {
    const trimmed = text.trim();
    const n = Number(trimmed);
    if (trimmed === "" || !Number.isFinite(n)) return `${key} geçerli bir sayı olmalı.`;
    out[key] = n;
  }
  return out;
}
