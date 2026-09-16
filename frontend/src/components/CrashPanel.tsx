import { useEffect, useState } from "react";
import {
  crashJobWsUrl,
  fetchCrashJob,
  postCrashSolve,
  type CrashJobSnapshot,
  type CrashSolveResponse,
} from "../api/crash";
import ButtonGroup from "./ButtonGroup";
import CrashSchematic, { type CrashScenarioId } from "./CrashSchematic";

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

function num(raw: string): number {
  const v = Number(raw);
  if (!Number.isFinite(v)) throw new Error(`Sayı geçersiz: ${raw}`);
  return v;
}

function optionalNum(raw: string): number | undefined {
  const t = raw.trim();
  if (!t) return undefined;
  return num(t);
}

function fmt(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

export default function CrashPanel({
  geometryId,
  meshDimension,
}: {
  geometryId: number | null;
  meshDimension: number | null;
}) {
  const [scenario, setScenario] = useState<CrashScenarioId>("rigid_wall");
  const [speed, setSpeed] = useState("10");
  const [angle, setAngle] = useState("0");
  const [wx, setWx] = useState("0");
  const [wy, setWy] = useState("0");
  const [wz, setWz] = useState("0");
  const [nx, setNx] = useState("0");
  const [ny, setNy] = useState("0");
  const [nz, setNz] = useState("1");
  const [tEnd, setTEnd] = useState("10");
  const [law, setLaw] = useState<"elastic" | "plastic">("elastic");
  const [isolid, setIsolid] = useState("1");
  const [ismstr, setIsmstr] = useState("0");
  const [nip, setNip] = useState("1");
  const [sigmaY, setSigmaY] = useState("");
  const [hardenB, setHardenB] = useState("0");
  const [hardenN, setHardenN] = useState("1");
  const [runSolver, setRunSolver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CrashSolveResponse | null>(null);
  const [snapshot, setSnapshot] = useState<CrashJobSnapshot | null>(null);

  const jobId = result?.job_id ?? snapshot?.job_id ?? null;
  const status = snapshot?.status ?? result?.status ?? null;
  const polling = Boolean(jobId && status && !TERMINAL.has(status));

  useEffect(() => {
    if (!jobId || !polling) return;
    const tick = () => {
      fetchCrashJob(jobId)
        .then(setSnapshot)
        .catch(() => undefined);
    };
    tick();
    const interval = window.setInterval(tick, 2000);
    let ws: WebSocket | null = null;
    if (typeof WebSocket !== "undefined") {
      try {
        ws = new WebSocket(crashJobWsUrl(jobId));
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(String(ev.data)) as CrashJobSnapshot;
            setSnapshot((prev) => ({ ...prev, ...data, job_id: data.job_id || jobId }));
          } catch {
            /* ignore */
          }
        };
      } catch {
        ws = null;
      }
    }
    return () => {
      window.clearInterval(interval);
      ws?.close();
    };
  }, [jobId, polling]);

  function applyScenario(id: CrashScenarioId) {
    setScenario(id);
    if (id === "rigid_wall") {
      setSpeed("10");
      setAngle("0");
      setTEnd("10");
    } else {
      setSpeed("20");
      setAngle("0");
      setTEnd("5");
    }
    setWx("0");
    setWy("0");
    setWz("0");
    setNx("0");
    setNy("0");
    setNz("1");
  }

  async function handleSubmit() {
    if (geometryId == null) return;
    setBusy(true);
    setError(null);
    try {
      const sy = optionalNum(sigmaY);
      const body = await postCrashSolve({
        geometry_id: geometryId,
        scenario,
        barrier: {
          speed_m_s: num(speed),
          angle_deg: num(angle),
          wall: {
            point: [num(wx), num(wy), num(wz)],
            normal: [num(nx), num(ny), num(nz)],
          },
        },
        dimension: 3,
        run_solver: runSolver,
        wait: false,
        t_end_ms: num(tEnd),
        model: {
          law,
          isolid: num(isolid),
          ismstr: num(ismstr),
          nip: num(nip),
          sigma_y_pa: sy,
          harden_b_mpa: num(hardenB),
          harden_n: num(hardenN),
        },
      });
      setResult(body);
      setSnapshot({
        job_id: body.job_id,
        geometry_id: body.geometry_id,
        status: body.status,
        message: body.message,
        scalars: body.scalars,
        percent: body.status === "pending" ? 0 : undefined,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Crash isteği başarısız.");
    } finally {
      setBusy(false);
    }
  }

  const scalars = snapshot?.scalars ?? result?.scalars ?? {};
  const percent = snapshot?.percent ?? 0;
  const canRun = geometryId != null && meshDimension === 3 && !busy;
  const wallTitle =
    scenario === "plate_ball" ? "Rijit plaka nokta (mm) — /RWALL" : "Rigid wall nokta (mm)";
  const normalTitle =
    scenario === "plate_ball" ? "Rijit plaka normal" : "Rigid wall normal";

  return (
    <div className="panel material-panel">
      <span className="eyebrow">Faz 1 · OpenRadioss</span>
      <h1>Crash</h1>
      <p className="lead material-lead">
        Durability sonuçları bu sekmede değişmez. 3D tet mesh + malzeme ataması
        gerekir. Hız m/s (mm–ms: 1 m/s = 1 mm/ms). Kartlar: LAW1/LAW2, TYPE14
        Isolid / Ismstr / NIP.
      </p>
      {meshDimension !== 3 && (
        <p className="material-assign-hint">3D tet mesh yok — crash dimension=3 ister.</p>
      )}
      {geometryId == null && (
        <p className="material-assign-hint">Önce geometri yükleyin.</p>
      )}

      <ButtonGroup
        title="Senaryo"
        items={[
          {
            key: "rigid_wall",
            label: "Rigid wall",
            active: scenario === "rigid_wall",
            onClick: () => applyScenario("rigid_wall"),
          },
          {
            key: "plate_ball",
            label: "Plaka–küre",
            active: scenario === "plate_ball",
            onClick: () => applyScenario("plate_ball"),
          },
        ]}
      />
      <CrashSchematic scenario={scenario} />

      <p className="material-assignments-title">Kinematik</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>Hız (m/s)</span>
          <input value={speed} onChange={(e) => setSpeed(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Açı (°)</span>
          <input value={angle} onChange={(e) => setAngle(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>t_end (ms)</span>
          <input value={tEnd} onChange={(e) => setTEnd(e.target.value)} />
        </label>
      </div>
      <p className="material-assignments-title">{wallTitle}</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>x</span>
          <input value={wx} onChange={(e) => setWx(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>y</span>
          <input value={wy} onChange={(e) => setWy(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>z</span>
          <input value={wz} onChange={(e) => setWz(e.target.value)} />
        </label>
      </div>
      <p className="material-assignments-title">{normalTitle}</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>nx</span>
          <input value={nx} onChange={(e) => setNx(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>ny</span>
          <input value={ny} onChange={(e) => setNy(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>nz</span>
          <input value={nz} onChange={(e) => setNz(e.target.value)} />
        </label>
      </div>

      <p className="material-assignments-title">Malzeme kanunu</p>
      <ButtonGroup
        title="LAW"
        items={[
          {
            key: "elastic",
            label: "LAW1 elastik",
            active: law === "elastic",
            onClick: () => setLaw("elastic"),
          },
          {
            key: "plastic",
            label: "LAW2 plastik",
            active: law === "plastic",
            onClick: () => setLaw("plastic"),
          },
        ]}
      />
      {law === "plastic" && (
        <div className="mesh-grid">
          <label className="mesh-field">
            <span>σy (Pa) — boşsa atanan malzeme</span>
            <input value={sigmaY} onChange={(e) => setSigmaY(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>LAW2 b (MPa)</span>
            <input value={hardenB} onChange={(e) => setHardenB(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>LAW2 n</span>
            <input value={hardenN} onChange={(e) => setHardenN(e.target.value)} />
          </label>
        </div>
      )}

      <p className="material-assignments-title">Eleman — /PROP/TYPE14</p>
      <div className="mesh-grid">
        <label className="mesh-field">
          <span>Isolid</span>
          <input value={isolid} onChange={(e) => setIsolid(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>Ismstr</span>
          <input value={ismstr} onChange={(e) => setIsmstr(e.target.value)} />
        </label>
        <label className="mesh-field">
          <span>NIP</span>
          <input value={nip} onChange={(e) => setNip(e.target.value)} />
        </label>
      </div>

      <label className="material-check">
        <input
          type="checkbox"
          checked={runSolver}
          onChange={(e) => setRunSolver(e.target.checked)}
        />
        OpenRadioss çalıştır (kuruluysa)
      </label>
      <button
        type="button"
        className="material-assign-button"
        disabled={!canRun}
        onClick={() => void handleSubmit()}
      >
        {busy ? "Gönderiliyor…" : ".rad üret / çöz"}
      </button>
      {error && <p className="material-assign-hint">{error}</p>}

      {(result || snapshot) && (
        <div className="material-assignments">
          <p className="material-assignments-title">Job</p>
          <p className="material-assign-hint">
            {snapshot?.job_id ?? result?.job_id} · {status} · {snapshot?.message ?? result?.message}
          </p>
          {polling && (
            <div className="crash-progress-track" role="progressbar" aria-valuenow={percent}>
              <div className="crash-progress-fill" style={{ width: `${Math.min(100, percent)}%` }} />
            </div>
          )}
          {snapshot?.cycle != null && (
            <p className="material-assign-hint">
              cycle {snapshot.cycle}
              {snapshot.time_ms != null ? ` · t=${fmt(snapshot.time_ms)} ms` : ""} · %{fmt(percent)}
            </p>
          )}
          {result?.starter_url && (
            <a className="material-inp-link" href={result.starter_url} target="_blank" rel="noreferrer">
              starter .rad
            </a>
          )}
          {Object.keys(scalars).length > 0 && (
            <ul className="crash-scalar-list">
              <li>HIC15 {fmt(scalars.hic15)}</li>
              <li>HIC36 {fmt(scalars.hic36)}</li>
              <li>acc_peak_g {fmt(scalars.acc_peak_g)}</li>
              <li>IE_final {fmt(scalars.internal_energy_final)}</li>
              <li>KE_final {fmt(scalars.kinetic_energy_final)}</li>
              <li>RWALL Fmax {fmt(scalars.rwall_force_max)}</li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
