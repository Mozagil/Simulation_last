/**
 * "Belgeler" penceresi (navbar, kullanıcı isteği 2026-10-08): crash'teki her
 * özellik / düğme / kart — ne yapar, hangi senaryoda, OpenRadioss kartı ve
 * LS-DYNA karşılığı (≈, bilgi amaçlı). İçerik `docs/crashDoc.ts`.
 */
import { useEffect, useMemo, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DocItem } from "../docs/crashDoc";
import { dynaFor } from "../lib/dynaKeywords";
import { CRASH_BOOK, DOC_BOOKS, type DocBook } from "../docs/books";

const MAP_ID = "eslesme";
const SCEN_ID = "senaryolar";
const TRAIN_ID = "egitim";
const EX_ID = "ornekler";

function itemDyna(it: DocItem, book: DocBook = CRASH_BOOK): string | null {
  if (!book.dynaColumn) return null;
  return it.dyna ?? (it.card ? dynaFor(it.card) : null);
}

function matches(it: DocItem, q: string): boolean {
  if (!q) return true;
  const hay = [it.name, it.what, it.when, it.card, itemDyna(it)].filter(Boolean).join(" ").toLocaleLowerCase("tr");
  return hay.includes(q);
}

const low = (x: string) => x.toLocaleLowerCase("tr");

/** Arama süzgeci (boş q = tümü). */
function filterDocs(book: DocBook, q: string) {
  const sections = book.sections
    .map((s) => ({ ...s, items: (s.items ?? []).filter((it) => matches(it, q)) }))
    .filter((s) => !q || s.items.length > 0 || low(s.title + " " + s.intro).includes(q));
  const scenarios = (book.scenarios?.rows ?? []).filter(
    (s) => !q || low([s.title, s.setup, s.features.join(" "), s.template].join(" ")).includes(q),
  );
  const mapRows = Object.entries(book.dynaMap ?? {}).filter(([c, d]) => !q || low(c).includes(q) || low(d).includes(q));
  const examples = (book.examples?.rows ?? []).filter(
    (e) => !q || low([e.title, e.setup, ...e.inputs, ...e.targets, ...e.results, e.lesson].join(" ")).includes(q),
  );
  const testHay = (t: { id: string; title: string; learn: string; expect: string; steps: string[] }) =>
    low([t.id, t.title, t.learn, t.expect, ...t.steps].join(" "));
  const groups = (book.training?.groups ?? [])
    .map((g) => ({ ...g, tests: g.tests.filter((t) => !q || testHay(t).includes(q)) }))
    .filter((g) => g.tests.length > 0);
  return { sections, scenarios, mapRows, examples, groups };
}

