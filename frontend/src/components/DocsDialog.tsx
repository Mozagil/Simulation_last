/**
 * "Belgeler" penceresi (navbar, kullanıcı isteği 2026-10-08): crash'teki her
 * özellik / düğme / kart — ne yapar, hangi senaryoda, OpenRadioss kartı ve
 * LS-DYNA karşılığı (≈, bilgi amaçlı). İçerik `docs/crashDoc.ts`.
 */
import { useEffect, useMemo, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CRASH_DOC, CRASH_SCENARIOS, type DocItem } from "../docs/crashDoc";
import { DYNA_EQUIV, dynaFor } from "../lib/dynaKeywords";
import { CRASH_TRAINING, TRAINING_RECORD } from "../docs/crashTraining";

const MAP_ID = "eslesme";
const SCEN_ID = "senaryolar";
const TRAIN_ID = "egitim";

function itemDyna(it: DocItem): string | null {
  return it.dyna ?? (it.card ? dynaFor(it.card) : null);
}

function matches(it: DocItem, q: string): boolean {
  if (!q) return true;
  const hay = [it.name, it.what, it.when, it.card, itemDyna(it)].filter(Boolean).join(" ").toLocaleLowerCase("tr");
  return hay.includes(q);
}

/** Arama süzgeci (boş q = tümü). */
function filterDocs(q: string) {
  const sections = CRASH_DOC.map((s) => ({ ...s, items: (s.items ?? []).filter((it) => matches(it, q)) })).filter(
    (s) => !q || s.items.length > 0 || s.title.toLocaleLowerCase("tr").includes(q),
  );
  const scenarios = CRASH_SCENARIOS.filter(
    (s) => !q || [s.title, s.setup, s.features.join(" "), s.template].join(" ").toLocaleLowerCase("tr").includes(q),
  );
  const mapRows = Object.entries(DYNA_EQUIV).filter(
    ([c, d]) => !q || c.toLocaleLowerCase("tr").includes(q) || d.toLocaleLowerCase("tr").includes(q),
  );
  return { sections, scenarios, mapRows };
}

/** Belge içeriği — pencerede ve PDF baskısında aynı bileşen. */
export function DocsContent({ q, onZoom }: { q: string; onZoom: (z: { src: string; caption: string }) => void }) {
  const { sections, scenarios, mapRows } = filterDocs(q);
  return (
    <>
    <p className="docs-note">
      LS-DYNA sütunu yaklaşık eşdeğer keyword adıdır (≈), yalnız bilgi amaçlı — bu projede LS-DYNA
      kullanılmaz. “Ne zaman” satırları tipik kullanımı anlatır; değer ve karar mühendisindir.
    </p>
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
                  <th>OpenRadioss</th>
                  <th>LS-DYNA ≈</th>
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
                    <td className="docs-dyna">{itemDyna(it) ?? "—"}</td>
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

    <section id={`doc-${SCEN_ID}`} className="docs-section">
      <h2>Hazır senaryolar (+ Yeni crash vakası)</h2>
      <p>Katalogdaki 15 örnek; her birinin kurulumu, kullandığı özellikler ve doğrulama ölçütü.</p>
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

    <section id={`doc-${TRAIN_ID}`} className="docs-section docs-training">
      <h2>Eğitim testleri (T1–T18)</h2>
      <p>
        Modele göre sıralı: her model grubun başında bir kez kurulur; ardından gelen her test bir öncekinden
        yalnız <b>tek şeyi</b> değiştirir. {TRAINING_RECORD}
      </p>
      {CRASH_TRAINING.filter((g) => !q || g.tests.some((t) => [t.id, t.title, t.learn, t.expect, ...t.steps].join(" ").toLocaleLowerCase("tr").includes(q))).map((g) => (
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
          {g.tests
            .filter((t) => !q || [t.id, t.title, t.learn, t.expect, ...t.steps].join(" ").toLocaleLowerCase("tr").includes(q))
            .map((t) => (
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
export function buildDocsPdfHtml(origin: string): string {
  const html = renderToStaticMarkup(<DocsContent q="" onZoom={() => undefined} />);
  const date = new Date().toLocaleDateString("tr-TR");
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<base href="${origin}/">
<title>SimSurrogate — Crash Belgeleri</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>${PRINT_CSS}</style></head><body>
<header class="cover"><h1>Crash (OpenRadioss) — Belgeler</h1>
<p>SimSurrogate · her özellik, düğme ve kart: ne yapar, hangi senaryoda, OpenRadioss kartı ve LS-DYNA karşılığı · ${date}</p></header>
<main class="docs-main">${html}</main></body></html>`;
}

/** Tüm belgeyi gizli bir çerçevede hazırlar ve tarayıcının yazdır penceresini
 * açar — "PDF olarak kaydet" ile indirilir. Açılır pencere engelinden etkilenmez. */
export function openDocsPdf(): boolean {
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
  w.document.write(buildDocsPdfHtml(window.location.origin));
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

  const { sections, scenarios } = useMemo(() => filterDocs(q), [q]);
  const [pdfBlocked, setPdfBlocked] = useState(false);

  const go = (id: string) => document.getElementById(`doc-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="docs-backdrop" role="presentation" onClick={onClose}>
      <div className="docs-dialog" role="dialog" aria-label="Belgeler" onClick={(e) => e.stopPropagation()}>
        <header className="docs-head">
          <div className="docs-head-title">
            <strong>Belgeler · Crash (OpenRadioss)</strong>
            <span>Her özellik, düğme ve kart: ne yapar, hangi senaryoda, OpenRadioss kartı ve LS-DYNA karşılığı.</span>
          </div>
          <input
            className="docs-search"
            type="search"
            placeholder="Ara: kızak, TYPE7, hourglass, *RIGIDWALL…"
            aria-label="Belgelerde ara"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            className="docs-pdf"
            title="Tüm belgeyi PDF olarak indir (yazdır penceresinde “PDF olarak kaydet”)"
            onClick={() => setPdfBlocked(!openDocsPdf())}
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
            <button type="button" onClick={() => go(SCEN_ID)}>
              Hazır senaryolar ({scenarios.length})
            </button>
            <button type="button" onClick={() => go(MAP_ID)}>
              OpenRadioss ↔ LS-DYNA tablosu
            </button>
            <button type="button" className="docs-nav-train" onClick={() => go(TRAIN_ID)}>
              Eğitim testleri (T1–T18)
            </button>
          </nav>
          <main className="docs-main">
            <DocsContent q={q} onZoom={setZoom} />
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
