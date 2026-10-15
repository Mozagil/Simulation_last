/** 1.23 D3 — koşu sırasında canlı: adım (cycle), t / t_end, anlık Δt, şimdiye kadarki en
 * küçük Δt, eklenen kütle (DM/M), yüzde, geçen ve kalan süre. Değerler engine çıktısının
 * basılan satırlarından ("NC= … T= … DT= … DM/M= …", "ELAPSED / REMAINING TIME");
 * kalan süre Radioss'un kendi tahmini. Yorum yok.
 *
 * 1.25a — her koşuda: koşu başlar başlamaz görünür ("başlıyor", değerler —); bitince /
 * başarısızken son canlı değerlerle kalır (geçen süre durur); STALE_S'den uzun süre yeni
 * değer gelmezse son güncellemenin yaşı yazılır (veri; uyarı / öneri değil).
 */

import { useEffect, useRef, useState } from "react";

/** Bu süreden (s) uzun yeni değer gelmezse "son güncelleme … önce" gösterilir. */
export const STALE_S = 30;

/** Paneldeki canlı değerler (iş anlık görüntüsünden). */
export interface LiveValues {
  cycle?: number | null;
  time_ms?: number | null;
  dt_ms?: number | null;
  percent?: number | null;
  mass_added_rel?: number | null;
  elapsed_s?: number | null;
  remaining_s?: number | null;
}

export type LivePhase = "starting" | "running" | "finished" | "failed";

function num(v: number): string {
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(1);
  if (a >= 0.01) return String(Number(v.toPrecision(4)));
  return v.toExponential(3);
}

export function elapsedText(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} dk ${String(s % 60).padStart(2, "0")} s` : `${s} s`;
}

/** İş durumu → panel evresi. Koşu sürerken adım yoksa "başlıyor". */
export function livePhase(status: string | null | undefined, running: boolean, cycle: number | null | undefined): LivePhase {
  if (running) return cycle != null ? "running" : "starting";
  return status === "failed" ? "failed" : "finished";
}

const PHASE_TEXT: Record<LivePhase, string> = {
  starting: "Başlıyor — ilk adım bekleniyor",
  running: "Koşuyor",
  finished: "Bitti · son canlı değerler",
  failed: "Başarısız · son canlı değerler",
};

export default function CrashLiveProgress({
  phase,
  values,
  tEndMs,
}: {
  phase: LivePhase;
  values: LiveValues | null;
  tEndMs: number | null;
}) {
  const v = values ?? {};
  const running = phase === "starting" || phase === "running";
  const startRef = useRef(Date.now());
  const endRef = useRef<number | null>(null);
  const minDtRef = useRef<number | null>(null);
  const lastChangeRef = useRef(Date.now());
  const lastKeyRef = useRef("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  if (running) endRef.current = null;
  else if (endRef.current == null) endRef.current = Date.now();
  if (v.dt_ms != null && v.dt_ms > 0 && (minDtRef.current == null || v.dt_ms < minDtRef.current)) minDtRef.current = v.dt_ms;
  const key = `${v.cycle ?? ""}|${v.time_ms ?? ""}`;
  if (key !== lastKeyRef.current) {
    lastKeyRef.current = key;
    lastChangeRef.current = Date.now();
  }
  const clock = endRef.current ?? now;
  const staleS = running ? (now - lastChangeRef.current) / 1000 : 0;
  const percent = v.percent ?? 0;

  const cells: [string, string][] = [
    ["Adım", v.cycle != null ? String(v.cycle) : "—"],
    ["t", v.time_ms != null ? `${num(v.time_ms)}${tEndMs ? ` / ${num(tEndMs)}` : ""} ms` : "—"],
    ["Δt", v.dt_ms != null ? `${num(v.dt_ms)} ms` : "—"],
    ["Δt en küçük", minDtRef.current != null ? `${num(minDtRef.current)} ms` : "—"],
    ["DM/M", v.mass_added_rel != null ? num(v.mass_added_rel) : "—"],
    ["İlerleme", `%${percent.toFixed(1)}`],
    ["Geçen", elapsedText(v.elapsed_s ?? (clock - startRef.current) / 1000)],
    ["Kalan (Radioss)", running && v.remaining_s != null ? elapsedText(v.remaining_s) : "—"],
  ];
  return (
    <div className={`crash-live-wrap crash-live-${phase}`} data-testid="crash-live-wrap">
      <p className="crash-live-head" data-testid="crash-live-phase">
        <span className="crash-live-dot" aria-hidden="true" />
        {PHASE_TEXT[phase]}
        {staleS >= STALE_S && (
          <span className="crash-live-stale" data-testid="crash-live-stale">
            {" "}
            · son güncelleme {elapsedText(staleS)} önce
          </span>
        )}
      </p>
      <dl className="crash-live" data-testid="crash-live">
        {cells.map(([k, val]) => (
          <div key={k} className="crash-live-cell">
            <dt>{k}</dt>
            <dd>{val}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
