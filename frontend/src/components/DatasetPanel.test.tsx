import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DatasetPanel, { relativeAgo } from "./DatasetPanel";

vi.mock("../api/dataset", () => ({
  DatasetError: class DatasetError extends Error {},
  fetchDatasetSummary: vi.fn(),
  downloadDataset: vi.fn(),
  importDataset: vi.fn(),
}));
vi.mock("../api/surrogate", () => ({ fetchCorpusList: vi.fn(), freezeCorpus: vi.fn() }));

import { downloadDataset, fetchDatasetSummary, importDataset } from "../api/dataset";
import { fetchCorpusList, freezeCorpus } from "../api/surrogate";

const SUMMARY = {
  geometries: 380,
  materials: 8,
  analysis_runs: 300,
  solved_runs: 240,
  training_samples: 200,
  by_template: [
    { template_id: "cantilever_beam", runs: 252, solved: 248, excluded: 7 },
    { template_id: null, runs: 44, solved: 43, excluded: 0 },
  ],
};

describe("DatasetPanel — veri seti aşaması", () => {
  beforeEach(() => {
    vi.mocked(fetchDatasetSummary).mockReset();
    vi.mocked(downloadDataset).mockReset();
    vi.mocked(importDataset).mockReset();
    vi.mocked(fetchCorpusList).mockReset();
    vi.mocked(freezeCorpus).mockReset();
    vi.mocked(fetchDatasetSummary).mockResolvedValue(SUMMARY as never);
    vi.mocked(downloadDataset).mockResolvedValue(undefined as never);
    vi.mocked(fetchCorpusList).mockResolvedValue([
      { name: "kiris-v2", frozen_at: "2026-09-12T10:40:00", n_runs: 200, template_id: "cantilever_beam", n_manual: 8 },
      { name: "plaka-v1", frozen_at: null, n_runs: 198, template_id: "plate_with_hole", n_manual: 0 },
    ] as never);
    window.localStorage.clear();
  });

  it("sayaçları, şablon çubuklarını ve korpus kartlarını gösterir", async () => {
    render(<DatasetPanel />);
    expect(await screen.findByText("çözülmüş run")).toBeInTheDocument();
    expect(screen.getByText("240")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument(); // çözülmemiş
    const rows = screen.getAllByTestId("template-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("cantilever_beam");
    expect(rows[0]).toHaveTextContent("248");
    expect(rows[1]).toHaveTextContent("şablonsuz");
    // korpus kartları: tarihli en yeni üstte ve seçili; tarihsiz sonda
    const cards = await screen.findAllByRole("button", { name: /run$/ });
    expect(cards[0]).toHaveTextContent("kiris-v2");
    expect(cards[0]).toHaveTextContent("200 run");
    expect(cards[0]).toHaveTextContent("8 elle");
    expect(cards[0]).toHaveTextContent("donduruldu 12.09 · 10:40");
    expect(cards[0]).toHaveAttribute("aria-pressed", "true");
    expect(cards[1]).toHaveTextContent("plaka-v1");
    expect(screen.getByText("yedek alınmadı")).toBeInTheDocument();
  });

  it("eğitim seti seçilip indirilebilir", async () => {
    render(<DatasetPanel />);
    const btn = await screen.findByRole("button", { name: "kiris-v2'i indir" });
    fireEvent.click(btn);
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    expect(downloadDataset).toHaveBeenCalledWith({
      onlySolved: true,
      runIds: undefined,
      corpusName: "kiris-v2",
    });
    expect(await screen.findByText(/"kiris-v2" eğitim seti indirildi/)).toBeInTheDocument();
    // eğitim seti indirmek "son yedek" sayılmaz
    expect(screen.getByText("yedek alınmadı")).toBeInTheDocument();
  });

  it("çipten başka set seçilince o set indirilir (sol kart da eşlenir)", async () => {
    render(<DatasetPanel />);
    const chips = within(await screen.findByRole("group", { name: "Eğitim seti" }));
    fireEvent.click(chips.getByRole("button", { name: "plaka-v1 · 198" }));
    fireEvent.click(screen.getByRole("button", { name: "plaka-v1'i indir" }));
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    expect(vi.mocked(downloadDataset).mock.calls[0][0]).toMatchObject({ corpusName: "plaka-v1" });
    const cards = screen.getAllByRole("button", { name: /run$/ });
    expect(cards.find((c) => c.textContent?.includes("plaka-v1"))).toHaveAttribute("aria-pressed", "true");
  });

  it("arşivi indir korpus göndermez ve son yedek rozetini günceller", async () => {
    render(<DatasetPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Arşivi indir" }));
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    expect(downloadDataset).toHaveBeenCalledWith({ onlySolved: true, runIds: undefined, corpusName: undefined });
    expect(await screen.findByText("son yedek az önce")).toBeInTheDocument();
    expect(window.localStorage.getItem("simsurrogate.dataset.lastExport")).not.toBeNull();
  });

  it("donmuş set yoksa indirme düğmesi pasif, kart açıklaması gösterilir", async () => {
    vi.mocked(fetchCorpusList).mockResolvedValue([]);
    render(<DatasetPanel />);
    await screen.findByRole("button", { name: "Arşivi indir" });
    expect(screen.queryByRole("group", { name: "Eğitim seti" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Eğitim setini indir" })).toBeDisabled();
    expect(screen.getByText("Henüz donmuş set yok.")).toBeInTheDocument();
  });

  it("seçili run'lar kartı seçim yokken pasif, varken sayıyı gönderir", async () => {
    const { rerender } = render(<DatasetPanel />);
    await screen.findByRole("button", { name: "Arşivi indir" });
    expect(screen.getByRole("button", { name: "Seçili run'ları indir" })).toBeDisabled();
    rerender(<DatasetPanel selectedRunIds={[4, 9, 12]} />);
    fireEvent.click(screen.getByRole("button", { name: "Seçili 3 run'ı indir" }));
    await waitFor(() => expect(downloadDataset).toHaveBeenCalledTimes(1));
    expect(vi.mocked(downloadDataset).mock.calls[0][0]).toMatchObject({ runIds: [4, 9, 12] });
  });

  it("yeni set dondurur, listeyi yeniler ve günlüğe yazar", async () => {
    vi.mocked(freezeCorpus).mockResolvedValue({ manifest: { run_ids: [1, 2, 3] } });
    render(<DatasetPanel templateId="cantilever_beam" />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Yeni set dondur" }));
    fireEvent.change(screen.getByLabelText("Yeni set adı"), { target: { value: "kiris_v4" } });
    fireEvent.click(screen.getByRole("button", { name: "Dondur" }));
    await waitFor(() => expect(freezeCorpus).toHaveBeenCalledWith("kiris_v4", { templateId: "cantilever_beam" }));
    expect(await screen.findByText("Set donduruldu: kiris_v4 · 3 run")).toBeInTheDocument();
    expect(fetchCorpusList).toHaveBeenCalledTimes(2);
  });

  it("dosya seçilince içe aktarır ve özeti yeniler", async () => {
    vi.mocked(importDataset).mockResolvedValue({ format_version: 1, source_created_at: null, added: { runs: 38, geometries: 6 } });
    render(<DatasetPanel />);
    const input = (await screen.findByLabelText("Arşiv dosyası")) as HTMLInputElement;
    const file = new File(["x"], "arsiv.tar.gz");
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(importDataset).toHaveBeenCalledWith(file));
    expect(await screen.findByText("İçe aktarıldı — runs: 38, geometries: 6")).toBeInTheDocument();
    expect(fetchDatasetSummary).toHaveBeenCalledTimes(2);
  });
});

describe("relativeAgo", () => {
  it("dakika, saat, gün", () => {
    const now = 1_000_000_000_000;
    expect(relativeAgo(now - 20e3, now)).toBe("az önce");
    expect(relativeAgo(now - 5 * 60e3, now)).toBe("5 dk önce");
    expect(relativeAgo(now - 3 * 3600e3, now)).toBe("3 saat önce");
    expect(relativeAgo(now - 6 * 86400e3, now)).toBe("6 gün önce");
  });
});
