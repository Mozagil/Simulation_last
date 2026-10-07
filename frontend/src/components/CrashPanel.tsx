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
import CrashLoadCards, { cardsPayload, type LoadCard } from "./CrashLoadCards";
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

type ObstacleKind = "wall" | "part" | "none";
type BehaviorKind = "impact" | "driven" | "fixed" | "free";
type PanelTab = "setup" | "scenario" | "history" | "catalog";

export interface PartBehavior {
  kind: BehaviorKind;
  speed: string;
  dir: [string, string, string];
  drive: string;
  axis: "X" | "Y" | "Z";
}

const defaultBehavior = (): PartBehavior => ({ kind: "impact", speed: "10", dir: ["0", "0", "-1"], drive: "-1", axis: "Z" });

const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: "setup", label: "Model kur" },
  { id: "scenario", label: "Hızlı senaryo" },
  { id: "history", label: "Geçmiş" },
  { id: "catalog", label: "Katalog & validasyon" },
];

export const BEHAVIOR_OPTIONS: { id: BehaviorKind; label: string; hint: string }[] = [
  { id: "impact", label: "Çarpıyor (ilk hız)", hint: "t = 0'da bu hızla fırlatılır, sonra serbest — çarpınca yavaşlar." },
  { id: "driven", label: "Sürülüyor (sabit hız)", hint: "Tüm süre boyunca bu hızla itilir (pres / piston gibi); yavaşlamaz." },
  { id: "fixed", label: "Sabit", hint: "Tamamen kilitli; hiç hareket etmez (ör. duvara bağlı plaka)." },
  { id: "free", label: "Serbest", hint: "Hızı yok, kilitli değil — yalnız başka parça çarpınca hareket eder." },
];

const OBSTACLE_OPTIONS: { id: ObstacleKind; label: string; title: string }[] = [
  { id: "wall", label: "Rijit duvar", title: "Sonsuz, hiç ezilmeyen düz duvar (/RWALL). Nokta ve normal ile konumlanır." },
  { id: "part", label: "Diğer parça", title: "Modeldeki başka bir parçaya çarpar — aşağıda temas tanımlanır (/INTER)." },
  { id: "none", label: "Hiçbiri", title: "Engel yok (ör. yalnız sürülen / serbest bırakılan parça)." },
];

export function roleOf(kind: BehaviorKind): "moving" | "fixed" | "free" {
  return kind === "fixed" ? "fixed" : kind === "free" ? "free" : "moving";
}

/** Parça davranışları → ilk hız / dayatılmış hız kartları (+ Gelişmiş kartlar). */
export function mergedLoads(
  partIds: number[],
  behaviorOf: (pid: number) => PartBehavior,
  extra: ReturnType<typeof cardsPayload>,
) {
  const n = (raw: string, label: string) => {
    const v = Number(raw);
    if (raw.trim() === "" || !Number.isFinite(v)) throw new Error(`${label}: sayı olmalı.`);
    return v;
  };
  const initial: Record<string, unknown>[] = [];
  const imposed: Record<string, unknown>[] = [];
  for (const pid of partIds) {
    const b = behaviorOf(pid);
    if (b.kind === "impact") {
      const dir = b.dir.map((d, k) => n(d, `Parça #${pid} yön ${"xyz"[k]}`));
      if (dir.every((d) => d === 0)) throw new Error(`Parça #${pid}: yön vektörü sıfır olamaz.`);
      initial.push({ name: `parca_${pid}`, part_id: pid, speed_m_s: n(b.speed, `Parça #${pid} hız`), direction: dir });
    } else if (b.kind === "driven") {
      imposed.push({ name: `parca_${pid}`, part_id: pid, direction: b.axis, velocity_m_s: n(b.drive, `Parça #${pid} sürme hızı`), t_start_ms: 0, t_stop_ms: 0 });
    }
  }
  return {
    initial_velocities: [...initial, ...extra.initial_velocities],
    imposed_velocities: [...imposed, ...extra.imposed_velocities],
    boundary_conditions: extra.boundary_conditions,
    rigid_bodies: extra.rigid_bodies,
  };
}

const vecText = (d: [string, string, string]) => `(${d.join(", ")})`;

