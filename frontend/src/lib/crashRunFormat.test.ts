import { describe, expect, it } from "vitest";
import { curveGroup, curveLabel, curveUnit } from "./crashRunFormat";

describe("1.25c2 — eğri grupları / etiketleri", () => {
  it("anahtar → grup", () => {
    expect(curveGroup("rwall_force")).toBe("Kuvvet");
    expect(curveGroup("internal_energy")).toBe("Enerji");
    expect(curveGroup("contact_2_force")).toBe("Temas");
    expect(curveGroup("section_1_impulse")).toBe("Kesit");
    expect(curveGroup("acc_g_cfc1000")).toBe("İvme");
    expect(curveGroup("rwall_impulse")).toBe("İmpuls");
    expect(curveGroup("th_node_12_AX")).toBe("TH kanalları");
  });

  it("anahtar → okunur ad + birim; bilinmeyen anahtar ham kalır", () => {
    expect(curveLabel("rwall_force")).toBe("Duvar kuvveti (kN)");
    expect(curveLabel("rwall_force_cfc600")).toBe("Duvar kuvveti · CFC 600 (kN)");
    expect(curveLabel("kinetic_energy")).toBe("Kinetik enerji (KE) (J)");
    expect(curveLabel("contact_2_force")).toBe("Temas 2 kuvveti (kN)");
    expect(curveLabel("section_1_impulse")).toBe("Kesit 1 impulsu (N·s)");
    expect(curveLabel("acc_g_cfc1000")).toBe("İvme bileşkesi · CFC 1000 (g)");
    expect(curveLabel("th_node_12_AX")).toBe("th_node_12_AX");
  });

  it("impuls eğrisi kuvvet sayılmaz (ortalama kuvvet çizilmez), birim N·s", () => {
    expect(curveUnit("rwall_impulse")).toMatchObject({ unit: "N·s", isForce: false });
    expect(curveUnit("rwall_force")).toMatchObject({ unit: "kN", isForce: true });
  });
});
