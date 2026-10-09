/**
 * AKIŞ (CFD) · 3 · Akış — Faz 2.7b: yama rolleri, akışkan, türbülans, çözüm
 * ayarları, kuvvet yamaları, Çalıştır + canlı residual grafiği. Değerler
 * mühendisindir (varsayılanlar resmi pitzDaily / ISA havası); öneri yok.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchCfdJob,
  postCfdSolve,
  type CfdJobSnapshot,
  type CfdMeshMeta,
  type CfdPatchKind,
} from "../api/cfd";
import CfdResidualChart from "./CfdResidualChart";

const KIND_LABEL: Record<CfdPatchKind, string> = {
  inlet: "Giriş (hız)",
  outlet: "Çıkış (basınç)",
  wall: "Duvar",
  slip: "Kaymalı duvar",
  farfield: "Serbest akım",
  symmetry: "Simetri",
  empty: "Boş (2B)",
};
const KINDS = Object.keys(KIND_LABEL) as CfdPatchKind[];
const TUNNEL = new Set(["inlet", "outlet", "sides", "ground"]);

function defaultKind(name: string): CfdPatchKind {
  if (name === "inlet") return "inlet";
  if (name === "outlet") return "outlet";
  if (name === "sides") return "slip";
  return "wall";
}

function num(v: string): number {
  return Number(String(v).replace(",", "."));
}

function Field({ label, unit, value, onChange, disabled }: { label: string; unit?: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <label className="crash-unit-field">
      <span>{label}</span>
      <span className="crash-unit-box">
        <input aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        {unit && <em>{unit}</em>}
      </span>
    </label>
  );
}

function Acc({ n, title, summary, open, onToggle, children }: { n: number; title: string; summary: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <section className="crash-acc" aria-label={title}>
      <button type="button" className="crash-acc-toggle" aria-expanded={open} onClick={onToggle}>
        <span className="crash-acc-n">{n}</span>
        <span className="crash-acc-text">
          <strong>{title}</strong>
          <span className="crash-acc-summary">{summary}</span>
        </span>
        <span className="crash-acc-chev" aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && <div className="crash-acc-body">{children}</div>}
    </section>
  );
}

export default function CfdSolvePanel({
  mesh,
  geometryId = null,
  pollMs = 2000,
  onSolved,
}: {
  mesh: CfdMeshMeta | null;
  geometryId?: number | null;
  pollMs?: number;
  onSolved?: (job: CfdJobSnapshot) => void;
}) {
  const patches = useMemo(() => mesh?.patches ?? [], [mesh]);
  const [kinds, setKinds] = useState<Record<string, CfdPatchKind>>({});
  const [vel, setVel] = useState<[string, string, string]>(["10", "0", "0"]);
  const [fluid, setFluid] = useState({ nu: "1.5e-5", rho: "1.225" });
  const [turb, setTurb] = useState({ model: "kOmegaSST" as "laminar" | "kOmegaSST", intensity: "0.01", length: "0.01" });
  const [ctl, setCtl] = useState({ iterations: "1000", residual_p: "1e-4", residual_u: "1e-5", relax_u: "0.7", relax_other: "0.5" });
  const [forcePatches, setForcePatches] = useState<string[]>([]);
  const [ref, setRef] = useState({ a: "", l: "", avg: "100" });
  const [name, setName] = useState("");
  const [open, setOpen] = useState<1 | 2 | 3 | 4 | null>(1);
  const [job, setJob] = useState<CfdJobSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    setKinds(Object.fromEntries(patches.map((p) => [p, defaultKind(p)])));
    setForcePatches(patches.filter((p) => !TUNNEL.has(p)));
    setJob(null);
  }, [patches]);
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const toggle = (g: 1 | 2 | 3 | 4) => setOpen((cur) => (cur === g ? null : g));
  const u = vel.map(num) as [number, number, number];
  const speed = Math.hypot(...u);
  const kindOf = (p: string) => kinds[p] ?? defaultKind(p);

  function poll(id: string) {
    timer.current = window.setTimeout(async () => {
      try {
        const j = await fetchCfdJob(id);
        setJob(j);
        if (j.status === "pending" || j.hub_state === "running") {
          poll(id);
          return;
        }
        setBusy(false);
        if (j.status === "solved") onSolved?.(j);
        else if (j.status === "failed") setError(j.message);
      } catch (e) {
        setBusy(false);
        setError((e as Error).message);
      }
    }, pollMs);
  }

  async function run() {
    if (!mesh) return;
    setBusy(true);
    setError(null);
    setJob(null);
    const withVel = (k: CfdPatchKind) => k === "inlet" || k === "farfield";
    const forces =
      forcePatches.length > 0 && num(ref.a) > 0 && num(ref.l) > 0
        ? {
            patches: forcePatches,
            cofr_m: [0, 0, 0] as [number, number, number],
            u_ref_m_s: speed,
            l_ref_m: num(ref.l),
            a_ref_m2: num(ref.a),
            average_last: num(ref.avg),
          }
        : null;
    try {
      const res = await postCfdSolve({
        mesh_id: mesh.mesh_id,
        geometry_id: geometryId ?? mesh.geometry_id,
        name: name.trim() || null,
        case: {
          nu_m2_s: num(fluid.nu),
          rho_kg_m3: num(fluid.rho),
          patches: patches.map((p) => {
            const k = kindOf(p);
            return withVel(k) ? { name: p, kind: k, velocity_m_s: u } : k === "outlet" ? { name: p, kind: k, pressure: 0 } : { name: p, kind: k };
          }),
          turbulence: { model: turb.model, intensity: num(turb.intensity), length_scale_m: num(turb.length) },
          control: {
            iterations: num(ctl.iterations),
            write_interval: num(ctl.iterations),
            residual_p: num(ctl.residual_p),
            residual_u: num(ctl.residual_u),
            relax_u: num(ctl.relax_u),
            relax_other: num(ctl.relax_other),
          },
          initial_velocity_m_s: u,
          forces,
        },
      });
      setJob({ job_id: res.job_id, status: res.status as CfdJobSnapshot["status"], message: res.message });
      setOpen(null);
      poll(res.job_id);
    } catch (e) {
      setBusy(false);
      setError((e as Error).message);
    }
  }

  if (!mesh) {
    return (
      <div className="panel material-panel" data-testid="cfd-solve-panel">
        <span className="eyebrow">Faz 2 · Akış</span>
        <h1>Akış çözümü</h1>
        <p className="crash-behavior-hint">Önce 2 · Mesh adımında akışkan ağını üretin; yamalar oradan gelir.</p>
      </div>
    );
  }

  const residuals = job?.curves?.residuals ?? {};
  const its = job?.curves?.iteration ?? [];
  const sc = job?.scalars ?? {};

  return (
    <div className="panel material-panel" data-testid="cfd-solve-panel">
      <span className="eyebrow">Faz 2 · Akış · simpleFoam</span>
      <h1>Akış çözümü</h1>
      <p className="lead material-lead">
        Mesh: {mesh.check.cells ?? "—"} hücre ({mesh.mesher === "cfmesh" ? "cfMesh" : "snappyHexMesh"}). Daimi,
        sıkıştırılamaz (Mach ≲ 0.3 için).
      </p>

      <Acc n={1} title="Yamalar (sınır koşulları)" summary={patches.map((p) => `${p}: ${KIND_LABEL[kindOf(p)]}`).join(" · ")} open={open === 1} onToggle={() => toggle(1)}>
        <table className="cfd-table">
          <tbody>
            {patches.map((p) => (
              <tr key={p}>
                <th>{p}</th>
                <td>
                  <select aria-label={`Yama ${p}`} value={kindOf(p)} disabled={busy} onChange={(e) => setKinds((k) => ({ ...k, [p]: e.target.value as CfdPatchKind }))}>
                    {KINDS.map((k) => (
                      <option key={k} value={k}>
                        {KIND_LABEL[k]}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="crash-behavior-hint">Giriş ve serbest akım yamalarına aynı hız vektörü verilir; çıkış basıncı 0 (kinematik).</p>
        <div className="crash-expert-grid cols-3">
          {(["Ux", "Uy", "Uz"] as const).map((lbl, i) => (
            <Field key={lbl} label={lbl} unit="m/s" value={vel[i]} disabled={busy} onChange={(v) => setVel((cur) => cur.map((c, j) => (j === i ? v : c)) as [string, string, string])} />
          ))}
        </div>
      </Acc>

      <Acc n={2} title="Akışkan ve türbülans" summary={`ν ${fluid.nu} m²/s · ρ ${fluid.rho} kg/m³ · ${turb.model === "laminar" ? "laminer" : "k-ω SST"}`} open={open === 2} onToggle={() => toggle(2)}>
        <div className="crash-expert-grid cols-3">
          <Field label="ν (kinematik viskozite)" unit="m²/s" value={fluid.nu} disabled={busy} onChange={(v) => setFluid((f) => ({ ...f, nu: v }))} />
          <Field label="ρ (yoğunluk)" unit="kg/m³" value={fluid.rho} disabled={busy} onChange={(v) => setFluid((f) => ({ ...f, rho: v }))} />
        </div>
        <span className="doe-seg" role="group" aria-label="Türbülans modeli">
          {(["laminar", "kOmegaSST"] as const).map((m) => (
            <button key={m} type="button" className={turb.model === m ? "doe-seg-opt active" : "doe-seg-opt"} aria-pressed={turb.model === m} disabled={busy} onClick={() => setTurb((t) => ({ ...t, model: m }))}>
              {m === "laminar" ? "Laminer" : "k-ω SST"}
            </button>
          ))}
        </span>
        {turb.model === "kOmegaSST" && (
          <div className="crash-expert-grid cols-3">
            <Field label="Türbülans yoğunluğu" value={turb.intensity} disabled={busy} onChange={(v) => setTurb((t) => ({ ...t, intensity: v }))} />
            <Field label="Uzunluk ölçeği" unit="m" value={turb.length} disabled={busy} onChange={(v) => setTurb((t) => ({ ...t, length: v }))} />
          </div>
        )}
        <p className="crash-behavior-hint" data-testid="cfd-re">
          |U| = {speed.toPrecision(3)} m/s · Re (gövde boyu L = {mesh.domain.body_length_m.toPrecision(3)} m) ={" "}
          {(speed * mesh.domain.body_length_m / num(fluid.nu)).toExponential(2)}
        </p>
      </Acc>

      <Acc n={3} title="Çözüm ayarları" summary={`${ctl.iterations} iterasyon · residual p ${ctl.residual_p}, U ${ctl.residual_u} · gevşetme ${ctl.relax_u}/${ctl.relax_other}`} open={open === 3} onToggle={() => toggle(3)}>
        <div className="crash-expert-grid cols-3">
          <Field label="İterasyon sınırı" value={ctl.iterations} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, iterations: v }))} />
          <Field label="Residual hedefi p" value={ctl.residual_p} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, residual_p: v }))} />
          <Field label="Residual hedefi U" value={ctl.residual_u} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, residual_u: v }))} />
          <Field label="Gevşetme U" value={ctl.relax_u} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, relax_u: v }))} />
          <Field label="Gevşetme diğer" value={ctl.relax_other} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, relax_other: v }))} />
        </div>
      </Acc>

      <Acc n={4} title="Kuvvet ve katsayılar" summary={forcePatches.length ? `${forcePatches.join(", ")} · A ${ref.a || "—"} m² · l ${ref.l || "—"} m` : "kuvvet okunmaz"} open={open === 4} onToggle={() => toggle(4)}>
        <p className="crash-behavior-hint">Seçili yamaların toplam kuvveti; Cd = F/(½ρU²A). A ve l boşsa kuvvet okunmaz.</p>
        <span className="docs-chips">
          {patches.filter((p) => !TUNNEL.has(p)).map((p) => (
            <label key={p} className="docs-chip">
              <input
                type="checkbox"
                aria-label={`Kuvvet ${p}`}
                checked={forcePatches.includes(p)}
                disabled={busy}
                onChange={(e) => setForcePatches((cur) => (e.target.checked ? [...cur, p] : cur.filter((x) => x !== p)))}
              />{" "}
              {p}
            </label>
          ))}
        </span>
        <div className="crash-expert-grid cols-3">
          <Field label="Referans alan A" unit="m²" value={ref.a} disabled={busy} onChange={(v) => setRef((r) => ({ ...r, a: v }))} />
          <Field label="Referans uzunluk l" unit="m" value={ref.l} disabled={busy} onChange={(v) => setRef((r) => ({ ...r, l: v }))} />
          <Field label="Ortalama son N" unit="iterasyon" value={ref.avg} disabled={busy} onChange={(v) => setRef((r) => ({ ...r, avg: v }))} />
        </div>
      </Acc>

      <label className="crash-unit-field wide">
        <span>Koşu adı</span>
        <span className="crash-unit-box">
          <input aria-label="Koşu adı" value={name} disabled={busy} placeholder="isteğe bağlı" onChange={(e) => setName(e.target.value)} />
        </span>
      </label>
      <button type="button" className="material-assign-button" disabled={busy} onClick={() => void run()}>
        {busy ? "Çözülüyor…" : "Çalıştır (simpleFoam)"}
      </button>
      {error && <p className="error-message" role="alert">{error}</p>}

      {job && (
        <section className="cfd-run" aria-label="Koşu">
          <p className="crash-behavior-hint" data-testid="cfd-solve-status">
            {job.status === "solved" || job.status === "failed" ? job.message : `iterasyon ${job.iteration ?? 0} / ${ctl.iterations}`}
          </p>
          <CfdResidualChart iterations={its} residuals={residuals} />
          {job.status === "solved" && (
            <table className="cfd-table" data-testid="cfd-solve-summary">
              <tbody>
                <tr><th>İterasyon</th><td>{sc.iterations} · {sc.converged ? "yakınsadı" : "iterasyon sınırı"}</td></tr>
                {sc.Cd !== undefined && <tr><th>Cd (son / ort. ± std)</th><td>{sc.Cd.toPrecision(4)} / {sc.Cd_mean?.toPrecision(4)} ± {sc.Cd_std?.toPrecision(2)}</td></tr>}
                {sc.Cl !== undefined && <tr><th>Cl (ort.)</th><td>{sc.Cl_mean?.toPrecision(4)}</td></tr>}
                {sc.CdA_m2 !== undefined && <tr><th>CdA</th><td>{sc.CdA_m2.toPrecision(4)} m²</td></tr>}
                {sc.force_total_x !== undefined && <tr><th>Toplam Fx</th><td>{sc.force_total_x.toPrecision(4)} N</td></tr>}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
