import { useCallback, useEffect, useState } from "react";
import { fetchMaterials } from "../api/materials";
import {
  createDoeStudy,
  fetchDoeQuality,
  fetchDoeStudies,
  startQualitySet,
  type DoeQualityInfo,
  type DoeStudyInfo,
} from "../api/doe";

const CANTILEVER_SCENARIOS = [
  {
    name: "tip_-y",
    bcs: [
      { type: "fixed", region: "ankastre_uc" },
      { type: "cload", region: "yuk_yuzeyi", fx: 0, fy: -500, fz: 0 },
    ],
  },
  {
    name: "tip_-z",
    bcs: [
      { type: "fixed", region: "ankastre_uc" },
      { type: "cload", region: "yuk_yuzeyi", fx: 0, fy: 0, fz: -500 },
    ],
  },
];

function formatCounts(counts: Record<string, number> | undefined): string {
  if (!counts) return "";
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}:${v}`)
    .join(" · ");
}

export default function DoePanel({
  refreshKey,
  onInspectRun,
  onEditRun,
}: {
  refreshKey?: number;
  /** Bir DOE vakasının çözümünü inceleme ekranında açar. */
  onInspectRun?: (runId: number) => void;
  /** Bir DOE vakasını tezgaha geri yükler (tüm adımlar düzenlenebilir). */
  onEditRun?: (runId: number) => void;
}) {
  const [studies, setStudies] = useState<DoeStudyInfo[]>([]);
  const [qualityById, setQualityById] = useState<Record<number, DoeQualityInfo>>({});
  const [expandedStudyId, setExpandedStudyId] = useState<number | null>(null);
  const [nSamples, setNSamples] = useState("8");
  const [seed, setSeed] = useState("42");
  const [runSolver, setRunSolver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchDoeStudies()
      .then(setStudies)
      .catch((e) => setError(e instanceof Error ? e.message : "DOE listesi alınamadı."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  useEffect(() => {
    const running = studies.some((s) => s.status === "running" || s.status === "pending");
    if (!running) return;
    const t = window.setInterval(reload, 5000);
    return () => window.clearInterval(t);
  }, [studies, reload]);

  useEffect(() => {
    let cancelled = false;
    const ids = studies.slice(0, 5).map((s) => s.id);
    Promise.all(
      ids.map(async (id) => {
        try {
          const q = await fetchDoeQuality(id);
          return [id, q] as const;
        } catch {
          return null;
        }
      }),
    ).then((rows) => {
      if (cancelled) return;
      const next: Record<number, DoeQualityInfo> = {};
      for (const row of rows) {
        if (row) next[row[0]] = row[1];
      }
      setQualityById(next);
    });
    return () => {
      cancelled = true;
    };
  }, [studies]);

  async function handleStart() {
    setBusy(true);
    setError(null);
    try {
      const materials = await fetchMaterials();
      if (!materials.length) {
        throw new Error("Malzeme kütüphanesi boş.");
      }
      const n = parseInt(nSamples, 10);
      const s = parseInt(seed, 10);
      if (!Number.isFinite(n) || n < 1) throw new Error("Örnek sayısı geçersiz.");
      await createDoeStudy(
        {
          name: "cantilever LHS",
          template_id: "cantilever_beam",
          seed: Number.isFinite(s) ? s : 0,
          n_samples: n,
          geometry: {
            length: [400, 600],
            thickness: [8, 12],
            width: [40, 60],
          },
          element_size: [6, 12],
          material_ids: [materials[0].id],
          bc_scenarios: CANTILEVER_SCENARIOS,
          dimension: 3,
          element_scheme: "tet",
          run_solver: runSolver,
        },
        true,
      );
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "DOE başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function handleQualitySet() {
    setBusy(true);
    setError(null);
    try {
      const materials = await fetchMaterials();
      if (!materials.length) {
        throw new Error("Malzeme kütüphanesi boş.");
      }
      await startQualitySet({
        material_ids: [materials[0].id],
        run_solver: runSolver,
        wait: false,
      });
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kalite seti başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.5 · DOE</span>
      <h1>Toplu tarama</h1>
      <p className="lead">
        Ankastre kiriş şablonundan Latin Hypercube örnekler. BC&apos;ler isimli
        bölgelere bağlanır; bir örnek patlarsa diğerleri durmaz.
      </p>
      <p className="lead">
        Kalite seti: 200 ankastre kiriş, tohum 2026. L 450–700 mm, T 8–12 mm, W
        35–70 mm, eleman 6–14 mm, uç yükü −800…−200 N (−y). Tek malzeme, tek BC
        (ankastre + uç CLOAD). Kapalı form sapması ve kaba aykırı değerler
        sayılır; mesh/BC önerisi yok.
      </p>

      <div className="doe-fields">
        <label className="mesh-field">
          <span>Örnek</span>
          <input value={nSamples} onChange={(e) => setNSamples(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Tohum</span>
          <input value={seed} onChange={(e) => setSeed(e.target.value)} />
        </label>
        <label className="dataset-filter">
          <input
            type="checkbox"
            checked={runSolver}
            onChange={(e) => setRunSolver(e.target.checked)}
          />
          ccx çalıştır
        </label>
      </div>

      <div className="doe-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={busy}
          onClick={() => void handleStart()}
        >
          {busy ? "Çalışıyor…" : "DOE başlat"}
        </button>
        <button
          type="button"
          className="material-assign-button"
          disabled={busy}
          onClick={() => void handleQualitySet()}
        >
          200&apos;lük kalite seti
        </button>
      </div>

      {studies.length > 0 && (
        <ul className="doe-study-list">
          {studies.slice(0, 5).map((st) => {
            const q = qualityById[st.id];
            const expanded = expandedStudyId === st.id;
            return (
              <li key={st.id}>
                <button
                  type="button"
                  className="doe-study-head"
                  aria-expanded={expanded}
                  onClick={() => setExpandedStudyId(expanded ? null : st.id)}
                >
                  <span className="doe-study-caret">{expanded ? "▾" : "▸"}</span>
                  <strong>#{st.id}</strong> {st.status} · {st.n_cases} örnek
                  {st.message ? ` · ${st.message}` : ""}
                  {q ? (
                    <span className="doe-quality">
                      {" "}
                      · kalite ok:{q.n_ok}
                      {formatCounts(q.counts) ? ` · ${formatCounts(q.counts)}` : ""}
                    </span>
                  ) : null}
                </button>

                {expanded && (
                  <div className="doe-case-table">
                    {st.cases.length === 0 ? (
                      <p className="material-assign-hint">Bu çalışmada vaka yok.</p>
                    ) : (
                      <table>
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>parametreler</th>
                            <th>eleman</th>
                            <th>durum</th>
                            <th aria-label="işlemler" />
                          </tr>
                        </thead>
                        <tbody>
                          {st.cases.map((c) => (
                            <tr key={c.id}>
                              <td>{c.index}</td>
                              <td className="doe-case-params">
                                {Object.entries(c.geometry_params)
                                  .map(([k, v]) => `${k} ${v}`)
                                  .join(" · ") || "—"}
                              </td>
                              <td>{c.element_size}</td>
                              <td>
                                <span className={`doe-case-status doe-case-status-${c.status}`}>
                                  {c.status}
                                </span>
                                {c.message ? (
                                  <span className="doe-case-message"> · {c.message}</span>
                                ) : null}
                              </td>
                              <td className="doe-case-actions">
                                {c.run_id !== null ? (
                                  <>
                                    {onInspectRun && (
                                      <button
                                        type="button"
                                        onClick={() => onInspectRun(c.run_id as number)}
                                      >
                                        İncele
                                      </button>
                                    )}
                                    {onEditRun && (
                                      <button
                                        type="button"
                                        onClick={() => onEditRun(c.run_id as number)}
                                      >
                                        Düzenle
                                      </button>
                                    )}
                                  </>
                                ) : (
                                  <span className="material-assign-hint">çözüm yok</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && <p className="dataset-error">{error}</p>}
    </div>
  );
}
