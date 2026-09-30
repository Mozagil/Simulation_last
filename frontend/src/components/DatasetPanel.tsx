import { useCallback, useEffect, useRef, useState } from "react";
import {
  downloadDataset,
  fetchDatasetSummary,
  importDataset,
  type DatasetSummary,
} from "../api/dataset";
import { fetchCorpusList, freezeCorpus, type CorpusListItem } from "../api/surrogate";

/**
 * Veri seti aşaması — Claude Design "ML Studio 1a".
 *
 * NEDEN VAR: Analiz geçmişi Codespace'in Postgres volume'ünde, çözüm
 * dosyaları `uploads/` altında yaşıyor ve ikisi de `.gitignore`'da.
 * Codespace silinince ikisi de gidiyor — gerçekten yaşandı, tüm geçmiş
 * kayboldu. Export endpoint'i backend'de vardı ama düğmesi yoktu; görünür
 * olmayan bir yedekleme adımı unutulur.
 *
 * Sol pano: sayaçlar, şablona göre çubuklar, donmuş korpuslar (tıklayınca
 * indirilecek set seçilir, "+ Yeni set dondur" ile yenisi).
 * Sağ pano: uyarı şeridi, üç indirme kartı (tümü / eğitim seti / seçili
 * run'lar), sürükle-bırak içe aktarma, bu oturumun işlem günlüğü.
 *
 * "Son yedek" rozeti bu tarayıcıda kaydedilen son başarılı arşiv
 * indirmesinden gelir (localStorage) — backend yedek geçmişi tutmuyor.
 */

const LAST_EXPORT_KEY = "simsurrogate.dataset.lastExport";

