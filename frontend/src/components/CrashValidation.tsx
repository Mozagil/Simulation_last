import { useEffect, useState } from "react";
import { fetchCrashValidation, type CrashValidationReport } from "../api/crash";

/** Crash validasyon raporu (1.17f): analitik / literatür referanslarına göre
 * oranlar. Kabul kriteri yok — oranlar veri, eşik mühendisin. */

function fmt(v: number | null | undefined, digits = 3): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(digits);
  if (Math.abs(v) >= 1e-3) return v.toFixed(4);
  return v.toExponential(2);
}

/** Oran / kesir: sabit 3 hane (0.978), üstel gösterim yok. */
function fr(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "—" : v.toFixed(3);
}

export default function CrashValidation() {
  const [report, setReport] = useState<CrashValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCrashValidation()
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : "Rapor okunamadı."));
  }, []);

  return (
    <details className="crash-mat-section crash-validation" data-testid="crash-validation">
      <summary>Validasyon (1.17f){report ? ` · ${report.generated_at.slice(0, 10)}` : ""}</summary>
      {error && <p className="material-assign-hint">{error}</p>}
      {report && (
        <>
          <p className="material-assign-hint">
            {report.setup.template} {report.setup.L_mm}×{report.setup.h_mm}×{report.setup.b_mm} mm, t{" "}
            {report.setup.t_mm} · {report.setup.material} · v0 {report.setup.v0_m_s} m/s. {report.setup.note}
          </p>
          {report.cases.map((c) =>
            c.rows ? (
              <div key={c.id} className="crash-validation-case">
                <p className="crash-validation-title">
                  {c.id} · {c.title} <span className="crash-run-meta">koşu #{c.run_id}</span>
                </p>
                <div className="crash-history-scroll">
                  <table className="doe-table crash-compare-table">
                    <thead>
                      <tr>
                        <th>büyüklük</th>
                        <th>sim</th>
                        <th>referans</th>
                        <th>oran</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.rows.map((r) => (
                        <tr key={r.quantity}>
                          <td>
                            {r.quantity}
                            <span className="crash-run-meta">{r.ref_label}</span>
                            {r.alt_label && (
                              <span className="crash-run-meta">
                                {r.alt_label}: {fmt(r.alt_ref)}
                              </span>
                            )}
                          </td>
                          <td className="crash-run-num">{fmt(r.sim)}</td>
                          <td className="crash-run-num">{fmt(r.ref)}</td>
                          <td className="crash-run-num">{fr(r.ratio)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="crash-run-meta">
                  enerji dengesi {fr(c.energy_balance_rel)} · hourglass/IE {fr(c.hourglass_ratio)}
                </p>
              </div>
            ) : (
              <div key={c.id} className="crash-validation-case">
                <p className="crash-validation-title">
                  {c.id} · {c.title}
                </p>
                <p className="crash-run-meta">
                  {c.references?.formula} · W&amp;A {fmt(c.references?.wierzbicki_abramowicz_1983_kn)} kN · A&amp;J{" "}
                  {fmt(c.references?.abramowicz_jones_1984_kn)} kN
                </p>
                <div className="crash-history-scroll">
                  <table className="doe-table crash-compare-table" data-testid="crash-validation-mesh">
                    <thead>
                      <tr>
                        <th>eleman mm</th>
                        <th>δ mm</th>
                        <th>Pm kN</th>
                        <th>/W&amp;A</th>
                        <th>/A&amp;J</th>
                        <th>HG/IE</th>
                        <th>s</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(c.mesh ?? []).map((m) => (
                        <tr key={m.element_mm}>
                          <td>{m.element_mm}</td>
                          <td className="crash-run-num">{fmt(m.crush_mm)}</td>
                          <td className="crash-run-num">{fmt(m.pm_energy_kn)}</td>
                          <td className="crash-run-num">{fr(m.ratio_wa)}</td>
                          <td className="crash-run-num">{fr(m.ratio_aj)}</td>
                          <td className="crash-run-num">{fr(m.hourglass_ratio)}</td>
                          <td className="crash-run-num">{fmt(m.wall_s, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ),
          )}
        </>
      )}
    </details>
  );
}
