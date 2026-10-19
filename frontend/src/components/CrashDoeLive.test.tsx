import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/crash", () => ({ fetchCrashJob: vi.fn() }));

import { fetchCrashJob } from "../api/crash";
import CrashDoeLive from "./CrashDoeLive";

describe("1.25a2-2 CrashDoeLive", () => {
  beforeEach(() => vi.mocked(fetchCrashJob).mockReset());

  it("örnek değişince yeni iş; çalışma bitince son örneğin son canlı değerleri kalır (hub'ın cycle 1'i değil)", async () => {
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "j0", status: "pending", cycle: 7400, time_ms: 4, percent: 99.9 });
    const { rerender } = render(<CrashDoeLive studyId={4} jobId="j0" caseIndex={0} nCases={2} studyRunning />);
    await waitFor(() => expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım7400"));

    // sıradaki örnek: yeni iş, değerler sıfırdan ("Başlıyor")
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "j1", status: "pending", cycle: null });
    rerender(<CrashDoeLive studyId={4} jobId="j1" caseIndex={1} nCases={2} studyRunning />);
    expect(screen.getByTestId("crash-doe-live")).toHaveTextContent("Örnek #1");
    await waitFor(() => expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Başlıyor"));
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "j1", status: "pending", cycle: 6200, time_ms: 3.35, percent: 83.7 });
    await waitFor(() => expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım6200"), { timeout: 3000 });

    // örnekler arası (sıradakinin geometri / mesh'i, iş yok): son değerler + "hazırlanıyor" notu
    vi.mocked(fetchCrashJob).mockResolvedValue({ job_id: "j1", status: "solved", cycle: 1, time_ms: 0 });
    rerender(<CrashDoeLive studyId={4} jobId={null} caseIndex={null} nCases={2} studyRunning />);
    expect(screen.getByTestId("crash-doe-live-next")).toHaveTextContent("sıradaki örnek hazırlanıyor");
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım6200");

    // çalışma bitti: not yok, son değerlerle "Bitti"
    rerender(<CrashDoeLive studyId={4} jobId={null} caseIndex={null} nCases={2} studyRunning={false} />);
    expect(screen.queryByTestId("crash-doe-live-next")).not.toBeInTheDocument();
    expect(screen.getByTestId("crash-live-phase")).toHaveTextContent("Bitti · son canlı değerler");
    expect(screen.getByTestId("crash-live")).toHaveTextContent("Adım6200");

    // başka çalışma → panel yok
    rerender(<CrashDoeLive studyId={5} jobId={null} caseIndex={null} nCases={3} studyRunning={false} />);
    expect(screen.queryByTestId("crash-doe-live")).not.toBeInTheDocument();
  });
});
