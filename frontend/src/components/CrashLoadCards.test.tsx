import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import CrashLoadCards, {
  cardSummary,
  cardsPayload,
  coverage,
  newCard,
  railDofs,
  type LoadCard,
} from "./CrashLoadCards";

describe("cardsPayload / özet / kapsama", () => {
  it("kartları istek alanlarına çevirir", () => {
    const cards: LoadCard[] = [
      { ...newCard(1, "inivel", "part:0"), speed: "8", dir: ["0", "0", "-1"] },
      { ...newCard(2, "bcs", "region:taban"), dofs: "111000" },
      { ...newCard(3, "impvel", "part:1"), axis: "Z", velocity: "-2", tStop: "5" },
      { ...newCard(4, "rbody", "region:kizak"), mass: "50" },
    ];
    expect(cardsPayload(cards)).toEqual({
      initial_velocities: [{ name: "inivel_1", part_id: 0, speed_m_s: 8, direction: [0, 0, -1] }],
      boundary_conditions: [{ name: "bcs_2", region: "taban", dofs: "111000" }],
      imposed_velocities: [{ name: "impvel_3", part_id: 1, direction: "Z", velocity_m_s: -2, t_start_ms: 0, t_stop_ms: 5 }],
      rigid_bodies: [{ name: "rbody_4", region: "kizak", mass_kg: 50 }],
    });
  });

  it("kızak rayda: çarpma ekseni serbest, ray /BCS'i rijit gövdeye bağlanır; ivme kaydı", () => {
    const sled: LoadCard = { ...newCard(1, "rbody", "region:kutu_arka"), mass: "40", rbMotion: "rail", hic: true };
    expect(railDofs("X")).toBe("011111");
    expect(railDofs("Z")).toBe("110111");
    expect(cardsPayload([sled], "X")).toMatchObject({
      rigid_bodies: [{ name: "rbody_1", region: "kutu_arka", mass_kg: 40, th_accel: true }],
      boundary_conditions: [{ name: "rbody_1_ray", rigid_body: "rbody_1", dofs: "011111" }],
    });
    expect(cardSummary(sled, "X")).toBe("kutu_arka → rijit + 40 kg · rayda (yalnız x) · ivme kaydı");
    // serbest: ray /BCS yok
    expect(cardsPayload([{ ...sled, rbMotion: "free" }]).boundary_conditions).toEqual([]);
  });

  it("geçersiz değerde açık hata; kütle boş bırakılamaz", () => {
    expect(() => cardsPayload([{ ...newCard(1, "bcs", "part:0"), dofs: "12" }])).toThrow(/DOF/);
    expect(() => cardsPayload([{ ...newCard(1, "inivel", "part:0"), speed: "" }])).toThrow(/hız/);
    expect(() => cardsPayload([newCard(1, "inivel", "")])).toThrow(/hedef/);
    expect(() => cardsPayload([newCard(1, "rbody", "part:0")])).toThrow(/kütle/);
  });

  it("kilit özeti okunur", () => {
    expect(cardSummary({ ...newCard(1, "bcs", "region:plaka_kenar"), dofs: "111111" })).toBe("plaka_kenar → tamamen kilitli");
    expect(cardSummary({ ...newCard(1, "bcs", "region:yan"), dofs: "001000" })).toBe("yan → Tz kilitli");
  });

  it("kart modunda ilk hızı olmayan hareketli parça işaretlenir", () => {
    const cov = coverage([0, 1, 2], { 2: "fixed" }, [newCard(1, "inivel", "part:0")]);
    expect(cov.map((c) => [c.partId, c.role, c.noVelocity])).toEqual([
      [0, "moving", false],
      [1, "moving", true],
      [2, "fixed", false],
    ]);
    expect(coverage([0, 1], {}, []).some((c) => c.noVelocity)).toBe(false);
  });
});

function Harness({ regions = ["kutu_arka", "plaka_kenar"] }: { regions?: string[] }) {
  const [cards, setCards] = useState<LoadCard[]>([]);
  return <CrashLoadCards cards={cards} onChange={setCards} partIds={[0, 1]} regions={regions} impactAxis="X" />;
}

describe("CrashLoadCards", () => {
  it("ne-zaman satırlı ekleme düğmesi; kart açık gelir, hedef çipi seçilir, kapanınca özet, silinir", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "+ Bölgeyi kilitle" })).toHaveTextContent(/Ankastre kenar/);
    fireEvent.click(screen.getByRole("button", { name: "+ Bölgeyi kilitle" }));
    const card = screen.getByTestId("crash-card-bcs");
    const targets = within(card).getByRole("group", { name: "Bölgeyi kilitle #1 hedef" });
    fireEvent.click(within(targets).getByRole("button", { name: "bölge: plaka_kenar" }));
    fireEvent.click(within(card).getByLabelText("Rz kilitli"));
    expect(within(card).getByTestId("crash-card-summary")).toHaveTextContent("plaka_kenar → yalnız Rz serbest");
    fireEvent.click(within(card).getByRole("button", { name: "Bölgeyi kilitle #1 kapat" }));
    expect(within(card).queryByRole("group", { name: "Bölgeyi kilitle #1 hedef" })).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: "Bölgeyi kilitle #1 sil" }));
    expect(screen.queryByTestId("crash-card-bcs")).toBeNull();
  });

  it("hazır kurulum 'Kızak testi': arka bölge, rayda, kütle boş (mühendis girer)", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Kızak testi" }));
    const card = screen.getByTestId("crash-card-rbody");
    expect(within(card).getByTestId("crash-card-summary")).toHaveTextContent(
      "kutu_arka → rijit kütle girilmedi · rayda (yalnız x)",
    );
    fireEvent.change(within(card).getByLabelText("Ek kütle"), { target: { value: "40" } });
    expect(within(card).getByTestId("crash-card-summary")).toHaveTextContent("kutu_arka → rijit + 40 kg · rayda (yalnız x)");
  });

  it("bölge yoksa yönlendirme metni", () => {
    render(<Harness regions={[]} />);
    expect(screen.getByText(/Bölge yok/)).toBeInTheDocument();
  });
});
