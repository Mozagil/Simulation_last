/**
 * "Belgeler" penceresi (navbar, kullanıcı isteği 2026-10-08): crash'teki her
 * özellik / düğme / kart — ne yapar, hangi senaryoda, OpenRadioss kartı ve
 * LS-DYNA karşılığı (≈, bilgi amaçlı). İçerik `docs/crashDoc.ts`.
 */
import { useEffect, useMemo, useState } from "react";
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

  const sections = useMemo(
    () =>
      CRASH_DOC.map((s) => ({ ...s, items: (s.items ?? []).filter((it) => matches(it, q)) })).filter(
        (s) => !q || s.items.length > 0 || s.title.toLocaleLowerCase("tr").includes(q),
      ),
    [q],
  );
  const scenarios = CRASH_SCENARIOS.filter(
    (s) => !q || [s.title, s.setup, s.features.join(" "), s.template].join(" ").toLocaleLowerCase("tr").includes(q),
  );
  const mapRows = Object.entries(DYNA_EQUIV).filter(
    ([c, d]) => !q || c.toLocaleLowerCase("tr").includes(q) || d.toLocaleLowerCase("tr").includes(q),
  );

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
                    <button type="button" className="docs-img-btn" onClick={() => setZoom({ src: s.image!, caption: s.imageCaption ?? "" })}>
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
                    <button type="button" className="docs-img-btn" onClick={() => setZoom(g)}>
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
