/** 1.21e-2d — LS-DYNA keyword (.k / .dyn) içe aktarma penceresi (kullanıcı kararı 2026-10-12).
 *
 * Akış: dosyalar + birim çarpanları (mühendisten; tahmin yok) → çeviri raporu (dikkat edilecekler
 * üstte: uyarılar, atlanan keyword / satırlar, malzemesiz parçalar) + 3B önizleme → "Raporu okudum"
 * → koşu (`/crash/import/dyna/{id}/solve`) + canlı ilerleme. Kaynak keyword adları yalnız veri
 * (≈ karşılık; LS-DYNA kurulmaz / çalıştırılmaz, keyword yazılmaz — docs/LICENSING.md).
 */

import { useEffect, useRef, useState } from "react";

import {
  fetchCrashJob,
  fetchDynaImportPreview,
  postDynaImport,
  postDynaImportSolve,
  type DynaImportPreview,
  type DynaImportReport,
  type DynaImportSolveResponse,
} from "../api/crash";
import { useBackdropClose } from "../lib/useBackdropClose";
import CrashImportPreview from "./CrashImportPreview";
import CrashLiveProgress, { livePhase, type LiveValues } from "./CrashLiveProgress";

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

/** Raporda mühendisin önce görmesi gerekenler (uyarı, atlanan, malzemesiz). */
export function attentionItems(r: DynaImportReport): string[] {
  const out: string[] = [];
  for (const w of r.parse.warnings ?? []) out.push(`Okuma: ${w}`);
  for (const [kw, n] of Object.entries(r.parse.skipped ?? {})) out.push(`Atlanan keyword *${kw} × ${n} (çevrilmez)`);
  for (const w of r.mesh.warnings ?? []) out.push(`Ağ: ${w}`);
  for (const pid of r.materials.unassigned ?? []) out.push(`PID ${pid}: malzemesi çevrilmedi`);
  for (const w of r.materials.warnings ?? []) out.push(`Malzeme: ${w}`);
  for (const row of r.setup.rows) if (row.status !== "çevrildi") out.push(`Kurulum ${row.where}: ${row.source} ${row.status} — ${row.detail}`);
  for (const w of r.setup.warnings ?? []) out.push(`Kurulum: ${w}`);
  return out;
}

/** Dosyadaki bitiş süresi (dosya zaman birimi) → ms; yoksa null. */
export function fileEndTimeMs(r: DynaImportReport): number | null {
  const t = r.parse.end_time;
  return t != null && t > 0 ? Number((t * r.units.time_to_s * 1000).toPrecision(6)) : null;
}

