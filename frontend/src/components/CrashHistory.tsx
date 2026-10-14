import { useEffect, useMemo, useRef, useState } from "react";
import {
  compareCrashRuns,
  fetchCrashRuns,
  patchCrashRun,
  type CrashRunCompared,
  type CrashRunSummary,
} from "../api/crash";
import CrashAnimationViewer from "./CrashAnimationViewer";
import CrashRunCharts from "./CrashRunCharts";
import CrashForceChart, { type ForceSeries } from "./CrashForceChart";

/** Crash koşu geçmişi + karşılaştırma (1.16b). Veri gösterir: koşular, skalerler,
 * seçilen kuvvet eğrisi üst üste. Yorum / sıralama önerisi yok. */

/** Karşılaştırma tablosu satırları (varsa); kesit / temas tepe değerleri ayrıca. */
const SCALAR_ROWS: [string, string][] = [
  ["rwall_force_max", "Duvar Fmax (kN)"],
  ["rwall_impulse_final", "Duvar impuls (N·s)"],
  ["internal_energy_final", "IE son (J)"],
  ["kinetic_energy_final", "KE son (J)"],
  ["energy_balance_rel", "Enerji dengesi"],
  ["timestep_min", "Δt_min (ms)"],
  ["mass_added_rel", "Eklenen kütle oranı"],
  ["elements_deleted", "Silinen eleman"],
];

const MAX_COMPARE = 6;

function fmt(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v === 0) return "0";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const label = (r: CrashRunSummary) => r.name?.trim() || `#${r.id}`;
// Iraksayan koşu (Hata #1) failed ama eğri/animasyon ıraksama anına kadar incelenir.
const hasResults = (r: CrashRunSummary) => r.status === "solved" || r.scalars.diverged_at_ms != null;

/** Ana viewport'ta açılacak deforme şekil; 1.23 C5 — ikinci koşu ile yan yana. */
export interface CrashAnimTarget {
  id: number;
  title: string;
  compareWith?: { id: number; title: string };
}

