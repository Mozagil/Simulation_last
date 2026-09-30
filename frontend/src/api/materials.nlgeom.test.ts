import { afterEach, describe, expect, it, vi } from "vitest";
import { isValidIncrements, solveGeometry } from "./materials";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function lastBody(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

describe("solveGeometry — NLGEOM (TODO 4)", () => {
  const base = { dimension: 3 as const, bcs: [] };

  it("kapalıyken nlgeom/n_increments hiç gönderilmez (lineer istek değişmez)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await solveGeometry(1, { ...base, nlgeom: false, n_increments: 40 });
    const body = lastBody(fetchMock);
    expect(body).not.toHaveProperty("nlgeom");
    expect(body).not.toHaveProperty("n_increments");
  });

  it("açıkken nlgeom ve artım sayısı gönderilir", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await solveGeometry(1, { ...base, nlgeom: true, n_increments: 40 });
    expect(lastBody(fetchMock)).toMatchObject({ nlgeom: true, n_increments: 40 });
  });
});

describe("solveGeometry — plastisite (ROADMAP 0.6.4)", () => {
  it("açıkken plasticity ve artım sayısı gider; NLGEOM olmadan da", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await solveGeometry(1, { dimension: 3, bcs: [], plasticity: true, n_increments: 25 });
    const body = lastBody(fetchMock);
    expect(body).toMatchObject({ plasticity: true, n_increments: 25 });
    expect(body).not.toHaveProperty("nlgeom");
  });

  it("kapalıyken alan hiç gönderilmez", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await solveGeometry(1, { dimension: 3, bcs: [], plasticity: false, n_increments: 25 });
    const body = lastBody(fetchMock);
    expect(body).not.toHaveProperty("plasticity");
    expect(body).not.toHaveProperty("n_increments");
  });
});

describe("parsePlasticCurve", () => {
  it("satırları okur, boşta null, hatalı satırda açık hata", async () => {
    const { parsePlasticCurve } = await import("./materials");
    expect(parsePlasticCurve("")).toBeNull();
    expect(parsePlasticCurve("235, 0\n454; 0.229")).toEqual([[235, 0], [454, 0.229]]);
    expect(() => parsePlasticCurve("235, 0.01")).toThrow(/ε_p = 0/);
    expect(() => parsePlasticCurve("235, 0\nabc")).toThrow(/2\. satır/);
    expect(() => parsePlasticCurve("235, 0\n300, 0.2\n400, 0.1")).toThrow(/artan/);
  });

  it("solveGeometry tabloyu yalnız plastisite açıkken gönderir", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await solveGeometry(1, { dimension: 3, bcs: [], plasticity: true, plastic_curve: [[235, 0], [454, 0.229]] });
    expect(lastBody(fetchMock)).toMatchObject({ plasticity: true, plastic_curve: [[235, 0], [454, 0.229]] });
  });
});

describe("screenSolve", () => {
  it("geometry_id ve bcs ile ön kontrol ister, sonucu döner", async () => {
    const { screenSolve } = await import("./materials");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ has_analytic: true, u_over_l: 0.33, u_mm: 330, sigma_mpa: 220, threshold: 0.1, large_deformation: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const out = await screenSolve(7, [{ type: "cload", fy: -60 }]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/geometry/7/solve/screen");
    expect(lastBody(fetchMock)).toEqual({ bcs: [{ type: "cload", fy: -60 }] });
    expect(out.large_deformation).toBe(true);
  });
});

describe("isValidIncrements", () => {
  it("backend sınırı 1–500 tam sayı", () => {
    expect(isValidIncrements("20")).toBe(true);
    expect(isValidIncrements("1")).toBe(true);
    expect(isValidIncrements("500")).toBe(true);
    expect(isValidIncrements("0")).toBe(false);
    expect(isValidIncrements("501")).toBe(false);
    expect(isValidIncrements("2.5")).toBe(false);
    expect(isValidIncrements("")).toBe(false);
  });
});
