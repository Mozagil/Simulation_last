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
import { CURVE_GROUPS, curveGroup, curveLabel, curveUnit, fmtScalar, runHasResults, runLabel, runTitle } from "../lib/crashRunFormat";
import CrashCompareAnim, { gridColumns } from "./CrashCompareAnim";
import CrashForceChart, { type ForceSeries } from "./CrashForceChart";

/** Skaler tablosu satırı: okunur ad + birim ayrı sütunda; `scale` gösterim çarpanı (oran → %). */
export type ScalarRow = { key: string; label: string; unit: string; scale?: number };

/** 1.25d — skaler tablosu satırları (varsa); kesit / temas tepe değerleri ayrıca. */
export const SCALAR_ROWS: ScalarRow[] = [
  { key: "rwall_force_max", label: "Duvar kuvveti, tepe", unit: "kN" },
  { key: "rwall_impulse_final", label: "Duvar impulsu, son", unit: "N·s" },
  { key: "internal_energy_final", label: "İç enerji, son", unit: "J" },
  { key: "kinetic_energy_final", label: "Kinetik enerji, son", unit: "J" },
  { key: "hourglass_energy_final", label: "Hourglass enerjisi, son", unit: "J" },
  { key: "energy_balance_rel", label: "Enerji dengesi |ΔE| / E", unit: "%", scale: 100 },
  { key: "timestep_min", label: "En küçük zaman adımı Δt", unit: "ms" },
  { key: "mass_added_rel", label: "Eklenen kütle oranı", unit: "%", scale: 100 },
  { key: "elements_deleted", label: "Silinen eleman", unit: "adet" },
];

/** `section_3_force_max` → "Kesit 3 kuvveti, tepe" (kN); eşleşmezse null. */
export function extraScalarRow(key: string): ScalarRow | null {
  const m = /^(section|contact)_(\d+)_force_max$/.exec(key);
  if (!m) return null;
  return { key, label: `${m[1] === "section" ? "Kesit" : "Temas"} ${m[2]} kuvveti, tepe`, unit: "kN" };
}

function scalarCell(v: number | undefined, row: ScalarRow): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (row.unit === "adet") return String(Math.round(v));
  if (row.unit === "%") return (v * (row.scale ?? 1)).toFixed(2);
  // |v| < 1: üslü yerine ondalık (0.8660, 0.0005393); çok küçükte JS yine üslü yazar
  if (v !== 0 && Math.abs(v) < 1) return v.toPrecision(4);
  return fmtScalar(v);
}

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
    () =>
      [...new Set(runs.flatMap((r) => Object.keys(r.curves).filter((k) => k !== "time")))].sort(
        (x, y) => CURVE_GROUPS.indexOf(curveGroup(x)) - CURVE_GROUPS.indexOf(curveGroup(y)) || x.localeCompare(y),
      ),
    [runs],
  );
  const [curveKey, setCurveKey] = useState(() => (curveKeys.includes("rwall_force") ? "rwall_force" : (curveKeys[0] ?? "")));
  const [tMaxRaw, setTMaxRaw] = useState("");
  const tMaxNum = Number(tMaxRaw.replace(",", "."));
  const tMax = tMaxRaw.trim() !== "" && Number.isFinite(tMaxNum) && tMaxNum > 0 ? tMaxNum : null;

  // 1.25b — ızgaradaki koşular: sonuçlu koşuların hepsi varsayılan; çiplerle çıkarılır / eklenir
  const animRuns = runs.filter((r) => r.solver_ran && runHasResults(r));
  const [shown, setShown] = useState<Set<number>>(() => new Set(animRuns.map((r) => r.id)));
  const gridRuns = animRuns.filter((r) => shown.has(r.id));
  const toggleShown = (id: number) =>
    setShown((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const extraRows = [...new Set(runs.flatMap((r) => Object.keys(r.scalars)))]
    .sort((x, y) => x.localeCompare(y, undefined, { numeric: true }))
    .map(extraScalarRow)
    .filter((r): r is ScalarRow => r != null);
  const rows = [...SCALAR_ROWS, ...extraRows].filter((row) => runs.some((r) => r.scalars[row.key] != null));

  const main = compareSeries(runs, curveKey, tMax);
  const mainU = curveUnit(curveKey);
  const energy = curveKey === "internal_energy" ? [] : compareSeries(runs, "internal_energy", tMax);

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
              <div className="crash-var-chips crash-compare-pick" role="group" aria-label="Izgaradaki koşular">
                {animRuns.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className={shown.has(r.id) ? "crash-var-chip active" : "crash-var-chip"}
                    aria-pressed={shown.has(r.id)}
                    onClick={() => toggleShown(r.id)}
                  >
                    {runTitle(r)}
                  </button>
                ))}
              </div>
            )}
            {gridRuns.length >= 2 ? (
              <div className="crash-compare-page-anim" data-rows={Math.ceil(gridRuns.length / gridColumns(gridRuns.length))}>
                <CrashCompareAnim
                  runs={gridRuns.map((r) => ({ id: r.id, title: runTitle(r) }))}
                />
              </div>
            ) : (
              <p className="doe-empty">Izgara için en az iki koşu seçin.</p>
            )}
          </>
        )}
      </section>

      <section className="crash-compare-page-section" aria-label="Skalerler">
        <h3>Skalerler</h3>
        <div className="crash-history-scroll">
          <table className="crash-scalar-table" aria-label="Skaler karşılaştırma">
            <thead>
              <tr>
                <th scope="col" className="crash-scalar-th-name">
                  Büyüklük
                </th>
                <th scope="col" className="crash-scalar-th-unit">
                  Birim
                </th>
                {runs.map((r) => (
                  <th key={r.id} scope="col" className="crash-scalar-th-run" title={runLabel(r)}>
                    <span className="crash-scalar-th-id">#{r.id}</span>
                    {r.name?.trim() && <span className="crash-scalar-th-sub">{r.name.trim()}</span>}
                    <span className="crash-scalar-th-sub">
                      geo {r.geometry_id} · {r.t_end_ms} ms
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  <th scope="row" title={row.key}>
                    {row.label}
                  </th>
                  <td className="crash-scalar-unit">{row.unit}</td>
                  {runs.map((r) => (
                    <td key={r.id} className="crash-run-num">
                      {scalarCell(r.scalars[row.key], row)}
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
                {CURVE_GROUPS.map((g) => {
                  const keys = curveKeys.filter((k) => curveGroup(k) === g);
                  return keys.length ? (
                    <optgroup key={g} label={g}>
                      {keys.map((k) => (
                        <option key={k} value={k}>
                          {curveLabel(k)}
                        </option>
                      ))}
                    </optgroup>
                  ) : null;
                })}
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
