import { afterEach, describe, expect, it, vi } from "vitest";
import { generateMesh } from "./geometry";

describe("1.23 E — mesh isteğinde eğriliğe göre boyut", () => {
  afterEach(() => vi.restoreAllMocks());

  const fetchSpy = () =>
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ geometry_id: 1, element_size: 30, dimension: 2, element_scheme: "tet" }), { status: 200 }),
    );

  it("açıkken curvature_elements + curvature_min_size gönderilir", async () => {
    const spy = fetchSpy();
    await generateMesh(1, 30, 2, "tet", {}, false, {}, { elements: 100, minSize: 1 });
    const body = JSON.parse(String(spy.mock.calls[0][1]?.body));
    expect(body).toMatchObject({ element_size: 30, curvature_elements: 100, curvature_min_size: 1 });
  });

  it("kapalıyken alan yok (eski istek aynı)", async () => {
    const spy = fetchSpy();
    await generateMesh(1, 30, 2, "tet");
    const body = JSON.parse(String(spy.mock.calls[0][1]?.body));
    expect(body).not.toHaveProperty("curvature_elements");
    expect(body).not.toHaveProperty("curvature_min_size");
    expect(body).not.toHaveProperty("shell_order");
  });

  it("2D'de kabuk mertebesi 2 → shell_order: 2; 3D'de gönderilmez", async () => {
    const spy = fetchSpy();
    await generateMesh(1, 8, 2, "quad", {}, false, {}, null, 2);
    expect(JSON.parse(String(spy.mock.calls[0][1]?.body))).toMatchObject({ shell_order: 2 });
    await generateMesh(1, 8, 3, "tet", {}, false, {}, null, 2);
    expect(JSON.parse(String(spy.mock.calls[1][1]?.body))).not.toHaveProperty("shell_order");
  });
});
