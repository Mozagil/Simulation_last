/**
 * AKIŞ (CFD) · 3 · Akış — Faz 2.7b: yama rolleri, akışkan, türbülans, çözüm
 * ayarları, kuvvet yamaları, Çalıştır + canlı residual grafiği. Değerler
 * mühendisindir (varsayılanlar resmi pitzDaily / ISA havası); öneri yok.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchCfdJob,
  postBarrowman,
  postCfdSolve,
  postRocketSolve,
  type BarrowmanResult,
  type CfdJobSnapshot,
  type CfdMeshMeta,
  type CfdPatchKind,
  type CfdSolver,
  type RocketSolveBody,
} from "../api/cfd";
import CfdResidualChart from "./CfdResidualChart";
import CfdResults from "./CfdResults";
import CfdSweepPanel from "./CfdSweepPanel";

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
const SOLVERS: { id: CfdSolver; label: string; hint: string }[] = [
  { id: "simpleFoam", label: "simpleFoam", hint: "sıkıştırılamaz, daimi (Mach ≲ 0.3)" },
  { id: "rhoSimpleFoam", label: "rhoSimpleFoam", hint: "sıkıştırılabilir, daimi (Mach ~0.3–0.8)" },
  { id: "rhoCentralFoam", label: "rhoCentralFoam", hint: "şok yakalayan, yerel zaman adımı (Mach ~0.8+)" },
];
const ROCKET_PATCHES = ["burun", "govde", "kanatcik"];

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
  const [ctl, setCtl] = useState({ iterations: "1000", residual_p: "1e-4", residual_u: "1e-5", relax_u: "0.7", relax_other: "0.5", n_procs: "1" });
  // R4: çözücü seçimi + sıkıştırılabilir ayarlar
  const [solver, setSolver] = useState<CfdSolver>("simpleFoam");
  const [comp, setComp] = useState({ p_inf: "101325", t_inf: "288.15", transonic: false, max_co: "0.5" });
  const [forcePatches, setForcePatches] = useState<string[]>([]);
  const [ref, setRef] = useState({ a: "", l: "", avg: "100" });
  const [name, setName] = useState("");
  // Roket rüzgâr tüneli modu (R3): hız, α, CG → /cfd/rocket/solve; Barrowman ön izleme.
  const isRocket = ROCKET_PATCHES.every((p) => patches.includes(p));
  const [mode, setMode] = useState<"general" | "rocket">("general");
  const [rk, setRk] = useState({ speed: "50", alpha: "4", cg: "", temp: "288.15" });
  const [barrowman, setBarrowman] = useState<BarrowmanResult | null>(null);
  const [open, setOpen] = useState<1 | 2 | 3 | 4 | null>(1);
  const [job, setJob] = useState<CfdJobSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    setKinds(Object.fromEntries(patches.map((p) => [p, defaultKind(p)])));
    setForcePatches(patches.filter((p) => !TUNNEL.has(p)));
    setJob(null);
    setBarrowman(null);
    setMode(ROCKET_PATCHES.every((p) => patches.includes(p)) ? "rocket" : "general");
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

  async function runBarrowman() {
    if (!mesh) return;
    setError(null);
    try {
      setBarrowman(await postBarrowman({ geometry_id: geometryId ?? mesh.geometry_id, cg_mm: rk.cg.trim() ? num(rk.cg) : null }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  /** R3 / R5 ortak alanları (hız, α hariç). */
  function rocketBase(meshId: string): Omit<RocketSolveBody, "speed_m_s" | "alpha_deg"> {
    return {
        mesh_id: meshId,
        cg_mm: rk.cg.trim() ? num(rk.cg) : null,
        rho_kg_m3: num(fluid.rho),
        nu_m2_s: num(fluid.nu),
        temperature_k: num(rk.temp),
        turbulence_model: turb.model,
        solver,
        p_inf_pa: num(comp.p_inf),
        transonic: comp.transonic,
        max_co: num(comp.max_co),
        n_procs: num(ctl.n_procs),
        iterations: num(ctl.iterations),
        relax_u: num(ctl.relax_u),
        relax_other: num(ctl.relax_other),
        residual_p: num(ctl.residual_p),
        residual_u: num(ctl.residual_u),
        name: name.trim() || null,
    };
  }

  async function runRocket() {
    if (!mesh) return;
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const res = await postRocketSolve({ ...rocketBase(mesh.mesh_id), speed_m_s: num(rk.speed), alpha_deg: num(rk.alpha) });
      setBarrowman(res.barrowman);
      setJob({ job_id: res.job_id, status: res.status as CfdJobSnapshot["status"], message: res.message });
      setOpen(null);
      poll(res.job_id);
    } catch (e) {
      setBusy(false);
      setError((e as Error).message);
    }
  }

  async function run() {
    if (!mesh) return;
    if (mode === "rocket") {
      await runRocket();
      return;
    }
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
            n_procs: num(ctl.n_procs),
          },
          solver,
          compressible: { p_inf_pa: num(comp.p_inf), t_inf_k: num(comp.t_inf), transonic: comp.transonic, max_co: num(comp.max_co) },
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

  return (
    <div className="panel material-panel" data-testid="cfd-solve-panel">
      <span className="eyebrow">Faz 2 · Akış · {solver}</span>
      <h1>Akış çözümü</h1>
      <p className="lead material-lead">
        Mesh: {mesh.check.cells ?? "—"} hücre ({mesh.mesher === "cfmesh" ? "cfMesh" : "snappyHexMesh"}). Çözücü
        3. grupta seçilir.
      </p>

      {isRocket && (
        <span className="doe-seg" role="group" aria-label="Koşu türü">
          {(["general", "rocket"] as const).map((m) => (
            <button key={m} type="button" className={mode === m ? "doe-seg-opt active" : "doe-seg-opt"} aria-pressed={mode === m} disabled={busy} onClick={() => setMode(m)}>
              {m === "general" ? "Genel akış" : "Roket rüzgâr tüneli"}
            </button>
          ))}
        </span>
      )}

      {mode === "rocket" && (
        <section className="crash-acc" aria-label="Roket koşusu">
          <div className="crash-acc-body">
            <p className="crash-behavior-hint">
              Tünel sınırları serbest akım; U∞ = V·(cos α, 0, sin α). Gövde yamaları kuvvet, moment CG'ye (boşsa burun ucuna) göre.
            </p>
            <div className="crash-expert-grid cols-3">
              <Field label="Hız V" unit="m/s" value={rk.speed} disabled={busy} onChange={(v) => setRk((x) => ({ ...x, speed: v }))} />
              <Field label="Hücum açısı α" unit="°" value={rk.alpha} disabled={busy} onChange={(v) => setRk((x) => ({ ...x, alpha: v }))} />
              <Field label="Ağırlık merkezi (burun ucundan)" unit="mm" value={rk.cg} disabled={busy} onChange={(v) => setRk((x) => ({ ...x, cg: v }))} />
              <Field label="Sıcaklık (Mach için)" unit="K" value={rk.temp} disabled={busy} onChange={(v) => setRk((x) => ({ ...x, temp: v }))} />
            </div>
            <p className="crash-behavior-hint" data-testid="cfd-mach">
              Mach = {(num(rk.speed) / Math.sqrt(1.4 * 287.05 * num(rk.temp))).toFixed(3)} · çözücü {solver}
            </p>
            <button type="button" className="doe-btn doe-btn-ghost" disabled={busy} onClick={() => void runBarrowman()}>
              Barrowman (analitik CP, CNα)
            </button>
            {barrowman && (
              <table className="cfd-table" data-testid="cfd-barrowman">
                <thead>
                  <tr><th>Bileşen</th><th>CNα</th><th>X (mm)</th></tr>
                </thead>
                <tbody>
                  {barrowman.components.map((c) => (
                    <tr key={c.name}><td>{c.name}</td><td>{c.cn_alpha.toPrecision(4)}</td><td>{c.x_mm.toPrecision(5)}</td></tr>
                  ))}
                  <tr>
                    <td><strong>Toplam</strong></td>
                    <td>{barrowman.cn_alpha.toPrecision(4)}</td>
                    <td>{barrowman.x_cp_mm.toPrecision(5)}{barrowman.stability_calibers !== undefined ? ` · kararlılık ${barrowman.stability_calibers.toFixed(2)} kal.` : ""}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {mode === "general" && (
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
      )}

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

      <Acc n={3} title="Çözücü ve çözüm ayarları" summary={`${solver} · ${ctl.iterations} iterasyon · gevşetme ${ctl.relax_u}/${ctl.relax_other}${num(ctl.n_procs) > 1 ? ` · ${ctl.n_procs} çekirdek` : ""}`} open={open === 3} onToggle={() => toggle(3)}>
        <span className="doe-seg" role="group" aria-label="Çözücü">
          {SOLVERS.map((s) => (
            <button key={s.id} type="button" className={solver === s.id ? "doe-seg-opt active" : "doe-seg-opt"} aria-pressed={solver === s.id} disabled={busy} title={s.hint} onClick={() => setSolver(s.id)}>
              {s.label}
            </button>
          ))}
        </span>
        <p className="crash-behavior-hint" data-testid="cfd-solver-hint">{SOLVERS.find((s) => s.id === solver)!.hint}</p>
        {solver !== "simpleFoam" && (
          <div className="crash-expert-grid cols-3">
            <Field label="Serbest akım basıncı" unit="Pa" value={comp.p_inf} disabled={busy} onChange={(v) => setComp((c) => ({ ...c, p_inf: v }))} />
            {mode === "general" && <Field label="Serbest akım sıcaklığı" unit="K" value={comp.t_inf} disabled={busy} onChange={(v) => setComp((c) => ({ ...c, t_inf: v }))} />}
            {solver === "rhoCentralFoam" && <Field label="Courant sınırı" value={comp.max_co} disabled={busy} onChange={(v) => setComp((c) => ({ ...c, max_co: v }))} />}
          </div>
        )}
        {solver === "rhoSimpleFoam" && (
          <label className="material-check">
            <input type="checkbox" checked={comp.transonic} disabled={busy} onChange={(e) => setComp((c) => ({ ...c, transonic: e.target.checked }))} />
            <span>Transonik basınç denklemi</span>
          </label>
        )}
        <div className="crash-expert-grid cols-3">
          <Field label="İterasyon sınırı" value={ctl.iterations} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, iterations: v }))} />
          <Field label="Residual hedefi p" value={ctl.residual_p} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, residual_p: v }))} />
          <Field label="Residual hedefi U" value={ctl.residual_u} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, residual_u: v }))} />
          <Field label="Gevşetme U" value={ctl.relax_u} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, relax_u: v }))} />
          <Field label="Gevşetme diğer" value={ctl.relax_other} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, relax_other: v }))} />
          <Field label="Çekirdek sayısı" value={ctl.n_procs} disabled={busy} onChange={(v) => setCtl((c) => ({ ...c, n_procs: v }))} />
        </div>
      </Acc>

      {mode === "general" && (
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
      )}

      <label className="crash-unit-field wide">
        <span>Koşu adı</span>
        <span className="crash-unit-box">
          <input aria-label="Koşu adı" value={name} disabled={busy} placeholder="isteğe bağlı" onChange={(e) => setName(e.target.value)} />
        </span>
      </label>
      <button type="button" className="material-assign-button" disabled={busy} onClick={() => void run()}>
        {busy ? "Çözülüyor…" : mode === "rocket" ? "Roket koşusunu çalıştır" : `Çalıştır (${solver})`}
      </button>
      {error && <p className="error-message" role="alert">{error}</p>}

      {job && (
        <section className="cfd-run" aria-label="Koşu">
          <p className="crash-behavior-hint" data-testid="cfd-solve-status">
            {job.status === "solved" || job.status === "failed" ? job.message : `iterasyon ${job.iteration ?? 0} / ${ctl.iterations}`}
          </p>
          <CfdResidualChart iterations={its} residuals={residuals} />
          {job.status === "solved" && <CfdResults job={job} />}
        </section>
      )}
      {mode === "rocket" && mesh && <CfdSweepPanel base={rocketBase(mesh.mesh_id)} temperatureK={num(rk.temp)} disabled={busy} />}
    </div>
  );
}
