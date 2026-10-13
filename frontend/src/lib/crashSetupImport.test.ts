import { describe, expect, it } from "vitest";
import { cardsFromRequest, matCardFromModel } from "./crashSetupImport";
import { cardsPayload } from "../components/CrashLoadCards";
import { matCardPayload } from "../components/CrashMaterialCard";

describe("crashSetupImport (1.23 B1c)", () => {
  it("model → kart → model gidiş-dönüş: LAW2 + Johnson-Cook kopma", () => {
    const model = {
      law: "plastic" as const,
      sigma_y_pa: 235,
      harden_b_mpa: 300,
      harden_n: 0.4,
      eps_p_max: 0.3,
      fail: { johnson: { d1: 0.05, d2: 3.4, d3: -2.1, d4: 0.002, d5: 0.6, eps_dot0_per_s: 1, ifail_sh: 1, ifail_so: 1, dadv: 0 } },
    };
    const card = matCardFromModel(model);
    expect(card.law).toBe("plastic");
    expect(card.sigmaY).toBe("235");
    expect(card.failJohnson?.d2).toBe("3.4");
    expect(card.failTens).toBeNull();
    expect(matCardPayload(card)).toMatchObject({ law: "plastic", sigma_y_pa: 235, harden_n: 0.4, fail: { johnson: { d3: -2.1 } } });
  });

  it("boş model varsayılan kart; LAW36 boş eğri listesi = malzemeden", () => {
    expect(matCardFromModel(null).law).toBe("plastic");
    expect(matCardFromModel({ law: "tabulated", tab_curves: [] }).curvesFromMaterial).toBe(true);
    const c = matCardFromModel({ law: "tabulated", tab_curves: [{ eps_dot_per_s: 0, points: [[0, 235], [0.1, 300]] }] });
    expect(c.tabCurves[0].points).toBe("0 235\n0.1 300");
  });

  it("kart listeleri → Ek tanımlar kartları; tekrar gövdeye aynı (kızak rayda)", () => {
    const req = {
      initial_velocities: [{ name: "inivel_1", part_id: 1, speed_m_s: 5, direction: [0, 0, -1] }],
      boundary_conditions: [
        { name: "bcs_2", region: "plaka_kenar", dofs: "111111" },
        { name: "rbody_3_ray", rigid_body: "rbody_3", dofs: "011111" },
      ],
      imposed_velocities: [],
      rigid_bodies: [{ name: "rbody_3", region: "kutu_arka", mass_kg: 40, th_accel: true }],
    };
    const cards = cardsFromRequest(req, "X");
    expect(cards.map((c) => [c.kind, c.target])).toEqual([
      ["inivel", "part:1"],
      ["bcs", "region:plaka_kenar"],
      ["rbody", "region:kutu_arka"],
    ]);
    const rb = cards[2];
    expect(rb.rbMotion).toBe("rail");
    expect(rb.mass).toBe("40");
    expect(rb.hic).toBe(true);
    const back = cardsPayload(cards, "X");
    expect(back.rigid_bodies[0]).toMatchObject({ region: "kutu_arka", mass_kg: 40, th_accel: true });
    expect(back.boundary_conditions).toContainEqual({ name: "bcs_2", region: "plaka_kenar", dofs: "111111" });
    expect(back.initial_velocities[0]).toMatchObject({ part_id: 1, speed_m_s: 5, direction: [0, 0, -1] });
  });
});
