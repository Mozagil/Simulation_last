import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import CrashLoadCards, { cardsPayload, coverage, newCard, type LoadCard } from "./CrashLoadCards";

describe("cardsPayload / coverage (TODO 11.9)", () => {
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

  it("geçersiz değerde açık hata", () => {
    expect(() => cardsPayload([{ ...newCard(1, "bcs", "part:0"), dofs: "12" }])).toThrow(/DOF/);
    expect(() => cardsPayload([{ ...newCard(1, "inivel", "part:0"), speed: "" }])).toThrow(/hız/);
    expect(() => cardsPayload([newCard(1, "inivel", "")])).toThrow(/hedef/);
  });

  it("kart modunda ilk hızı olmayan hareketli parça işaretlenir", () => {
    const cov = coverage([0, 1, 2], { 2: "fixed" }, [newCard(1, "inivel", "part:0")]);
    expect(cov.map((c) => [c.partId, c.role, c.cards, c.noVelocity])).toEqual([
      [0, "moving", ["İlk hız"], false],
      [1, "moving", [], true],
      [2, "fixed", [], false],
    ]);
    // kart yoksa eski davranış: uyarı yok
    expect(coverage([0, 1], {}, []).some((c) => c.noVelocity)).toBe(false);
  });
});

function Harness() {
  const [cards, setCards] = useState<LoadCard[]>([]);
  return <CrashLoadCards cards={cards} onChange={setCards} partIds={[0, 1]} regions={["taban"]} roles={{}} />;
}

describe("CrashLoadCards", () => {
  it("kart ekler, hedef seçer, siler; kapsama özeti güncellenir", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "+ İlk hız" }));
    const card = screen.getByTestId("crash-card-inivel");
    const target = within(card).getByLabelText("İlk hız #1 hedef") as HTMLSelectElement;
    expect([...target.options].map((o) => o.value)).toEqual(["part:0", "part:1", "region:taban"]);
    const summary = screen.getByLabelText("Kapsama özeti");
    expect(summary).toHaveTextContent("#0rol: hareketlikart: İlk hız");
    expect(summary).toHaveTextContent("⚠ ilk hız kartı yok");
    fireEvent.change(target, { target: { value: "region:taban" } });
    expect(summary).toHaveTextContent("bölge kartları: İlk hız → taban");
    fireEvent.click(within(card).getByRole("button", { name: "İlk hız #1 sil" }));
    expect(screen.queryByTestId("crash-card-inivel")).toBeNull();
  });

  it("bölge yoksa yönlendirme metni", () => {
    render(<CrashLoadCards cards={[]} onChange={() => undefined} partIds={[0]} regions={[]} roles={{}} />);
    expect(screen.getByText(/Bölge yok/)).toBeInTheDocument();
  });
});