function readLastExport(): number | null {
  try {
    const v = window.localStorage.getItem(LAST_EXPORT_KEY);
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function writeLastExport(ts: number): void {
  try {
    window.localStorage.setItem(LAST_EXPORT_KEY, String(ts));
  } catch {
    /* özel pencere / engelli depolama: rozet güncellenmez, iş sürer */
  }
}

/** "6 gün önce", "3 saat önce", "az önce". */
export function relativeAgo(ts: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return "az önce";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} dk önce`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} saat önce`;
  const d = Math.round(h / 24);
  return `${d} gün önce`;
}

function fmtFrozen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function nowClock(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

interface LogRow {
  t: string;
  msg: string;
  tag: "dışa" | "içe" | "set" | "hata";
}

const STALE_DAYS = 7;

export default function DatasetPanel({
  refreshKey,
  selectedRunIds,
  templateId,
}: {
  refreshKey?: number;
  /** Geçmiş listesinde işaretli run'lar — varsa yalnız onlar indirilebilir. */
  selectedRunIds?: number[];
  /** Stüdyonun şablonu: yeni set bu şablonun run'larından dondurulur. */
  templateId?: string | null;
}) {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  // Donmuş eğitim setleri: temiz veriyi indirmenin tek yolu. "Yalnız
  // çözülmüş" süzgeci elle dışlananları ve süzgeçten düşenleri de alıyor.
  const [corpora, setCorpora] = useState<CorpusListItem[]>([]);
  const [corpus, setCorpus] = useState<string>("");
  const [busy, setBusy] = useState<"export" | "import" | "freeze" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<LogRow[]>([]);
  // Çözülmemiş run'ların sonuç dosyası yoktur; arşivi büyütmekten başka
  // işe yaramazlar. Varsayılan olarak dışarıda bırakılıyor.
  const [onlySolved, setOnlySolved] = useState(true);
  const [lastExport, setLastExport] = useState<number | null>(() => readLastExport());
  const [freezeOpen, setFreezeOpen] = useState(false);
  const [freezeName, setFreezeName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const reloadCorpora = useCallback(() => {
    return fetchCorpusList()
      .then((raw) => {
        // En yeni üstte; tarihi olmayanlar sonda. Varsayılan seçim en yeni set.
        const list = [...raw].sort((a, b) => (b.frozen_at ?? "").localeCompare(a.frozen_at ?? ""));
        setCorpora(list);
        setCorpus((prev) => (prev && list.some((c) => c.name === prev) ? prev : list[0]?.name ?? ""));
      })
      .catch(() => setCorpora([]));
  }, []);

  useEffect(() => {
    void reloadCorpora();
  }, [reloadCorpora, refreshKey]);

  const reload = useCallback(() => {
    fetchDatasetSummary()
      .then(setSummary)
      .catch((e) => setError(e instanceof Error ? e.message : "Özet alınamadı."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  function pushLog(msg: string, tag: LogRow["tag"]) {
    setLog((prev) => [{ t: nowClock(), msg, tag }, ...prev].slice(0, 8));
  }

  async function handleExport(runIds?: number[], corpusName?: string) {
    setBusy("export");
    setError(null);
    try {
      await downloadDataset({ onlySolved, runIds, corpusName });
      pushLog(
        corpusName
          ? `"${corpusName}" eğitim seti indirildi (setin tanımı da arşivde).`
          : runIds?.length
            ? `${runIds.length} run indirildi.`
            : "Arşiv indirildi. Bu ortam dışında bir yerde saklayın.",
        "dışa",
      );
      if (!runIds?.length && !corpusName) {
        const ts = Date.now();
        writeLastExport(ts);
        setLastExport(ts);
      }
    } catch (e) {
      const m = e instanceof Error ? e.message : "Dışa aktarma başarısız.";
      setError(m);
      pushLog(m, "hata");
    } finally {
      setBusy(null);
    }
  }

  async function handleImport(file: File) {
    setBusy("import");
    setError(null);
    try {
      const r = await importDataset(file);
      const added = Object.entries(r.added)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join(", ");
      pushLog(added ? `İçe aktarıldı — ${added}` : "Arşivde yeni kayıt yoktu.", "içe");
      reload();
      void reloadCorpora();
    } catch (e) {
      const m = e instanceof Error ? e.message : "İçe aktarma başarısız.";
      setError(m);
      pushLog(m, "hata");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleFreeze() {
    const name = freezeName.trim();
    if (!name) {
      setError("Set adı boş olamaz.");
      return;
    }
    setBusy("freeze");
    setError(null);
    try {
      const r = await freezeCorpus(name, { templateId: templateId ?? undefined });
      pushLog(`Set donduruldu: ${name} · ${r.manifest.run_ids.length} run`, "set");
      setFreezeOpen(false);
      setFreezeName("");
      await reloadCorpora();
      setCorpus(name);
    } catch (e) {
      const m = e instanceof Error ? e.message : "Set dondurulamadı.";
      setError(m);
      pushLog(m, "hata");
    } finally {
      setBusy(null);
    }
  }

  const unsolved = summary != null ? summary.analysis_runs - summary.solved_runs : 0;
  const byTemplate = summary?.by_template ?? [];
  const maxRuns = Math.max(1, ...byTemplate.map((r) => r.runs));
  const selectedCorpus = corpora.find((c) => c.name === corpus) ?? null;
  const nSelected = selectedRunIds?.length ?? 0;
  const stale = lastExport == null || Date.now() - lastExport > STALE_DAYS * 86400e3;

  return (
    <div className="doe-stage ds-stage" data-testid="dataset-stage">
      {/* ── Sol pano ─────────────────────────────────────────────── */}
      <div className="doe-pane-l">
        <div className="doe-phead">
          <span className="doe-phead-title">
            <span className="ml-k">0.5 · Veri seti</span>
            <span className="ml-h">Eğitim verisi</span>
          </span>
          <span className={`doe-st ${stale ? "doe-st-warn" : "doe-st-ok"} ds-backup-badge`} title="Bu tarayıcıda kaydedilen son tam arşiv indirmesi">
            {lastExport == null ? "yedek alınmadı" : `son yedek ${relativeAgo(lastExport)}`}
          </span>
        </div>
        <div className="doe-pane-body ds-body">
          {summary === null ? (
            <p className="doe-empty">Yükleniyor…</p>
          ) : (
            <div className="ds-stats">
              <span><span className="ds-big">{summary.solved_runs}</span><span className="ds-sb">çözülmüş run</span></span>
              <span><span className="ds-big">{summary.training_samples}</span><span className="ds-sb">eğitim .npz</span></span>
              <span><span className="ds-big">{summary.geometries}</span><span className="ds-sb">geometri</span></span>
              <span><span className="ds-big">{summary.materials}</span><span className="ds-sb">malzeme</span></span>
              <span><span className="ds-big ds-big-warn">{unsolved}</span><span className="ds-sb">çözülmemiş</span></span>
            </div>
          )}

          {byTemplate.length > 0 && (
            <div className="ds-section">
              <span className="ds-legend-row">
                <span className="ml-k">Şablona göre</span>
                <span className="ds-legend"><span className="ds-sw ds-sw-solved" />çözülmüş</span>
                <span className="ds-legend"><span className="ds-sw ds-sw-unsolved" />çözülmemiş</span>
                <span className="ds-legend"><span className="ds-sw ds-sw-excluded" />dışlanan</span>
              </span>
              {byTemplate.map((row) => {
                const solved = Math.max(0, row.solved - row.excluded);
                const unsolvedT = Math.max(0, row.runs - row.solved);
                const w = (n: number) => `${(n / maxRuns) * 100}%`;
                return (
                  <div className="ds-trow" key={row.template_id ?? "__none__"} data-testid="template-row">
                    <span className="ds-tname">
                      {row.template_id ?? <span className="dataset-template-none">şablonsuz</span>}
                    </span>
                    <span className="ds-tbar" aria-hidden="true">
                      <span className="ds-sw-solved" style={{ width: w(solved) }} />
                      <span className="ds-sw-unsolved" style={{ width: w(unsolvedT) }} />
                      <span className="ds-sw-excluded" style={{ width: w(row.excluded) }} />
                    </span>
                    <span className="ds-tnum">
                      <strong>{row.solved}</strong>
                      <span className="ds-sb"> / {row.runs}</span>
                    </span>
                  </div>
                );
              })}
              <span className="ds-sb ds-note">
                Her şablon ayrı bir model demektir — korpus tek şablondan eğitilir. Arşiv ise hepsini birlikte taşır.
              </span>
            </div>
          )}

          <div className="ds-section">
            <span className="ds-legend-row">
              <span className="ml-k">Eğitim setleri · donmuş korpuslar</span>
              <button
                type="button"
                className="doe-btn doe-btn-ghost ds-ghost"
                disabled={busy !== null}
                onClick={() => setFreezeOpen((v) => !v)}
              >
                + Yeni set dondur
              </button>
            </span>
            {freezeOpen && (
              <div className="ds-freeze">
                <input
                  className="doe-num ds-freeze-input"
                  aria-label="Yeni set adı"
                  placeholder="örn. kiris_v4"
                  value={freezeName}
                  disabled={busy !== null}
                  onChange={(e) => setFreezeName(e.target.value)}
                />
                <span className="ds-sb">
                  {templateId ? `${templateId} · canlı süzgeçten` : "tüm şablonlar · canlı süzgeçten"}
                </span>
                <button
                  type="button"
                  className="doe-btn doe-btn-primary"
                  disabled={busy !== null}
                  onClick={() => void handleFreeze()}
                >
                  {busy === "freeze" ? "Donduruluyor…" : "Dondur"}
                </button>
              </div>
            )}
            {corpora.length === 0 ? (
              <span className="ds-sb">Henüz donmuş set yok.</span>
            ) : (
              corpora.map((c) => {
                const on = c.name === corpus;
                return (
                  <button
                    key={c.name}
                    type="button"
                    className={on ? "ds-corpus active" : "ds-corpus"}
                    aria-pressed={on}
                    onClick={() => setCorpus(c.name)}
                  >
                    <span className="ds-corpus-main">
                      <strong>{c.name}</strong>
                      <span className="ds-sb">
                        {c.template_id ?? "şablonsuz"}
                        {c.frozen_at ? ` · donduruldu ${fmtFrozen(c.frozen_at)}` : ""}
                      </span>
                    </span>
                    <span className="ds-sb">{c.n_manual > 0 ? `${c.n_manual} elle` : "—"}</span>
                    <span className="ds-corpus-runs">{c.n_runs} run</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ── Sağ pano ─────────────────────────────────────────────── */}
      <div className="doe-pane-r ds-right">
        <span className="doe-phead-title">
          <span className="ml-k">Yedekle ve taşı</span>
          <span className="ml-h">Dışa / içe aktar</span>
        </span>

        <div className="ds-warn" role="note">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3l9 16H3z" />
            <path d="M12 10v4M12 17h.01" />
          </svg>
          <span>Analiz geçmişi ve çözüm dosyaları yalnız bu ortamda yaşar. Ortam silinirse veri de gider — düzenli arşiv alın.</span>
        </div>

        <div className="ds-cards">
          <div className="ds-card ds-card-primary">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 4v11" /><path d="M7 10l5 5 5-5" /><path d="M4 19h16" />
            </svg>
            <span className="ds-card-title">Tümünü indir</span>
            <span className="ds-sb ds-card-desc">Tüm veritabanı satırları ve çözüm dosyaları (.frd.gz, .train.npz) tek arşivde.</span>
            <label className="doe-pfoot-check">
              <input type="checkbox" checked={onlySolved} onChange={(e) => setOnlySolved(e.target.checked)} />
              Yalnız çözülmüş run'lar
            </label>
            <span className="ds-sb">
              {summary ? `~${onlySolved ? summary.solved_runs : summary.analysis_runs} run` : " "}
            </span>
            <button
              type="button"
              className="doe-btn doe-btn-primary ds-card-btn"
              disabled={busy !== null}
              onClick={() => void handleExport()}
            >
              {busy === "export" ? "Hazırlanıyor…" : "Arşivi indir"}
            </button>
          </div>

          <div className="ds-card">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 7l8-4 8 4-8 4z" /><path d="M4 12l8 4 8-4" /><path d="M4 17l8 4 8-4" />
            </svg>
            <span className="ds-card-title">Eğitim setini indir</span>
            <span className="ds-sb ds-card-desc">Yalnız donmuş setin run'ları + setin tanımı. Temiz veriyi taşımanın tek yolu.</span>
            {corpora.length > 0 ? (
              <span className="doe-chips" role="group" aria-label="Eğitim seti">
                {corpora.map((c) => (
                  <button
                    key={c.name}
                    type="button"
                    className={c.name === corpus ? "doe-chip active" : "doe-chip"}
                    aria-pressed={c.name === corpus}
                    onClick={() => setCorpus(c.name)}
                  >
                    {c.name} · {c.n_runs}
                  </button>
                ))}
              </span>
            ) : (
              <span className="ds-sb">Donmuş set yok — soldan "+ Yeni set dondur".</span>
            )}
            <button
              type="button"
              className="doe-btn ds-card-btn"
              disabled={busy !== null || !selectedCorpus}
              onClick={() => selectedCorpus && void handleExport(undefined, selectedCorpus.name)}
              title="Yalnız bu donmuş setin run'ları + setin tanımı"
            >
              {selectedCorpus ? `${selectedCorpus.name}'i indir` : "Eğitim setini indir"}
            </button>
          </div>

          <div className="ds-card">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 11l3 3 5-6" /><path d="M4 4h16v16H4z" />
            </svg>
            <span className="ds-card-title">Seçili run'lar</span>
            <span className="ds-sb ds-card-desc">Analiz Geçmişi'nde işaretlenen run'lar. Geçmişte seçim yoksa pasif.</span>
            <span className="ds-count">
              <span className="ds-big">{nSelected}</span>
              <span className="ds-sb">run seçili</span>
            </span>
            <button
              type="button"
              className="doe-btn ds-card-btn"
              disabled={busy !== null || nSelected === 0}
              onClick={() => selectedRunIds && void handleExport(selectedRunIds)}
            >
              {nSelected > 0 ? `Seçili ${nSelected} run'ı indir` : "Seçili run'ları indir"}
            </button>
          </div>
        </div>

        <label
          className={dragOver ? "ds-drop ds-drop-over" : "ds-drop"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void handleImport(f);
          }}
        >
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 15V4" /><path d="M7 9l5-5 5 5" /><path d="M4 19h16" />
          </svg>
          <span className="ds-drop-text">
            <span className="ds-card-title">İçe aktar</span>
            <span className="ds-sb">.tar.gz / .tgz arşivini bırakın veya seçin</span>
            <span className="ds-sb">İçe aktarma hiçbir kaydı silmez, ekler — aynı arşivi iki kez almak kayıtları çoğaltır.</span>
          </span>
          <span className="doe-btn ds-drop-btn">{busy === "import" ? "Aktarılıyor…" : "Dosya seç"}</span>
          <input
            ref={fileRef}
            type="file"
            accept=".tar.gz,.tgz"
            aria-label="Arşiv dosyası"
            disabled={busy !== null}
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleImport(f);
            }}
          />
        </label>

        {(log.length > 0 || error) && (
          <div className="ds-section">
            <span className="ml-k">Son işlemler</span>
            {error && <p className="dataset-error">{error}</p>}
            {log.map((l, i) => (
              <span className="ds-logrow" key={`${l.t}-${i}`}>
                <span className="ds-sb">{l.t}</span>
                <span>{l.msg}</span>
                <span className={`doe-st ${l.tag === "içe" || l.tag === "set" ? "doe-st-ok" : l.tag === "hata" ? "doe-st-warn" : ""}`}>{l.tag}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
