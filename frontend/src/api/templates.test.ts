import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TemplateApiError,
  createGeometryFromTemplate,
  downloadGeometryStep,
  fetchTemplates,
} from "./templates";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fetchTemplates", () => {
  it("GET /templates gövdesinden listeyi döner", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        count: 1,
        templates: [{ id: "cantilever_beam", name: "Ankastre kiriş" }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const list = await fetchTemplates();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/templates");
    expect(list).toEqual([{ id: "cantilever_beam", name: "Ankastre kiriş" }]);
  });

  it("HTTP hata kodunda TemplateApiError fırlatır", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    await expect(fetchTemplates()).rejects.toBeInstanceOf(TemplateApiError);
  });
});

describe("createGeometryFromTemplate", () => {
  it("POST /templates/{id}/create ile params gönderir", async () => {
    const created = { geometry_id: 9, template_id: "cantilever_beam" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(created));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createGeometryFromTemplate("cantilever_beam", {
      length: 400,
      thickness: 10,
      width: 50,
    });
    expect(result.geometry_id).toBe(9);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/templates/cantilever_beam/create",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          params: { length: 400, thickness: 10, width: 50 },
        }),
      }),
    );
  });

  it("sunucu metnini TemplateApiError olarak iletir", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("L en az 5*thickness olmalı.", { status: 422 })),
    );
    await expect(createGeometryFromTemplate("cantilever_beam", { length: 1 })).rejects.toThrow(
      "L en az 5*thickness olmalı.",
    );
  });
});

function okBlobResponse(bytes = "ISO-10303"): { ok: boolean; status: number; blob: () => Promise<Blob> } {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob([bytes], { type: "application/octet-stream" }),
  };
}

describe("downloadGeometryStep", () => {
  it("blob'u .step dosya adı ile indirir", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okBlobResponse());
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn().mockReturnValue("blob:step");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    const click = vi.fn();
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        Object.defineProperty(el, "click", { value: click });
      }
      return el;
    });

    await downloadGeometryStep(9, "9.step");
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/geometry/9/step");
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:step");
  });

  it("uzantısız ada .step ekler", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okBlobResponse("x")));
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn().mockReturnValue("blob:step"),
      revokeObjectURL: vi.fn(),
    });
    let downloadAttr = "";
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        Object.defineProperty(el, "click", { value: vi.fn() });
        Object.defineProperty(el, "download", {
          get: () => downloadAttr,
          set: (v: string) => {
            downloadAttr = v;
          },
        });
      }
      return el;
    });

    await downloadGeometryStep(3, "parca");
    expect(downloadAttr).toBe("parca.step");
  });

  it("HTTP hata kodunda TemplateApiError fırlatır", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
    await expect(downloadGeometryStep(99, "x.step")).rejects.toBeInstanceOf(TemplateApiError);
  });
});
