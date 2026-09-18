/** Surrogate eğitim / tahmin API (0.5.6–0.5.9). */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class SurrogateApiError extends Error {}

export interface TrainingCorpusInfo {
  source?: string;
  name?: string;
  n_scanned?: number;
  n_kept?: number;
  template_id?: string | null;
  youngs_modulus?: number | null;
  poisson_ratio?: number | null;
  dropped?: Record<string, number>;
  flagged?: Record<string, number>;
}

/** Skaler model turu. "auto": log-log varsa o, yoksa RF. */
export type ScalarModelKind = "rf" | "loglinear";

export interface ScalarExponent {
  feature: string;
  exponent: number;
  /** false ise katsayi "us" diye okunamaz (sabit ya da esdogrusal sutun). */
  identifiable: boolean;
  reason: string | null;
}

export interface ScalarModelInfo {
  n_samples?: number;
  n_train?: number;
  n_test?: number;
  has_holdout?: boolean;
  corpus?: TrainingCorpusInfo | null;
  metrics?: {
    train?: Record<string, { r2: number | null; mae: number; mape: number }>;
    test?: Record<string, { r2: number | null; mae: number; mape: number }> | null;
  };
  exponents?: Record<string, ScalarExponent[]>;
  constant_features?: string[];
  collinear_features?: string[][];
}

export interface SurrogateStatus {
  scalar_rf: ScalarModelInfo | null;
  /** Log-log lineer model (0.6.3). Güç yasası hedeflerinde RF'ten çok daha
   * isabetli; ikisi birlikte tutulur, biri diğerini silmez. */
  scalar_loglinear: ScalarModelInfo | null;
  field_gnn: {
    n_samples?: number;
    corpus?: TrainingCorpusInfo | null;
    metrics?: {
      node_rmse?: Record<string, number>;
      scalar_rmse?: Record<string, number>;
      rmse_by_element_size?: Record<string, number>;
    };
  } | null;
}

export interface SurrogatePredictResult {
  kind: "field" | "scalar";
  source: string;
  out_of_domain: boolean;
  run_id: number;
  geometry_id: number;
  field_metrics: Record<string, number> | null;
  message: string;
  preview: {
    node_ids: number[];
    nodes: number[][];
    displacement_magnitude: number[];
    displacement_vectors: number[][];
    von_mises: number[];
    max_displacement: number;
    max_von_mises: number;
    critical_node_id: number | null;
    modes: unknown[];
    source?: string;
  };
}

async function parseError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && d.message) return String(d.message);
    if (d != null) return String(d);
  } catch {
    /* ignore */
  }
  return `${fallback} (HTTP ${res.status}).`;
}

export async function fetchSurrogateStatus(): Promise<SurrogateStatus> {
  const res = await fetch(`${API_BASE_URL}/surrogate/status`);
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Surrogate durumu alınamadı"));
  return (await res.json()) as SurrogateStatus;
}

function corpusQuery(corpusName?: string | null): string {
  return corpusName ? `?corpus_name=${encodeURIComponent(corpusName)}` : "";
}

export async function trainScalarRf(
  corpusName?: string | null,
  model: ScalarModelKind = "rf",
): Promise<(ScalarModelInfo & { model_kind?: ScalarModelKind }) | null> {
  const q = corpusQuery(corpusName);
  const url = `${API_BASE_URL}/surrogate/scalar/train${q ? `${q}&` : "?"}model=${model}`;
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Skaler eğitim başarısız"));
  return (await res.json()) as ScalarModelInfo & { model_kind?: ScalarModelKind };
}

export async function trainFieldGnn(
  corpusName?: string | null,
): Promise<SurrogateStatus["field_gnn"]> {
  const res = await fetch(`${API_BASE_URL}/surrogate/gnn/train${corpusQuery(corpusName)}`, {
    method: "POST",
  });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "GNN eğitimi başarısız"));
  return (await res.json()) as SurrogateStatus["field_gnn"];
}

