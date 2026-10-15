import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/crash", () => ({
  postDynaImport: vi.fn(),
  fetchDynaImportPreview: vi.fn(),
  postDynaImportSolve: vi.fn(),
  fetchCrashJob: vi.fn(),
}));

import { fetchCrashJob, fetchDynaImportPreview, postDynaImport, postDynaImportSolve, type DynaImportReport } from "../api/crash";
import CrashImportDialog, { attentionItems, fileEndTimeMs } from "./CrashImportDialog";
import { previewTriangles } from "./CrashImportPreview";

const REPORT: DynaImportReport = {
  import_id: "a".repeat(32),
  file: "model.k",
  units: { length_to_mm: 1000, mass_to_kg: 1, time_to_s: 1 },
  rates_per_s: [],
  parse: { nodes: 8, shells: 2, solids: 0, parts: 2, end_time: 0.01, skipped: { FOO: 1 }, files: ["model.k", "kurulum.k"], warnings: [] },
  mesh: {
    nodes: 8, shells: 2, sh3n: 0, tets: 0, bricks: 0, warnings: [],
    parts: [
      { pid: 1, part_id: 0, title: "plaka", kind: "shell", thickness_mm: 1, elements: 1, mid: 1 },
      { pid: 2, part_id: 1, title: "kapak", kind: "shell", thickness_mm: 1, elements: 1, mid: 1 },
    ],
  },
  materials: {
    parts: [{ pid: 1, mid: 1, keyword: "MAT_024", law: "plastic", note: "SIGY + ETAN" }],
    unassigned: [2],
    warnings: [],
  },
  setup: {
    rows: [
      { source: "*CONTACT_AUTOMATIC_NODES_TO_SURFACE", where: "kurulum.k:9", target: "/INTER/TYPE7", status: "çevrildi", detail: "slave 2 → master 1" },
      { source: "*BOUNDARY_SPC_NODE", where: "kurulum.k:26", target: null, status: "atlandı", detail: "yerel sistem CID 5 desteklenmiyor" },
    ],
    warnings: [],
  },
};

const PREVIEW = {
  nodes: [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1]] as [number, number, number][],
  faces: [[0, 1, 2, 3], [4, 5, 6]],
  face_part: [1, 2],
  part_faces: { "1": 1, "2": 1 },
  bbox_mm: { min: [0, 0, 0] as [number, number, number], max: [1, 1, 1] as [number, number, number] },
};

describe("1.21e-2d CrashImportDialog", () => {
  beforeEach(() => {
    vi.mocked(postDynaImport).mockReset().mockResolvedValue(REPORT);
    vi.mocked(fetchDynaImportPreview).mockReset().mockResolvedValue(PREVIEW);
    vi.mocked(postDynaImportSolve).mockReset();
    vi.mocked(fetchCrashJob).mockReset().mockResolvedValue({ job_id: "j", status: "pending", cycle: 100, time_ms: 1, percent: 10 });
  });

  it("dikkat: atlanan keyword, malzemesiz parça, atlanan kurulum satırı; dosya süresi → ms", () => {
    const a = attentionItems(REPORT);
    expect(a).toEqual([
      "Atlanan keyword *FOO × 1 (çevrilmez)",
      "PID 2: malzemesi çevrilmedi",
      "Kurulum kurulum.k:26: *BOUNDARY_SPC_NODE atlandı — yerel sistem CID 5 desteklenmiyor",
    ]);
    expect(fileEndTimeMs(REPORT)).toBe(10);
    expect(fileEndTimeMs({ ...REPORT, parse: { ...REPORT.parse, end_time: null } })).toBeNull();
  });

  it("önizleme üçgenleri: dörtgen → 2, üçgen → 1; parça rengi", () => {
    const t = previewTriangles(PREVIEW);
    expect(t.positions.length / 9).toBe(3);
    expect(t.pids).toEqual([1, 2]);
  });

  it("birimler girilmeden Çevir kapalı; çeviri → rapor; 'okudum' → koşu açılır, süre dosyadan; koş", async () => {
    vi.mocked(postDynaImportSolve).mockResolvedValue({ job_id: "j", import_id: REPORT.import_id, run_id: 378, status: "pending", message: "", openradioss_available: true });
    const onRun = vi.fn();
    render(<CrashImportDialog onClose={() => undefined} onRunStarted={onRun} />);
    const file = new File(["*KEYWORD"], "model.k");
    fireEvent.change(screen.getByLabelText("Ana dosya"), { target: { files: [file] } });
    const btn = screen.getByRole("button", { name: "Çevir" });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Uzunluk → mm"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Kütle → kg"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Zaman → s"), { target: { value: "1" } });
    fireEvent.click(btn);
    const rep = await screen.findByTestId("crash-import-report");
    expect(vi.mocked(postDynaImport).mock.calls[0][0]).toMatchObject({ lengthToMm: "1000", massToKg: "1", timeToS: "1" });
    expect(within(rep).getByTestId("crash-import-attention")).toHaveTextContent("Dikkat · 3");
    expect(within(rep).getByRole("table", { name: "Parçalar" })).toHaveTextContent("≈ *MAT_024 → plastic");
    expect(screen.queryByTestId("crash-import-run")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByLabelText("Süre (ms)")).toHaveValue("10");
    fireEvent.click(screen.getByRole("button", { name: "OpenRadioss çalıştır" }));
    await waitFor(() => expect(postDynaImportSolve).toHaveBeenCalledWith(REPORT.import_id, { name: "İçe aktarma · model.k", t_end_ms: 10 }));
    expect(onRun).toHaveBeenCalled();
    expect(await screen.findByText(/Koşu #378/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım100"));
  });

  it("çeviri hatası mesajı", async () => {
    vi.mocked(postDynaImport).mockRejectedValue(new Error("*NODE 1 ikinci kez"));
    render(<CrashImportDialog onClose={() => undefined} />);
    fireEvent.change(screen.getByLabelText("Ana dosya"), { target: { files: [new File(["x"], "a.k")] } });
    for (const l of ["Uzunluk → mm", "Kütle → kg", "Zaman → s"]) fireEvent.change(screen.getByLabelText(l), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Çevir" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ikinci kez");
  });
});
