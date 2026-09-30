/**
 * ML Stüdyo üst şeridi ve aşama çubuğu için canlı durum (ML Studio 1a).
 *
 * Tek bir hook: şablon listesi, DOE çalışmaları, korpuslar ve seçili
 * şablonun model durumu çekilir; aşama başına kısa bir satır üretilir.
 *   DOE      → en yeni çalışma: "#14 · 200 örnek" (çalışıyorsa belirtilir)
 *   Veri seti→ "412 run · 3 korpus"
 *   Yakınsama→ boş (backend'de liste ucu yok; tarama paneli kendi tutar)
 *   Model    → aktif model + test MAPE: "hybrid · σ %1.86"
 *   Tahmin   → son tahmin uzay içinde/dışında
 * Hiçbir şey hesaplanmaz, yalnız API çıktısı özetlenir. Çekim hatası
 * sessiz: satır boş kalır, stüdyo çalışmaya devam eder.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchDoeStudies, type DoeStudyInfo } from "../api/doe";
import {
  fetchCorpusList,
  fetchSurrogateStatus,
  type CorpusListItem,
  type ScalarModelInfo,
  type SurrogateStatus,
} from "../api/surrogate";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";
import type { MlStage } from "./MlStudioNav";

export interface MlStudioMetaInput {
  templateId: string | null;
  runCount: number;
  /** Son tahmin uzay dışı mı (null: henüz tahmin yok). */
  lastPredictionOod: boolean | null;
  /** Artınca çekimler yenilenir (run/korpus/model değişti). */
  refreshKey?: number;
}

export interface MlStudioStatusResult {
  /** Bilinen tüm şablonlar. */
  templates: GeometryTemplateInfo[];
  /** Veri ya da modeli olan şablon kimlikleri — üst şerit çipleri. */
  templatesWithData: string[];
  meta: Partial<Record<MlStage, string>>;
}

function mapeOf(info: ScalarModelInfo | null | undefined, key: string): number | null {
  const v = info?.metrics?.test?.[key]?.mape;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Saf: durumlardan aşama satırları. Test edilebilir, hook'tan bağımsız. */
export function buildStageMeta(
  input: MlStudioMetaInput,
  studies: DoeStudyInfo[],
  corpora: CorpusListItem[],
  status: SurrogateStatus | null,
): Partial<Record<MlStage, string>> {
  const meta: Partial<Record<MlStage, string>> = {};
  const tid = input.templateId;

  const study = studies.find((s) => !tid || s.template_id === tid);
  if (study) {
    const running = study.status === "running" || study.status === "pending";
    meta.doe = `#${study.id} · ${study.n_cases} örnek${running ? " · çalışıyor" : ""}`;
  } else if (tid) {
    meta.doe = "çalışma yok";
  }

  const nCorpus = corpora.filter((c) => !tid || c.template_id === tid).length;
  meta.data = `${input.runCount} run · ${nCorpus} korpus`;

  if (status) {
    const pick: [string, ScalarModelInfo | null][] = [
      ["hybrid", status.scalar_hybrid],
      ["loglinear", status.scalar_loglinear],
      ["RF", status.scalar_rf],
    ];
    const found = pick.find(([, info]) => info != null);
    if (found) {
      const s = mapeOf(found[1], "max_von_mises");
      const u = mapeOf(found[1], "max_displacement");
      const part = s != null ? `σ %${(s * 100).toFixed(2)}` : u != null ? `u %${(u * 100).toFixed(2)}` : "eğitildi";
      meta.model = `${found[0]} · ${part}`;
    } else if (tid) {
      meta.model = "model yok";
    }
  }

  if (input.lastPredictionOod != null) {
    meta.pred = input.lastPredictionOod ? "son tahmin uzay dışı" : "son tahmin uzay içinde";
  }
  return meta;
}

export function useMlStudioStatus(input: MlStudioMetaInput): MlStudioStatusResult {
  const [templates, setTemplates] = useState<GeometryTemplateInfo[]>([]);
  const [studies, setStudies] = useState<DoeStudyInfo[]>([]);
  const [corpora, setCorpora] = useState<CorpusListItem[]>([]);
  const [status, setStatus] = useState<SurrogateStatus | null>(null);
  const { templateId, refreshKey } = input;

  useEffect(() => {
    let cancelled = false;
    fetchTemplates()
      .then((l) => {
        if (!cancelled) setTemplates(l);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchDoeStudies()
      .then((l) => {
        if (!cancelled) setStudies(l);
      })
      .catch(() => undefined);
    fetchCorpusList()
      .then((l) => {
        if (!cancelled) setCorpora(l);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    let cancelled = false;
    setStatus(null);
    fetchSurrogateStatus(templateId)
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [templateId, refreshKey]);

  const templatesWithData = useMemo(() => {
    const ids = new Set<string>();
    for (const s of studies) ids.add(s.template_id);
    for (const c of corpora) if (c.template_id) ids.add(c.template_id);
    for (const k of Object.keys(status?.templates ?? {})) ids.add(k);
    return templates.map((t) => t.id).filter((id) => ids.has(id));
  }, [studies, corpora, status, templates]);

  const meta = useMemo(
    () => buildStageMeta(input, studies, corpora, status),
    // input nesnesi her render'da yeni; alanları üzerinden bağımlılık.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [input.templateId, input.runCount, input.lastPredictionOod, studies, corpora, status],
  );

  return { templates, templatesWithData, meta };
}
