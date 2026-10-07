import { useEffect, useState } from "react";
import {
  crashJobWsUrl,
  fetchCrashJob,
  postCrashSolve,
  type CrashContactSpec,
  type CrashJobSnapshot,
  type CrashModelPayload,
  type CrashPartSpec,
  type CrashSolveResponse,
} from "../api/crash";
import CrashMaterialCard, { defaultMatCard, matCardPayload, type MatCardState } from "./CrashMaterialCard";
import CrashOutputCard, { defaultOutput, outputPayload, type OutputState } from "./CrashOutputCard";
import CrashForceChart, { forceSeriesFromCurves } from "./CrashForceChart";
import CrashHistory from "./CrashHistory";
import CrashCatalog from "./CrashCatalog";
import CrashScenarioCard from "./CrashScenarioCard";
import CrashValidation from "./CrashValidation";
import CrashLoadCards, { cardsPayload, type LoadCard, type PartRole } from "./CrashLoadCards";
import CrashSchematic from "./CrashSchematic";

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

function fmt(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toExponential(3);
}

type LoadingKind = "inivel" | "impvel" | "gravity";
type ObstacleKind = "wall" | "part" | "none";

const LOADING_OPTIONS: { id: string; label: string; title: string; disabled?: boolean }[] = [
  { id: "inivel", label: "İlk hız", title: "/INIVEL — hareketli parçalar (ya da İlk hız kartları)" },
  { id: "impvel", label: "Dayatılmış hız", title: "/IMPVEL — Tutma altındaki kartlardan" },
  { id: "gravity", label: "Yerçekimi", title: "/GRAV — tüm düğümlere sabit ivme" },
  { id: "pressure", label: "Basınç/patlama", title: "Yalnız Hızlı senaryo (K10/K12)", disabled: true },
  { id: "sph", label: "SPH mermi", title: "Yalnız Hızlı senaryo (K12)", disabled: true },
];

const OBSTACLE_OPTIONS: { id: ObstacleKind; label: string; title: string }[] = [
  { id: "wall", label: "Rijit duvar", title: "/RWALL — sonsuz rijit düzlem" },
  { id: "part", label: "Başka parça (temas)", title: "/INTER — parçalar arası temas" },
  { id: "none", label: "Yok", title: "Duvar yok; ilk hız yönü vektörle" },
];

export const CRASH_PRESETS: { id: string; label: string; loading: LoadingKind; obstacle: ObstacleKind }[] = [
  { id: "box_wall", label: "Crash box → rijit duvar", loading: "inivel", obstacle: "wall" },
  { id: "part_part", label: "Çarpan parça → hedef parça (temas)", loading: "inivel", obstacle: "part" },
  { id: "impvel_free", label: "Dayatılmış hız, engelsiz (kartlarla)", loading: "impvel", obstacle: "none" },
];

