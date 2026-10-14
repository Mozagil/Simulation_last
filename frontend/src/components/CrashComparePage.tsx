/** Koşu karşılaştırması — tam ekran tek sayfa (kullanıcı 2026-10-14: "geçmişin altında
 * değil, yeni bir sayfada one pager gibi").
 *
 * Bölümler: koşu kartları · deforme şekil yan yana (ortak zaman; 2'den fazla koşuda çift
 * seçilir) · skaler tablosu · eğriler (seçilebilir eğri + iç enerji, üst üste). Veri
 * gösterir; sıralama / yorum yok.
 */

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import type { CrashRunCompared } from "../api/crash";
import { curveUnit, fmtScalar, runHasResults, runLabel, runTitle } from "../lib/crashRunFormat";
import CrashCompareAnim from "./CrashCompareAnim";
import CrashForceChart, { type ForceSeries } from "./CrashForceChart";

/** Skaler tablosu satırları (varsa); kesit / temas tepe değerleri ayrıca. */
export const SCALAR_ROWS: [string, string][] = [
  ["rwall_force_max", "Duvar Fmax (kN)"],
  ["rwall_impulse_final", "Duvar impuls (N·s)"],
  ["internal_energy_final", "IE son (J)"],
  ["kinetic_energy_final", "KE son (J)"],
  ["hourglass_energy_final", "HG son (J)"],
  ["energy_balance_rel", "Enerji dengesi"],
  ["timestep_min", "Δt_min (ms)"],
  ["mass_added_rel", "Eklenen kütle oranı"],
  ["elements_deleted", "Silinen eleman"],
];

/** Karşılaştırmadaki koşulardan `key` eğrisi; t ≤ tMax kırpılır (yalnız görünüm). */
export function compareSeries(runs: CrashRunCompared[], key: string, tMax: number | null): ForceSeries[] {
  return runs
    .filter((r) => r.curves[key] && r.curves.time)
    .map((r) => {
      const t = r.curves.time;
      const cut = tMax == null ? -1 : t.findIndex((v) => v > tMax);
      const n = cut !== -1 ? Math.max(2, cut) : t.length;
      return { key: `run-${r.id}`, label: runTitle(r), values: r.curves[key].slice(0, n), time: t.slice(0, n) };
    });
}

