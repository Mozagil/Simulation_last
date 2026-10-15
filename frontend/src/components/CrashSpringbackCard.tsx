/** 1.24c3 — 5 · Sonuçlar → "Geri sekme": backend skalerleri (1.24c1, iki tanım; model + parça)
 * tablosu + |u|max–t eğrisi (animasyon karelerinden, istemcide). Veri gösterir; hangi tanıma
 * bakılacağı ve koşunun sekmeye kadar uzatılması mühendisin.
 */

import { useEffect, useMemo, useState } from "react";

import { fetchCrashAnimation } from "../api/crash";
import { springbackCurves, springbackRows, type SbDef, type SpringbackCurves } from "../lib/crashSpringback";
import CrashForceChart, { type ForceSeries } from "./CrashForceChart";

const DEF_LABEL: Record<SbDef, string> = {
  disp: "Mutlak |u|",
  def: "Öteleme çıkarılmış |u − ū|",
};

function mm(v: number | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v === 0) return "0";
  return Math.abs(v) >= 100 ? v.toFixed(1) : Math.abs(v) >= 0.01 ? v.toFixed(3) : v.toExponential(2);
}

/** Eğri: sonlu olmayan kare atlanır (seri kendi zaman ekseniyle). */
function seriesOf(c: SpringbackCurves, scope: "model" | number): ForceSeries[] {
  const s = c.series.get(scope);
  if (!s) return [];
  return (["disp", "def"] as const).map((d) => {
    const keep = s[d].map((v, i) => [c.time[i], v] as const).filter(([, v]) => Number.isFinite(v));
    return { key: d, label: DEF_LABEL[d], values: keep.map(([, v]) => v), time: keep.map(([t]) => t) };
  });
}

export default function CrashSpringbackCard({ scalars, runId }: { scalars: Record<string, number>; runId: number | null }) {
  const rows = useMemo(() => springbackRows(scalars), [scalars]);
  const hasRows = rows.length > 0;
  const [curves, setCurves] = useState<SpringbackCurves | null>(null);
  const [curveError, setCurveError] = useState<string | null>(null);
  const [scope, setScope] = useState<"model" | number>("model");

  useEffect(() => {
    setCurves(null);
    setCurveError(null);
    if (runId == null || !hasRows) return;
    let cancelled = false;
    fetchCrashAnimation(runId)
      .then((a) => {
        if (cancelled) return;
        const c = springbackCurves(a);
        if (c) setCurves(c);
        else setCurveError("Animasyonda en az iki kare yok.");
      })
      .catch((e) => !cancelled && setCurveError(e instanceof Error ? e.message : "Animasyon alınamadı."));
    return () => {
      cancelled = true;
    };
  }, [runId, hasRows]);

  if (rows.length === 0) return null;
  const scopes = [...new Set(rows.map((r) => r.scope))];
  const series = curves ? seriesOf(curves, scope) : [];

  return (
    <div className="crash-springback" data-testid="crash-springback">
      <p className="crash-expert-title">Geri sekme · mm</p>
      <p className="crash-behavior-hint">
        Kare başına en büyük yer değiştirme. Mutlak: ilk konuma göre (rijit öteleme dahil — tabanı sabit parçada
        deformasyon). Öteleme çıkarılmış: parçanın ortalama ötelemesi çıkarılmış (rijit dönme kalır). Geri sekme =
        tepe − son (tepe son karedeyse 0).
      </p>
      <div className="crash-history-scroll">
        <table className="doe-table crash-springback-table" aria-label="Geri sekme">
          <thead>
            <tr>
              <th>Kapsam</th>
              <th>Tanım</th>
              <th>Tepe (mm)</th>
              <th>t tepe (ms)</th>
              <th>Son (mm)</th>
              <th>Geri sekme (mm)</th>
              <th>Oran (%)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.scope}-${r.def}`}>
                <td>{r.scope === "model" ? "Model" : `Parça #${r.scope}`}</td>
                <td>{DEF_LABEL[r.def]}</td>
                <td>{mm(r.peak)}</td>
                <td>{mm(r.tPeak)}</td>
                <td>{mm(r.final)}</td>
                <td>{mm(r.springback)}</td>
                <td>{r.ratio != null ? (100 * r.ratio).toFixed(1) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {scopes.length > 1 && (
        <div className="crash-var-chips" role="group" aria-label="Geri sekme eğrisi kapsamı">
          {scopes.map((s) => (
            <button
              key={String(s)}
              type="button"
              className={scope === s ? "crash-var-chip active" : "crash-var-chip"}
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
            >
              {s === "model" ? "Model" : `#${s}`}
            </button>
          ))}
        </div>
      )}
      {series.length > 0 && (
        <CrashForceChart
          time={series[0].time ?? []}
          series={series}
          title="|u|max · mm"
          unit="mm"
          yLabel="yer değiştirme"
          ariaLabel="Yer değiştirme–zaman grafiği"
          note="Animasyon karelerinden (yüzey düğümleri); kare aralığı Çıktı ayarları → Animasyon."
        />
      )}
      {curveError && <p className="crash-behavior-hint">Eğri: {curveError}</p>}
    </div>
  );
}
