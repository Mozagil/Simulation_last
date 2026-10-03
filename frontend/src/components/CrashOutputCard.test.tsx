import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import CrashOutputCard, { defaultOutput, outputPayload, parseNodeIds, type OutputState } from "./CrashOutputCard";

function Harness({ onState }: { onState: (s: OutputState) => void }) {
  const [s, setS] = useState<OutputState>(defaultOutput);
  return (
    <CrashOutputCard
      value={s}
      partOptions={[0, 1]}
      onChange={(n) => {
        setS(n);
        onState(n);
      }}
    />
  );
}

describe("CrashOutputCard", () => {
  it("varsayılan = backend varsayılanı (eski deck)", () => {
    expect(outputPayload(defaultOutput())).toEqual({
      engine: { th_dt_ms: null, anim_dt_ms: null, dt_kind: "", dt_scale: 0, dt_min_ms: 0 },
      filters: { force_cfc: null, acc_cfc: null },
      th: {
        rwall: { enabled: true, vars: ["FNX", "FNY", "FNZ"] },
        inter: { enabled: true, vars: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"] },
        part: { enabled: true, vars: ["IE", "KE"] },
        sect: { enabled: true, vars: ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"] },
        node_ids: [],
        node_vars: ["AX", "AY", "AZ"],
      },
      sections: [],
    });
  });

  it("düğüm kimlikleri: virgül/boşluk, tekrar atılır, geçersiz hata", () => {
    expect(parseNodeIds("12, 480 12;7")).toEqual([12, 480, 7]);
    expect(() => parseNodeIds("12, x")).toThrow(/düğüm kimliği/);
  });

  it("zaman adımı kartı, TH çipleri ve kesit arayüzden payload'a", () => {
    let last = defaultOutput();
    render(<Harness onState={(s) => (last = s)} />);
    fireEvent.change(screen.getByLabelText("TH aralığı (ms)"), { target: { value: "0.002" } });
    // tür seçilmeden Δt alanları kapalı
    expect(screen.getByLabelText("Δt_min (ms)")).toBeDisabled();
    fireEvent.click(
      within(screen.getByRole("group", { name: "Zaman adımı kartı" })).getByRole("button", { name: "NODA/CST/0" }),
    );
    fireEvent.change(screen.getByLabelText("Δt_sca"), { target: { value: "0.9" } });
    fireEvent.change(screen.getByLabelText("Δt_min (ms)"), { target: { value: "0.001" } });
    fireEvent.click(screen.getByLabelText("Parça — /TH/PART"));
    const rwall = screen.getByRole("group", { name: "Rijit duvar — /TH/RWALL değişkenleri" });
    fireEvent.click(within(rwall).getByRole("button", { name: "FTX" }));
    fireEvent.change(screen.getByLabelText("Düğüm — /TH/NODE (kimlikler)"), { target: { value: "1, 2" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Düğüm değişkenleri" })).getByRole("button", { name: "DX" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Kesit ekle" }));
    const sec = screen.getByTestId("crash-section-1");
    for (const [lab, val] of [["M x", "20"], ["M y", "-10"], ["M1 x", "20"], ["M1 y", "60"], ["M2 x", "20"], ["M2 z", "60"]]) {
      fireEvent.change(within(sec).getByLabelText(`Kesit 1 ${lab}`), { target: { value: val } });
    }
    fireEvent.click(within(sec).getByRole("button", { name: "#1" }));
    fireEvent.change(within(sec).getByLabelText("Kesit 1 Iframe"), { target: { value: "11" } });
    const p = outputPayload(last);
    expect(p.engine).toEqual({ th_dt_ms: 0.002, anim_dt_ms: null, dt_kind: "NODA/CST/0", dt_scale: 0.9, dt_min_ms: 0.001 });
    expect(p.th.part.enabled).toBe(false);
    expect(p.th.rwall.vars).toEqual(["FNX", "FNY", "FNZ", "FTX"]);
    expect(p.th.node_ids).toEqual([1, 2]);
    expect(p.th.node_vars).toEqual(["AX", "AY", "AZ", "DX"]);
    expect(p.sections).toEqual([
      { name: "section_1", origin: [20, -10, 0], corner1: [20, 60, 0], corner2: [20, 0, 60], parts: [1], iframe: 11 },
    ]);
    fireEvent.click(within(sec).getByRole("button", { name: "Kesit 1 sil" }));
    expect(screen.queryByTestId("crash-section-1")).not.toBeInTheDocument();
  });

  it("geçersiz kesit koordinatı alan adıyla hata", () => {
    const s = defaultOutput();
    s.sections = [{ id: 1, name: "a", m: ["x", "0", "0"], m1: ["0", "0", "0"], m2: ["0", "0", "0"], parts: [], iframe: "10" }];
    expect(() => outputPayload(s)).toThrow(/Kesit 1 M x/);
  });
});
