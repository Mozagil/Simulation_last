import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CrashModelPanel, { fmtNum, scenarioFor } from "./CrashModelPanel";

vi.mock("../api/crashMl", () => ({
  fetchCrashCorpus: vi.fn(),
  fetchCrashDoeStudies: vi.fn(),
  fetchCrashModels: vi.fn(),
  trainCrashModel: vi.fn(),
  CRASH_KIND_LABEL: { rf: "Random Forest", loglinear: "Log-log lineer", hybrid: "Hibrit (log-log + RF artık)" },
}));
vi.mock("../api/crash", () => ({ fetchCrashCatalog: vi.fn() }));

import { fetchCrashCorpus, fetchCrashDoeStudies, fetchCrashModels, trainCrashModel } from "../api/crashMl";
import { fetchCrashCatalog } from "../api/crash";

const CORPUS = {
  template_id: "crash_box_shell",
  scenario: "rigid_wall",
  study_id: 3,
  n_runs: 24,
  features: ["req.barrier.speed_m_s", "geom.wall"],
  constant_features: { "geom.box_length": 300 },
  targets: { peak_force_kn: 24, mean_force_kn: 24, energy_absorbed_j: 24, crush_mm: 5 },
  dropped: { other_template: 3 },
};

const MODEL = {
  template_id: "crash_box_shell",
  scenario: "rigid_wall",
  study_id: 3,
  n_runs: 24,
  feature_keys: ["req.barrier.speed_m_s", "geom.wall"],
  dropped_features: [],
  constant_features: {},
  bounds: {},
  seed: 2026,
  targets: [
    { key: "peak_force_kn", label: "Tepe duvar kuvveti", unit: "kN", definition: "", trained: true,
      cv: { n: 24, r2: 0.9312, mae: 4.21, mape: 0.034, folds: 5 } },
    { key: "crush_mm", label: "Ezilme mesafesi", unit: "mm", definition: "", trained: false,
      cv: { n: 5, skipped: "en az 8 dolu satır gerekir" } },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCrashCatalog).mockResolvedValue({
    entries: [],
    scenario_templates: { crash_box_shell: 2, plate_ball_shell: 2 },
  } as never);
  vi.mocked(fetchCrashDoeStudies).mockResolvedValue([
    { id: 3, name: "kutu-v1", template_id: "crash_box_shell", seed: 1, status: "completed", message: null,
      created_at: null, vary: null, n_cases: 24, counts: {} },
    { id: 4, name: "küre", template_id: "plate_ball_shell", seed: 1, status: "completed", message: null,
      created_at: null, vary: null, n_cases: 10, counts: {} },
  ]);
  vi.mocked(fetchCrashCorpus).mockResolvedValue(CORPUS);
  vi.mocked(fetchCrashModels).mockResolvedValue([]);
});

describe("yardımcılar", () => {
  it("senaryo şablondan, sayı biçimi", () => {
    expect(scenarioFor("plate_ball_shell")).toBe("plate_ball");
    expect(scenarioFor("crash_box_shell")).toBe("rigid_wall");
    expect(fmtNum(0.93123)).toBe("0.931");
    expect(fmtNum(undefined)).toBe("—");
  });
});

