import { useEffect, useState } from "react";
import {
  crashJobWsUrl,
  fetchCrashJob,
  postCrashSolve,
  type CrashContactSpec,
  type CrashJobSnapshot,
  type CrashPartSpec,
  type CrashSolveResponse,
} from "../api/crash";
import ButtonGroup from "./ButtonGroup";
import CrashForceChart, { forceSeriesFromCurves } from "./CrashForceChart";
import CrashSchematic, { type CrashScenarioId } from "./CrashSchematic";

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

/** Temas satırı: sayısal alanlar ham metin (input), gönderimde sayıya çevrilir. */
interface ContactRow {
  id: number;
  type: 7 | 24;
  master: number;
  slave: number;
  fric: string;
  stfac: string;
  gapmin: string;
  istf: string;
  inacti: string;
  iedge: string;
}

let contactRowSeq = 0;

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
  partIds = [],
  materialAssignments = [],
}: {
  geometryId: number | null;
  meshDimension: number | null;
  /** 3B mesh'teki parça kimlikleri (hacim sırası). Boşsa tek parça varsayılır. */
  partIds?: number[];
  /** Parça → malzeme adı (3 · Material adımında atananlar). */
  materialAssignments?: { part_id: number; material_name: string | null }[];
}) {
  const [scenario, setScenario] = useState<CrashScenarioId>("rigid_wall");
  // Parça rolleri: mühendis seçer; varsayılan hepsi hareketli (tek parçalı
  // eski davranışla aynı). Sabit parça /BCS ile tutulur, ilk hız almaz.
  const [partRoles, setPartRoles] = useState<Record<number, "moving" | "fixed">>({});
  // Temas tanımları (1.12): varsayılan yok — mühendis satır ekler.
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const [useRigidWall, setUseRigidWall] = useState(true);
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
  // Kabuk (2D mesh) — /PROP/TYPE1. 0 = Radioss /DEF_SHELL varsayılanı; öneri yok.
  const [shellT, setShellT] = useState("");
  const [partT, setPartT] = useState<Record<number, string>>({});
  const [ishell, setIshell] = useState("0");
  const [ish3n, setIsh3n] = useState("0");
  const [shellIsmstr, setShellIsmstr] = useState("0");
  const [shellNip, setShellNip] = useState("0");
  const [sigmaY, setSigmaY] = useState("");
  const [hardenB, setHardenB] = useState("0");
  const [hardenN, setHardenN] = useState("1");
  const [runSolver, setRunSolver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CrashSolveResponse | null>(null);
  const [snapshot, setSnapshot] = useState<CrashJobSnapshot | null>(null);

  // 2D mesh → kabuk parçalar (/SHELL, /SH3N, /PROP/TYPE1); 3D → solid (TYPE14).
  const isShell = meshDimension === 2;
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

  // Tek parçalı mesh'te partIds boş gelir: parça 0 (self-contact mümkün).
  const partOptions = partIds.length > 0 ? partIds : [0];

  function addContact() {
    contactRowSeq += 1;
    setContacts((rows) => [
      ...rows,
      {
        id: contactRowSeq,
        type: 7,
        master: partOptions[partOptions.length - 1],
        slave: partOptions[0],
        fric: "0",
        stfac: "1",
        gapmin: "0",
        istf: "0",
        inacti: "0",
        iedge: "0",
      },
    ]);
  }

  function updateContact(id: number, patch: Partial<ContactRow>) {
    setContacts((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function contactPayload(r: ContactRow): CrashContactSpec {
    return {
      type: r.type,
      master_part: r.master,
      slave_part: r.slave,
      fric: num(r.fric),
      stfac: num(r.stfac),
      gapmin: r.type === 7 ? num(r.gapmin) : 0,
      istf: num(r.istf),
      inacti: num(r.inacti),
      iedge: r.type === 24 ? num(r.iedge) : 0,
    };
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
        dimension: isShell ? 2 : 3,
        run_solver: runSolver,
        wait: false,
        t_end_ms: num(tEnd),
        parts:
          partIds.length > 0
            ? partIds.map(
                (pid): CrashPartSpec => ({
                  part_id: pid,
                  role: partRoles[pid] ?? "moving",
                  ...(isShell ? { thickness_mm: optionalNum(partT[pid] ?? "") ?? null } : {}),
                }),
              )
            : undefined,
        contacts: contacts.map(contactPayload),
        use_rigid_wall: useRigidWall,
        model: {
          law,
          isolid: num(isolid),
          ismstr: num(ismstr),
          nip: num(nip),
          sigma_y_pa: sy,
          harden_b_mpa: num(hardenB),
          harden_n: num(hardenN),
          ...(isShell
            ? {
                shell: {
                  thickness_mm: optionalNum(shellT) ?? null,
                  ishell: num(ishell),
                  ish3n: num(ish3n),
                  ismstr: num(shellIsmstr),
                  nip: num(shellNip),
                },
              }
            : {}),
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
  const canRun = geometryId != null && (meshDimension === 2 || meshDimension === 3) && !busy;
  // Duvar kapalıyken nokta/normal yine gönderilir: bariyer ilk hız yönünü
  // normalden türetir (açı 0° → −normal yönünde).
  const wallTitle = !useRigidWall
    ? "Bariyer nokta (mm) — duvar kapalı"
    : scenario === "plate_ball"
      ? "Rijit plaka nokta (mm) — /RWALL"
      : "Rigid wall nokta (mm)";
  const normalTitle = !useRigidWall
    ? "Bariyer normal — duvar kapalı, yalnız ilk hız yönü"
    : scenario === "plate_ball"
      ? "Rijit plaka normal"
      : "Rigid wall normal";
  const curves = snapshot?.curves;
  const forceSeries = forceSeriesFromCurves(curves);
  const contactPeaks = Object.keys(scalars)
    .map((k) => /^contact_(\d+)_force_max$/.exec(k))
    .filter((m): m is RegExpExecArray => m != null)
    .sort((a, b) => Number(a[1]) - Number(b[1]));

  return (
    <div className="panel material-panel">
      <span className="eyebrow">Faz 1 · OpenRadioss</span>
      <h1>Crash</h1>
      <p className="lead material-lead">
        Durability sonuçları bu sekmede değişmez. 3D (solid) ya da 2D (kabuk) mesh + malzeme ataması
        gerekir. Hız m/s (mm–ms: 1 m/s = 1 mm/ms). Kartlar: LAW1/LAW2, TYPE14
        Isolid / Ismstr / NIP.
      </p>
      {meshDimension !== 2 && meshDimension !== 3 && (
        <p className="material-assign-hint">Mesh yok — crash 3D (solid) ya da 2D (kabuk) mesh ister.</p>
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
      <label className="material-check">
        <input
          type="checkbox"
          checked={useRigidWall}
          disabled={busy}
          onChange={(e) => setUseRigidWall(e.target.checked)}
        />
        Rijit duvar (/RWALL)
      </label>
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

      {partIds.length > 0 && (
        <>
          <p className="material-assignments-title">Parçalar</p>
          <table className="doe-table crash-parts" data-testid="crash-parts">
            <thead>
              <tr>
                <th>parça</th>
                <th>malzeme</th>
                <th>rol</th>
                {isShell && <th>t (mm)</th>}
              </tr>
            </thead>
            <tbody>
              {partIds.map((pid) => {
                const mat = materialAssignments.find((a) => a.part_id === pid)?.material_name;
                const role = partRoles[pid] ?? "moving";
                return (
                  <tr key={pid}>
                    <td>#{pid}</td>
                    <td className={mat ? undefined : "crash-part-missing"}>{mat ?? "atama yok"}</td>
                    <td>
                      <span className="doe-seg" role="group" aria-label={`Parça ${pid} rolü`}>
                        <button
                          type="button"
                          className={role === "moving" ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === "moving"}
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: "moving" }))}
                        >
                          Hareketli
                        </button>
                        <button
                          type="button"
                          className={role === "fixed" ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === "fixed"}
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: "fixed" }))}
                        >
                          Sabit
                        </button>
                      </span>
                    </td>
                    {isShell && (
                      <td>
                        <input
                          className="crash-part-t"
                          aria-label={`Parça ${pid} t`}
                          placeholder="ortak"
                          value={partT[pid] ?? ""}
                          disabled={busy}
                          onChange={(e) => setPartT((t) => ({ ...t, [pid]: e.target.value }))}
                        />
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="material-assign-hint">
            Hareketli parça ilk hızı alır; sabit parça /BCS ile tutulur. Her parçaya malzeme
            atanmalı (3 · Material).
          </p>
        </>
      )}

      <p className="material-assignments-title">Temas — /INTER</p>
      {contacts.length > 0 && (
        <div className="crash-contacts" data-testid="crash-contacts">
          {contacts.map((c, i) => {
            const k = i + 1;
            const field = (
              key: "fric" | "stfac" | "gapmin" | "istf" | "inacti" | "iedge",
              label: string,
              off = false,
            ) => (
              <label className="mesh-field">
                <span>{label}</span>
                <input
                  aria-label={`Temas ${k} ${label.split(" ")[0]}`}
                  value={off ? "—" : c[key]}
                  disabled={busy || off}
                  onChange={(e) => updateContact(c.id, { [key]: e.target.value })}
                />
              </label>
            );
            const partSelect = (key: "master" | "slave", label: string) => (
              <label className="mesh-field">
                <span>{label}</span>
                <select
                  aria-label={`Temas ${k} ${key}`}
                  value={c[key]}
                  disabled={busy}
                  onChange={(e) => updateContact(c.id, { [key]: Number(e.target.value) })}
                >
                  {partOptions.map((pid) => (
                    <option key={pid} value={pid}>
                      parça #{pid}
                    </option>
                  ))}
                </select>
              </label>
            );
            return (
              <div key={c.id} className="crash-contact-card">
                <div className="crash-contact-head">
                  <strong>
                    Temas {k}
                    {c.master === c.slave ? " · self" : ""}
                  </strong>
                  <span className="doe-seg" role="group" aria-label={`Temas ${k} tipi`}>
                    {([7, 24] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        className={c.type === t ? "doe-seg-opt active" : "doe-seg-opt"}
                        aria-pressed={c.type === t}
                        disabled={busy}
                        onClick={() => updateContact(c.id, { type: t })}
                      >
                        TYPE{t}
                      </button>
                    ))}
                  </span>
                  <button
                    type="button"
                    className="crash-contact-remove"
                    aria-label={`Temas ${k} sil`}
                    disabled={busy}
                    onClick={() => setContacts((rows) => rows.filter((r) => r.id !== c.id))}
                  >
                    ×
                  </button>
                </div>
                <div className="crash-contact-parts">
                  {partSelect("slave", c.type === 7 ? "slave (düğümler)" : "slave (yüzey)")}
                  <span className="crash-contact-arrow" aria-hidden="true">
                    {c.type === 7 ? "→" : "↔"}
                  </span>
                  {partSelect("master", "master (yüzey)")}
                </div>
                <div className="mesh-grid">
                  {field("fric", "Fric")}
                  {field("stfac", "Stfac")}
                  {c.type === 7 ? field("gapmin", "GAPmin (mm)") : field("iedge", "Iedge")}
                  {field("istf", "Istf")}
                  {field("inacti", "Inacti")}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <button
        type="button"
        className="doe-btn doe-btn-ghost crash-contact-add"
        disabled={busy}
        onClick={addContact}
      >
        + Temas ekle
      </button>
      <p className="material-assign-hint">
        TYPE7: slave parçanın düğümleri → master parçanın dış yüzeyi. TYPE24: iki dış yüzey
        birbirine karşı (simetrik). master = slave → self-contact. Bayraklarda 0 = Radioss
        varsayılanı.
      </p>

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

      {isShell ? (
        <>
          <p className="material-assignments-title">Kabuk — /PROP/TYPE1</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>t (mm) — ortak</span>
              <input value={shellT} placeholder="—" onChange={(e) => setShellT(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ishell</span>
              <input value={ishell} onChange={(e) => setIshell(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ish3n</span>
              <input value={ish3n} onChange={(e) => setIsh3n(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ismstr (kabuk)</span>
              <input value={shellIsmstr} onChange={(e) => setShellIsmstr(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>N</span>
              <input value={shellNip} onChange={(e) => setShellNip(e.target.value)} />
            </label>
          </div>
          <p className="material-assign-hint">
            Kalınlık: parça satırındaki t, yoksa ortak t; ikisi de boşsa çözüm hata verir.
            Bayraklarda 0 = Radioss /DEF_SHELL varsayılanı. N: 0, 1 ya da 3…10.
          </p>
        </>
      ) : (
        <>
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
        </>
      )}

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
              {scalars.rwall_impulse_final != null && (
                <li>RWALL impuls {fmt(scalars.rwall_impulse_final)} N·s</li>
              )}
              {contactPeaks.map((m) => (
                <li key={m[0]}>
                  Temas {m[1]} Fmax {fmt(scalars[m[0]])} kN · impuls{" "}
                  {fmt(scalars[`contact_${m[1]}_impulse_final`])} N·s
                </li>
              ))}
            </ul>
          )}
          {curves?.time && forceSeries.length > 0 && (
            <CrashForceChart time={curves.time} series={forceSeries} />
          )}
        </div>
      )}
    </div>
  );
}
