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