describe("CrashModelPanel", () => {
  it("DOE kaynağıyla korpus ister, eğitir, CV tablosunu gösterir", async () => {
    vi.mocked(trainCrashModel).mockResolvedValue(MODEL);
    render(<CrashModelPanel />);
    expect(await screen.findByText("Bu şablon / senaryo için kayıtlı model yok.")).toBeInTheDocument();
    // yalnız seçili şablonun DOE'leri listelenir
    const source = screen.getByLabelText("Kaynak") as HTMLSelectElement;
    expect(Array.from(source.options).map((o) => o.value)).toEqual(["", "3"]);
    fireEvent.change(source, { target: { value: "3" } });
    await waitFor(() =>
      expect(fetchCrashCorpus).toHaveBeenLastCalledWith({ template_id: "crash_box_shell", scenario: "rigid_wall", study_id: 3, include_raw_cards: false }),
    );
    expect(await screen.findByText("geom.wall")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Eğit · 5-fold CV" }));
    await waitFor(() => expect(trainCrashModel).toHaveBeenCalledWith({ template_id: "crash_box_shell", scenario: "rigid_wall", study_id: 3, include_raw_cards: false, kind: "auto" }));
    expect(await screen.findByText("0.931")).toBeInTheDocument();
    expect(screen.getByText("3.4%")).toBeInTheDocument();
    expect(screen.getByText("en az 8 dolu satır gerekir")).toBeInTheDocument();
  });

  it("şablon değişince senaryo ve kaynak sıfırlanır", async () => {
    render(<CrashModelPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "plate_ball" }));
    await waitFor(() =>
      expect(fetchCrashCorpus).toHaveBeenLastCalledWith({ template_id: "plate_ball_shell", scenario: "plate_ball", study_id: null, include_raw_cards: false }),
    );
  });

  it("1.22f: ham kartlı koşular anahtarla korpusa ve eğitime girer; düşen sayısı görünür", async () => {
    vi.mocked(fetchCrashCorpus).mockResolvedValue({ ...CORPUS, dropped: { raw_cards: 2 } });
    vi.mocked(trainCrashModel).mockResolvedValue(MODEL);
    render(<CrashModelPanel />);
    expect(await screen.findByText("düşen · raw_cards: 2")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Ham kartlı koşuları dahil et"));
    await waitFor(() =>
      expect(fetchCrashCorpus).toHaveBeenLastCalledWith({ template_id: "crash_box_shell", scenario: "rigid_wall", study_id: null, include_raw_cards: true }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Eğit · 5-fold CV" }));
    await waitFor(() =>
      expect(trainCrashModel).toHaveBeenCalledWith({ template_id: "crash_box_shell", scenario: "rigid_wall", study_id: null, include_raw_cards: true, kind: "auto" }),
    );
  });
});


describe("1.27a — tür seçimi ve tür karşılaştırma tablosu", () => {
  it("tür seçici isteğe gider; auto modelde üç türün MAPE'si ve seçilen tür görünür", async () => {
    const auto = {
      ...MODEL,
      requested_kind: "auto" as const,
      design_spec: { feature_keys: ["req.barrier.speed_m_s", "geom.wall"], log_keys: ["geom.wall"], raw_keys: ["req.barrier.speed_m_s"] },
      targets: [
        { ...MODEL.targets[0], kind: "loglinear" as const,
          cv: { n: 24, r2: 0.98, mae: 1.2, mape: 0.011, folds: 5, kind: "loglinear" as const,
            kinds: { rf: { n: 24, r2: 0.93, mae: 4.21, mape: 0.034, folds: 5 },
                     loglinear: { n: 24, r2: 0.98, mae: 1.2, mape: 0.011, folds: 5 },
                     hybrid: { n: 22, r2: 0.97, mae: 1.5, mape: 0.014, folds: 5, dropped_nonpositive: 2 } } } },
        MODEL.targets[1],
      ],
    };
    vi.mocked(trainCrashModel).mockResolvedValue(auto);
    render(<CrashModelPanel />);
    await screen.findByTestId("crash-model-stage");
    fireEvent.click(screen.getByRole("button", { name: "loglinear" }));
    fireEvent.click(screen.getByRole("button", { name: "Eğit · 5-fold CV" }));
    await waitFor(() => expect(trainCrashModel).toHaveBeenCalledWith(expect.objectContaining({ kind: "loglinear" })));
    const cmp = await screen.findByRole("table", { name: "Tür karşılaştırması" });
    expect(within(cmp).getByText("1.1% ✓")).toBeInTheDocument();
    expect(within(cmp).getByText("3.4%")).toBeInTheDocument();
    expect(within(cmp).getByText("1.4% (−2)")).toBeInTheDocument();
    expect(screen.getByText(/log'a girmeyen/)).toHaveTextContent("req.barrier.speed_m_s");
  });
});
