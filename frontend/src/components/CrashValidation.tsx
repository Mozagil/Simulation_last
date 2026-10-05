import { useEffect, useState } from "react";
import {
  fetchCrashValidation,
  fetchValidationThresholds,
  putValidationThresholds,
  type CrashValidationCase,
  type CrashValidationReport,
  type CrashValidationRun,
  type CrashValidationThreshold,
  type CrashValidationThresholds,
} from "../api/crash";

/** Crash validasyon raporu (1.17f, 1.18e): analitik / literatür referanslarına
 * göre oranlar. Eşikleri mühendis girer; araç yalnız eşiğe göre işaretler. */

/** [alan, erişilebilir ad, kısa sütun başlığı] */
const THR_KEYS: [keyof CrashValidationThreshold, string, string][] = [
  ["ratio_min", "oran min", "oran ≥"],
  ["ratio_max", "oran maks", "oran ≤"],
  ["energy_balance_max", "denge maks", "denge ≤"],
  ["hourglass_max", "HG/IE maks", "HG ≤"],
];

const EMPTY_THR: CrashValidationThreshold = {
  ratio_min: null,
  ratio_max: null,
  energy_balance_max: null,
  hourglass_max: null,
};

/** Vaka eşiği: vaka kaydındaki dolu alan varsayılanı ezer, boş alan varsayılana düşer. */
export function effectiveThreshold(t: CrashValidationThresholds | null, id: string): CrashValidationThreshold {
  const d = t?.default ?? EMPTY_THR;
  const c = t?.cases[id];
  return {
    ratio_min: c?.ratio_min ?? d.ratio_min ?? null,
    ratio_max: c?.ratio_max ?? d.ratio_max ?? null,
    energy_balance_max: c?.energy_balance_max ?? d.energy_balance_max ?? null,
    hourglass_max: c?.hourglass_max ?? d.hourglass_max ?? null,
  };
}

/** Oranın eşiğe göre yönü: "low" / "high" / "in"; eşik ya da oran yoksa null. */
export function ratioMark(v: number | null | undefined, th: CrashValidationThreshold): "low" | "high" | "in" | null {
  if (v == null || Number.isNaN(v) || (th.ratio_min == null && th.ratio_max == null)) return null;
  if (th.ratio_min != null && v < th.ratio_min) return "low";
  if (th.ratio_max != null && v > th.ratio_max) return "high";
  return "in";
}

/** Vaka eşik sonucu: kontrol edilen ölçüt var mı, dışında kalanlar (veri). */
export function caseThresholdResult(
  c: CrashValidationCase,
  th: CrashValidationThreshold,
): { checked: boolean; out: string[] } {
  const sm = caseSummary(c);
  const ratios = c.rows ? c.rows.map((r) => r.ratio) : (c.mesh ?? []).flatMap((m) => [m.ratio_wa, m.ratio_aj]);
  const marks = ratios.map((v) => ratioMark(v, th)).filter((m) => m != null);
  const out: string[] = [];
  const nOut = marks.filter((m) => m !== "in").length;
  if (nOut) out.push(`oran ${nOut}`);
  let checked = marks.length > 0;
  if (th.energy_balance_max != null && sm.energy_balance_rel != null) {
    checked = true;
    if (sm.energy_balance_rel > th.energy_balance_max) out.push("denge");
  }
  if (th.hourglass_max != null && sm.hourglass_ratio != null) {
    checked = true;
    if (sm.hourglass_ratio > th.hourglass_max) out.push("HG");
  }
  return { checked, out };
}

function MarkCell({ v, th }: { v: number | null | undefined; th: CrashValidationThreshold }) {
  const m = ratioMark(v, th);
  const cls = m == null ? "" : m === "in" ? " crash-thr-in" : " crash-thr-out";
  const title =
    m == null ? undefined : `eşik ${th.ratio_min ?? "—"} – ${th.ratio_max ?? "—"}: ${m === "in" ? "içinde" : "dışında"}`;
  return (
    <td className={`crash-run-num${cls}`} title={title}>
      {fr(v)}
      {m === "low" ? " ↓" : m === "high" ? " ↑" : ""}
    </td>
  );
}

function LimitText({ v, max, label }: { v: number | null | undefined; max: number | null; label: string }) {
  if (max == null || v == null) {
    return (
      <>
        {label} {fr(v)}
      </>
    );
  }
  return (
    <span className={v > max ? "crash-thr-out" : "crash-thr-in"} title={`eşik ≤ ${max}`}>
      {label} {fr(v)} (≤ {max})
    </span>
  );
}

