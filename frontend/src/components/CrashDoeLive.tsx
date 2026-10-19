/** 1.25a2-2 — DOE'de çalışan örneğin canlı ilerlemesi.
 *
 * Kaynak: çalışmanın `current_job_id`'si (backend 1.25a2-1, bellekte) → `/crash/jobs/{id}`
 * yoklanır (1,5 s). Paneli `CrashLiveProgress` ile aynı: örnek başlar başlamaz görünür;
 * çalışma bitince son örneğin son canlı değerleriyle kalır. Son değerler yalnız iş sürerken
 * alınır (bitmiş işte hub'ın "cycle 1" satırı kullanılmaz). Yorum yok.
 */

import { useEffect, useState } from "react";

import { fetchCrashJob } from "../api/crash";
import CrashLiveProgress, { livePhase, type LiveValues } from "./CrashLiveProgress";

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);
const POLL_MS = 1500;

interface LastJob {
  jobId: string;
  caseIndex: number | null;
  status: string | null;
  values: LiveValues | null;
}

export default function CrashDoeLive({
  studyId,
  jobId,
  caseIndex,
  nCases,
  studyRunning,
}: {
  studyId: number;
  jobId: string | null;
  caseIndex: number | null;
  nCases: number;
  /** Çalışma sürüyor mu: örnekler arasında (sıradakinin geometri / mesh'i, iş yok) not yazılır */
  studyRunning: boolean;
}) {
  const [last, setLast] = useState<LastJob | null>(null);

  // Başka çalışmaya geçince önceki çalışmanın son değerleri gösterilmez.
  useEffect(() => setLast(null), [studyId]);

  useEffect(() => {
    if (!jobId) return;
    setLast((l) => (l?.jobId === jobId ? l : { jobId, caseIndex, status: "pending", values: null }));
    let cancelled = false;
    const tick = () => {
      fetchCrashJob(jobId)
        .then((s) => {
          if (cancelled) return;
          const done = s.status != null && TERMINAL.has(s.status);
          setLast((l) => {
            const base = l?.jobId === jobId ? l : { jobId, caseIndex, status: null, values: null };
            if (done || s.cycle == null) return { ...base, status: s.status ?? base.status };
            const { cycle, time_ms, dt_ms, percent, mass_added_rel, elapsed_s, remaining_s } = s;
            return { ...base, status: s.status ?? null, values: { cycle, time_ms, dt_ms, percent, mass_added_rel, elapsed_s, remaining_s } };
          });
        })
        .catch(() => undefined);
    };
    tick();
    const t = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [jobId, caseIndex]);

  if (!last) return null;
  const running = jobId != null && last.jobId === jobId && !(last.status != null && TERMINAL.has(last.status));
  return (
    <div className="crash-doe-live" aria-label="Örnek canlı ilerleme" data-testid="crash-doe-live">
      <p className="crash-doe-live-title">
        Örnek #{last.caseIndex ?? "—"}
        <span className="ds-sb">
          {" "}
          · {nCases} örnekten · iş {last.jobId.slice(0, 8)}
        </span>
      </p>
      {studyRunning && !running && (
        <p className="crash-doe-live-next" data-testid="crash-doe-live-next">
          Çalışma sürüyor · sıradaki örnek hazırlanıyor (geometri / mesh); aşağıda önceki örneğin son değerleri
        </p>
      )}
      <CrashLiveProgress
        key={last.jobId}
        phase={livePhase(running ? "running" : last.status, running, last.values?.cycle)}
        values={last.values}
        tEndMs={null}
      />
    </div>
  );
}
