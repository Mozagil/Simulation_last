import { useMemo, useState, type MouseEvent as ReactMouseEvent } from "react";
import type { RunSummary } from "../api/runs";
import {
  summarizeTemplateParams,
  type SymbolMap,
} from "../templates/paramSummary";

const EXPANDED_DEFAULT_H = 220;
const EXPANDED_MIN_H = 120;
const EXPANDED_MAX_H = 640;

/** Donmuş eğitim setine göre run'ın durumu (manifest'ten gelir). */
export type CorpusRole = "auto" | "manual_pass" | "manual_override" | "outside";

const CORPUS_BADGE: Record<CorpusRole, { text: string; title: string }> = {
  auto: { text: "eğitim", title: "Süzgeç dondurulurken sete alındı" },
  manual_pass: { text: "manuel ✓", title: "Elle eklendi, süzgeci geçti" },
  manual_override: {
    text: "manuel ⚠",
    title: "Elle eklendi, süzgeci geçmedi (override)",
  },
  outside: { text: "sette değil", title: "Eğitim setinde yok — deneme çözümü" },
};

interface HistoryFooterProps {
  runs: RunSummary[];
  compareSelection: number[];
  busy: boolean;
  editBusy?: boolean;
  paramSymbols: SymbolMap;
  corpusName?: string | null;
  corpusRoles?: Record<number, CorpusRole>;
  onToggleCompare: (id: number) => void;
  onReview: (id: number) => void;
  onEdit: (id: number) => void;
  onDelete: (id: number, name: string) => void;
  onCompare: () => void;
  /** Bir run'ı deneme/mükerrer/kalitesiz diye işaretler ya da geri alır. */
  onSetExcluded?: (id: number, excluded: boolean) => void;
}

