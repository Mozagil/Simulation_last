/**
 * AKIŞ · koşu geçmişi ve karşılaştırma — Faz 2.7d (`cfd_runs`). Koşular yeniden
 * eskiye; en çok 6 koşu seçilip temel skalerleri yan yana. Dışlama silmez.
 */
import { useEffect, useState } from "react";
import { fetchCfdRuns, patchCfdRun, type CfdRunSummary } from "../api/cfd";

const MAX_COMPARE = 6;

type Row = { label: string; get: (r: CfdRunSummary) => unknown; digits?: number };

const aero = (r: CfdRunSummary) => ((r.reference as { aero?: Record<string, number> } | null)?.aero ?? {}) as Record<string, number>;

const ROWS: Row[] = [
  { label: "Mesh", get: (r) => r.mesh_kind },
  { label: "Türbülans", get: (r) => r.turbulence },
  { label: "İterasyon", get: (r) => r.scalars.iterations },
  { label: "Yakınsadı", get: (r) => (r.scalars.converged === undefined ? undefined : r.scalars.converged ? "evet" : "hayır") },
  { label: "Cd (ort.)", get: (r) => r.scalars.Cd_mean, digits: 4 },
  { label: "Cd std", get: (r) => r.scalars.Cd_std, digits: 2 },
  { label: "Cl (ort.)", get: (r) => r.scalars.Cl_mean, digits: 4 },
  { label: "CdA (ort.) m²", get: (r) => r.scalars.CdA_mean_m2, digits: 4 },
  { label: "Toplam Fx (N)", get: (r) => r.scalars.force_total_x, digits: 4 },
  { label: "Δp (Pa)", get: (r) => r.scalars.dp_pa, digits: 4 },
  { label: "Roket CN", get: (r) => aero(r).CN, digits: 4 },
  { label: "Roket CNα (/rad)", get: (r) => aero(r).CN_alpha_per_rad, digits: 4 },
  { label: "Basınç merkezi (mm)", get: (r) => (aero(r).x_cp_m !== undefined ? aero(r).x_cp_m * 1000 : undefined), digits: 5 },
  { label: "Kararlılık (kal.)", get: (r) => aero(r).stability_calibers, digits: 3 },
];

function show(v: unknown, digits = 4): string {
  if (v === undefined || v === null) return "—";
  return typeof v === "number" ? v.toPrecision(digits) : String(v);
}

export default function CfdRunsPanel({ geometryId = null, refreshKey = 0 }: { geometryId?: number | null; refreshKey?: number }) {
  const [runs, setRuns] = useState<CfdRunSummary[]>([]);
  const [onlyThis, setOnlyThis] = useState(true);
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      const res = await fetchCfdRuns(onlyThis ? geometryId : null);
      setRuns(res.runs);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometryId, onlyThis, refreshKey]);

  async function toggleExcluded(r: CfdRunSummary) {
    try {
      const upd = await patchCfdRun(r.id, { excluded: !r.excluded });
      setRuns((cur) => cur.map((x) => (x.id === r.id ? { ...x, excluded: upd.excluded } : x)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const picked = runs.filter((r) => selected.includes(r.id));

  return (
    <section className="crash-acc" aria-label="Koşu geçmişi">
      <button type="button" className="crash-acc-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="crash-acc-n">⏱</span>
        <span className="crash-acc-text">
          <strong>Koşu geçmişi</strong>
          <span className="crash-acc-summary">{runs.length} koşu{selected.length ? ` · ${selected.length} seçili` : ""}</span>
        </span>
        <span className="crash-acc-chev" aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="crash-acc-body" data-testid="cfd-runs">
          <label className="material-check">
            <input type="checkbox" checked={onlyThis} disabled={geometryId == null} onChange={(e) => setOnlyThis(e.target.checked)} />
            <span>Yalnız bu geometri</span>
          </label>
          {error && <p className="error-message" role="alert">{error}</p>}
          <table className="cfd-table">
            <thead>
              <tr><th></th><th>#</th><th>Ad</th><th>Durum</th><th>Cd (ort.)</th><th></th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className={r.excluded ? "cfd-run-excluded" : undefined}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Seç ${r.id}`}
                      checked={selected.includes(r.id)}
                      disabled={!selected.includes(r.id) && selected.length >= MAX_COMPARE}
                      onChange={(e) => setSelected((cur) => (e.target.checked ? [...cur, r.id] : cur.filter((x) => x !== r.id)))}
                    />
                  </td>
                  <td>{r.id}</td>
                  <td title={r.message ?? ""}>{r.name ?? (r.created_at ? new Date(r.created_at).toLocaleString("tr-TR") : "—")}</td>
                  <td>{r.status}</td>
                  <td>{show(r.scalars.Cd_mean)}</td>
                  <td>
                    <button type="button" className="doe-btn doe-btn-ghost" onClick={() => void toggleExcluded(r)}>
                      {r.excluded ? "geri al" : "dışla"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {picked.length >= 2 && (
            <>
              <p className="crash-expert-title">Karşılaştırma</p>
              <table className="cfd-table" data-testid="cfd-runs-compare">
                <thead>
                  <tr>
                    <th></th>
                    {picked.map((r) => (
                      <th key={r.id}>#{r.id}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.filter((row) => picked.some((r) => row.get(r) !== undefined && row.get(r) !== null)).map((row) => (
                    <tr key={row.label}>
                      <th>{row.label}</th>
                      {picked.map((r) => (
                        <td key={r.id}>{show(row.get(r), row.digits)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </section>
  );
}
