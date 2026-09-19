import { useCallback, useEffect, useRef, useState } from "react";
import {
  downloadDataset,
  fetchDatasetSummary,
  importDataset,
  type DatasetSummary,
} from "../api/dataset";
import { fetchCorpusList, type CorpusListItem } from "../api/surrogate";

/**
 * Veri seti paneli — birikmiş analiz verisinin görünürlüğü ve yedeklenmesi.
 *
 * NEDEN VAR: Analiz geçmişi Codespace'in Postgres volume'ünde, çözüm
 * dosyaları `uploads/` altında yaşıyor ve ikisi de `.gitignore`'da.
 * Codespace silinince ikisi de gidiyor — gerçekten yaşandı, tüm geçmiş
 * kayboldu. Export endpoint'i backend'de vardı ama düğmesi yoktu; görünür
 * olmayan bir yedekleme adımı unutulur.
 *
 * İkinci amaç: surrogate için binlerce run birikmesi gerekiyor. Kaç
 * çözülmüş run olduğunu görmeden DOE'nin ilerlediği takip edilemez.
 */
export default function DatasetPanel({
  refreshKey,
  selectedRunIds,
}: {
  refreshKey?: number;
  /** Geçmiş listesinde işaretli run'lar — varsa yalnız onlar indirilebilir. */
  selectedRunIds?: number[];
}) {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  // Donmuş eğitim setleri: temiz veriyi indirmenin tek yolu. "Yalnız
  // çözülmüş" süzgeci elle dışlananları ve süzgeçten düşenleri de alıyor.
  const [corpora, setCorpora] = useState<CorpusListItem[]>([]);
  const [corpus, setCorpus] = useState<string>("");
  const [busy, setBusy] = useState<"export" | "import" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Çözülmemiş run'ların sonuç dosyası yoktur; arşivi büyütmekten başka
  // işe yaramazlar. Varsayılan olarak dışarıda bırakılıyor.
  const [onlySolved, setOnlySolved] = useState(true);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void fetchCorpusList()
      .then((list) => {
        setCorpora(list);
        setCorpus((prev) => prev || (list.length ? list[list.length - 1].name : ""));
      })
      .catch(() => setCorpora([]));
  }, []);

  const reload = useCallback(() => {
    fetchDatasetSummary()
      .then(setSummary)
      .catch((e) => setError(e instanceof Error ? e.message : "Özet alınamadı."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  async function handleExport(runIds?: number[], corpusName?: string) {
    setBusy("export");
    setError(null);
    setMessage(null);
    try {
      await downloadDataset({ onlySolved, runIds, corpusName });
      setMessage(
        corpusName
          ? `"${corpusName}" eğitim seti indirildi (setin tanımı da arşivde).`
          : runIds?.length
            ? `${runIds.length} run indirildi.`
            : "Arşiv indirildi. Bu ortam dışında bir yerde saklayın.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dışa aktarma başarısız.");
    } finally {
      setBusy(null);
    }
  }

  async function handleImport(file: File) {
    setBusy("import");
    setError(null);
    setMessage(null);
    try {
      const r = await importDataset(file);
      const added = Object.entries(r.added)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join(", ");
      setMessage(added ? `İçe aktarıldı — ${added}` : "Arşivde yeni kayıt yoktu.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "İçe aktarma başarısız.");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const unsolved =
    summary != null ? summary.analysis_runs - summary.solved_runs : 0;

  return (
    <div className="panel dataset-panel">
      <span className="eyebrow">Faz 0.5 · Veri seti</span>
      <h1>Eğitim verisi</h1>
      <p className="lead">
        Analiz geçmişi ve çözüm dosyaları yalnız bu ortamda yaşar. Ortam
        silinirse veri de gider — düzenli olarak arşiv alın.
      </p>

      {summary === null ? (
        <p className="material-assign-hint">Yükleniyor…</p>
      ) : (
        <div className="dataset-stats">
          <div>
            <strong>{summary.solved_runs}</strong>
            <span>çözülmüş run</span>
          </div>
          <div>
            <strong>{summary.training_samples}</strong>
            <span>eğitim .npz</span>
          </div>
          <div>
            <strong>{summary.geometries}</strong>
            <span>geometri</span>
          </div>
          <div>
            <strong>{summary.materials}</strong>
            <span>malzeme</span>
          </div>
          {unsolved > 0 && (
            <div className="dataset-stat-muted">
              <strong>{unsolved}</strong>
              <span>çözülmemiş</span>
            </div>
          )}
        </div>
      )}

      {summary?.by_template && summary.by_template.length > 0 && (
        <>
          <p className="material-assignments-title">Şablona göre</p>
          <table className="dataset-template-table">
            <thead>
              <tr>
                <th>şablon</th>
                <th>çözülmüş</th>
                <th>toplam</th>
                <th>dışlanan</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_template.map((row) => (
                <tr key={row.template_id ?? "__none__"}>
                  <td>
                    {row.template_id ?? (
                      <span className="dataset-template-none">
                        şablonsuz (yüklenen geometri)
                      </span>
                    )}
                  </td>
                  <td className="dataset-template-num">{row.solved}</td>
                  <td className="dataset-template-num">{row.runs}</td>
                  <td className="dataset-template-num">
                    {row.excluded > 0 ? row.excluded : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="material-assign-hint">
            Her şablon ayrı bir model demektir — korpus tek şablondan
            eğitilir. Arşiv ise hepsini birlikte taşır.
          </p>
        </>
      )}

      <label className="dataset-filter">
        <input
          type="checkbox"
          checked={onlySolved}
          onChange={(e) => setOnlySolved(e.target.checked)}
        />
        Yalnız çözülmüş run'lar
      </label>

      {corpora.length > 0 && (
        <label className="mesh-field">
          <span>Eğitim seti</span>
          <select value={corpus} onChange={(e) => setCorpus(e.target.value)}>
            {corpora.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} · {c.n_runs} run
                {c.template_id ? ` · ${c.template_id}` : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="dataset-actions">
        <button
          type="button"
          className="material-assign-button"
          disabled={busy !== null}
          onClick={() => void handleExport()}
        >
          {busy === "export" ? "Hazırlanıyor…" : "Tümünü indir"}
        </button>
        {corpus && (
          <button
            type="button"
            className="material-assign-button"
            disabled={busy !== null}
            onClick={() => void handleExport(undefined, corpus)}
            title="Yalnız bu donmuş setin run'ları + setin tanımı"
          >
            Eğitim setini indir ({corpus})
          </button>
        )}
        {selectedRunIds && selectedRunIds.length > 0 && (
          <button
            type="button"
            className="material-secondary-button"
            disabled={busy !== null}
            onClick={() => void handleExport(selectedRunIds)}
          >
            Seçili {selectedRunIds.length} run
          </button>
        )}
        <button
          type="button"
          className="material-secondary-button"
          disabled={busy !== null}
          onClick={() => fileRef.current?.click()}
        >
          {busy === "import" ? "Aktarılıyor…" : "İçe aktar"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".tar.gz,.tgz"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleImport(f);
          }}
        />
      </div>

      <p className="material-assign-hint">
        Arşiv veritabanı satırlarını ve çözüm dosyalarını (.frd.gz, .train.npz)
        birlikte taşır. İçe aktarma hiçbir kaydı silmez, ekler — aynı arşivi
        iki kez almak kayıtları çoğaltır.
      </p>

      {message && <p className="dataset-message">{message}</p>}
      {error && <p className="dataset-error">{error}</p>}
    </div>
  );
}
