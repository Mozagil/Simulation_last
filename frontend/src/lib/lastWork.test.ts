import { beforeEach, describe, expect, it } from "vitest";
import { lastWorkLabel, pauseLastWork, readLastWork, saveLastWork } from "./lastWork";

describe("1.23 B3b — son crash çalışması", () => {
  beforeEach(() => window.localStorage.removeItem("crashLastWork"));

  it("kaydet / oku; kayıt yoksa null", () => {
    expect(readLastWork()).toBeNull();
    saveLastWork({ geometryId: 4277, name: "x.step", runId: 325, dim: 2, auto: true });
    expect(readLastWork()).toEqual({ geometryId: 4277, name: "x.step", runId: 325, dim: 2, auto: true });
  });

  it("bozuk / eksik kayıt yok sayılır, eksik alanlar varsayılana döner", () => {
    window.localStorage.setItem("crashLastWork", "{bozuk");
    expect(readLastWork()).toBeNull();
    window.localStorage.setItem("crashLastWork", JSON.stringify({ geometryId: -1 }));
    expect(readLastWork()).toBeNull();
    window.localStorage.setItem("crashLastWork", JSON.stringify({ geometryId: 9, dim: 7 }));
    expect(readLastWork()).toEqual({ geometryId: 9, name: "geometri #9", runId: null, dim: null, auto: true });
  });

  it("Yeni Case: kayıt durur, kendiliğinden açılma kapanır", () => {
    saveLastWork({ geometryId: 9, name: "a.step", runId: null, dim: 3, auto: true });
    pauseLastWork();
    expect(readLastWork()).toMatchObject({ geometryId: 9, auto: false });
  });

  it("etiket: koşuysa koşu + geometri, değilse dosya adı", () => {
    expect(lastWorkLabel({ geometryId: 4277, name: "x", runId: 325, dim: 2, auto: true })).toBe("koşu #325 · geometri #4277");
    expect(lastWorkLabel({ geometryId: 9, name: "a.step", runId: null, dim: null, auto: true })).toBe("a.step");
  });
});
