import { useEffect, useState } from "react";
import {
  compareCrashRuns,
  fetchCrashRuns,
  patchCrashRun,
  type CrashRunCompared,
  type CrashRunSummary,
} from "../api/crash";
import CrashAnimationViewer from "./CrashAnimationViewer";
import CrashRunCharts from "./CrashRunCharts";
import CrashComparePage from "./CrashComparePage";
import { fmtScalar as fmt, runHasResults as hasResults, runLabel as label } from "../lib/crashRunFormat";

/** Crash koşu geçmişi + karşılaştırma (1.16b). Veri gösterir: koşular, skalerler,
 * seçilen kuvvet eğrisi üst üste. Yorum / sıralama önerisi yok. Karşılaştırma ayrı
 * tam ekran sayfada (CrashComparePage). */

const MAX_COMPARE = 6;

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Ana viewport'ta açılacak deforme şekil. */
export interface CrashAnimTarget {
  id: number;
  title: string;
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
  onAnimate?: (run: CrashAnimTarget | null) => void;
  /** 1.23 B3a — koşunun geometrisi + mesh'i + kurulumu panellere yüklenir. */
  onLoadRun?: (runId: number) => void;
}) {
  const [runs, setRuns] = useState<CrashRunSummary[]>([]);
  const [showExcluded, setShowExcluded] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [compared, setCompared] = useState<CrashRunCompared[] | null>(null);
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
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karşılaştırma başarısız.");
    }
  }

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
      {compared && compared.length > 0 && <CrashComparePage runs={compared} onClose={() => setCompared(null)} />}
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
                    {geometryId == null ? (r.geometry_id != null ? ` · geo ${r.geometry_id}` : " · içe aktarma (.k)") : ""} ·{" "}
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