/** Belge içeriği — pencerede ve PDF baskısında aynı bileşen. */
export function DocsContent({
  q,
  onZoom,
  book = CRASH_BOOK,
}: {
  q: string;
  onZoom: (z: { src: string; caption: string }) => void;
  book?: DocBook;
}) {
  const { sections, scenarios, mapRows, examples, groups } = filterDocs(book, q);
  return (
    <>
    <p className="docs-note">{book.note}</p>
    {sections.map((s) => (
      <section key={s.id} id={`doc-${s.id}`} className="docs-section">
        <h2>{s.title}</h2>
        <p>{s.intro}</p>
        {s.image && (
          <figure className="docs-figure">
            <button type="button" className="docs-img-btn" onClick={() => onZoom({ src: s.image!, caption: s.imageCaption ?? "" })}>
              <img src={s.image} alt={s.imageCaption ?? s.title} loading="lazy" />
            </button>
            {s.imageCaption && <figcaption>{s.imageCaption}</figcaption>}
          </figure>
        )}
        {s.items.length > 0 && (
          <div className="docs-table-wrap">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Öğe</th>
                  <th>Ne yapar · ne zaman</th>
                  <th>{book.cardHeader}</th>
                  {book.dynaColumn && <th>LS-DYNA ≈</th>}
                </tr>
              </thead>
              <tbody>
                {s.items.map((it) => (
                  <tr key={it.name}>
                    <td className="docs-name">{it.name}</td>
                    <td>
                      {it.what}
                      {it.when && <span className="docs-when">Ne zaman: {it.when}</span>}
                    </td>
                    <td>{it.card ? <code>{it.card}</code> : "—"}</td>
                    {book.dynaColumn && <td className="docs-dyna">{itemDyna(it, book) ?? "—"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {s.gallery?.map((g) => (
          <figure key={g.src} className="docs-figure">
            <button type="button" className="docs-img-btn" onClick={() => onZoom(g)}>
              <img src={g.src} alt={g.caption} loading="lazy" />
            </button>
            <figcaption>{g.caption}</figcaption>
          </figure>
        ))}
      </section>
    ))}

    {book.scenarios && (
    <section id={`doc-${SCEN_ID}`} className="docs-section">
      <h2>{book.scenarios.title}</h2>
      <p>{book.scenarios.intro}</p>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>Senaryo</th>
              <th>Kurulum</th>
              <th>Kullanılan özellikler</th>
              <th>Doğrulama · referans</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => (
              <tr key={s.id}>
                <td className="docs-name">
                  {s.title}
                  <code className="docs-tpl">{s.template}</code>
                </td>
                <td>{s.setup}</td>
                <td>
                  <span className="docs-chips">
                    {s.features.map((f) => (
                      <span key={f} className="docs-chip">
                        {f}
                      </span>
                    ))}
                  </span>
                </td>
                <td>
                  {s.validation}
                  <span className="docs-when">{s.reference}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
    )}

    {book.dynaMap && (
    <section id={`doc-${MAP_ID}`} className="docs-section">
      <h2>OpenRadioss ↔ LS-DYNA tablosu</h2>
      <p>Arayüzde kullanılan tüm kartlar ve yaklaşık LS-DYNA karşılıkları (frontend/src/lib/dynaKeywords.ts).</p>
      <div className="docs-table-wrap">
        <table className="docs-table docs-map">
          <thead>
            <tr>
              <th>OpenRadioss</th>
              <th>LS-DYNA ≈</th>
            </tr>
          </thead>
          <tbody>
            {mapRows.map(([c, d]) => (
              <tr key={c}>
                <td>
                  <code>{c}</code>
                </td>
                <td className="docs-dyna">{d}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
    )}

    {book.examples && examples.length > 0 && (
    <section id={`doc-${EX_ID}`} className="docs-section">
      <h2>{book.examples.title}</h2>
      <p>{book.examples.intro}</p>
      {examples.map((e) => (
        <article key={e.id} className="docs-train-card docs-example" data-testid={`example-${e.id}`}>
          <header>
            <span className="docs-train-id">{e.domain === "crash" ? "Crash" : "Durability"}</span>
            <strong>{e.title}</strong>
          </header>
          <p>
            <b>Kurulum:</b> {e.setup}
          </p>
          <p>
            <b>Girdiler:</b> {e.inputs.join(" · ")}
          </p>
          <p>
            <b>Hedefler:</b> {e.targets.join(" · ")}
          </p>
          <ul>
            {e.results.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="docs-train-answer">Ders: {e.lesson}</p>
        </article>
      ))}
    </section>
    )}

    {book.training && (
    <section id={`doc-${TRAIN_ID}`} className="docs-section docs-training">
      <h2>{book.training.title}</h2>
      <p>{book.training.intro}</p>
      {groups.map((g) => (
        <div key={g.title} className="docs-train-group">
          <h3>{g.title}</h3>
          <div className="docs-train-base">
            <strong>Modeli kur (bir kez)</strong>
            <ol>
              {g.setup.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ol>
          </div>
          {g.tests.map((t) => (
              <article key={t.id} className="docs-train-card" data-testid={`train-${t.id}`}>
                <header>
                  <span className="docs-train-id">{t.id}</span>
                  <strong>{t.title}</strong>
                  <span className="docs-chip">{t.area}</span>
                </header>
                <p className="docs-train-learn">{t.learn}</p>
                <p className="docs-train-change">
                  <b>Değişen:</b> {t.change}
                </p>
                <ol>
                  {t.steps.map((st) => (
                    <li key={st}>{st}</li>
                  ))}
                </ol>
                {t.observe && (
                  <p>
                    <b>Bak:</b> {t.observe}
                  </p>
                )}
                <p>
                  <b>Beklenen:</b> {t.expect}
                </p>
                {t.answer && <p className="docs-train-answer">Biri sorarsa: “{t.answer}”</p>}
              </article>
            ))}
        </div>
      ))}
    </section>
    )}
    </>
  );
}

/** Baskı / PDF sayfasının stili (A4; Türkçe karakterli font; görsel ve kartlar bölünmez). */
const PRINT_CSS = `
@page { size: A4; margin: 14mm 12mm 16mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "IBM Plex Sans", "Segoe UI", "Noto Sans", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1d1f20; background: #fff; }
code, .docs-dyna, .docs-tpl { font-family: "IBM Plex Mono", Consolas, monospace; }
.cover { border-bottom: 2px solid #5980a6; margin-bottom: 10mm; padding-bottom: 4mm; }
.cover h1 { margin: 0 0 2mm; font-size: 20pt; }
.cover p { margin: 0; color: #5d5d60; }
.docs-note { padding: 6px 10px; border: 1px solid #d9dde3; border-radius: 6px; background: #f4f5f7; color: #5d5d60; font-size: 9.5pt; }
.docs-section { margin-bottom: 8mm; }
.docs-section h2 { font-size: 14pt; margin: 6mm 0 2mm; break-after: avoid; page-break-after: avoid; color: #1d1f20; }
.docs-section > p { margin: 0 0 3mm; }
.docs-figure { margin: 3mm 0 4mm; break-inside: avoid; page-break-inside: avoid; }
.docs-img-btn { display: block; padding: 0; border: 1px solid #d9dde3; border-radius: 6px; background: none; overflow: hidden; }
.docs-figure img { display: block; max-width: 100%; max-height: 115mm; object-fit: contain; margin: 0 auto; }
.docs-figure figcaption { font-size: 9pt; color: #5d5d60; margin-top: 1.5mm; }
.docs-table-wrap { border: 1px solid #d9dde3; }
.docs-table { width: 100%; border-collapse: collapse; font-size: 9.5pt; table-layout: fixed; }
.docs-table th:nth-child(1) { width: 21%; } .docs-table th:nth-child(2) { width: 43%; }
.docs-table th:nth-child(3) { width: 14%; } .docs-table th:nth-child(4) { width: 22%; }
.docs-map th:nth-child(1) { width: 35%; } .docs-map th:nth-child(2) { width: 65%; }
.docs-table td { overflow-wrap: anywhere; }
.docs-table thead { display: table-header-group; }
.docs-table th, .docs-table td { padding: 5px 7px; text-align: left; vertical-align: top; border-bottom: 1px solid #e3e6ea; }
.docs-table th { background: #f4f5f7; color: #5d5d60; font-weight: 600; }
.docs-table tr { break-inside: avoid; page-break-inside: avoid; }
.docs-name { font-weight: 600; }
.docs-when { display: block; color: #5d5d60; font-size: 9pt; margin-top: 1mm; }
.docs-dyna { color: #4a7099; font-size: 9pt; overflow-wrap: anywhere; }
.docs-chips { display: flex; flex-wrap: wrap; gap: 3px; }
.docs-chip { padding: 1px 6px; font-size: 8.5pt; border: 1px solid #d9dde3; border-radius: 999px; background: #f4f5f7; }
.docs-train-group { break-before: auto; }
.docs-train-group h3 { font-size: 12pt; margin: 5mm 0 2mm; break-after: avoid; page-break-after: avoid; }
.docs-train-base, .docs-train-card { break-inside: avoid; page-break-inside: avoid; padding: 6px 10px; margin-bottom: 3mm; border: 1px solid #d9dde3; border-radius: 6px; }
.docs-train-base { background: #f4f5f7; }
.docs-train-card header { display: flex; gap: 6px; align-items: center; }
.docs-train-id { padding: 0 7px; color: #fff; background: #5980a6; border-radius: 999px; font-weight: 700; font-size: 9pt; }
.docs-train-learn { color: #0b7a6e; font-weight: 500; }
.docs-train-change { padding: 2px 6px; background: #eef3f8; border-radius: 4px; }
.docs-train-answer { padding: 3px 6px; background: #f4f5f7; border-radius: 4px; }
.docs-train-card p { margin: 1.5mm 0; }
.docs-train-card ol, .docs-train-base ol { margin: 1.5mm 0; padding-left: 6mm; }
`;

/** Baskı sayfasının tam HTML'i (arama süzgeci olmadan tüm belge). */
export function buildDocsPdfHtml(origin: string, book: DocBook = CRASH_BOOK): string {
  const html = renderToStaticMarkup(<DocsContent q="" onZoom={() => undefined} book={book} />);
  const date = new Date().toLocaleDateString("tr-TR");
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<base href="${origin}/">
<title>SimSurrogate — ${book.tab} Belgeleri</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>${PRINT_CSS}</style></head><body>
<header class="cover"><h1>${book.title} — Belgeler</h1>
<p>SimSurrogate · ${book.subtitle} · ${date}</p></header>
<main class="docs-main">${html}</main></body></html>`;
}

/** Tüm belgeyi gizli bir çerçevede hazırlar ve tarayıcının yazdır penceresini
 * açar — "PDF olarak kaydet" ile indirilir. Açılır pencere engelinden etkilenmez. */
export function openDocsPdf(book: DocBook = CRASH_BOOK): boolean {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  document.body.appendChild(frame);
  const w = frame.contentWindow;
  if (!w) {
    frame.remove();
    return false;
  }
  w.document.open();
  w.document.write(buildDocsPdfHtml(window.location.origin, book));
  w.document.close();
  const ready = async () => {
    const imgs = Array.from(w.document.images);
    await Promise.all(
      imgs.map((im) => (im.complete ? Promise.resolve() : new Promise((r) => { im.onload = im.onerror = () => r(null); }))),
    );
    try {
      await w.document.fonts.ready;
    } catch {
      /* font yüklenemezse yedek font */
    }
    w.focus();
    w.print();
    // yazdır penceresi kapanınca çerçeveyi kaldır
    setTimeout(() => frame.remove(), 60_000);
  };
  void ready();
  return true;
}

export default function DocsDialog({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState<{ src: string; caption: string } | null>(null);
  const q = query.trim().toLocaleLowerCase("tr");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") (zoom ? setZoom(null) : onClose());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, zoom]);

  const [bookId, setBookId] = useState<DocBook["id"]>("crash");
  const book = DOC_BOOKS.find((b) => b.id === bookId) ?? CRASH_BOOK;
  const { sections, scenarios, examples, groups } = useMemo(() => filterDocs(book, q), [book, q]);
  const [pdfBlocked, setPdfBlocked] = useState(false);

  const go = (id: string) => document.getElementById(`doc-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="docs-backdrop" role="presentation" onClick={onClose}>
      <div className="docs-dialog" role="dialog" aria-label="Belgeler" onClick={(e) => e.stopPropagation()}>
        <header className="docs-head">
          <div className="docs-head-title">
            <strong>Belgeler · {book.title}</strong>
            <span>{book.subtitle}</span>
          </div>
          {DOC_BOOKS.length > 1 && (
            <div className="docs-tabs" role="tablist" aria-label="Belge">
              {DOC_BOOKS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  role="tab"
                  aria-selected={b.id === book.id}
                  className={b.id === book.id ? "docs-tab active" : "docs-tab"}
                  onClick={() => setBookId(b.id)}
                >
                  {b.tab}
                </button>
              ))}
            </div>
          )}
          <input
            className="docs-search"
            type="search"
            placeholder={book.searchPlaceholder}
            aria-label="Belgelerde ara"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            className="docs-pdf"
            title="Tüm belgeyi PDF olarak indir (yazdır penceresinde “PDF olarak kaydet”)"
            onClick={() => setPdfBlocked(!openDocsPdf(book))}
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13h10" />
            </svg>
            PDF indir
          </button>
          {pdfBlocked && <span className="docs-pdf-warn">PDF sayfası hazırlanamadı.</span>}
          <button type="button" className="docs-close" aria-label="Belgeleri kapat" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="docs-body">
          <nav className="docs-nav" aria-label="İçindekiler">
            {sections.map((s) => (
              <button key={s.id} type="button" onClick={() => go(s.id)}>
                {s.title}
              </button>
            ))}
            {book.scenarios && (
              <button type="button" onClick={() => go(SCEN_ID)}>
                {book.id === "crash" ? "Hazır senaryolar" : book.scenarios.title} ({scenarios.length})
              </button>
            )}
            {book.dynaMap && (
              <button type="button" onClick={() => go(MAP_ID)}>
                OpenRadioss ↔ LS-DYNA tablosu
              </button>
            )}
            {book.examples && examples.length > 0 && (
              <button type="button" onClick={() => go(EX_ID)}>
                {book.examples.title}
              </button>
            )}
            {book.training && groups.length > 0 && (
              <button type="button" className="docs-nav-train" onClick={() => go(TRAIN_ID)}>
                {book.training.title}
              </button>
            )}
          </nav>
          <main className="docs-main">
            <DocsContent q={q} onZoom={setZoom} book={book} />
          </main>
        </div>
        {zoom && (
          <div className="docs-zoom" role="presentation" onClick={() => setZoom(null)}>
            <figure>
              <img src={zoom.src} alt={zoom.caption} />
              <figcaption>{zoom.caption}</figcaption>
            </figure>
          </div>
        )}
      </div>
    </div>
  );
}