export default function CrashComparePage({ runs, onClose }: { runs: CrashRunCompared[]; onClose: () => void }) {
  const curveKeys = useMemo(
    () => [...new Set(runs.flatMap((r) => Object.keys(r.curves).filter((k) => k !== "time")))].sort(),
    [runs],
  );
  const [curveKey, setCurveKey] = useState(() => (curveKeys.includes("rwall_force") ? "rwall_force" : (curveKeys[0] ?? "")));
  const [tMaxRaw, setTMaxRaw] = useState("");
  const tMaxNum = Number(tMaxRaw.replace(",", "."));
  const tMax = tMaxRaw.trim() !== "" && Number.isFinite(tMaxNum) && tMaxNum > 0 ? tMaxNum : null;

  // animasyon çifti: sonuçlu koşulardan ilk ikisi; 2'den fazlaysa seçilir
  const animRuns = runs.filter((r) => r.solver_ran && runHasResults(r));
  const [pairA, setPairA] = useState(animRuns[0]?.id ?? null);
  const [pairB, setPairB] = useState(animRuns[1]?.id ?? null);
  const a = animRuns.find((r) => r.id === pairA);
  const b = animRuns.find((r) => r.id === pairB);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const extraRows: [string, string][] = [
    ...new Set(runs.flatMap((r) => Object.keys(r.scalars).filter((k) => /^(section|contact)_\d+_force_max$/.test(k)))),
  ]
    .sort()
    .map((k) => [
      k,
      k.replace(/^section_(\d+)_force_max$/, "Kesit $1 Fmax (kN)").replace(/^contact_(\d+)_force_max$/, "Temas $1 Fmax (kN)"),
    ]);
  const rows = [...SCALAR_ROWS, ...extraRows].filter(([k]) => runs.some((r) => r.scalars[k] != null));

  const main = compareSeries(runs, curveKey, tMax);
  const mainU = curveUnit(curveKey);
  const energy = curveKey === "internal_energy" ? [] : compareSeries(runs, "internal_energy", tMax);

  const runOption = (id: number) => {
    return runTitle(animRuns.find((x) => x.id === id)!);
  };

  return createPortal(
    <div className="crash-compare-page" role="dialog" aria-label="Koşu karşılaştırması" data-testid="crash-compare">
      <header className="crash-compare-page-head">
        <div>
          <h2>Koşu karşılaştırması</h2>
          <p className="ds-sb">{runs.length} koşu · veriler kayıtlı sonuçlardan; kabul eşiği mühendisin</p>
        </div>
        <button type="button" className="doe-btn doe-btn-ghost" onClick={onClose} title="Kapat (ESC)">
          Kapat
        </button>
      </header>

      <section className="crash-compare-page-runs" aria-label="Koşular">
        {runs.map((r) => (
          <div key={r.id} className="crash-compare-run-card">
            <strong>
              #{r.id} {r.name?.trim() ? r.name : ""}
            </strong>
            <span className="ds-sb">
              geo {r.geometry_id} · {r.t_end_ms} ms · <span className={`crash-run-status crash-run-${r.status}`}>{r.status}</span>
            </span>
            <span className="crash-compare-run-fmax">
              Duvar Fmax <b>{fmtScalar(r.scalars.rwall_force_max)}</b> kN
            </span>
          </div>
        ))}
      </section>

      <section className="crash-compare-page-section" aria-label="Deforme şekil">
        <h3>Deforme şekil</h3>
        {animRuns.length < 2 ? (
          <p className="doe-empty">Yan yana animasyon için en az iki çözülmüş koşu gerekir.</p>
        ) : (
          <>
            {animRuns.length > 2 && (
              <div className="crash-compare-pair">
                <label className="mesh-field">
                  <span>Sol</span>
                  <select aria-label="Sol animasyon" value={pairA ?? ""} onChange={(e) => setPairA(Number(e.target.value))}>
                    {animRuns.map((r) => (
                      <option key={r.id} value={r.id}>
                        {runOption(r.id)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="mesh-field">
                  <span>Sağ</span>
                  <select aria-label="Sağ animasyon" value={pairB ?? ""} onChange={(e) => setPairB(Number(e.target.value))}>
                    {animRuns.map((r) => (
                      <option key={r.id} value={r.id}>
                        {runOption(r.id)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
            {a && b && (
              <div className="crash-compare-page-anim">
                <CrashCompareAnim
                  key={`${a.id}-${b.id}`}
                  a={{ id: a.id, title: runTitle(a) }}
                  b={{ id: b.id, title: runTitle(b) }}
                />
              </div>
            )}
          </>
        )}
      </section>

      <section className="crash-compare-page-section" aria-label="Skalerler">
        <h3>Skalerler</h3>
        <div className="crash-history-scroll">
          <table className="doe-table crash-compare-table">
            <thead>
              <tr>
                <th />
                {runs.map((r) => (
                  <th key={r.id} title={runLabel(r)}>
                    #{r.id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([k, title]) => (
                <tr key={k}>
                  <td>{title}</td>
                  {runs.map((r) => (
                    <td key={r.id} className="crash-run-num">
                      {fmtScalar(r.scalars[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="crash-compare-page-section" aria-label="Eğriler">
        <h3>Eğriler</h3>
        <div className="crash-compare-controls">
          {curveKeys.length > 0 && (
            <label className="mesh-field">
              <span>Eğri</span>
              <select aria-label="Karşılaştırma eğrisi" value={curveKey} onChange={(e) => setCurveKey(e.target.value)}>
                {curveKeys.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="mesh-field">
            <span>t üst (ms)</span>
            <input aria-label="Grafik zaman üst sınırı" value={tMaxRaw} placeholder="tümü" onChange={(e) => setTMaxRaw(e.target.value)} />
          </label>
        </div>
        <div className="crash-compare-page-charts">
          {main.length > 0 ? (
            <CrashForceChart
              time={main[0].time ?? []}
              series={main}
              title={mainU.title}
              unit={mainU.unit}
              yLabel={mainU.yLabel}
              showMean={mainU.isForce}
            />
          ) : (
            <p className="doe-empty">Seçili koşularda bu eğri yok.</p>
          )}
          {energy.length > 0 && (
            <CrashForceChart
              time={energy[0].time ?? []}
              series={energy}
              title="İç enerji · J"
              unit="J"
              yLabel="enerji"
              ariaLabel="İç enerji–zaman grafiği"
            />
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}
