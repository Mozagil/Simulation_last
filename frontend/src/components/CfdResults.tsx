/**
 * AKIŞ · sonuçlar — Faz 2.7c. Tamamlanmış koşunun verisi: özet, yama başına
 * kuvvet, kuvvet katsayısı geçmişi, roket koşusunda katsayılar + basınç merkezi
 * + Barrowman ile yan yana. Yalnız veri; yorum / öneri yok.
 */
import type { CfdJobSnapshot } from "../api/cfd";
import CfdFieldViewer from "./CfdFieldViewer";
import CfdResidualChart from "./CfdResidualChart";

function f(v: unknown, d = 4): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toPrecision(d) : "—";
}

/** scalars → yama başına {x, y, z, pressure_x, viscous_x}; "total" ayrı. */
export function patchForces(sc: Record<string, number>): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  for (const [k, v] of Object.entries(sc)) {
    const m = /^force_(.+?)(?:_(pressure|viscous))?_([xyz])$/.exec(k);
    if (!m) continue;
    const [, tag, part, axis] = m;
    (out[tag] ??= {})[part ? `${part}_${axis}` : axis] = v;
  }
  return out;
}

export default function CfdResults({ job }: { job: CfdJobSnapshot }) {
  const sc = job.scalars ?? {};
  const forces = patchForces(sc);
  const patches = Object.keys(forces).filter((p) => p !== "total");
  const coeffs = job.curves?.force_coeffs;
  const ra = (job.rocket_aero ?? null) as Record<string, number | Record<string, number>> | null;
  const rb = ra && typeof ra.barrowman === "object" ? (ra.barrowman as Record<string, number>) : null;
  const rk = (job as unknown as { rocket?: { mach?: number; alpha_deg?: number; speed_m_s?: number; cg_given?: boolean } }).rocket;

  return (
    <div className="cfd-results" data-testid="cfd-results">
      <p className="crash-expert-title">Özet</p>
      <table className="cfd-table" data-testid="cfd-solve-summary">
        <tbody>
          <tr><th>İterasyon</th><td>{sc.iterations} · {sc.converged ? "yakınsadı" : "iterasyon sınırı"}</td></tr>
          {sc.Cd !== undefined && <tr><th>Cd (son / ort. ± std)</th><td>{f(sc.Cd)} / {f(sc.Cd_mean)} ± {f(sc.Cd_std, 2)}</td></tr>}
          {sc.Cl !== undefined && <tr><th>Cl (son / ort.)</th><td>{f(sc.Cl)} / {f(sc.Cl_mean)}</td></tr>}
          {sc.CmPitch !== undefined && <tr><th>Cm yunuslama (ort.)</th><td>{f(sc.CmPitch_mean)}</td></tr>}
          {sc.CdA_m2 !== undefined && <tr><th>CdA (son / ort.)</th><td>{f(sc.CdA_m2)} / {f(sc.CdA_mean_m2)} m²</td></tr>}
          {sc.force_total_x !== undefined && (
            <tr><th>Toplam kuvvet (x, y, z)</th><td>{f(sc.force_total_x)}, {f(sc.force_total_y)}, {f(sc.force_total_z)} N</td></tr>
          )}
          {sc.force_total_pressure_x !== undefined && (
            <tr><th>Fx basınç / viskoz</th><td>{f(sc.force_total_pressure_x)} / {f(sc.force_total_viscous_x)} N</td></tr>
          )}
          {sc.dp_pa !== undefined && <tr><th>Δp</th><td>{f(sc.dp_pa)} Pa</td></tr>}
        </tbody>
      </table>

      {patches.length > 0 && (
        <>
          <p className="crash-expert-title">Yama başına kuvvet</p>
          <table className="cfd-table" data-testid="cfd-patch-forces">
            <thead>
              <tr><th>Yama</th><th>Fx (N)</th><th>basınç</th><th>viskoz</th><th>Fz (N)</th></tr>
            </thead>
            <tbody>
              {patches.map((p) => (
                <tr key={p}>
                  <td>{p}</td>
                  <td>{f(forces[p].x)}</td>
                  <td>{f(forces[p].pressure_x)}</td>
                  <td>{f(forces[p].viscous_x)}</td>
                  <td>{f(forces[p].z)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {coeffs?.iteration && (coeffs.Cd || coeffs.Cl) && (
        <>
          <p className="crash-expert-title">Katsayı geçmişi</p>
          <CfdResidualChart
            iterations={coeffs.iteration}
            residuals={Object.fromEntries((["Cd", "Cl"] as const).filter((k) => coeffs[k]).map((k) => [k, coeffs[k]!]))}
            log={false}
            label="Kuvvet katsayısı geçmişi"
            testId="cfd-coeff-chart"
          />
        </>
      )}

      {ra && Object.keys(ra).length > 0 && (
        <>
          <p className="crash-expert-title">Roket aerodinamiği</p>
          <table className="cfd-table" data-testid="cfd-rocket-aero">
            <tbody>
              {rk && <tr><th>Hız · α · Mach</th><td>{f(rk.speed_m_s, 3)} m/s · {f(rk.alpha_deg, 3)}° · {f(rk.mach, 3)}</td></tr>}
              <tr><th>CA / CN (gövde ekseni)</th><td>{f(ra.CA)} / {f(ra.CN)}</td></tr>
              <tr><th>CD / CL (rüzgâr ekseni)</th><td>{f(ra.CD)} / {f(ra.CL)}</td></tr>
              <tr><th>Cm (referans noktaya göre)</th><td>{f(ra.Cm)}</td></tr>
              <tr><th>Basınç merkezi</th><td>{typeof ra.x_cp_m === "number" ? `${f((ra.x_cp_m as number) * 1000, 5)} mm · ${f(ra.x_cp_calibers, 4)} kal.` : "α ≈ 0 — tanımsız"}</td></tr>
              {typeof ra.CN_alpha_per_rad === "number" && <tr><th>CNα</th><td>{f(ra.CN_alpha_per_rad)} /rad</td></tr>}
              {typeof ra.stability_calibers === "number" && <tr><th>Kararlılık payı</th><td>{f(ra.stability_calibers, 3)} kalibre</td></tr>}
            </tbody>
          </table>
          {rb && (
            <table className="cfd-table" data-testid="cfd-rocket-barrowman">
              <thead>
                <tr><th></th><th>CFD</th><th>Barrowman</th><th>fark</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>CNα (/rad)</td>
                  <td>{f(ra.CN_alpha_per_rad)}</td>
                  <td>{f(rb.cn_alpha_barrowman)}</td>
                  <td>{typeof rb.cn_alpha_diff_percent === "number" ? `%${rb.cn_alpha_diff_percent.toFixed(1)}` : "—"}</td>
                </tr>
                <tr>
                  <td>Basınç merkezi (mm)</td>
                  <td>{typeof ra.x_cp_m === "number" ? f((ra.x_cp_m as number) * 1000, 5) : "—"}</td>
                  <td>{f(rb.x_cp_barrowman_m * 1000, 5)}</td>
                  <td>{typeof rb.x_cp_diff_calibers === "number" ? `${rb.x_cp_diff_calibers.toFixed(2)} kal.` : "—"}</td>
                </tr>
              </tbody>
            </table>
          )}
        </>
      )}
      <CfdFieldViewer jobId={job.job_id} />
    </div>
  );
}