export default function CrashPanel({
  geometryId,
  meshDimension,
  partIds = [],
  materialAssignments = [],
  componentThickness = {},
  onScenarioGeometry,
  selectedPartIds = [],
  onPartSelect,
  onPartHover,
  regions = [],
  animRunId = null,
  onAnimateRun,
}: {
  geometryId: number | null;
  meshDimension: number | null;
  /** 3B mesh'teki parça kimlikleri (hacim sırası). Boşsa tek parça varsayılır. */
  partIds?: number[];
  /** Parça → malzeme adı (3 · Material adımında atananlar). */
  materialAssignments?: { part_id: number; material_name: string | null }[];
  /** 2D: parça → ürün ağacı bileşen kalınlığı (mm). Kabuk kalınlığının tek
   * kaynağı Malzeme adımıdır; panel yalnız gösterir, backend oradan okur. */
  componentThickness?: Record<number, number | null>;
  /** Hızlı senaryonun ürettiği geometri (App viewport'a yükler, TODO 11.6). */
  onScenarioGeometry?: (geometryId: number, name: string) => void;
  /** TODO 11.7 — viewport / ürün ağacı ile ortak parça seçimi. */
  selectedPartIds?: number[];
  onPartSelect?: (partId: number) => void;
  onPartHover?: (partId: number | null) => void;
  /** Physical Group adları (şablon bölgeleri + kullanıcı grupları) — kart hedefi (11.3/11.9). */
  regions?: string[];
  /** TODO 11.4 — deforme şekil ana viewport'ta (App). */
  animRunId?: number | null;
  onAnimateRun?: (run: { id: number; title: string } | null) => void;
}) {
  // Parça rolleri: mühendis seçer; varsayılan hepsi hareketli (tek parçalı
  // eski davranışla aynı). Sabit parça /BCS ile tutulur, ilk hız almaz.
  const [partRoles, setPartRoles] = useState<Record<number, PartRole>>({});
  // TODO 11.9 — kart tabanlı yükleme / tutma
  const [loadCards, setLoadCards] = useState<LoadCard[]>([]);
  // Temas tanımları (1.12): varsayılan yok — mühendis satır ekler.
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  // TODO 11.2 — üç soru: yükleme kaynağı, engel, tutma (kartlar 11.9).
  const [loading, setLoading] = useState<LoadingKind>("inivel");
  const [obstacle, setObstacle] = useState<ObstacleKind>("wall");
  const useRigidWall = obstacle === "wall";
  // 11.1 — duvar yokken ilk hız yönü (duvar varken normal + açıdan)
  const [dx, setDx] = useState("-1");
  const [dy, setDy] = useState("0");
  const [dz, setDz] = useState("0");
  const [gravAccel, setGravAccel] = useState("-9.81");
  const [gravDir, setGravDir] = useState<"X" | "Y" | "Z">("Z");
  const [speed, setSpeed] = useState("10");
  const [angle, setAngle] = useState("0");
  const [wx, setWx] = useState("0");
  const [wy, setWy] = useState("0");
  const [wz, setWz] = useState("0");
  const [nx, setNx] = useState("0");
  const [ny, setNy] = useState("0");
  const [nz, setNz] = useState("1");
  const [tEnd, setTEnd] = useState("10");
  // Malzeme kartı (1.14e): global kart + isteğe bağlı parça başına kart (1.14b).
  // partCards'ta olmayan parça global karta düşer.
  const [matCard, setMatCard] = useState<MatCardState>(defaultMatCard);
  const [partCards, setPartCards] = useState<Record<number, MatCardState>>({});
  // 1.15d — engine / TH / kesit ayarları; boş = backend varsayılanı (eski deck)
  const [output, setOutput] = useState<OutputState>(defaultOutput);
  /** 1.17g-7 — hızlı senaryo başlayınca / bitince geçmişi yenile */
  const [scenarioTick, setScenarioTick] = useState(0);
  const [isolid, setIsolid] = useState("1");
  const [ismstr, setIsmstr] = useState("0");
  const [nip, setNip] = useState("1");
  // Kabuk (2D mesh) — /PROP/TYPE1. 0 = Radioss /DEF_SHELL varsayılanı; öneri yok.
  const [ishell, setIshell] = useState("0");
  const [ish3n, setIsh3n] = useState("0");
  const [shellIsmstr, setShellIsmstr] = useState("0");
  const [shellNip, setShellNip] = useState("0");
  // 1.17h — hourglass kontrolü; 0 = Radioss varsayılanı
  const [hgHm, setHgHm] = useState("0");
  const [hgHf, setHgHf] = useState("0");
  const [hgHr, setHgHr] = useState("0");
  const [hgSolid, setHgSolid] = useState("0");
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

  function chooseObstacle(next: ObstacleKind) {
    setObstacle(next);
    // "Başka parça": temas tanımı yoksa bir TYPE7 satırı aç (mühendis düzenler).
    if (next === "part" && contacts.length === 0) addContact();
  }

  function applyPreset(id: string) {
    const preset = CRASH_PRESETS.find((x) => x.id === id);
    if (!preset) return;
    setLoading(preset.loading);
    chooseObstacle(preset.obstacle);
  }

  async function handleSubmit() {
    if (geometryId == null) return;
    setBusy(true);
    setError(null);
    try {
      // Eleman bayrakları (TYPE14 / kabuk TYPE1) global; parça kartı yalnız malzemeyi değiştirir.
      const elementFlags = {
        isolid: num(isolid),
        ismstr: num(ismstr),
        nip: num(nip),
        solid_hourglass_h: num(hgSolid),
        ...(isShell
          ? {
              shell: {
                ishell: num(ishell),
                ish3n: num(ish3n),
                ismstr: num(shellIsmstr),
                nip: num(shellNip),
                hm: num(hgHm),
                hf: num(hgHf),
                hr: num(hgHr),
              },
            }
          : {}),
      };
      const modelFor = (card: MatCardState, label: string) =>
        ({ ...elementFlags, ...matCardPayload(card, label) }) as CrashModelPayload;
      const body = await postCrashSolve({
        geometry_id: geometryId,
        barrier: {
          // Yükleme ilk hız değilse bariyer hızı 0 (yük kartlardan / yerçekiminden).
          speed_m_s: loading === "inivel" ? num(speed) : 0,
          angle_deg: obstacle === "wall" ? num(angle) : 0,
          wall: {
            point: [num(wx), num(wy), num(wz)],
            normal: [num(nx), num(ny), num(nz)],
          },
          ...(obstacle !== "wall" ? { direction: [num(dx), num(dy), num(dz)] as [number, number, number] } : {}),
        },
        ...(loading === "gravity" ? { gravity: { accel_m_s2: num(gravAccel), direction: gravDir } } : {}),
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
                  ...(partCards[pid] ? { model: modelFor(partCards[pid], `Parça #${pid}`) } : {}),
                }),
              )
            : undefined,
        contacts: contacts.map(contactPayload),
        use_rigid_wall: useRigidWall,
        ...cardsPayload(loadCards),
        model: modelFor(matCard, "Global"),
        ...outputPayload(output),
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
  const curves = snapshot?.curves;
  const forceSeries = forceSeriesFromCurves(curves);
  const diagnostics = snapshot?.diagnostics ?? result?.diagnostics;
  const msgList = (m: Record<string, number> | undefined) =>
    Object.entries(m ?? {}).map(([id, n]) => (n > 1 ? `${id} ×${n}` : id));
  const starterMsgs = {
    errors: msgList(diagnostics?.starter_errors),
    warnings: msgList(diagnostics?.starter_warnings),
  };
  // 1.17e — CFC süzülmüş tepe değerleri (…_max_cfcN, acc_peak_g_cfcN, hic15_cfcN)
  const cfcPeaks = Object.keys(scalars)
    .filter((k) => /_cfc\d+$/.test(k) && !k.startsWith("sample_ratio"))
    .sort();
  const sectionPeaks = Object.keys(scalars)
    .map((k) => /^section_(\d+)_force_max$/.exec(k))
    .filter((m): m is RegExpExecArray => m != null)
    .sort((a, b) => Number(a[1]) - Number(b[1]));
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
        gerekir. Hız m/s (mm–ms: 1 m/s = 1 mm/ms). Kartlar: LAW1 / LAW2 / LAW36, /FAIL,
        TYPE14 Isolid / Ismstr / NIP.
      </p>
      {meshDimension !== 2 && meshDimension !== 3 && (
        <p className="material-assign-hint">Mesh yok — crash 3D (solid) ya da 2D (kabuk) mesh ister.</p>
      )}
      {geometryId == null && (
        <p className="material-assign-hint">Önce geometri yükleyin.</p>
      )}

      <CrashSchematic />

      <div className="crash-q-preset">
        <label className="mesh-field">
          <span>Hazır senaryo</span>
          <select aria-label="Hazır senaryo" value="" disabled={busy} onChange={(e) => applyPreset(e.target.value)}>
            <option value="">— seç (üç soruyu doldurur) —</option>
            {CRASH_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="crash-q" aria-label="1 · Yükleme">
        <p className="crash-q-title">1 · Yükleme</p>
        <div className="doe-seg crash-q-options" role="radiogroup" aria-label="Yükleme kaynağı">
          {LOADING_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={loading === o.id}
              className={loading === o.id ? "doe-seg-opt active" : "doe-seg-opt"}
              disabled={busy || o.disabled}
              title={o.title}
              onClick={() => setLoading(o.id as LoadingKind)}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="mesh-grid">
          {loading === "inivel" && (
            <label className="mesh-field">
              <span>Hız (m/s)</span>
              <input value={speed} disabled={busy} onChange={(e) => setSpeed(e.target.value)} />
            </label>
          )}
          {loading === "inivel" && obstacle === "wall" && (
            <label className="mesh-field">
              <span>Açı (°)</span>
              <input value={angle} disabled={busy} onChange={(e) => setAngle(e.target.value)} />
            </label>
          )}
          {loading === "gravity" && (
            <>
              <label className="mesh-field">
                <span>g (m/s², işaretli)</span>
                <input aria-label="Yerçekimi ivmesi" value={gravAccel} disabled={busy} onChange={(e) => setGravAccel(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>eksen</span>
                <select aria-label="Yerçekimi ekseni" value={gravDir} disabled={busy} onChange={(e) => setGravDir(e.target.value as "X" | "Y" | "Z")}>
                  <option>X</option>
                  <option>Y</option>
                  <option>Z</option>
                </select>
              </label>
            </>
          )}
          <label className="mesh-field">
            <span>t_end (ms)</span>
            <input value={tEnd} disabled={busy} onChange={(e) => setTEnd(e.target.value)} />
          </label>
        </div>
        {loading === "inivel" && obstacle !== "wall" && (
          <>
            <p className="material-assignments-title">İlk hız yönü (duvar yok — vektör)</p>
            <div className="mesh-grid">
              <label className="mesh-field">
                <span>x</span>
                <input aria-label="Hız yönü x" value={dx} disabled={busy} onChange={(e) => setDx(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>y</span>
                <input aria-label="Hız yönü y" value={dy} disabled={busy} onChange={(e) => setDy(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>z</span>
                <input aria-label="Hız yönü z" value={dz} disabled={busy} onChange={(e) => setDz(e.target.value)} />
              </label>
            </div>
          </>
        )}
        {loading === "impvel" && (
          <p className="material-assign-hint">
            Dayatılmış hız 3 · Tutma altındaki kartlardan gelir (+ Dayatılmış hız). Bariyer ilk hızı gönderilmez.
          </p>
        )}
        {loading === "inivel" && loadCards.some((c) => c.kind === "inivel") && (
          <p className="material-assign-hint">
            İlk hız kartı tanımlı — parçalara bariyer hızı verilmez, hız kartlardan gelir (kapsama özeti).
          </p>
        )}
      </section>

      <section className="crash-q" aria-label="2 · Engel">
        <p className="crash-q-title">2 · Engel</p>
        <div className="doe-seg crash-q-options" role="radiogroup" aria-label="Engel">
          {OBSTACLE_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={obstacle === o.id}
              className={obstacle === o.id ? "doe-seg-opt active" : "doe-seg-opt"}
              disabled={busy}
              title={o.title}
              onClick={() => chooseObstacle(o.id)}
            >
              {o.label}
            </button>
          ))}
        </div>
        {obstacle === "wall" && (
          <>
            <p className="material-assignments-title">Rigid wall nokta (mm)</p>
            <div className="mesh-grid">
              <label className="mesh-field">
                <span>x</span>
                <input aria-label="Duvar nokta x" value={wx} disabled={busy} onChange={(e) => setWx(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>y</span>
                <input aria-label="Duvar nokta y" value={wy} disabled={busy} onChange={(e) => setWy(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>z</span>
                <input aria-label="Duvar nokta z" value={wz} disabled={busy} onChange={(e) => setWz(e.target.value)} />
              </label>
            </div>
            <p className="material-assignments-title">Rigid wall normal</p>
            <div className="mesh-grid">
              <label className="mesh-field">
                <span>nx</span>
                <input aria-label="Duvar normal nx" value={nx} disabled={busy} onChange={(e) => setNx(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>ny</span>
                <input aria-label="Duvar normal ny" value={ny} disabled={busy} onChange={(e) => setNy(e.target.value)} />
              </label>
              <label className="mesh-field">
                <span>nz</span>
                <input aria-label="Duvar normal nz" value={nz} disabled={busy} onChange={(e) => setNz(e.target.value)} />
              </label>
            </div>
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
      </section>

      <p className="crash-q-title">3 · Tutma</p>
      {partIds.length > 0 && (
        <>
          <p className="material-assignments-title">Parçalar</p>
          <table className="doe-table crash-parts" data-testid="crash-parts">
            <thead>
              <tr>
                <th>parça</th>
                <th>malzeme</th>
                <th>rol</th>
                <th>kart</th>
                {isShell && <th>t (mm)</th>}
              </tr>
            </thead>
            <tbody>
              {partIds.map((pid) => {
                const mat = materialAssignments.find((a) => a.part_id === pid)?.material_name;
                const role = partRoles[pid] ?? "moving";
                return (
                  <tr
                    key={pid}
                    className={selectedPartIds.includes(pid) ? "crash-part-selected" : undefined}
                    onMouseEnter={() => onPartHover?.(pid)}
                    onMouseLeave={() => onPartHover?.(null)}
                  >
                    <td>
                      <button
                        type="button"
                        className="crash-part-pick"
                        aria-pressed={selectedPartIds.includes(pid)}
                        title="Viewport'ta göster"
                        onClick={() => onPartSelect?.(pid)}
                      >
                        #{pid}
                      </button>
                    </td>
                    <td className={mat ? undefined : "crash-part-missing"}>{mat ?? "atama yok"}</td>
                    <td>
                      <span className="doe-seg" role="group" aria-label={`Parça ${pid} rolü`}>
                        <button
                          type="button"
                          className={role === "moving" ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === "moving"}
                          title="İlk hızı alır (ilk hız kartı yoksa bariyer hızı); rijit duvarla temas eder"
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: "moving" }))}
                        >
                          Hareketli
                        </button>
                        <button
                          type="button"
                          className={role === "fixed" ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === "fixed"}
                          title="Tüm düğümleri /BCS ile kilitli; ilk hız almaz"
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: "fixed" }))}
                        >
                          Sabit
                        </button>
                        <button
                          type="button"
                          className={role === "free" ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === "free"}
                          title="İlk hız almaz, kilitlenmez — yalnız temasla hareket eder"
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: "free" }))}
                        >
                          Serbest
                        </button>
                      </span>
                    </td>
                    <td>
                      <span className="doe-seg" role="group" aria-label={`Parça ${pid} kartı`}>
                        <button
                          type="button"
                          className={partCards[pid] ? "doe-seg-opt" : "doe-seg-opt active"}
                          aria-pressed={!partCards[pid]}
                          disabled={busy}
                          onClick={() =>
                            setPartCards((c) => {
                              const next = { ...c };
                              delete next[pid];
                              return next;
                            })
                          }
                        >
                          Global
                        </button>
                        <button
                          type="button"
                          className={partCards[pid] ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={Boolean(partCards[pid])}
                          disabled={busy}
                          onClick={() => setPartCards((c) => (c[pid] ? c : { ...c, [pid]: { ...matCard } }))}
                        >
                          Ayrı
                        </button>
                      </span>
                    </td>
                    {isShell && (
                      <td
                        data-testid={`crash-part-t-${pid}`}
                        className={componentThickness[pid] ? undefined : "crash-part-missing"}
                      >
                        {componentThickness[pid] ? `${componentThickness[pid]}` : "yok"}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="material-assign-hint">
            Rol açıklamaları düğme ipucunda. Her parçaya malzeme atanmalı (3 · Material).
            Kart: Global = aşağıdaki ortak kart; Ayrı = parçanın kendi kartı (global kartın o
            anki kopyasıyla açılır).
          </p>
        </>
      )}

      <CrashLoadCards
        cards={loadCards}
        onChange={setLoadCards}
        partIds={partIds}
        regions={regions}
        roles={partRoles}
        disabled={busy}
      />


      <p className="material-assignments-title">
        {Object.keys(partCards).length > 0 ? "Malzeme kartı — global" : "Malzeme kartı"}
      </p>
      <CrashMaterialCard value={matCard} onChange={setMatCard} disabled={busy} testId="crash-mat-global" />
      {partIds
        .filter((pid) => partCards[pid])
        .map((pid) => (
          <div key={pid} className="crash-contact-card crash-mat-part">
            <div className="crash-contact-head">
              <strong>Parça #{pid} — malzeme kartı</strong>
            </div>
            <CrashMaterialCard
              value={partCards[pid]}
              onChange={(next) => setPartCards((c) => ({ ...c, [pid]: next }))}
              disabled={busy}
              testId={`crash-mat-part-${pid}`}
            />
          </div>
        ))}

      <details className="crash-advanced">
        <summary>İleri ayarlar — eleman formülasyonu, hourglass</summary>
      {isShell ? (
        <>
          <p className="material-assignments-title">Kabuk — /PROP/TYPE1</p>
          <div className="mesh-grid">
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
          <p className="material-assignments-title">Hourglass kontrolü — /PROP/TYPE1</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>Hm</span>
              <input aria-label="Hourglass Hm" value={hgHm} onChange={(e) => setHgHm(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Hf</span>
              <input aria-label="Hourglass Hf" value={hgHf} onChange={(e) => setHgHf(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Hr</span>
              <input aria-label="Hourglass Hr" value={hgHr} onChange={(e) => setHgHr(e.target.value)} />
            </label>
          </div>
          <p className="material-assign-hint">
            Hm membran, Hf düzlem dışı, Hr dönme katsayısı; aralık 0…0.05, 0 = Radioss
            varsayılanı (0.01). Ishell 1–4 hourglass formülasyonlarında etkili.
          </p>
          <p className="material-assign-hint">
            Kalınlık ürün ağacından (3 · Material → bileşen kalınlığı); burada yalnız
            gösterilir. Bayraklarda 0 = Radioss /DEF_SHELL varsayılanı. N: 0, 1 ya da 3…10.
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
          <label className="mesh-field">
            <span>h (hourglass)</span>
            <input aria-label="Hourglass h" value={hgSolid} onChange={(e) => setHgSolid(e.target.value)} />
          </label>
        </div>
        <p className="material-assign-hint">
          h: hourglass viskozite katsayısı, aralık 0…0.15, 0 = Radioss varsayılanı (0.10).
        </p>
        </>
      )}
      </details>

      <p className="material-assignments-title">Çıktı ve kontrol</p>
      <CrashOutputCard value={output} onChange={setOutput} partOptions={partOptions} disabled={busy} />

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
          {/* 1.17g — iş bitince hub'ın son cycle değeri ("cycle 1") gösterilmez */}
          {polling && snapshot?.cycle != null && (
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
              {scalars.hourglass_energy_final != null && (
                <li>
                  HG_final {fmt(scalars.hourglass_energy_final)} · HG/IE {fmt(scalars.hourglass_ratio)}
                </li>
              )}
              <li>RWALL Fmax {fmt(scalars.rwall_force_max)}</li>
              {scalars.rwall_impulse_final != null && (
                <li>RWALL impuls {fmt(scalars.rwall_impulse_final)} N·s</li>
              )}
              {sectionPeaks.map((m) => (
                <li key={m[0]}>
                  Kesit {m[1]} Fmax {fmt(scalars[m[0]])} kN · impuls{" "}
                  {fmt(scalars[`section_${m[1]}_impulse_final`])} N·s
                </li>
              ))}
              {cfcPeaks.map((k) => (
                <li key={k} data-testid="crash-cfc-peak">
                  {k.replace(/_cfc(\d+)$/, "")} CFC{/_cfc(\d+)$/.exec(k)?.[1]} {fmt(scalars[k])}
                </li>
              ))}
              {scalars.timestep_min != null && (
                <li data-testid="crash-timestep">
                  Δt_min {fmt(scalars.timestep_min)} ms
                  {scalars.mass_added_rel ? ` · eklenen kütle %${(scalars.mass_added_rel * 100).toFixed(1)}` : ""}
                </li>
              )}
              {scalars.elements_deleted != null && (
                <li data-testid="crash-deleted">
                  Silinen eleman {scalars.elements_deleted}
                  {scalars.deletion_time_first != null
                    ? ` · ilk ≤ ${fmt(scalars.deletion_time_first)} ms · son ≤ ${fmt(scalars.deletion_time_last)} ms`
                    : ""}
                </li>
              )}
              {contactPeaks.map((m) => (
                <li key={m[0]}>
                  Temas {m[1]} Fmax {fmt(scalars[m[0]])} kN · impuls{" "}
                  {fmt(scalars[`contact_${m[1]}_impulse_final`])} N·s
                </li>
              ))}
            </ul>
          )}
          {(starterMsgs.errors.length > 0 || starterMsgs.warnings.length > 0) && (
            <p className="material-assign-hint" data-testid="crash-starter-msgs">
              Starter
              {starterMsgs.errors.length > 0 ? ` · hata ID ${starterMsgs.errors.join(", ")}` : " · 0 hata"}
              {starterMsgs.warnings.length > 0 ? ` · uyarı ID ${starterMsgs.warnings.join(", ")}` : ""}
            </p>
          )}
          {curves?.time && forceSeries.length > 0 && (
            <CrashForceChart time={curves.time} series={forceSeries} />
          )}
        </div>
      )}

      <CrashCatalog />
      <CrashScenarioCard onDone={() => setScenarioTick((t) => t + 1)} onGeometry={onScenarioGeometry} />
      <CrashHistory
        geometryId={geometryId}
        refreshKey={`${jobId ?? ""}:${status ?? ""}:${scenarioTick}`}
        activeAnimId={animRunId}
        onAnimate={onAnimateRun}
      />
      <CrashValidation />
    </div>
  );
}
