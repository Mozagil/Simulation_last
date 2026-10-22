import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CRASH_DOC, CRASH_SCENARIOS } from "../docs/crashDoc";
import { dynaFor } from "../lib/dynaKeywords";
import DocsDialog from "./DocsDialog";

describe("Belgeler penceresi", () => {
  it("içerik tutarlı: her kartın LS-DYNA karşılığı var, 16 senaryo, görseller public/docs/crash altında", () => {
    for (const s of CRASH_DOC) {
      for (const it of s.items ?? []) {
        if (it.card) expect(dynaFor(it.card), `${s.id}: ${it.card}`).not.toBeNull();
      }
      if (s.image) expect(s.image).toMatch(/^\/docs\/crash\//);
    }
    expect(CRASH_SCENARIOS).toHaveLength(16);
  });

  it("bölümler, OpenRadioss + LS-DYNA sütunları; arama süzer; Esc kapatır", () => {
    const onClose = vi.fn();
    render(<DocsDialog onClose={onClose} />);
    const dlg = screen.getByRole("dialog", { name: "Belgeler" });
    expect(within(dlg).getByRole("heading", { name: "4 · Crash → 4 Ek tanımlar" })).toBeInTheDocument();
    expect(within(dlg).getAllByText("*BOUNDARY_SPC_SET").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Belgelerde ara"), { target: { value: "kızak" } });
    expect(within(dlg).queryByRole("heading", { name: "4 · Crash → 3 Temaslar" })).toBeNull();
    expect(within(dlg).getByRole("heading", { name: "4 · Crash → 4 Ek tanımlar" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Belgeler sırası", () => {
  it("bölümler arayüzdeki adım sırasını izler (3 · Material, 4 · Crash'ten önce; Sonuçlar en sonda)", () => {
    const ids = CRASH_DOC.map((s) => s.id);
    expect(ids.indexOf("malzeme")).toBeLessThan(ids.indexOf("carpma"));
    expect(ids.indexOf("cikti")).toBeLessThan(ids.indexOf("sonuclar"));
    expect(ids.indexOf("uzman")).toBeLessThan(ids.indexOf("cikti"));
  });
});

describe("Belgeler · eğitim sayfası", () => {
  it("son sayfa: T1–T30, modele göre gruplu; aramada süzülür", () => {
    render(<DocsDialog onClose={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Eğitim testleri (T1–T30)" })).toBeInTheDocument();
    for (const id of ["T1", "T9", "T18"]) expect(screen.getByTestId(`train-${id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Belgelerde ara"), { target: { value: "kızak" } });
    expect(screen.getByTestId("train-T9")).toBeInTheDocument();
    expect(screen.queryByTestId("train-T1")).toBeNull();
  });

  it("1.25e: Model 1 kızaklı kurulum + gerekçe notu; T1–T5 ölçülen değerler koşu no ile", () => {
    render(<DocsDialog onClose={() => undefined} />);
    expect(screen.getByRole("heading", { name: /Model 1 — Crash box \(3 mm\) \+ 100 kg kızak/ })).toBeInTheDocument();
    expect(screen.getByText(/bölge kutu_arka · kütle 100 kg · hareket Serbest/)).toBeInTheDocument();
    expect(screen.getByText(/Neden kızak \+ 20 ms/)).toHaveClass("docs-train-note");
    for (const id of ["T1", "T2", "T3", "T4", "T5"]) expect(screen.getByTestId(`train-measured-${id}`)).toHaveTextContent(/#3\d\d/);
    expect(screen.getByTestId("train-measured-T1")).toHaveTextContent("impuls 2017 N·s");
    expect(screen.queryByTestId("train-measured-T6")).toBeNull();
  });
});

describe("Belgeler · PDF indir", () => {
  it("tam belge HTML'i: Türkçe, utf-8, taban adres, bölünmez görsel/kart kuralları, eğitim ve eşleme sayfaları", async () => {
    const { buildDocsPdfHtml } = await import("./DocsDialog");
    const html = buildDocsPdfHtml("http://localhost:5173");
    expect(html).toContain('<html lang="tr">');
    expect(html).toContain('<meta charset="utf-8">');
    expect(html).toContain('<base href="http://localhost:5173/">');
    expect(html).toContain("Eğitim testleri (T1–T30)");
    expect(html).toContain("OpenRadioss ↔ LS-DYNA tablosu");
    expect(html).toContain("page-break-inside: avoid");
    expect(html).toContain("/docs/crash/01-genel.jpg");
    // gizli çerçevede tembel görsel hiç yüklenmez → yazdır hiç açılmazdı
    expect(html).not.toContain('loading="lazy"');
  });

  it("yüklenmeyen görsel yazdırı kilitlemez — üst sınırdan sonra yazdır açılır", async () => {
    vi.useFakeTimers();
    try {
      const { openDocsPdf } = await import("./DocsDialog");
      const printSpy = vi.fn();
      document.querySelectorAll("iframe").forEach((f) => f.remove()); // önceki testin çerçevesi
      const obs = new MutationObserver(() => {
        const f = document.querySelector("iframe");
        if (f?.contentWindow) f.contentWindow.print = printSpy;
      });
      obs.observe(document.body, { childList: true });
      expect(openDocsPdf()).toBe(true);
      // jsdom görselleri yüklemez (onload hiç gelmez) — takılan görsel durumu
      await vi.advanceTimersByTimeAsync(15_000);
      expect(printSpy).toHaveBeenCalledTimes(1);
      obs.disconnect();
    } finally {
      vi.useRealTimers();
    }
  });

  it("gizli çerçevede yazdır başlatılır (açılır pencere yok)", async () => {
    const { openDocsPdf } = await import("./DocsDialog");
    const printSpy = vi.fn();
    const before = document.querySelectorAll("iframe").length;
    const obs = new MutationObserver(() => {
      const f = document.querySelector("iframe");
      if (f?.contentWindow) f.contentWindow.print = printSpy;
    });
    obs.observe(document.body, { childList: true });
    expect(openDocsPdf()).toBe(true);
    expect(document.querySelectorAll("iframe").length).toBe(before + 1);
    obs.disconnect();
  });
});

describe("Belgeler · sekmeler", () => {
  it("ML sekmesi: kendi bölümleri ve gerçek örnekleri; LS-DYNA sütunu yok", () => {
    render(<DocsDialog onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "ML" }));
    expect(screen.getByText("Belgeler · ML Stüdyo (vekil model)")).toBeInTheDocument();
    expect(screen.getByTestId("example-crash-box-doe3")).toBeInTheDocument();
    expect(screen.queryByText("LS-DYNA ≈")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Crash" }));
    expect(screen.getAllByText("LS-DYNA ≈").length).toBeGreaterThan(0);
  });
});

describe("Belgeler · Durability sekmesi", () => {
  it("bölümler, şablonlar ve D eğitim testleri; LS-DYNA sütunu yok", () => {
    render(<DocsDialog onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "Durability" }));
    expect(screen.getByText("Belgeler · Durability (CalculiX)")).toBeInTheDocument();
    expect(screen.getAllByText("Durability şablonları").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/D1\b/).length).toBeGreaterThan(0);
    expect(screen.queryByText("LS-DYNA ≈")).toBeNull();
  });
});

describe("Belgeler · Akış sekmesi", () => {
  it("CFD bölümleri, roket modülü ve akış şablonları; LS-DYNA sütunu yok", () => {
    render(<DocsDialog onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "Akış" }));
    expect(screen.getByText("Belgeler · Akış (OpenFOAM)")).toBeInTheDocument();
    expect(screen.getAllByText(/rhoCentralFoam/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Akış şablonları").length).toBeGreaterThan(0);
    expect(screen.queryByText("LS-DYNA ≈")).toBeNull();
  });
});

describe("Belgeler · Kompozit sekmesi", () => {
  it("kompozit bölümleri, doğrulama vakaları ve sonuç görseli; LS-DYNA sütunu yok", () => {
    render(<DocsDialog onClose={() => undefined} />);
    fireEvent.click(screen.getByRole("tab", { name: "Kompozit" }));
    expect(screen.getByText("Belgeler · Kompozit (CalculiX katmanlı kabuk)")).toBeInTheDocument();
    expect(screen.getAllByText(/Tsai-Wu/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Doğrulama vakaları").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\*SHELL SECTION, ELSET=PART_n, COMPOSITE/).length).toBeGreaterThan(0);
    expect(screen.queryByText("LS-DYNA ≈")).toBeNull();
  });
});