export default function CrashHistory({
  geometryId,
  refreshKey,
  activeAnimId,
  onAnimate,
  onLoadRun,
}: {
  geometryId: number | null;
  /** Değişince liste yeniden yüklenir (yeni iş / iş bitti). */
  refreshKey?: string;
  /** TODO 11.4 — verilirse deforme şekil App'te (ana viewport) açılır. */
  activeAnimId?: number | null;
  /** 1.23 C5 — `compareWith` verilirse iki koşu yan yana açılır. */
  onAnimate?: (run: CrashAnimTarget | null) => void;
  /** 1.23 B3a — koşunun geometrisi + mesh'i + kurulumu panellere yüklenir. */
  onLoadRun?: (runId: number) => void;
}) {
  const [runs, setRuns] = useState<CrashRunSummary[]>([]);
  const [showExcluded, setShowExcluded] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [compared, setCompared] = useState<CrashRunCompared[] | null>(null);
  // karşılaştırma gelince görünür alana kaydır (uzun listede aşağıda seçilmiş olabilir)
  const compareRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (compared?.length) compareRef.current?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }, [compared]);
  const [curveKey, setCurveKey] = useState("rwall_force");
  /** Grafik zaman üst sınırı (ms); boş = tüm aralık. Yalnız görünüm. */
  const [tMaxRaw, setTMaxRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  /** 1.17d — deforme şekli açık koşu */
  const [animRun, setAnimRun] = useState<CrashRunSummary | null>(null);
  /** 1.17e2 — grafik detayı açık koşu */
  const [chartRun, setChartRun] = useState<CrashRunSummary | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchCrashRuns(geometryId)
      .then((r) => {
        if (alive) {
          setRuns(r);
          setError(null);
        }
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Geçmiş okunamadı."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [geometryId, refreshKey, tick]);

  const visible = runs.filter((r) => showExcluded || !r.excluded);
  const hiddenCount = runs.length - visible.length;

  async function toggleExcluded(r: CrashRunSummary) {
    try {
      const next = await patchCrashRun(r.id, { excluded: !r.excluded });
      setRuns((rows) => rows.map((x) => (x.id === r.id ? next : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Güncellenemedi.");
    }
  }

  async function runCompare() {
    try {
      const res = await compareCrashRuns(selected);
      setCompared(res);
      const keys = new Set(res.flatMap((r) => Object.keys(r.curves).filter((k) => k !== "time")));
      if (!keys.has(curveKey)) setCurveKey([...keys][0] ?? "rwall_force");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karşılaştırma başarısız.");
    }
  }

  const curveKeys = useMemo(
    () =>
      [...new Set((compared ?? []).flatMap((r) => Object.keys(r.curves).filter((k) => k !== "time")))].sort(),
    [compared],
  );
  const tMax = Number(tMaxRaw.replace(",", "."));
  const clip = tMaxRaw.trim() !== "" && Number.isFinite(tMax) && tMax > 0;
  const series: ForceSeries[] = (compared ?? [])
    .filter((r) => r.curves[curveKey] && r.curves.time)
    .map((r) => {
      const t = r.curves.time;
      const cut = t.findIndex((v) => v > tMax);
      const n = clip && cut !== -1 ? Math.max(2, cut) : t.length; // yalnız t ≤ üst sınır
      return { key: `run-${r.id}`, label: `#${r.id} ${label(r)}`, values: r.curves[curveKey].slice(0, n), time: t.slice(0, n) };
    });
  const extraRows: [string, string][] = [
    ...new Set(
      (compared ?? []).flatMap((r) =>
        Object.keys(r.scalars).filter((k) => /^(section|contact)_\d+_force_max$/.test(k)),
      ),
    ),
  ]
    .sort()
    .map((k) => [k, k.replace(/^section_(\d+)_force_max$/, "Kesit $1 Fmax (kN)").replace(/^contact_(\d+)_force_max$/, "Temas $1 Fmax (kN)")]);
  const rows = [...SCALAR_ROWS, ...extraRows].filter(([k]) => (compared ?? []).some((r) => r.scalars[k] != null));

  return (
    <div className="material-assignments crash-history" data-testid="crash-history">
      <div className="crash-history-head">
        <p className="material-assignments-title">
          Koşu geçmişi{geometryId == null ? " · tüm geometriler" : ""} · {visible.length}
        </p>
        {/* kullanıcı 2026-10-14: karşılaştırma listenin altında kalıyor, "çalışmadı" sanıldı → üstte */}
        <button
          type="button"
          className="doe-btn doe-btn-ghost crash-history-compare-btn"
          disabled={selected.length === 0}
          onClick={() => void runCompare()}
        >
          Karşılaştır ({selected.length}/{MAX_COMPARE})
        </button>
        <button type="button" className="crash-contact-remove" aria-label="Geçmişi yenile" onClick={() => setTick((t) => t + 1)}>
          ↻
        </button>
      </div>
      <label className="material-check">
        <input type="checkbox" checked={showExcluded} onChange={(e) => setShowExcluded(e.target.checked)} />
        Dışlananları göster{hiddenCount > 0 ? ` (${hiddenCount} gizli)` : ""}
      </label>
      {error && <p className="material-assign-hint">{error}</p>}
      {compared && compared.length > 0 && (
        <div className="crash-compare" data-testid="crash-compare" ref={compareRef}>
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
              <input
                aria-label="Grafik zaman üst sınırı"
                value={tMaxRaw}
                placeholder="tümü"
                onChange={(e) => setTMaxRaw(e.target.value)}
              />
            </label>
            {onAnimate && (
              <button
                type="button"
                className="doe-btn doe-btn-ghost"
                data-testid="crash-compare-anim-open"
                disabled={compared.length !== 2 || !compared.every((r) => r.solver_ran && hasResults(r))}
                title="İki koşunun deforme şeklini viewport'ta yan yana, ortak zamanla açar (tam 2 çözülmüş koşu)"
                onClick={() => {
                  const [a, b] = compared;
                  onAnimate({
                    id: a.id,
                    title: `#${a.id} ${label(a)}`,
                    compareWith: { id: b.id, title: `#${b.id} ${label(b)}` },
                  });
                }}
              >
                Animasyon yan yana
              </button>
            )}
          </div>
          {series.length > 0 ? (
            <CrashForceChart
              time={series[0].time ?? []}
              series={series}
              title={curveKey.startsWith("acc_g") ? "İvme · g" : "Kuvvet · kN"}
              unit={curveKey.startsWith("acc_g") ? "g" : "kN"}
              yLabel={curveKey.startsWith("acc_g") ? "ivme" : "kuvvet"}
              showMean={!curveKey.startsWith("acc_g")}
            />
          ) : (
            <p className="doe-empty">Seçili koşularda bu eğri yok.</p>
          )}
          <div className="crash-history-scroll">
            <table className="doe-table crash-compare-table">
              <thead>
                <tr>
                  <th />
                  {compared.map((r) => (
                    <th key={r.id} title={label(r)}>
                      #{r.id}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(([k, title]) => (
                  <tr key={k}>
                    <td>{title}</td>
                    {compared.map((r) => (
                      <td key={r.id} className="crash-run-num">
                        {fmt(r.scalars[k])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {visible.length === 0 ? (
        <p className="doe-empty">{loading ? "Yükleniyor…" : "Kayıtlı crash koşusu yok."}</p>
      ) : (
        <ul className="crash-run-list" aria-label="Crash koşuları">
          {visible.map((r) => {
            const on = selected.includes(r.id);
            return (
              <li key={r.id} className={r.excluded ? "crash-run-row crash-run-excluded" : "crash-run-row"}>
                <input
                  type="checkbox"
                  aria-label={`${label(r)} seç`}
                  checked={on}
                  disabled={!on && selected.length >= MAX_COMPARE}
                  onChange={() => setSelected((s) => (on ? s.filter((x) => x !== r.id) : [...s, r.id]))}
                />
                <span className="crash-run-main">
                  <span className="crash-run-name">
                    {label(r)}
                    {r.has_raw_cards && (
                      <span className="crash-run-tag" title="Ham kartla üretildi; ML korpusu varsayılan almaz">
                        ham kart
                      </span>
                    )}
                  </span>
                  <span className="crash-run-meta">
                    #{r.id} · {when(r.created_at)}
                    {geometryId == null ? ` · geo ${r.geometry_id}` : ""} ·{" "}
                    <span className={`crash-run-status crash-run-${r.status}`}>{r.status}</span>
                  </span>
                </span>
                <span className="crash-run-num" title="Duvar Fmax (kN)">
                  {fmt(r.scalars.rwall_force_max)}
                </span>
                <button
                  type="button"
                  className="crash-run-exclude"
                  aria-label={`${label(r)} grafikler`}
                  title="Grafikler (kuvvet, ivme, enerji)"
                  disabled={!hasResults(r)}
                  onClick={() => setChartRun((a) => (a?.id === r.id ? null : r))}
                >
                  {chartRun?.id === r.id ? "■" : "📈"}
                </button>
                <button
                  type="button"
                  className="crash-run-exclude"
                  aria-label={`${label(r)} deforme şekil`}
                  title="Deforme şekil (animasyon)"
                  disabled={!r.solver_ran || !hasResults(r)}
                  onClick={() => {
                    if (onAnimate) {
                      onAnimate(activeAnimId === r.id ? null : { id: r.id, title: `#${r.id} ${label(r)}` });
                    } else {
                      setAnimRun((a) => (a?.id === r.id ? null : r));
                    }
                  }}
                >
                  {(onAnimate ? activeAnimId === r.id : animRun?.id === r.id) ? "■" : "▶"}
                </button>
                {onLoadRun && (
                  <button
                    type="button"
                    className="crash-run-exclude"
                    aria-label={`${label(r)} yükle`}
                    title="Geometri + mesh + kurulumu panellere yükle (düzenle / yeniden koş)"
                    onClick={() => onLoadRun(r.id)}
                  >
                    ⤓
                  </button>
                )}
                <button
                  type="button"
                  className="crash-run-exclude"
                  aria-label={`${label(r)} ${r.excluded ? "geri al" : "dışla"}`}
                  title={r.excluded ? "Dışlamayı geri al" : "Dışla (korpus almaz)"}
                  onClick={() => void toggleExcluded(r)}
                >
                  {r.excluded ? "↺" : "⊘"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {chartRun && <CrashRunCharts runId={chartRun.id} title={`#${chartRun.id} ${label(chartRun)}`} />}
      {!onAnimate && animRun && <CrashAnimationViewer runId={animRun.id} title={`#${animRun.id} ${label(animRun)}`} />}

    </div>
  );
}