export default function HistoryFooter({
  runs,
  compareSelection,
  busy,
  editBusy = false,
  paramSymbols,
  corpusName = null,
  corpusRoles,
  onToggleCompare,
  onReview,
  onEdit,
  onDelete,
  onCompare,
  onSetExcluded,
}: HistoryFooterProps) {
  const [expanded, setExpanded] = useState(false);
  const [height, setHeight] = useState(EXPANDED_DEFAULT_H);
  // Süzgeçler tamamen istemci tarafında: liste zaten bellekte, sunucuya
  // gitmeye gerek yok. Şablon ve DOE seti seçenekleri veriden türetiliyor.
  const [templateFilter, setTemplateFilter] = useState<string>("");
  const [studyFilter, setStudyFilter] = useState<string>("");
  const [hideExcluded, setHideExcluded] = useState(false);

  const templates = useMemo(
    () => [...new Set(runs.map((r) => r.template_id).filter(Boolean))].sort() as string[],
    [runs],
  );
  const studies = useMemo(
    () =>
      [...new Set(runs.map((r) => r.doe_study_id).filter((v) => v != null))].sort(
        (a, b) => (b as number) - (a as number),
      ) as number[],
    [runs],
  );

  const visible = useMemo(
    () =>
      runs.filter((r) => {
        if (templateFilter && r.template_id !== templateFilter) return false;
        if (studyFilter === "manual" && r.doe_study_id != null) return false;
        if (studyFilter && studyFilter !== "manual" &&
            String(r.doe_study_id ?? "") !== studyFilter) return false;
        if (hideExcluded && r.excluded) return false;
        return true;
      }),
    [runs, templateFilter, studyFilter, hideExcluded],
  );
  const excludedCount = useMemo(
    () => runs.filter((r) => r.excluded).length,
    [runs],
  );

  // Klasör görünümü: şablon → koşu (DOE seti / elle çözülen). 900 run'da
  // düz liste okunmuyor; açılır menüler de tek seferde tek bir kesit
  // gösteriyor. Ağaç, hepsini aynı anda ama katlanmış halde gösterir.
  const [grouped, setGrouped] = useState(true);
  //: İkinci seviyenin neye göre ayrılacağı.
  //  "corpus" — eğitim setinde mi: asıl sorulan ayrım bu ("bu veri
  //             modeli eğitiyor mu, yoksa deneme mi").
  //  "study"  — hangi DOE setinden geldi: koşuları izlemek için.
  const [groupBy, setGroupBy] = useState<"corpus" | "study">("corpus");
  const [openKeys, setOpenKeys] = useState<Set<string>>(() => new Set());
  // Kullanıcı hiçbir klasöre dokunmadıysa HEPSİ açık sayılır. Aksi halde
  // panel ilk açıldığında sadece kapalı klasör başlıkları görünür ve
  // "geçmiş boş" izlenimi verir.
  const [touched, setTouched] = useState(false);
  const isOpen = (k: string) => (touched ? openKeys.has(k) : true);

  function toggleKey(k: string) {
    setOpenKeys((prev) => {
      // İlk dokunuşta o ana kadar "açık" sayılan her şeyi gerçekten aç,
      // sonra tıklananı kapat — aksi halde ilk tık her şeyi kapatırdı.
      const base = touched ? prev : new Set(allKeys);
      const next = new Set(base);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
    setTouched(true);
  }

  /** visible listesini şablon → koşu ağacına çevirir. */
  const tree = useMemo(() => {
    const byTemplate = new Map<string, Map<string, RunSummary[]>>();
    for (const r of visible) {
      const t = r.template_id ?? "(şablonsuz · yüklenen geometri)";
      let s: string;
      if (groupBy === "study") {
        s =
          r.doe_study_id != null
            ? `DOE #${r.doe_study_id}`
            : "DOE dışı (tek tek çözülen)";
      } else if (r.excluded) {
        s = "elle dışlanan";
      } else if (!corpusName) {
        // Donmuş set yoksa üyelik bilinmiyor; uydurmak yerine söylüyoruz.
        s = "eğitim seti dondurulmamış";
      } else {
        const role = corpusRoles?.[r.id] ?? "outside";
        s =
          role === "outside"
            ? "eğitim dışı (deneme / süzgeçte elendi)"
            : "EĞİTİM SETİ";
      }
      if (!byTemplate.has(t)) byTemplate.set(t, new Map());
      const inner = byTemplate.get(t)!;
      if (!inner.has(s)) inner.set(s, []);
      inner.get(s)!.push(r);
    }
    // Şablonlar alfabetik; koşular DOE numarası büyükten küçüğe, elle
    // çözülenler en sonda.
    return [...byTemplate.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([tpl, inner]) => ({
        template: tpl,
        count: [...inner.values()].reduce((n, v) => n + v.length, 0),
        studies: [...inner.entries()].sort((a, b) => {
          // Eğitim seti hep en üstte; dışlananlar en altta.
          const rank = (k: string) =>
            k === "EĞİTİM SETİ" ? 0 : k === "elle dışlanan" ? 2 : 1;
          const d = rank(a[0]) - rank(b[0]);
          if (d !== 0) return d;
          return b[0].localeCompare(a[0], undefined, { numeric: true });
        }),
      }));
  }, [visible, groupBy, corpusName, corpusRoles]);

  /** Ağaçtaki tüm klasör anahtarları — "hepsi açık" varsayılanı için. */
  const allKeys = useMemo(() => {
    const keys: string[] = [];
    for (const node of tree) {
      const t = `t:${node.template}`;
      keys.push(t);
      for (const [study] of node.studies) keys.push(`${t}/${study}`);
    }
    return keys;
  }, [tree]);

  function startResize(e: ReactMouseEvent<HTMLDivElement>) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    // window dinleyicisi native MouseEvent alır, React'in sarmalayıcısını değil.
    function onMove(ev: globalThis.MouseEvent) {
      const next = startH - (ev.clientY - startY);
      setHeight(Math.min(EXPANDED_MAX_H, Math.max(EXPANDED_MIN_H, next)));
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }

  /** Tek bir geçmiş satırı. Hem düz listede hem klasör görünümünde
   *  aynı şekilde çizilsin diye ayrı fonksiyon. */
  function renderRow(r: RunSummary) {
              const label = r.name ?? `Run #${r.id}`;
              // Set dondurulmuşsa üye olmayan run "sette değil" olarak işaretlenir.
              const role: CorpusRole | null = corpusName
                ? (corpusRoles?.[r.id] ?? "outside")
                : null;
              const badge = role ? CORPUS_BADGE[role] : null;
              return (
                <li
                  key={r.id}
                  className={
                    r.excluded ? "history-item history-item-excluded" : "history-item"
                  }
                >
                  <label className="history-item-checkbox">
                    <input
                      type="checkbox"
                      checked={compareSelection.includes(r.id)}
                      onChange={() => onToggleCompare(r.id)}
                    />
                  </label>
                  <button
                    type="button"
                    className="history-item-body"
                    onClick={() => onReview(r.id)}
                  >
                    <div className="history-item-title">
                      {label}{" "}
                      <span className={`history-status history-status-${r.status}`}>
                        {r.status}
                      </span>
                      {badge && (
                        <>
                          {" "}
                          <span className={`history-corpus history-corpus-${role}`} title={badge.title}>
                            {badge.text}
                          </span>
                        </>
                      )}
                      {r.doe_study_id != null && (
                        <>
                          {" "}
                          <span className="history-study-tag" title="Hangi DOE setinden">
                            DOE #{r.doe_study_id}
                          </span>
                        </>
                      )}
                      {r.excluded && (
                        <>
                          {" "}
                          <span
                            className="history-excluded-tag"
                            title={r.exclude_reason ?? "Elle dışlandı — eğitime girmez"}
                          >
                            dışlandı
                          </span>
                        </>
                      )}
                    </div>
                    <div className="history-item-sub">
                      {r.geometry_filename} · {r.dimension === 2 ? "2D" : "3D"} ·{" "}
                      {new Date(r.created_at).toLocaleString("tr-TR")}
                    </div>
                    {r.template_params && (
                      <div className="history-item-params">
                        {summarizeTemplateParams(r.template_id, r.template_params, paramSymbols)}
                      </div>
                    )}
                    {r.scalars.max_von_mises !== undefined && (
                      <div className="history-item-scalar">
                        VM max: {r.scalars.max_von_mises.toExponential(2)} · Deplasman max:{" "}
                        {r.scalars.max_displacement?.toExponential(2) ?? "—"}
                      </div>
                    )}
                  </button>
                  <div className="history-item-actions">
                    <button
                      type="button"
                      className="history-action-button"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        onEdit(r.id);
                      }}
                    >
                      {editBusy ? "Yükleniyor…" : "Düzenle"}
                    </button>
                    {onSetExcluded && (
                      <button
                        type="button"
                        className="history-action-button"
                        disabled={busy}
                        title={
                          r.excluded
                            ? "Geri al — eğitim setine yeniden girer"
                            : "Deneme/mükerrer/kalitesiz olarak işaretle. Silinmez, eğitim setinden çıkar."
                        }
                        onClick={(event) => {
                          event.stopPropagation();
                          onSetExcluded(r.id, !r.excluded);
                        }}
                      >
                        {r.excluded ? "Geri al" : "Dışla"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="history-action-button history-action-button-danger"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(r.id, label);
                      }}
                    >
                      Sil
                    </button>
                  </div>
                </li>
              );
  }

  return (
    <div
      className={expanded ? "history-footer" : "history-footer history-footer-collapsed"}
      style={expanded ? { height: `${height}px` } : undefined}
    >
      {expanded && (
        <div
          className="resize-handle resize-handle-top"
          role="separator"
          aria-orientation="horizontal"
          title="Sürükleyerek yüksekliği ayarla"
          onMouseDown={startResize}
        />
      )}
      <div className="history-footer-bar">
        <button
          type="button"
          className="history-footer-title"
          aria-expanded={expanded}
          onClick={() => setExpanded((prev) => !prev)}
        >
          Analiz geçmişi
          <span className="history-footer-count">
            {visible.length === runs.length
              ? runs.length
              : `${visible.length}/${runs.length}`}
          </span>
        </button>
        {expanded && (
          <span className="history-filters">
            <select
              value={templateFilter}
              onChange={(e) => setTemplateFilter(e.target.value)}
              title="Şablona göre süz — kiriş ve delikli plaka karışmasın"
            >
              <option value="">tüm şablonlar</option>
              {templates.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={studyFilter}
              onChange={(e) => setStudyFilter(e.target.value)}
              title="DOE setine göre süz"
            >
              <option value="">tüm koşular</option>
              <option value="manual">elle çözülenler</option>
              {studies.map((id) => (
                <option key={id} value={String(id)}>
                  DOE #{id}
                </option>
              ))}
            </select>
            <label className="history-filter-check" title="Klasör görünümü">
              <input
                type="checkbox"
                checked={grouped}
                onChange={(e) => setGrouped(e.target.checked)}
              />
              klasörle
            </label>
            {grouped && (
              <select
                value={groupBy}
                onChange={(e) =>
                  setGroupBy(e.target.value as "corpus" | "study")
                }
                title="Klasörler neye göre ayrılsın"
              >
                <option value="corpus">eğitim durumuna göre</option>
                <option value="study">DOE setine göre</option>
              </select>
            )}
            <label className="history-filter-check" title="Dışlananları gizle">
              <input
                type="checkbox"
                checked={hideExcluded}
                onChange={(e) => setHideExcluded(e.target.checked)}
              />
              dışlananları gizle
              {excludedCount > 0 && ` (${excludedCount})`}
            </label>
          </span>
        )}
        {corpusName && (
          <span className="history-footer-hint" title="Rozetler bu donmuş eğitim setine göre">
            set: {corpusName}
          </span>
        )}
        {compareSelection.length > 0 && (
          <span className="history-footer-hint">{compareSelection.length}/2 seçili</span>
        )}
        {compareSelection.length === 2 && (
          <button type="button" className="history-footer-compare" onClick={onCompare}>
            Karşılaştır
          </button>
        )}
        <button
          type="button"
          className="history-footer-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? "Gizle" : "Aç"}
        </button>
      </div>
      {expanded && (
        runs.length === 0 ? (
          <p className="history-footer-empty">Henüz kayıtlı analiz yok.</p>
        ) : (
          grouped ? (
            <div className="history-tree">
              {tree.map((node) => {
                const tKey = `t:${node.template}`;
                const tOpen = isOpen(tKey);
                return (
                  <div className="history-folder" key={tKey}>
                    <button
                      type="button"
                      className="history-folder-head"
                      aria-expanded={tOpen}
                      onClick={() => toggleKey(tKey)}
                    >
                      <span className="history-folder-caret">
                        {tOpen ? "▾" : "▸"}
                      </span>
                      <span className="history-folder-name">{node.template}</span>
                      <span className="history-folder-count">{node.count}</span>
                    </button>
                    {tOpen &&
                      node.studies.map(([study, rows]) => {
                        const sKey = `${tKey}/${study}`;
                        const sOpen = isOpen(sKey);
                        return (
                          <div className="history-subfolder" key={sKey}>
                            <button
                              type="button"
                              className={
                                study === "EĞİTİM SETİ"
                                  ? "history-folder-head history-folder-head-sub history-folder-training"
                                  : study === "elle dışlanan"
                                    ? "history-folder-head history-folder-head-sub history-folder-muted"
                                    : "history-folder-head history-folder-head-sub"
                              }
                              aria-expanded={sOpen}
                              onClick={() => toggleKey(sKey)}
                            >
                              <span className="history-folder-caret">
                                {sOpen ? "▾" : "▸"}
                              </span>
                              <span className="history-folder-name">{study}</span>
                              <span className="history-folder-count">
                                {rows.length}
                              </span>
                            </button>
                            {sOpen && (
                              <ul className="history-list history-list-nested">
                                {rows.map(renderRow)}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                  </div>
                );
              })}
            </div>
          ) : (
            <ul className="history-list">{visible.map(renderRow)}</ul>
          )
        )
      )}
    </div>
  );
}
