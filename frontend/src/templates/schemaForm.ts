/** Pydantic JSON şemasından sayı alanı listesi — şablon formu / test. */

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: number | string;
  exclusiveMinimum?: number;
  minimum?: number;
  unit?: string;
  enum?: (string | number)[];
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

export interface SchemaEnumField {
  name: string;
  label: string;
  description: string;
  options: string[];
  defaultValue: string;
}

export function enumFieldsFromSchema(schema: JsonSchema): SchemaEnumField[] {
  const props = schema.properties ?? {};
  return Object.entries(props)
    .filter(([, p]) => Array.isArray(p.enum) && p.enum.length > 0)
    .map(([name, p]) => {
      const options = p.enum!.map((v) => String(v));
      const d = p.default != null ? String(p.default) : options[0];
      return {
        name,
        label: p.title ?? name,
        description: p.description ?? "",
        options,
        defaultValue: options.includes(d) ? d : options[0],
      };
    });
}

export function defaultsFromFields(
  fields: SchemaNumberField[],
  enums: SchemaEnumField[] = [],
): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const f of fields) out[f.name] = f.defaultValue;
  for (const f of enums) out[f.name] = f.defaultValue;
  return out;
}

export function parseParamInputs(
  raw: Record<string, string>,
  enumNames: Iterable<string> = [],
): Record<string, number | string> | string {
  const enums = new Set(enumNames);
  const out: Record<string, number | string> = {};
  for (const [key, text] of Object.entries(raw)) {
    const trimmed = text.trim();
    if (enums.has(key)) {
      if (trimmed === "") return `${key} seçilmeli.`;
      out[key] = trimmed;
      continue;
    }
    const n = Number(trimmed);
    if (trimmed === "" || !Number.isFinite(n)) return `${key} geçerli bir sayı olmalı.`;
    out[key] = n;
  }
  return out;
}
