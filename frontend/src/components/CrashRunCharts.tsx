import { useEffect, useState } from "react";
import { fetchCrashRun, type CrashRunDetail } from "../api/crash";
import CrashForceChart, {
  energySeriesFromCurves,
  FORCE_CHART_NOTE,
  forceSeriesFromCurves,
  type ForceSeries,
} from "./CrashForceChart";

/** Koşu detay grafikleri (1.17e2): kuvvet (ham + CFC), ivme bileşkesi (ham +
 * CFC), enerji (IE, KE) — kayıtlı koşunun job.json eğrilerinden, yeniden
 * koşmadan. Zaman üst sınırı yalnız görünüm. Veri gösterir, yorum yok. */

function clip(series: ForceSeries[], time: number[], tMax: number | null): { time: number[]; series: ForceSeries[] } {
  if (tMax == null) return { time, series };
  const cut = time.findIndex((t) => t > tMax);
  const n = cut === -1 ? time.length : Math.max(2, cut);
  return { time: time.slice(0, n), series: series.map((s) => ({ ...s, values: s.values.slice(0, n) })) };
}

function fmt(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

export default function CrashRunCharts({ runId, title }: { runId: number; title?: string }) {
  const [run, setRun] = useState<CrashRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tMaxRaw, setTMaxRaw] = useState("");

  useEffect(() => {
    let alive = true;
    setRun(null);
    setError(null);
    fetchCrashRun(runId)
      .then((r) => alive && setRun(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Koşu okunamadı."));
    return () => {
      alive = false;
    };
  }, [runId]);

  const curves = run?.curves ?? {};
  const time = curves.time ?? [];
  const tMaxNum = Number(tMaxRaw.replace(",", "."));
  const tMax = tMaxRaw.trim() && Number.isFinite(tMaxNum) && tMaxNum > 0 ? tMaxNum : null;

  const force = clip(forceSeriesFromCurves(curves), time, tMax);
  const accKeys = Object.keys(curves)
    .filter((k) => /^acc_g(_cfc\d+)?$/.test(k))
    .sort();
  const acc = clip(
    accKeys.map((k) => ({
      key: k,
      label: k === "acc_g" ? "|a| ham" : `|a| CFC${k.split("cfc")[1]}`,
      values: curves[k],
    })),
    time,
    tMax,
  );
  const energy = clip(energySeriesFromCurves(curves), time, tMax);
  const s = run?.scalars ?? {};

  return (
    <div className="crash-run-charts" data-testid="crash-run-charts">
      <p className="material-assignments-title">Grafikler{title ? ` · ${title}` : ""}</p>
      {error && <p className="material-assign-hint">{error}</p>}
      {!run && !error && <p className="doe-empty">Yükleniyor…</p>}
      {run && (
        <>
          <label className="mesh-field">
            <span>t üst (ms)</span>
            <input
              aria-label="Grafik zaman üst sınırı"
              value={tMaxRaw}
              placeholder="tümü"
              onChange={(e) => setTMaxRaw(e.target.value)}
            />
          </label>
          {force.series.length > 0 && (
            <CrashForceChart time={force.time} series={force.series} note={FORCE_CHART_NOTE} showMean />
          )}
          {acc.series.length > 0 && (
            <CrashForceChart time={acc.time} series={acc.series} title="İvme · g" unit="g" yLabel="ivme" ariaLabel="İvme–zaman grafiği" />
          )}
          {energy.series.length > 0 && (
            <CrashForceChart
              time={energy.time}
              series={energy.series}
              title="Enerji · J"
              unit="J"
              yLabel="enerji"
              ariaLabel="Enerji–zaman grafiği"
            />
          )}
          {force.series.length === 0 && acc.series.length === 0 && energy.series.length === 0 && (
            <p className="doe-empty">Bu koşuda zaman eğrisi yok.</p>
          )}
          <ul className="crash-scalar-list" data-testid="crash-run-scalars">
            <li>IE son {fmt(s.internal_energy_final)} J</li>
            <li>Enerji dengesi {fmt(s.energy_balance_rel)}</li>
            {s.hourglass_ratio != null && <li>Hourglass / IE {fmt(s.hourglass_ratio)}</li>}
            {s.contact_energy_final != null && (
              <li>
                Temas enerjisi son {fmt(s.contact_energy_final)} J · temas / IE {fmt(s.contact_energy_ratio)}
              </li>
            )}
            {s.rwall_impulse_final != null && <li>Duvar impulsu {fmt(s.rwall_impulse_final)} N·s</li>}
            {s.hic15 != null && <li>HIC15 {fmt(s.hic15)}</li>}
            {Object.keys(s)
              .filter((k) => /^hic15_cfc\d+$/.test(k))
              .map((k) => (
                <li key={k}>
                  HIC15 CFC{k.split("cfc")[1]} {fmt(s[k])}
                </li>
              ))}
          </ul>
        </>
      )}
    </div>
  );
}
