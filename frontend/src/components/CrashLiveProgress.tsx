/** 1.23 D3 — koşu sırasında canlı: adım (cycle), t / t_end, anlık Δt, şimdiye kadarki en
 * küçük Δt, eklenen kütle (DM/M), yüzde, geçen ve kalan süre. Değerler engine çıktısının
 * basılan satırlarından ("NC= … T= … DT= … DM/M= …", "ELAPSED / REMAINING TIME");
 * kalan süre Radioss'un kendi tahmini. Yorum yok.
 */

import { useEffect, useRef, useState } from "react";

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

export default function CrashLiveProgress({
  cycle,
  timeMs,
  dtMs,
  tEndMs,
  percent,
  massAddedRel,
  elapsedS,
  remainingS,
}: {
  cycle: number | null | undefined;
  timeMs: number | null | undefined;
  dtMs: number | null | undefined;
  tEndMs: number | null;
  percent: number;
  massAddedRel?: number | null;
  /** Radioss'un yazdığı geçen süre (s); yoksa tarayıcı saatiyle */
  elapsedS?: number | null;
  remainingS?: number | null;
}) {
  const startRef = useRef(Date.now());
  const minDtRef = useRef<number | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  if (dtMs != null && dtMs > 0 && (minDtRef.current == null || dtMs < minDtRef.current)) minDtRef.current = dtMs;

  const cells: [string, string][] = [
    ["Adım", cycle != null ? String(cycle) : "—"],
    ["t", timeMs != null ? `${num(timeMs)}${tEndMs ? ` / ${num(tEndMs)}` : ""} ms` : "—"],
    ["Δt", dtMs != null ? `${num(dtMs)} ms` : "—"],
    ["Δt en küçük", minDtRef.current != null ? `${num(minDtRef.current)} ms` : "—"],
    ["DM/M", massAddedRel != null ? num(massAddedRel) : "—"],
    ["İlerleme", `%${percent.toFixed(1)}`],
    ["Geçen", elapsedText(elapsedS ?? (now - startRef.current) / 1000)],
    ["Kalan (Radioss)", remainingS != null ? elapsedText(remainingS) : "—"],
  ];
  return (
    <dl className="crash-live" data-testid="crash-live">
      {cells.map(([k, v]) => (
        <div key={k} className="crash-live-cell">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
