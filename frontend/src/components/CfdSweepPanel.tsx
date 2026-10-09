import { useEffect, useRef, useState } from "react";
import { fetchRocketSweep, postRocketSweep, rocketSweepCsvUrl, type RocketSolveBody, type RocketSweep } from "../api/cfd";

/** R5 — Mach × α taraması: her nokta bir roket koşusu (sıralı, aynı mesh ve
 * çözücü). Mach başına tablo (CD, CNα, x_cp) + CSV. Çözücü Mach'a göre
 * değişmez — mühendisin seçimi. Yalnız veri. */

export function parseList(text: string): number[] {
  return text
    .split(/[;,\s]+/)
    .map((t) => t.trim())
    .filter(Boolean)
    .map(Number)
    .filter((v) => Number.isFinite(v));
}

function f(v: number | null | undefined, d = 4): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toPrecision(d) : "—";
}

export default function CfdSweepPanel({
  base,
  temperatureK,
  disabled,
  pollMs = 3000,
}: {
  base: Omit<RocketSolveBody, "speed_m_s" | "alpha_deg">;
  temperatureK: number;
  disabled?: boolean;
  pollMs?: number;
}) {
  const [machs, setMachs] = useState("0.3, 0.5, 0.8");
  const [alphas, setAlphas] = useState("0, 2, 4");
  const [sweep, setSweep] = useState<RocketSweep | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const ms = parseList(machs);
  const as = parseList(alphas);
  const a = Math.sqrt(1.4 * 287.05 * temperatureK);
  const busy = !!sweep && sweep.status !== "done";

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  function poll(id: string) {
    timer.current = window.setTimeout(async () => {
      try {
        const s = await fetchRocketSweep(id);
        setSweep(s);
        if (s.status !== "done") poll(id);
      } catch (e) {
        setError((e as Error).message);
      }
    }, pollMs);
  }

  async function start() {
    setError(null);
    try {
      const s = await postRocketSweep({ ...base, machs: ms, alphas_deg: as });
      setSweep(s);
      poll(s.sweep_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const done = sweep?.points.filter((p) => p.status === "solved" || p.status === "failed").length ?? 0;
  return (
    <section className="cfd-sweep" aria-label="Mach × α taraması">
      <h4>Mach × α taraması (aerodinamik tablo)</h4>
      <p className="crash-behavior-hint">
        Her nokta yukarıdaki ayarlarla ayrı bir koşu (çözücü {base.solver ?? "simpleFoam"}, sıralı). Hız = M · a, a = {a.toFixed(1)} m/s.
      </p>
      <div className="crash-expert-grid cols-3">
        <label className="crash-unit-field">
          <span>Mach listesi</span>
          <span className="crash-unit-box">
            <input aria-label="Mach listesi" value={machs} disabled={disabled || busy} onChange={(e) => setMachs(e.target.value)} />
          </span>
        </label>
        <label className="crash-unit-field">
          <span>α listesi</span>
          <span className="crash-unit-box">
            <input aria-label="α listesi" value={alphas} disabled={disabled || busy} onChange={(e) => setAlphas(e.target.value)} />
            <em>°</em>
          </span>
        </label>
      </div>
      <button type="button" className="doe-btn" disabled={disabled || busy || !ms.length || !as.length} onClick={() => void start()}>
        {busy ? `Taranıyor… ${done} / ${sweep?.points.length}` : `Taramayı başlat (${ms.length * as.length} koşu)`}
      </button>
      {error && <p className="error-message" role="alert">{error}</p>}
      {sweep && (
        <>
          {sweep.message && <p className="crash-behavior-hint" data-testid="cfd-sweep-status">{sweep.message}</p>}
          <table className="cfd-table" data-testid="cfd-sweep-points">
            <thead>
              <tr><th>Mach</th><th>α (°)</th><th>V (m/s)</th><th>Durum</th><th>CD</th><th>CN</th><th>CL</th><th>Cm</th><th>x_cp (mm)</th></tr>
            </thead>
            <tbody>
              {sweep.points.map((p) => (
                <tr key={`${p.mach}-${p.alpha_deg}`}>
                  <td>{p.mach}</td>
                  <td>{p.alpha_deg}</td>
                  <td>{p.speed_m_s.toFixed(1)}</td>
                  <td title={p.message}>{p.status}</td>
                  <td>{f(p.CD)}</td>
                  <td>{f(p.CN)}</td>
                  <td>{f(p.CL)}</td>
                  <td>{f(p.Cm)}</td>
                  <td>{typeof p.x_cp_m === "number" ? f(p.x_cp_m * 1000, 5) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {sweep.table.length > 0 && (
            <table className="cfd-table" data-testid="cfd-sweep-table">
              <thead>
                <tr><th>Mach</th><th>Nokta</th><th>CD (α = α_min)</th><th>CNα (1/rad)</th><th>x_cp ort. (mm)</th></tr>
              </thead>
              <tbody>
                {sweep.table.map((r) => (
                  <tr key={r.mach}>
                    <td>{r.mach}</td>
                    <td>{r.n_points}</td>
                    <td>{f(r.CD_alpha_min)} <small>(α {r.alpha_min_deg}°)</small></td>
                    <td>{f(r.CN_alpha_per_rad)}</td>
                    <td>{typeof r.x_cp_m_mean === "number" ? f(r.x_cp_m_mean * 1000, 5) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="cfd-sweep-links">
            <a href={rocketSweepCsvUrl(sweep.sweep_id, "table")} download>Tablo CSV</a> ·{" "}
            <a href={rocketSweepCsvUrl(sweep.sweep_id, "points")} download>Noktalar CSV</a>
          </p>
        </>
      )}
    </section>
  );
}