export async function predictSurrogate(body: {
  runId?: number;
  geometryId?: number;
}): Promise<SurrogatePredictResult> {
  const res = await fetch(`${API_BASE_URL}/surrogate/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: body.runId, geometry_id: body.geometryId }),
  });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Tahmin başarısız"));
  return (await res.json()) as SurrogatePredictResult;
}

export interface ParamPredictRequest {
  length: number;
  thickness: number;
  width: number;
  element_size: number;
  youngs_modulus: number;
  poisson_ratio: number;
  load_fx: number;
  load_fy: number;
  load_fz: number;
  pressure_mpa: number;
  dimension: number;
  compare_run_id?: number;
  /** Akma kontrolü için — verilmezse kontrol atlanır. */
  material_id?: number;
}

export interface ParamPredictResult {
  kind: "scalar";
  /** Tahmini gerçekte hangi model üretti — araç sessizce model değiştirmez. */
  model_kind?: ScalarModelKind;
  source: string;
  out_of_domain: boolean;
  predictions: { max_displacement: number; max_von_mises: number };
  features: Record<string, number>;
  fea: {
    run_id: number;
    geometry_id: number;
    max_displacement: number;
    max_von_mises: number;
  } | null;
  deviation_pct: {
    max_displacement_pct: number | null;
    max_von_mises_pct: number | null;
  } | null;
  message: string;
  /** Hangi özellikler eğitim kutusu dışında — "uzay dışı" demek tek
   *  başına kullanıcıya neyi düzelteceğini söylemiyor. */
  domain_violations?: {
    feature: string;
    value: number;
    min: number;
    max: number;
    side: "below" | "above";
    factor: number | null;
  }[];
  /** Akma kontrolü. OOD'den AYRI: OOD istatistikseldir ("bu noktayı
   *  görmedim"), bu fizikseldir ("sonuç doğru hesaplansa bile malzeme
   *  plastik davranıyorsa geçersiz"). Biri diğerini yakalamaz. */
  yield_check?: {
    material: string;
    sigma_mpa: number;
    yield_mpa: number;
    limit_mpa: number;
    utilisation: number | null;
    exceeds_yield: boolean;
    exceeds_limit: boolean;
    source: string;
  } | null;

}

export interface CorpusMembership {
  name: string;
  frozen_at: string | null;
  auto: number[];
  manual_pass: number[];
  manual_override: number[];
}

export interface CorpusListItem {
  name: string;
  frozen_at: string | null;
  n_runs: number;
  template_id: string | null;
  n_manual: number;
}

export async function fetchCorpusList(): Promise<CorpusListItem[]> {
  const res = await fetch(`${API_BASE_URL}/surrogate/corpus`);
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Eğitim setleri alınamadı"));
  const body = (await res.json()) as { manifests?: CorpusListItem[] };
  return body.manifests ?? [];
}

export interface CorpusRunVerdict {
  run_id: number;
  ok: boolean;
  reason: string | null;
  u_over_L: number | null;
  mesh_ratio: number | null;
  mesh_deviation: number | null;
  template_id: string | null;
  youngs_modulus: number | null;
}

export interface CorpusAddResult {
  name: string;
  n_runs: number;
  added: number[];
  rejected: { run_id: number; reason: string | null }[];
  already_present: number[];
  verdicts: CorpusRunVerdict[];
}

export async function freezeCorpus(name: string): Promise<{ manifest: { run_ids: number[] } }> {
  const res = await fetch(
    `${API_BASE_URL}/surrogate/corpus/freeze?name=${encodeURIComponent(name)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Set dondurulamadı"));
  return (await res.json()) as { manifest: { run_ids: number[] } };
}

export async function evaluateForCorpus(
  name: string,
  runIds: number[],
): Promise<{ verdicts: CorpusRunVerdict[]; already_present: number[] }> {
  const res = await fetch(
    `${API_BASE_URL}/surrogate/corpus/${encodeURIComponent(name)}/evaluate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_ids: runIds }),
    },
  );
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Karne alınamadı"));
  return (await res.json()) as { verdicts: CorpusRunVerdict[]; already_present: number[] };
}

export async function addRunsToCorpus(
  name: string,
  runIds: number[],
  override = false,
): Promise<CorpusAddResult> {
  const res = await fetch(`${API_BASE_URL}/surrogate/corpus/${encodeURIComponent(name)}/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: runIds, override }),
  });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Sete eklenemedi"));
  return (await res.json()) as CorpusAddResult;
}

export async function fetchCorpusMembership(name: string): Promise<CorpusMembership> {
  const res = await fetch(`${API_BASE_URL}/surrogate/corpus/${encodeURIComponent(name)}/membership`);
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Set üyeliği alınamadı"));
  return (await res.json()) as CorpusMembership;
}

export async function predictFromParams(
  body: ParamPredictRequest,
  model: ScalarModelKind | "auto" = "auto",
): Promise<ParamPredictResult> {
  const res = await fetch(`${API_BASE_URL}/surrogate/predict/params?model=${model}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Parametre tahmini başarısız"));
  return (await res.json()) as ParamPredictResult;
}