export default function CrashImportDialog({ onClose, onRunStarted }: { onClose: () => void; onRunStarted?: () => void }) {
  const backdrop = useBackdropClose(onClose);
  // Üst bileşen her çizimde yeni fonksiyon verebilir — yoklama efekti ona bağlanmaz.
  const onRunRef = useRef(onRunStarted);
  onRunRef.current = onRunStarted;
  const [main, setMain] = useState<File | null>(null);
  const [includes, setIncludes] = useState<File[]>([]);
  const [units, setUnits] = useState({ lengthToMm: "", massToKg: "", timeToS: "" });
  const [rates, setRates] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<DynaImportReport | null>(null);
  const [preview, setPreview] = useState<DynaImportPreview | null>(null);
  const [ack, setAck] = useState(false);
  const [name, setName] = useState("");
  const [tEnd, setTEnd] = useState("");
  const [job, setJob] = useState<DynaImportSolveResponse | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [live, setLive] = useState<LiveValues | null>(null);

  const unitsOk = Object.values(units).every((v) => Number(v.replace(",", ".")) > 0);

  async function translate() {
    if (!main) return;
    setBusy(true);
    setError(null);
    setReport(null);
    setPreview(null);
    setAck(false);
    setJob(null);
    try {
      const r = await postDynaImport({ main, includes, ...units, rates });
      setReport(r);
      const te = fileEndTimeMs(r);
      setTEnd(te != null ? String(te) : "");
      setName(`İçe aktarma · ${r.file}`);
      setPreview(await fetchDynaImportPreview(r.import_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "İçe aktarma başarısız.");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!report) return;
    setBusy(true);
    setError(null);
    try {
      const t = Number(tEnd.replace(",", "."));
      const res = await postDynaImportSolve(report.import_id, { name: name.trim() || undefined, ...(t > 0 ? { t_end_ms: t } : {}) });
      setJob(res);
      setJobStatus(res.status);
      setLive(null);
      onRunStarted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Koşu başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  // Koşu sürerken iş anlık görüntüsü (1,5 s); son canlı değerler kalır (1.25a).
  useEffect(() => {
    if (!job || (jobStatus && TERMINAL.has(jobStatus))) return;
    let cancelled = false;
    const tick = () =>
      fetchCrashJob(job.job_id)
        .then((s) => {
          if (cancelled) return;
          setJobStatus(s.status ?? null);
          if (s.status && TERMINAL.has(s.status)) onRunRef.current?.();
          else if (s.cycle != null) {
            const { cycle, time_ms, dt_ms, percent, mass_added_rel, elapsed_s, remaining_s } = s;
            setLive({ cycle, time_ms, dt_ms, percent, mass_added_rel, elapsed_s, remaining_s });
          }
        })
        .catch(() => undefined);
    tick();
    const id = window.setInterval(tick, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [job, jobStatus]);

  const attention = report ? attentionItems(report) : [];
  const running = job != null && !(jobStatus && TERMINAL.has(jobStatus));

  return (
    <div className="crash-newcase-backdrop" role="presentation" {...backdrop}>
      <div className="crash-newcase-dialog crash-import-dialog" role="dialog" aria-label="LS-DYNA içe aktar" onClick={(e) => e.stopPropagation()}>
        <div className="crash-newcase-head">
          <strong>LS-DYNA içe aktar (.k / .dyn)</strong>
          <span className="crash-behavior-hint">
            Kendi çeviricimiz okur → OpenRadioss kartları. LS-DYNA kurulmaz / çalıştırılmaz, keyword yazılmaz.
          </span>
          <button type="button" className="crash-doe-x" aria-label="Kapat" onClick={onClose}>
            ×
          </button>
        </div>

        <section className="crash-import-form" aria-label="Dosyalar ve birimler">
          <label className="crash-expert-field">
            <span>Ana dosya (.k / .key / .dyn)</span>
            <input aria-label="Ana dosya" type="file" accept=".k,.key,.dyn" disabled={busy} onChange={(e) => setMain(e.target.files?.[0] ?? null)} />
          </label>
          <label className="crash-expert-field">
            <span>*INCLUDE dosyaları (varsa)</span>
            <input aria-label="INCLUDE dosyaları" type="file" multiple disabled={busy} onChange={(e) => setIncludes([...(e.target.files ?? [])])} />
          </label>
          <p className="crash-behavior-hint">
            Birim çarpanları dosyanın birim sisteminden (ör. m → mm için 1000; mm-ton-s'de kütle 1000, zaman 1). Boş
            bırakılırsa çevrilmez — tahmin edilmez.
          </p>
          <div className="crash-expert-grid cols-3">
            {(
              [
                ["lengthToMm", "Uzunluk → mm"],
                ["massToKg", "Kütle → kg"],
                ["timeToS", "Zaman → s"],
              ] as const
            ).map(([k, lab]) => (
              <label key={k} className="crash-expert-field">
                <span>{lab}</span>
                <input aria-label={lab} value={units[k]} placeholder="ör. 1" disabled={busy} onChange={(e) => setUnits({ ...units, [k]: e.target.value })} />
              </label>
            ))}
          </div>
          <label className="crash-expert-field">
            <span>Hız etkisi için ε̇ listesi (1/s, virgüllü; boş = yok)</span>
            <input aria-label="ε̇ listesi" value={rates} placeholder="ör. 10, 100, 1000" disabled={busy} onChange={(e) => setRates(e.target.value)} />
          </label>
          <button type="button" className="material-assign-button" disabled={busy || !main || !unitsOk} onClick={() => void translate()}>
            {busy && !report ? "Çevriliyor…" : "Çevir"}
          </button>
        </section>

        {error && <p className="dataset-error" role="alert">{error}</p>}

        {report && (
          <section className="crash-import-report" aria-label="Çeviri raporu" data-testid="crash-import-report">
            <p className="crash-expert-title">
              Çeviri raporu · {report.file} · {report.parse.nodes} düğüm · {report.mesh.shells + report.mesh.sh3n} kabuk ·{" "}
              {report.mesh.tets + report.mesh.bricks} katı · {report.mesh.parts.length} parça
            </p>
            <div className={attention.length ? "crash-import-attention warn" : "crash-import-attention"} data-testid="crash-import-attention">
              <strong>{attention.length ? `Dikkat · ${attention.length}` : "Dikkat · uyarı / atlanan yok"}</strong>
              {attention.length > 0 && (
                <ul>
                  {attention.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="crash-import-grid">
              <div>
                <table className="doe-table crash-import-table" aria-label="Parçalar">
                  <thead>
                    <tr>
                      <th>PID</th>
                      <th>ad</th>
                      <th>tür</th>
                      <th>t (mm)</th>
                      <th>eleman</th>
                      <th>malzeme</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.mesh.parts.map((p) => {
                      const m = report.materials.parts.find((x) => x.pid === p.pid);
                      return (
                        <tr key={p.pid}>
                          <td>{p.pid}</td>
                          <td>{p.title || "—"}</td>
                          <td>{p.kind === "shell" ? "kabuk" : "katı"}</td>
                          <td>{p.thickness_mm ?? "—"}</td>
                          <td>{p.elements}</td>
                          <td title={m?.note}>{m ? `≈ *${m.keyword} → ${m.law}` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <table className="doe-table crash-import-table" aria-label="Kurulum satırları">
                  <thead>
                    <tr>
                      <th>kaynak (≈)</th>
                      <th>satır</th>
                      <th>hedef</th>
                      <th>durum</th>
                      <th>ayrıntı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.setup.rows.map((r, i) => (
                      <tr key={i} className={r.status !== "çevrildi" ? "doe-table-row-flagged" : undefined}>
                        <td>*{r.source.replace(/^\*/, "")}</td>
                        <td>{r.where}</td>
                        <td>{r.target ?? "—"}</td>
                        <td>{r.status}</td>
                        <td>{r.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview && <CrashImportPreview preview={preview} />}
            </div>

            <label className="material-check">
              <input type="checkbox" checked={ack} disabled={busy || running} onChange={(e) => setAck(e.target.checked)} />
              Raporu okudum (uyarılar ve atlananlar dahil); çevrilmeyen satırlar koşuda yok.
            </label>
            {ack && (
              <div className="crash-import-run" data-testid="crash-import-run">
                <div className="crash-expert-grid cols-2">
                  <label className="crash-expert-field">
                    <span>Koşu adı</span>
                    <input aria-label="Koşu adı" value={name} disabled={busy || running} onChange={(e) => setName(e.target.value)} />
                  </label>
                  <label className="crash-expert-field">
                    <span>Süre (ms){fileEndTimeMs(report) != null ? " · dosyadan" : " · dosyada yok"}</span>
                    <input aria-label="Süre (ms)" value={tEnd} placeholder="zorunlu" disabled={busy || running} onChange={(e) => setTEnd(e.target.value)} />
                  </label>
                </div>
                <button
                  type="button"
                  className="material-assign-button"
                  disabled={busy || running || !(Number(tEnd.replace(",", ".")) > 0)}
                  onClick={() => void run()}
                >
                  OpenRadioss çalıştır
                </button>
              </div>
            )}
            {job && (
              <div className="crash-import-job">
                <p className="material-assign-hint">
                  Koşu #{job.run_id ?? "—"} · {jobStatus} — geçmişte "içe aktarma (.k)" etiketiyle; deforme şekil ▶ ile.
                </p>
                <CrashLiveProgress
                  key={job.job_id}
                  phase={livePhase(jobStatus, running, live?.cycle)}
                  values={live}
                  tEndMs={Number(tEnd.replace(",", ".")) || null}
                />
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
