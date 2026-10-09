/** CFD DOE + vekil model API — Faz 2.9 (`/cfd/ml`). */
import type { CfdSolver } from "./cfd";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const d = (payload as { detail?: unknown } | null)?.detail;
    throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : `HTTP ${response.status}`);
  }
  return payload as T;
}

const post = <T,>(path: string, body: unknown) =>
  req<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export interface CfdDoeSample {
  index: number;
  template_params: Record<string, number | string>;
  mach: number;
  alpha_deg: number;
  status: string;
  message?: string;
  cells?: number | null;
  job_id?: string;
  aero?: Record<string, number | null>;
}

export interface CfdDoe {
  doe_id: string;
  name?: string | null;
  status: "pending" | "running" | "done";
  message?: string;
  solver: CfdSolver;
  samples: CfdDoeSample[];
}

export interface CfdDoeInfo {
  doe_id: string;
  name?: string | null;
  status: string;
  message?: string;
  created_at: string;
  solver: CfdSolver;
  n_samples: number;
}

export interface CfdDoeBody {
  name?: string | null;
  template_params: Record<string, number | string>;
  ranges: Record<string, [number, number]>;
  n_samples: number;
  seed?: number;
  mach: number;
  alpha_deg: number;
  mesher: "snappy" | "cfmesh";
  tunnel: Record<string, number | boolean>;
  snappy: Record<string, number | null>;
  solve: Record<string, unknown>;
}

export const postCfdDoe = (body: CfdDoeBody) => post<CfdDoe>("/cfd/ml/doe", { ...body, wait: false });
export const fetchCfdDoe = (id: string) => req<CfdDoe>(`/cfd/ml/doe/${id}`);
export const fetchCfdDoes = () => req<{ does: CfdDoeInfo[] }>("/cfd/ml/doe").then((r) => r.does);

export interface CfdCorpusSummary {
  application: CfdSolver;
  doe_id: string | null;
  n_runs: number;
  features: string[];
  constant_features: Record<string, number>;
  targets: Record<string, number>;
  dropped: Record<string, number>;
}

export interface CfdModelInfo {
  application: CfdSolver;
  doe_id: string | null;
  n_runs: number;
  feature_keys: string[];
  constant_features: Record<string, number>;
  bounds: Record<string, [number, number]>;
  targets: { key: string; label: string; unit: string; trained: boolean; cv?: { n: number; r2?: number; mae?: number; mape?: number; skipped?: string; folds?: number } }[];
}

export const fetchCfdCorpus = (q: { application: CfdSolver; doe_id: string | null }) => post<CfdCorpusSummary>("/cfd/ml/corpus", q);
export const trainCfdModel = (q: { application: CfdSolver; doe_id: string | null }) => post<CfdModelInfo>("/cfd/ml/train", q);
export const fetchCfdModels = () => req<{ models: CfdModelInfo[] }>("/cfd/ml/models").then((r) => r.models);
export const predictCfd = (body: { application: CfdSolver; inputs: Record<string, number> }) =>
  post<{ prediction: Record<string, number | null>; out_of_domain: string[] }>("/cfd/ml/predict", body);
