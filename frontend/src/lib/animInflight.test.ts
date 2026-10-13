import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCrashAnimation } from "../api/crash";

describe("fetchCrashAnimation — eşzamanlı istek paylaşımı", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("aynı koşu için aynı anda iki çağrı tek HTTP isteği; bitince yeni istek", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ faces: [], face_part: [], scalars: {}, frames: [] }), { status: 200 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const [a, b] = await Promise.all([fetchCrashAnimation(5), fetchCrashAnimation(5)]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
    await fetchCrashAnimation(5);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("200 ama geçersiz gövde: null yerine açık hata", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response('{"faces": [1,', { status: 200 }))));
    await expect(fetchCrashAnimation(6)).rejects.toThrow(/okunamadı/);
  });
});
