import { useEffect, useState } from "react";
import { fetchCrashCatalog, type CrashCatalogEntry } from "../api/crash";

/** K0 — explicit şablon kataloğu: sektör, örnek, durum, referans, doğrulama.
 * Salt veri; "hazır" olanlar Hızlı senaryo kartında koşulur. */

const SECTOR: Record<string, string> = {
  otomotiv: "Otomotiv",
  savunma: "Savunma",
  is_makineleri: "İş makineleri",
};

const STATUS: Record<CrashCatalogEntry["status"], string> = {
  ready: "hazır",
  planned: "planlı",
  major: "ayrı faz",
};

export default function CrashCatalog() {
  const [entries, setEntries] = useState<CrashCatalogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCrashCatalog()
      .then((c) => setEntries(c.entries))
      .catch((e) => setError(e instanceof Error ? e.message : "Katalog okunamadı."));
  }, []);

  const ready = entries?.filter((e) => e.status === "ready").length ?? 0;

  return (
    <details className="crash-mat-section crash-catalog" data-testid="crash-catalog">
      <summary>
        Explicit şablon kataloğu{entries ? ` · ${ready}/${entries.length} hazır` : ""}
      </summary>
      {error && <p className="material-assign-hint">{error}</p>}
      {entries && (
        <ul className="crash-catalog-list">
          {entries.map((e) => (
            <li key={e.id} className="crash-catalog-item" data-testid={`crash-catalog-${e.id}`}>
              <div className="crash-catalog-head">
                <span className="crash-catalog-title">{e.title}</span>
                <span className={`crash-catalog-status crash-catalog-${e.status}`}>{STATUS[e.status]}</span>
              </div>
              <span className="crash-run-meta">
                {SECTOR[e.sector] ?? e.sector} · {e.reference}
              </span>
              <span className="crash-run-meta">doğrulama: {e.validation}</span>
              {e.status !== "ready" && e.infrastructure && (
                <span className="crash-run-meta">
                  eksik: {e.infrastructure}
                  {e.step ? ` · ${e.step}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