/** Kurulumun düz Türkçe özeti — öneri değil, ne kurulduğunun okunuşu. */
export function describeSetup(o: {
  parts: { pid: number; b: PartBehavior }[];
  obstacle: ObstacleKind;
  contacts: number;
  gravity: string | null;
  tEnd: string;
  extraCards: number;
  /** Rijit duvar normali (yalnız engel = duvar) — yön kontrolü için. */
  wallNormal?: [string, string, string];
}): string[] {
  const lines = o.parts.map(({ pid, b }) => {
    if (b.kind === "impact") return `Parça #${pid}: t = 0'da ${b.speed} m/s ile ${vecText(b.dir)} yönünde başlıyor, sonra serbest.`;
    if (b.kind === "driven") return `Parça #${pid}: süre boyunca ${b.axis} ekseninde ${b.drive} m/s ile sürülüyor.`;
    if (b.kind === "fixed") return `Parça #${pid}: kilitli, hareket etmiyor.`;
    return `Parça #${pid}: serbest — yalnız temasla hareket eder.`;
  });
  lines.push(
    o.obstacle === "wall"
      ? "Engel: rijit duvar (çarpan ve sürülen parçalar duvarla temas eder)."
      : o.obstacle === "part"
        ? `Engel: diğer parça — ${o.contacts} temas tanımı.`
        : "Engel yok.",
  );
  if (o.obstacle !== "part" && o.contacts > 0) lines.push(`Ek temas: ${o.contacts} tanım (ör. self-contact).`);
  if (o.gravity) lines.push(`Yerçekimi: ${o.gravity}.`);
  if (o.extraCards > 0) lines.push(`Gelişmiş: ${o.extraCards} ek kart.`);
  lines.push(`Süre: ${o.tEnd} ms.`);
  if (o.obstacle === "wall" && o.wallNormal) {
    const nrm = o.wallNormal.map(Number);
    for (const { pid, b } of o.parts) {
      if (b.kind !== "impact") continue;
      const dot = b.dir.reduce((acc, d, k) => acc + Number(d) * nrm[k], 0);
      if (Number.isFinite(dot) && dot >= 0) lines.push(`⚠ Parça #${pid} duvara doğru gitmiyor (yön · duvar normali = ${dot}).`);
    }
  }
  const moving = o.parts.some(({ b }) => b.kind === "impact" || b.kind === "driven");
  if (!moving && !o.gravity) lines.push("⚠ Hiçbir parça hareket etmiyor ve yerçekimi yok — yük tanımlı değil.");
  if (o.obstacle === "part" && o.contacts === 0) lines.push("⚠ Diğer parça seçili ama temas tanımı yok — parçalar birbirinin içinden geçer.");
  return lines;
}

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
  // Sadeleştirilmiş kurulum (kullanıcı 2026-10-07): her parça için tek soru —
  // "bu parça ne yapıyor?". Hız yalnız buradan girilir.
  const [behaviors, setBehaviors] = useState<Record<number, PartBehavior>>({});
  // TODO 11.9 — kart tabanlı yükleme / tutma
  const [loadCards, setLoadCards] = useState<LoadCard[]>([]);
  // Temas tanımları (1.12): varsayılan yok — mühendis satır ekler.
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const [obstacle, setObstacle] = useState<ObstacleKind>("wall");
  const useRigidWall = obstacle === "wall";
  const [gravOn, setGravOn] = useState(false);
  const [gravAccel, setGravAccel] = useState("-9.81");
  const [tab, setTab] = useState<PanelTab>("setup");
  const [gravDir, setGravDir] = useState<"X" | "Y" | "Z">("Z");
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

  const behaviorOf = (pid: number): PartBehavior => behaviors[pid] ?? defaultBehavior();
  function setBehavior(pid: number, patch: Partial<PartBehavior>) {
    setBehaviors((b) => ({ ...b, [pid]: { ...(b[pid] ?? defaultBehavior()), ...patch } }));
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
        // Hız parçalardan (İlk hız / Dayatılmış hız kartları); bariyer yalnız duvar geometrisi.
        barrier: {
          speed_m_s: 0,
          angle_deg: 0,
          wall: {
            point: [num(wx), num(wy), num(wz)],
            normal: [num(nx), num(ny), num(nz)],
          },
        },
        ...(gravOn ? { gravity: { accel_m_s2: num(gravAccel), direction: gravDir } } : {}),
        dimension: isShell ? 2 : 3,
        run_solver: runSolver,
        wait: false,
        t_end_ms: num(tEnd),
        parts: partOptions.map(
          (pid): CrashPartSpec => ({
            part_id: pid,
            role: roleOf(behaviorOf(pid).kind),
            ...(partCards[pid] ? { model: modelFor(partCards[pid], `Parça #${pid}`) } : {}),
          }),
        ),
        contacts: contacts.map(contactPayload),
        use_rigid_wall: useRigidWall,
        ...mergedLoads(partOptions, behaviorOf, cardsPayload(loadCards)),
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
        Üç adım: her parçanın ne yaptığını seç, neye çarptığını seç, çalıştır. Önce mesh ve her
        parçaya malzeme gerekir (2 · Mesh, 3 · Material).
      </p>
      {meshDimension !== 2 && meshDimension !== 3 && (
        <p className="material-assign-hint">Mesh yok — crash 3D (solid) ya da 2D (kabuk) mesh ister.</p>
      )}
      {geometryId == null && (
        <p className="material-assign-hint">Önce geometri yükleyin.</p>
      )}

      <div className="crash-tabs doe-seg" role="tablist" aria-label="Crash paneli">
        {PANEL_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "doe-seg-opt active" : "doe-seg-opt"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "setup" && (
      <>
      <section className="crash-q" aria-label="Parçalar">
        <p className="crash-q-title">1 · Parçalar — bu parça ne yapıyor?</p>
        <div className="crash-behaviors" data-testid="crash-parts">
          {partOptions.map((pid) => {
            const b = behaviorOf(pid);
            const mat = materialAssignments.find((a) => a.part_id === pid)?.material_name;
            const selected = selectedPartIds.includes(pid);
            return (
              <div
                key={pid}
                className={selected ? "crash-behavior crash-part-selected" : "crash-behavior"}
                onMouseEnter={() => onPartHover?.(pid)}
                onMouseLeave={() => onPartHover?.(null)}
              >
                <div className="crash-behavior-head">
                  <button
                    type="button"
                    className="crash-part-pick"
                    aria-pressed={selected}
                    title="Viewport'ta göster"
                    onClick={() => onPartSelect?.(pid)}
                  >
                    #{pid}
                  </button>
                  <span className={mat ? "crash-behavior-mat" : "crash-behavior-mat crash-part-missing"}>
                    {mat ?? "malzeme yok"}
                    {isShell ? ` · t ${componentThickness[pid] ?? "yok"} mm` : ""}
                  </span>
                  <select
                    aria-label={`Parça ${pid} davranışı`}
                    value={b.kind}
                    disabled={busy}
                    onChange={(e) => setBehavior(pid, { kind: e.target.value as BehaviorKind })}
                  >
                    {BEHAVIOR_OPTIONS.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="crash-behavior-hint">{BEHAVIOR_OPTIONS.find((o) => o.id === b.kind)?.hint}</p>
                {b.kind === "impact" && (
                  <div className="crash-behavior-fields">
                    <label>
                      <span>hız (m/s)</span>
                      <input aria-label={`Parça ${pid} hız`} value={b.speed} disabled={busy} onChange={(e) => setBehavior(pid, { speed: e.target.value })} />
                    </label>
                    {(["x", "y", "z"] as const).map((ax, k) => (
                      <label key={ax}>
                        <span>yön {ax}</span>
                        <input
                          aria-label={`Parça ${pid} yön ${ax}`}
                          value={b.dir[k]}
                          disabled={busy}
                          onChange={(e) => {
                            const dir = [...b.dir] as [string, string, string];
                            dir[k] = e.target.value;
                            setBehavior(pid, { dir });
                          }}
                        />
                      </label>
                    ))}
                  </div>
                )}
                {b.kind === "driven" && (
                  <div className="crash-behavior-fields">
                    <label>
                      <span>hız (m/s, işaretli)</span>
                      <input aria-label={`Parça ${pid} sürme hızı`} value={b.drive} disabled={busy} onChange={(e) => setBehavior(pid, { drive: e.target.value })} />
                    </label>
                    <label>
                      <span>eksen</span>
                      <select aria-label={`Parça ${pid} sürme ekseni`} value={b.axis} disabled={busy} onChange={(e) => setBehavior(pid, { axis: e.target.value as "X" | "Y" | "Z" })}>
                        <option>X</option>
                        <option>Y</option>
                        <option>Z</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="crash-q" aria-label="Neye çarpıyor">
        <p className="crash-q-title">2 · Neye çarpıyor?</p>
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
        <p className="crash-behavior-hint">{OBSTACLE_OPTIONS.find((o) => o.id === obstacle)?.title}</p>
        {obstacle === "wall" && (
          <>
            {(
              [
                ["duvarın bir noktası (mm)", "nokta", [["x", wx, setWx], ["y", wy, setWy], ["z", wz, setWz]]],
                ["duvarın yüzü hangi yöne bakıyor (normal)", "normal", [["x", nx, setNx], ["y", ny, setNy], ["z", nz, setNz]]],
              ] as const
            ).map(([title, key, fields]) => (
              <div key={key} className="crash-wall-row">
                <span className="crash-behavior-hint">{title}</span>
                <div className="crash-behavior-fields">
                  {fields.map(([ax, v, set]) => (
                    <label key={ax}>
                      <span>{ax}</span>
                      <input aria-label={`Duvar ${key} ${ax}`} value={v} disabled={busy} onChange={(e) => set(e.target.value)} />
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
        <p className="material-assignments-title">Temaslar (parça–parça, self-contact)</p>
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

      <section className="crash-q" aria-label="Ortam">
        <p className="crash-q-title">3 · Süre ve ortam</p>
        <div className="crash-behavior-fields">
          <label>
            <span>süre (ms)</span>
            <input aria-label="Süre (ms)" value={tEnd} disabled={busy} onChange={(e) => setTEnd(e.target.value)} />
          </label>
          <label className="crash-grav-check">
            <input type="checkbox" checked={gravOn} disabled={busy} onChange={(e) => setGravOn(e.target.checked)} />
            <span>yerçekimi</span>
          </label>
          {gravOn && (
            <>
              <label>
                <span>g (m/s²)</span>
                <input aria-label="Yerçekimi ivmesi" value={gravAccel} disabled={busy} onChange={(e) => setGravAccel(e.target.value)} />
              </label>
              <label>
                <span>eksen</span>
                <select aria-label="Yerçekimi ekseni" value={gravDir} disabled={busy} onChange={(e) => setGravDir(e.target.value as "X" | "Y" | "Z")}>
                  <option>X</option>
                  <option>Y</option>
                  <option>Z</option>
                </select>
              </label>
            </>
          )}
        </div>
      </section>

      <section className="crash-summary" aria-label="Özet" data-testid="crash-summary">
        <p className="crash-q-title">Özet</p>
        {describeSetup({
          parts: partOptions.map((pid) => ({ pid, b: behaviorOf(pid) })),
          obstacle,
          contacts: contacts.length,
          gravity: gravOn ? `${gravAccel} m/s² ${gravDir}` : null,
          tEnd,
          extraCards: loadCards.length,
          wallNormal: [nx, ny, nz],
        }).map((line, i) => (
          <p key={i} className={line.startsWith("⚠") ? "crash-summary-line warn" : "crash-summary-line"}>
            {line}
          </p>
        ))}
      </section>

      <details className="crash-advanced">
        <summary>Gelişmiş — bölgeye sınır koşulu, ek kütle, rijit gövde</summary>
        <p className="material-assign-hint">
          Parçanın tamamı yukarıda tanımlanır. Buradaki kartlar bir bölgeye (yüzey grubu) ya da parçaya
          ek tanım ekler: ör. yalnız taban yüzeyini kilitlemek, kızak kütlesi eklemek.
        </p>
        <CrashLoadCards
          cards={loadCards}
          onChange={setLoadCards}
          partIds={partOptions}
          regions={regions}
          roles={{}}
          disabled={busy}
          showCoverage={false}
        />
      </details>

      <p className="material-assignments-title">
        {Object.keys(partCards).length > 0 ? "Malzeme kartı — global" : "Malzeme kartı"}
      </p>
      {partOptions.length > 1 && (
        <div className="crash-mat-toggles">
          {partOptions.map((pid) => (
            <div key={pid} className="crash-mat-toggle">
              <span>#{pid}</span>
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
            </div>
          ))}
          <span className="crash-behavior-hint">Global = aşağıdaki ortak kart; Ayrı = parçanın kendi kartı.</span>
        </div>
      )}
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

      </>
      )}

      {tab === "scenario" && (
        <>
          <CrashSchematic />
          <CrashScenarioCard onDone={() => setScenarioTick((t) => t + 1)} onGeometry={onScenarioGeometry} />
        </>
      )}
      {tab === "history" && (
        <CrashHistory
          geometryId={geometryId}
          refreshKey={`${jobId ?? ""}:${status ?? ""}:${scenarioTick}`}
          activeAnimId={animRunId}
          onAnimate={onAnimateRun}
        />
      )}
      {tab === "catalog" && (
        <>
          <CrashCatalog />
          <CrashValidation />
        </>
      )}
    </div>
  );
}
