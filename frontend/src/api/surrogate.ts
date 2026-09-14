/** Surrogate eğitim / tahmin API (0.5.6–0.5.9). */

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export class SurrogateApiError extends Error {}

export interface SurrogateStatus {
  scalar_rf: {
    n_samples?: number;
    metrics?: {
      train?: Record<string, { r2: number | null; mae: number; mape: number }>;
      test?: Record<string, { r2: number | null; mae: number; mape: number }>;
    };
  } | null;
  field_gnn: {
    n_samples?: number;
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
    if (body?.detail) return String(body.detail);
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

export async function trainScalarRf(): Promise<SurrogateStatus["scalar_rf"]> {
  const res = await fetch(`${API_BASE_URL}/surrogate/scalar/train`, { method: "POST" });
  if (!res.ok) throw new SurrogateApiError(await parseError(res, "Skaler eğitim başarısız"));
  return (await res.json()) as SurrogateStatus["scalar_rf"];
}

export async function trainFieldGnn(): Promise<SurrogateStatus["field_gnn"]> {
  const res = await fetch(`${API_BASE_URL}/surrogate/gnn/train`, { method: "POST" });
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
