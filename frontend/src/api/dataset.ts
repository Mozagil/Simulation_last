/** Veri seti dışa/içe aktarma API istemcisi.
 *
 * Neden arayüzde: export endpoint'i backend'de vardı ama düğmesi yoktu,
 * yani kullanıcının hatırlayıp elle `curl` atması gerekiyordu. Bir Codespace
 * silinmesiyle tüm analiz geçmişi kaybedildi — arşiv alma adımı görünür
 * olmadığı sürece unutulur.
 *
 * İkinci ve daha önemli fayda GÖRÜNÜRLÜK: kaç eğitim örneği biriktiğini
 * görmeden DOE'nin ilerlediği takip edilemez.
 */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface DatasetSummary {
  geometries: number;
  materials: number;
  analysis_runs: number;
  solved_runs: number;
}

export interface DatasetImportResult {
  format_version: number;
  source_created_at: string | null;
  added: Record<string, number>;
}

export class DatasetError extends Error {}

export async function fetchDatasetSummary(): Promise<DatasetSummary> {
  const res = await fetch(`${API_BASE_URL}/dataset/summary`);
  if (!res.ok) {
    throw new DatasetError(`Veri seti özeti alınamadı (HTTP ${res.status}).`);
  }
  return (await res.json()) as DatasetSummary;
}

/** Arşivi indirir.
 *
 * `window.open` yerine blob indirmesi kullanılıyor: arşiv büyük olabilir ve
 * yeni sekme açmak indirmeyi bazı tarayıcılarda sessizce engelliyor.
 */
export interface ExportFilters {
  includeFiles?: boolean;
  /** Yalnız bu run'lar. Tek bir vakayı paylaşmak ya da alt küme ayırmak için. */
  runIds?: number[];
  /** Bir geometrinin tüm senaryoları. */
  geometryId?: number;
  /** Çözülmemiş run'ları dışarıda bırak — sonuç dosyaları yoktur. */
  onlySolved?: boolean;
}

export async function downloadDataset(filters: ExportFilters = {}): Promise<void> {
  const q = new URLSearchParams();
  q.set("include_files", filters.includeFiles === false ? "false" : "true");
  if (filters.runIds?.length) q.set("run_ids", filters.runIds.join(","));
  if (filters.geometryId != null) q.set("geometry_id", String(filters.geometryId));
  if (filters.onlySolved) q.set("only_solved", "true");

  const res = await fetch(`${API_BASE_URL}/dataset/export?${q.toString()}`);
  if (!res.ok) {
    throw new DatasetError(`Dışa aktarma başarısız (HTTP ${res.status}).`);
  }
  const blob = await res.blob();
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const tag = filters.runIds?.length
    ? "-secili"
    : filters.onlySolved
      ? "-cozulmus"
      : "";
  a.download = `dataset${tag}-${stamp}.tar.gz`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function importDataset(file: File): Promise<DatasetImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}/dataset/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = `İçe aktarma başarısız (HTTP ${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* gövde okunamadıysa varsayılan mesaj kalsın */
    }
    throw new DatasetError(detail);
  }
  return (await res.json()) as DatasetImportResult;
}