function parseThr(v: string): number | null {
  const t = v.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) throw new Error(`Geçersiz eşik: "${v}"`);
  return n;
}

function ThresholdEditor({
  cases,
  value,
  onSaved,
}: {
  cases: CrashValidationCase[];
  value: CrashValidationThresholds | null;
  onSaved: (t: CrashValidationThresholds) => void;
}) {
  const ids = ["default", ...cases.map((c) => c.id)];
  const [text, setText] = useState<Record<string, Record<string, string>>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const toText = (t: CrashValidationThreshold | undefined) =>
      Object.fromEntries(THR_KEYS.map(([k]) => [k, t?.[k] != null ? String(t[k]) : ""]));
    setText(
      Object.fromEntries(
        ["default", ...cases.map((c) => c.id)].map((id) => [
          id,
          toText(id === "default" ? value?.default : value?.cases[id]),
        ]),
      ),
    );
  }, [value, cases]);

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const parse = (id: string): CrashValidationThreshold => ({
        ratio_min: parseThr(text[id]?.ratio_min ?? ""),
        ratio_max: parseThr(text[id]?.ratio_max ?? ""),
        energy_balance_max: parseThr(text[id]?.energy_balance_max ?? ""),
        hourglass_max: parseThr(text[id]?.hourglass_max ?? ""),
      });
      const body: CrashValidationThresholds = {
        default: parse("default"),
        cases: Object.fromEntries(cases.map((c) => [c.id, parse(c.id)])),
      };
      const saved = await putValidationThresholds(body);
      onSaved(saved);
      setMsg(`kaydedildi · ${(saved.updated_at ?? "").slice(0, 16).replace("T", " ")}`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Eşikler kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="crash-thr-editor" data-testid="crash-validation-thresholds">
      <summary>Kabul eşikleri (mühendis){value?.updated_at ? ` · ${value.updated_at.slice(0, 10)}` : ""}</summary>
      <p className="crash-run-meta">
        Boş = kontrol yok. Vaka satırındaki boş alan varsayılanı kullanır. Oran ve denge kesir (0.05 = %5).
      </p>
      <div className="crash-history-scroll">
        <table className="doe-table crash-compare-table">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>vaka</th>
              {THR_KEYS.map(([k, l, h]) => (
                <th key={k} title={l}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => (
              <tr key={id}>
                <td style={{ textAlign: "left" }}>{id === "default" ? "varsayılan" : id}</td>
                {THR_KEYS.map(([k, l]) => (
                  <td key={k}>
                    <input
                      className="crash-thr-input"
                      aria-label={`${id} ${l}`}
                      value={text[id]?.[k] ?? ""}
                      disabled={busy}
                      onChange={(e) => setText((t) => ({ ...t, [id]: { ...t[id], [k]: e.target.value } }))}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="material-assign-button" disabled={busy} onClick={() => void save()}>
        {busy ? "Kaydediliyor…" : "Eşikleri kaydet"}
      </button>
      {msg && <p className="crash-run-meta">{msg}</p>}
    </details>
  );
}

function fmt(v: number | null | undefined, digits = 3): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(digits);
  if (Math.abs(v) >= 1e-3) return v.toFixed(4);
  return v.toExponential(2);
}

/** Oran / kesir: sabit 3 hane (0.978), üstel gösterim yok. */
function fr(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "—" : v.toFixed(3);
}

/** Vaka özeti: referanslı satırların oran aralığı + en kötü koşu dengesi / HG (veri). */
export function caseSummary(c: CrashValidationCase): {
  n_runs: number;
  ratio_min: number | null;
  ratio_max: number | null;
  energy_balance_rel: number | null;
  hourglass_ratio: number | null;
} {
  const ratios = c.rows
    ? c.rows.map((r) => r.ratio)
    : (c.mesh ?? []).flatMap((m) => [m.ratio_wa, m.ratio_aj]);
  const rs = ratios.filter((v): v is number => v != null && !Number.isNaN(v));
  const quality: { energy_balance_rel?: number | null; hourglass_ratio?: number | null }[] =
    c.runs ?? c.mesh ?? [c];
  const worst = (k: "energy_balance_rel" | "hourglass_ratio") => {
    const vs = quality.map((q) => q[k]).filter((v): v is number => v != null && !Number.isNaN(v));
    return vs.length ? Math.max(...vs) : null;
  };
  return {
    n_runs: c.runs?.length ?? c.mesh?.length ?? (c.run_id != null ? 1 : 0),
    ratio_min: rs.length ? Math.min(...rs) : null,
    ratio_max: rs.length ? Math.max(...rs) : null,
    energy_balance_rel: worst("energy_balance_rel"),
    hourglass_ratio: worst("hourglass_ratio"),
  };
}

function runSetting(r: CrashValidationRun): string {
  const parts = [
    r.orientation,
    r.element_mm != null && !r.orientation?.includes(`${r.element_mm} mm`) ? `${r.element_mm} mm` : undefined,
    r.v0_m_s != null ? `${fmt(r.v0_m_s)} m/s` : undefined,
    r.control ? "kontrol" : undefined,
  ];
  return parts.filter(Boolean).join(" · ") || "—";
}

function RunsTable({ c }: { c: CrashValidationCase }) {
  if (!c.runs?.length) return null;
  return (
    <div className="crash-history-scroll">
      <table className="doe-table crash-compare-table" data-testid={`crash-validation-runs-${c.id}`}>
        <thead>
          <tr>
            <th>koşu</th>
            <th style={{ textAlign: "left" }}>ayar</th>
            <th title="enerji dengesi farkı">denge</th>
            <th>HG/IE</th>
            <th>F kN</th>
            <th>s</th>
          </tr>
        </thead>
        <tbody>
          {c.runs.map((r) => (
            <tr key={r.run_id}>
              <td>#{r.run_id}</td>
              <td style={{ textAlign: "left", whiteSpace: "normal" }}>{runSetting(r)}</td>
              <td className="crash-run-num">{fr(r.energy_balance_rel)}</td>
              <td className="crash-run-num">{fr(r.hourglass_ratio)}</td>
              <td className="crash-run-num">{fmt(r.force_max_kn ?? r.f_peak_kn ?? r.f_max_kn)}</td>
              <td className="crash-run-num">{fmt(r.wall_s, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryTable({ cases, thr }: { cases: CrashValidationCase[]; thr: CrashValidationThresholds | null }) {
  return (
    <div className="crash-history-scroll">
      <table className="doe-table crash-compare-table" data-testid="crash-validation-summary">
        <thead>
          <tr>
            <th>vaka</th>
            <th>koşu</th>
            <th>oran</th>
            <th title="vakanın koşuları içinde en büyük enerji dengesi farkı">denge</th>
            <th title="vakanın koşuları içinde en büyük hourglass / iç enerji">HG/IE</th>
            <th title="mühendis eşiğine göre; — = eşik yok">eşik</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const sm = caseSummary(c);
            const res = caseThresholdResult(c, effectiveThreshold(thr, c.id));
            return (
              <tr key={c.id}>
                <td title={c.title}>
                  <a href={`#crash-validation-${c.id}`}>{c.id}</a>
                  <span className="crash-run-meta">{c.title.split(" (")[0]}</span>
                </td>
                <td className="crash-run-num">{sm.n_runs || "—"}</td>
                <td className="crash-run-num">
                  {sm.ratio_min == null ? "—" : `${fr(sm.ratio_min)} – ${fr(sm.ratio_max)}`}
                </td>
                <td className="crash-run-num">{fr(sm.energy_balance_rel)}</td>
                <td className="crash-run-num">{fr(sm.hourglass_ratio)}</td>
                <td
                  className={res.checked ? (res.out.length ? "crash-thr-out" : "crash-thr-in") : undefined}
                  style={{ whiteSpace: "normal" }}
                  data-testid={`crash-validation-thr-${c.id}`}
                >
                  {!res.checked ? "—" : res.out.length ? "dışında" : "içinde"}
                  {res.out.length > 0 && <span className="crash-run-meta">{res.out.join(", ")}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function CrashValidation() {
  const [report, setReport] = useState<CrashValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [thr, setThr] = useState<CrashValidationThresholds | null>(null);

  useEffect(() => {
    fetchCrashValidation()
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : "Rapor okunamadı."));
    fetchValidationThresholds()
      .then(setThr)
      .catch(() => undefined);
  }, []);

  return (
    <details className="crash-mat-section crash-validation" data-testid="crash-validation">
      <summary>Validasyon{report ? ` · ${(report.updated_at ?? report.generated_at).slice(0, 10)}` : ""}</summary>
      {error && <p className="material-assign-hint">{error}</p>}
      {report && (
        <>
          <p className="material-assign-hint">
            {report.setup.template} {report.setup.L_mm}×{report.setup.h_mm}×{report.setup.b_mm} mm, t{" "}
            {report.setup.t_mm} · {report.setup.material} · v0 {report.setup.v0_m_s} m/s. {report.setup.note}
          </p>
          <p className="crash-validation-title">Özet · {report.cases.length} vaka</p>
          <p className="crash-run-meta">
            Oran: referanslı satırların en küçük – en büyük değeri; denge ve HG/IE vakanın koşuları içinde en büyüğü. Eşik
            sütunu yalnız aşağıda mühendisin girdiği eşiklere göre (girilmemişse —).
          </p>
          <SummaryTable cases={report.cases} thr={thr} />
          <ThresholdEditor cases={report.cases} value={thr} onSaved={setThr} />
          {report.cases.map((c) => {
            const th = effectiveThreshold(thr, c.id);
            return c.rows ? (
              <div key={c.id} id={`crash-validation-${c.id}`} className="crash-validation-case">
                <p className="crash-validation-title">
                  {c.id} · {c.title} {c.run_id != null && <span className="crash-run-meta">koşu #{c.run_id}</span>}
                </p>
                {c.references?.formula && <p className="crash-run-meta">{c.references.formula}</p>}
                {c.fit && (
                  <p className="crash-run-meta" data-testid={`crash-validation-fit-${c.id}`}>
                    v_bl {fmt(c.fit.v_bl_m_s)} m/s · a {fr(c.fit.a)} · R² {fr(c.fit.r2)} · tarama aralığı{" "}
                    {c.fit.bracket_low_m_s ?? "—"}–{c.fit.bracket_high_m_s ?? "—"} m/s (
                    {c.fit.v_bl_in_bracket ? "v_bl aralıkta" : "v_bl aralık dışında"})
                  </p>
                )}
                <div className="crash-history-scroll">
                  <table className="doe-table crash-compare-table">
                    <thead>
                      <tr>
                        <th>büyüklük</th>
                        <th>sim</th>
                        <th>referans</th>
                        <th>oran</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.rows.map((r) => (
                        <tr key={r.quantity}>
                          <td>
                            {r.quantity}
                            <span className="crash-run-meta">{r.ref_label}</span>
                            {r.alt_label && (
                              <span className="crash-run-meta">
                                {r.alt_label}: {fmt(r.alt_ref)}
                              </span>
                            )}
                          </td>
                          <td className="crash-run-num">{fmt(r.sim)}</td>
                          <td className="crash-run-num">{fmt(r.ref)}</td>
                          <MarkCell v={r.ratio} th={th} />
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <RunsTable c={c} />
                {c.energy_balance_rel != null && (
                  <p className="crash-run-meta">
                    <LimitText v={c.energy_balance_rel} max={th.energy_balance_max} label="enerji dengesi" /> ·{" "}
                    <LimitText v={c.hourglass_ratio} max={th.hourglass_max} label="hourglass/IE" />
                  </p>
                )}
              </div>
            ) : (
              <div key={c.id} id={`crash-validation-${c.id}`} className="crash-validation-case">
                <p className="crash-validation-title">
                  {c.id} · {c.title}
                </p>
                <p className="crash-run-meta">
                  {c.references?.formula} · W&amp;A {fmt(c.references?.wierzbicki_abramowicz_1983_kn)} kN · A&amp;J{" "}
                  {fmt(c.references?.abramowicz_jones_1984_kn)} kN
                </p>
                <div className="crash-history-scroll">
                  <table className="doe-table crash-compare-table" data-testid="crash-validation-mesh">
                    <thead>
                      <tr>
                        <th>eleman mm</th>
                        <th>δ mm</th>
                        <th>Pm kN</th>
                        <th>/W&amp;A</th>
                        <th>/A&amp;J</th>
                        <th>HG/IE</th>
                        <th>s</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(c.mesh ?? []).map((m) => (
                        <tr key={m.element_mm}>
                          <td>{m.element_mm}</td>
                          <td className="crash-run-num">{fmt(m.crush_mm)}</td>
                          <td className="crash-run-num">{fmt(m.pm_energy_kn)}</td>
                          <MarkCell v={m.ratio_wa} th={th} />
                          <MarkCell v={m.ratio_aj} th={th} />
                          <td className="crash-run-num">{fr(m.hourglass_ratio)}</td>
                          <td className="crash-run-num">{fmt(m.wall_s, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </>
      )}
    </details>
  );
}
