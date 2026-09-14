import { describe, expect, it } from "vitest";
import {
  defaultsFromFields,
  numberFieldsFromSchema,
  parseParamInputs,
} from "./schemaForm";

const CANTILEVER_SCHEMA = {
  properties: {
    length: {
      type: "number",
      title: "Length",
      description: "Kiriş uzunluğu L (x)",
      default: 500,
      exclusiveMinimum: 0,
      unit: "mm",
    },
    thickness: {
      type: "number",
      default: 10,
      exclusiveMinimum: 0,
      unit: "mm",
    },
    width: {
      type: "number",
      default: 50,
      exclusiveMinimum: 0,
      unit: "mm",
    },
  },
};

describe("numberFieldsFromSchema", () => {
  it("sayı alanlarını varsayılan ve birimle çıkarır", () => {
    const fields = numberFieldsFromSchema(CANTILEVER_SCHEMA);
    expect(fields.map((f) => f.name)).toEqual(["length", "thickness", "width"]);
    expect(fields[0].defaultValue).toBe(500);
    expect(fields[0].unit).toBe("mm");
    expect(fields[0].exclusiveMin).toBe(0);
  });

  it("sayı olmayan özellikleri atlar", () => {
    const fields = numberFieldsFromSchema({
      properties: {
        name: { type: "string" },
        n: { type: "number", default: 1 },
      },
    });
    expect(fields).toHaveLength(1);
    expect(fields[0].name).toBe("n");
  });

  it("integer tipi ve title yoksa alan adını etiket yapar", () => {
    const fields = numberFieldsFromSchema({
      properties: {
        count: { type: "integer", default: 2 },
      },
    });
    expect(fields[0]).toMatchObject({ name: "count", label: "count", defaultValue: 2 });
  });
});

describe("defaultsFromFields", () => {
  it("referans ankastre değerlerini doldurur", () => {
    const d = defaultsFromFields(numberFieldsFromSchema(CANTILEVER_SCHEMA));
    expect(d).toEqual({ length: 500, thickness: 10, width: 50 });
  });
});

describe("parseParamInputs", () => {
  it("metni sayıya çevirir", () => {
    expect(parseParamInputs({ length: "400.5", thickness: "10" })).toEqual({
      length: 400.5,
      thickness: 10,
    });
  });

  it("bozuk girdide alan adını döndürür", () => {
    expect(parseParamInputs({ length: "abc" })).toBe("length geçerli bir sayı olmalı.");
  });

  it("boş metni sayı saymaz", () => {
    expect(parseParamInputs({ length: "" })).toBe("length geçerli bir sayı olmalı.");
  });
});
