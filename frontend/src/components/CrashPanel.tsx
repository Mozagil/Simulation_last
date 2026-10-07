import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
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
import { defaultMatCard, matCardPayload, type MatCardState } from "./CrashMaterialCard";
import CrashMaterialSection, { matCardSummary } from "./CrashMaterialSection";
import type { CrashMarkers } from "./GeometryViewer";
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

type PanelTab = "setup" | "scenario" | "history" | "catalog";
type DirPreset = "+X" | "-X" | "+Y" | "-Y" | "+Z" | "-Z" | "custom";
type GroupState = string;

const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: "setup", label: "Model kur" },
  { id: "scenario", label: "Hızlı senaryo" },
  { id: "history", label: "Geçmiş" },
  { id: "catalog", label: "Katalog & validasyon" },
];

const DIR_PRESETS: { id: DirPreset; v: number[] }[] = [
  { id: "+X", v: [1, 0, 0] },
  { id: "-X", v: [-1, 0, 0] },
  { id: "+Y", v: [0, 1, 0] },
  { id: "-Y", v: [0, -1, 0] },
  { id: "+Z", v: [0, 0, 1] },
  { id: "-Z", v: [0, 0, -1] },
  { id: "custom", v: [0, 0, 1] },
];

export const ROLE_OPTIONS: { id: PartRole; label: string; short: string; hint: string }[] = [
  { id: "moving", label: "Hareketli", short: "hareketli", hint: "Çarpma hızını alır; rijit duvarla temas eder." },
  { id: "fixed", label: "Sabit", short: "sabit", hint: "Tamamen kilitli; hiç hareket etmez." },
  { id: "free", label: "Serbest", short: "serbest", hint: "Hızı yok, kilitli değil — yalnız temasla hareket eder." },
];

export function parseTriple(raw: string): [number, number, number] | null {
  const parts = raw.split(/[\s,;]+/).filter(Boolean).map(Number);
  return parts.length === 3 && parts.every(Number.isFinite) ? (parts as [number, number, number]) : null;
}

/** [0,0,-1] → "−Z"; eksen dışı vektör → "(a, b, c)". */
export function vecLabel(v: number[]): string {
  const nz = v.map((c, i) => [c, i] as const).filter(([c]) => c !== 0);
  if (nz.length === 1) return `${nz[0][0] > 0 ? "+" : "−"}${"XYZ"[nz[0][1]]}`;
  return `(${v.join(", ")})`;
}

function wallLabel(normal: number[], p: [number, number, number] | null): string {
  if (!p) return "konum ?";
  const nz = normal.map((c, i) => [c, i] as const).filter(([c]) => c !== 0);
  if (nz.length === 1) return `${"xyz"[nz[0][1]]}=${p[nz[0][1]]}`;
  return `(${p.join(", ")})`;
}

function AccHead({
  n,
  title,
  summary,
  state,
  open,
  onToggle,
}: {
  n: number;
  title: string;
  summary: string;
  state: GroupState;
  open: boolean;
  onToggle: () => void;
}) {
  const cls = state === "hazır" ? "ok" : state.endsWith("eksik") ? "warn" : "muted";
  return (
    <button type="button" className="crash-acc-toggle" aria-expanded={open} onClick={onToggle}>
      <span className="crash-acc-n">{n}</span>
      <span className="crash-acc-text">
        <strong>{title}</strong>
        <span className="crash-acc-summary">{summary}</span>
      </span>
      <span className={`crash-acc-state ${cls}`}>{state}</span>
      <span className="crash-acc-chev" aria-hidden="true">{open ? "▴" : "▾"}</span>
    </button>
  );
}

function UnitField({
  label,
  unit,
  value,
  onChange,
  disabled,
  placeholder,
  hideLabel,
  wide,
  ariaLabel,
}: {
  label: string;
  unit: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  hideLabel?: boolean;
  wide?: boolean;
  ariaLabel?: string;
}) {
  return (
    <label className={wide ? "crash-unit-field wide" : "crash-unit-field"}>
      {!hideLabel && <span>{label}</span>}
      <span className="crash-unit-box">
        <input aria-label={ariaLabel ?? label} value={value} placeholder={placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        {unit && <em>{unit}</em>}
      </span>
    </label>
  );
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
  material,
  onMarkersChange,
  onRequestPointPick,
  pickingPoint = false,
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
  /** Kullanıcı 2026-10-07: malzeme modeli 3 · Material adımında (state App'te).
   * Verilirse panel yalnız özet gösterir; verilmezse kart burada (bağımsız kullanım). */
  material?: {
    matCard: MatCardState;
    setMatCard: (next: MatCardState) => void;
    partCards: Record<number, MatCardState>;
    setPartCards: Dispatch<SetStateAction<Record<number, MatCardState>>>;
  };
  /** Viewport işaretleri (duvar düzlemi, hız oku, parça rol etiketleri). */
  onMarkersChange?: (markers: CrashMarkers | null) => void;
  /** "Modelden seç": viewport'ta tıklanan nokta geri verilir. */
  onRequestPointPick?: (done: (p: [number, number, number]) => void) => void;
  pickingPoint?: boolean;
}) {
  // Parça rolleri: mühendis seçer; varsayılan hepsi hareketli (tek parçalı
  // eski davranışla aynı). Sabit parça /BCS ile tutulur, ilk hız almaz.
  // Sadeleştirilmiş kurulum (kullanıcı 2026-10-07): her parça için tek soru —
  // "bu parça ne yapıyor?". Hız yalnız buradan girilir.
  const [partRoles, setPartRoles] = useState<Record<number, PartRole>>({});
  // Claude Design "Crash BC Sidebar" (2026-10-07): üç akordeon grubu.
  const [openGroup, setOpenGroup] = useState<1 | 2 | 3 | null>(1);
  const [impactMode, setImpactMode] = useState<"wall" | "free">("wall");
  const [speed, setSpeed] = useState("10");
  const [angle, setAngle] = useState("0");
  const [dirPreset, setDirPreset] = useState<DirPreset>("+Z");
  const [customDir, setCustomDir] = useState<[string, string, string]>(["0", "0", "1"]);
  const [wallPoint, setWallPoint] = useState("0, 0, 0");
  // TODO 11.9 — kart tabanlı yükleme / tutma
  const [loadCards, setLoadCards] = useState<LoadCard[]>([]);
  // Temas tanımları (1.12): varsayılan yok — mühendis satır ekler.
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const useRigidWall = impactMode === "wall";
  const [gravOn, setGravOn] = useState(false);
  const [gravAccel, setGravAccel] = useState("-9.81");
  const [tab, setTab] = useState<PanelTab>("setup");
  const [gravDir, setGravDir] = useState<"X" | "Y" | "Z">("Z");
  const [tEnd, setTEnd] = useState("10");
  // Malzeme kartı (1.14e): global kart + isteğe bağlı parça başına kart (1.14b).
  // partCards'ta olmayan parça global karta düşer.
  const [ownMatCard, setOwnMatCard] = useState<MatCardState>(defaultMatCard);
  const [ownPartCards, setOwnPartCards] = useState<Record<number, MatCardState>>({});
  const matCard = material?.matCard ?? ownMatCard;
  const setMatCard = material?.setMatCard ?? setOwnMatCard;
  const partCards = material?.partCards ?? ownPartCards;
  const setPartCards = material?.setPartCards ?? setOwnPartCards;
  // 1.15d — engine / TH / kesit ayarları; boş = backend varsayılanı (eski deck)
  const [output, setOutput] = useState<OutputState>(defaultOutput);
  /** 1.17g-7 — hızlı senaryo başlayınca / bitince geçmişi yenile */
  const [scenarioTick, setScenarioTick] = useState(0);
  const [isolid, setIsolid] = useState("1");
  const [ismstr, setIsmstr] = useState("");
  const [nip, setNip] = useState("1");
  // Kabuk (2D mesh) — /PROP/TYPE1. 0 = Radioss /DEF_SHELL varsayılanı; öneri yok.
  const [ishell, setIshell] = useState("");
  const [ish3n, setIsh3n] = useState("");
  const [shellIsmstr, setShellIsmstr] = useState("");
  const [shellNip, setShellNip] = useState("");
  // 1.17h — hourglass kontrolü; 0 = Radioss varsayılanı
  const [hgHm, setHgHm] = useState("");
  const [hgHf, setHgHf] = useState("");
  const [hgHr, setHgHr] = useState("");
  const [hgSolid, setHgSolid] = useState("");
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
        gapmin: "",
        istf: "",
        inacti: "",
        iedge: "",
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

  const toggleGroup = (g: 1 | 2 | 3) => setOpenGroup((cur) => (cur === g ? null : g));
  // Yön: duvar modunda düğme duvar normalidir (parça tersine gider); duvarsızda doğrudan hız yönü.
  const dirVec: number[] =
    dirPreset === "custom" ? customDir.map(Number) : DIR_PRESETS.find((d) => d.id === dirPreset)!.v;
  const approachDir = dirVec.map((c) => (c === 0 ? 0 : -c));
  const wallXYZ = parseTriple(wallPoint);

  // --- grup özetleri / hazır durumu (öneri değil: eksik bilginin listesi) ---
  const speedOk = Number.isFinite(Number(speed)) && speed.trim() !== "" && Number(speed) >= 0;
  const dirOk = dirVec.every(Number.isFinite) && dirVec.some((c) => c !== 0);
  const tEndOk = Number.isFinite(Number(tEnd)) && Number(tEnd) > 0;
  const impactMissing = [
    !speedOk && "Çarpma: hız sayı olmalı",
    !dirOk && "Çarpma: yön vektörü sıfır ya da geçersiz",
    !tEndOk && "Çarpma: süre pozitif olmalı",
    impactMode === "wall" && !wallXYZ && "Çarpma: duvar konumu 'x, y, z' olmalı",
  ].filter(Boolean) as string[];
  const impactState: GroupState = impactMissing.length ? `${impactMissing.length} eksik` : "hazır";
  const impactSummary =
    `${speed} m/s · ${vecLabel(impactMode === "wall" ? approachDir : dirVec)} yönü · ` +
    (impactMode === "wall" ? `rijit duvar ${wallLabel(dirVec, wallXYZ)}` : "duvarsız");
  const roleOfPart = (pid: number): PartRole => partRoles[pid] ?? "moving";
  const partsSummary = partOptions.map((pid) => `#${pid} ${ROLE_OPTIONS.find((o) => o.id === roleOfPart(pid))!.short}`).join(" · ");
  const noMaterial = partOptions.filter((pid) => materialAssignments.length > 0 && !materialAssignments.some((a) => a.part_id === pid && a.material_name));
  const partsMissing = [
    !partOptions.some((pid) => roleOfPart(pid) === "moving") && !gravOn && "Parçalar: hareketli parça yok",
    noMaterial.length > 0 && `Parçalar: malzemesiz ${noMaterial.map((p) => "#" + p).join(", ")}`,
  ].filter(Boolean) as string[];
  const partsState: GroupState = partsMissing.length ? `${partsMissing.length} eksik` : "hazır";
  const contactsSummary = contacts.length
    ? contacts.map((c) => (c.master === c.slave ? `#${c.master} kendi kendine` : `#${c.slave}→#${c.master}`)).join(" · ")
    : "temas yok";
  const contactsMissing =
    impactMode === "free" && contacts.length === 0 && partOptions.length > 1 ? ["Temaslar: duvarsız çarpmada parçalar arası temas yok"] : [];
  const contactsState: GroupState = contactsMissing.length ? `${contactsMissing.length} eksik` : contacts.length ? "hazır" : "isteğe bağlı";
  const readyCount = [impactState, partsState, contactsState].filter((st) => !st.endsWith("eksik")).length;
  // --- viewport işaretleri: panel değişince App'e bildir ---
  const markers: CrashMarkers = {
    wall: impactMode === "wall" && wallXYZ && dirOk ? { point: wallXYZ, normal: dirVec as [number, number, number] } : null,
    velocity:
      speedOk && dirOk
        ? { dir: (impactMode === "wall" ? approachDir : dirVec) as [number, number, number], label: `${speed} m/s` }
        : null,
    partLabels: Object.fromEntries(
      partOptions.map((pid) => [pid, `#${pid} ${ROLE_OPTIONS.find((o) => o.id === roleOfPart(pid))!.short}`]),
    ),
    partRoles: Object.fromEntries(partOptions.map((pid) => [pid, roleOfPart(pid)])),
  };
  const markersKey = JSON.stringify(markers);
  useEffect(() => {
    onMarkersChange?.(JSON.parse(markersKey) as CrashMarkers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markersKey]);
  useEffect(() => () => onMarkersChange?.(null), []); // eslint-disable-line react-hooks/exhaustive-deps

  const blockers = [
    ...(meshDimension !== 2 && meshDimension !== 3 ? ["Önce mesh üretin (2 · Mesh)"] : []),
    ...impactMissing,
    ...partsMissing,
    ...contactsMissing,
  ];

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
        // Ortak çarpma hızı hareketli parçalara (bariyer); duvar modunda yön duvar normalinden.
        barrier: {
          speed_m_s: num(speed),
          angle_deg: impactMode === "wall" ? num(angle) : 0,
          wall: {
            point: (wallXYZ ?? [0, 0, 0]) as [number, number, number],
            normal: dirVec as [number, number, number],
          },
          ...(impactMode === "free" ? { direction: dirVec as [number, number, number] } : {}),
        },
        ...(gravOn ? { gravity: { accel_m_s2: num(gravAccel), direction: gravDir } } : {}),
        dimension: isShell ? 2 : 3,
        run_solver: runSolver,
        wait: false,
        t_end_ms: num(tEnd),
        parts: partOptions.map(
          (pid): CrashPartSpec => ({
            part_id: pid,
            role: roleOfPart(pid),
            ...(partCards[pid] ? { model: modelFor(partCards[pid], `Parça #${pid}`) } : {}),
          }),
        ),
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
      <div className="crash-acc-head">
        <span className="crash-q-title">Sınır koşulları</span>
        <span className={readyCount === 3 ? "crash-acc-count ok" : "crash-acc-count"} data-testid="crash-ready-count">
          {readyCount} / 3 hazır
        </span>
      </div>

      <section className="crash-acc" aria-label="Çarpma">
        <AccHead n={1} title="Çarpma" summary={impactSummary} state={impactState} open={openGroup === 1} onToggle={() => toggleGroup(1)} />
        {openGroup === 1 && (
          <div className="crash-acc-body">
            <div className="doe-seg crash-q-options" role="radiogroup" aria-label="Çarpma türü">
              {([["wall", "Rijit duvara çarpma"], ["free", "Duvarsız · yalnız ilk hız"]] as const).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={impactMode === id}
                  className={impactMode === id ? "doe-seg-opt active" : "doe-seg-opt"}
                  disabled={busy}
                  onClick={() => setImpactMode(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="crash-unit-row">
              <UnitField label="Hız" unit="m/s" value={speed} onChange={setSpeed} disabled={busy} />
              {impactMode === "wall" && <UnitField label="Açı" unit="°" value={angle} onChange={setAngle} disabled={busy} />}
              <UnitField label="Süre" unit="ms" value={tEnd} onChange={setTEnd} disabled={busy} />
            </div>
            <div className="crash-field-label">
              <span>{impactMode === "wall" ? "Duvarın baktığı yön" : "Hız yönü"}</span>
              <code>{impactMode === "wall" ? "/RWALL normal" : "/INIVEL"}</code>
            </div>
            <div className="crash-dir-buttons" role="radiogroup" aria-label={impactMode === "wall" ? "Duvarın baktığı yön" : "Hız yönü"}>
              {DIR_PRESETS.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  role="radio"
                  aria-checked={dirPreset === d.id}
                  className={dirPreset === d.id ? "crash-dir-btn active" : "crash-dir-btn"}
                  disabled={busy}
                  onClick={() => setDirPreset(d.id)}
                >
                  {d.id === "custom" ? "Özel" : d.id}
                </button>
              ))}
            </div>
            {dirPreset === "custom" && (
              <div className="crash-unit-row">
                {(["x", "y", "z"] as const).map((ax, k) => (
                  <UnitField
                    key={ax}
                    label={ax}
                    unit=""
                    value={customDir[k]}
                    disabled={busy}
                    onChange={(v) => setCustomDir((d) => d.map((x, i) => (i === k ? v : x)) as [string, string, string])}
                  />
                ))}
              </div>
            )}
            <p className="crash-behavior-hint">
              {impactMode === "wall"
                ? `Parça duvara doğru, normalin tersine (${vecLabel(approachDir)}) ilerler.`
                : `Hareketli parçalar t = 0'da ${vecLabel(dirVec)} yönünde fırlatılır; engel yoksa çarpma temaslarla olur.`}
            </p>
            {impactMode === "wall" && (
              <>
                <div className="crash-field-label">
                  <span>Duvar konumu</span>
                  <code>/RWALL nokta</code>
                </div>
                <div className="crash-unit-row">
                  <UnitField label="Duvar konumu" hideLabel unit="mm" wide value={wallPoint} onChange={setWallPoint} disabled={busy} placeholder="0, 0, 0" />
                  {onRequestPointPick && (
                    <button
                      type="button"
                      className={pickingPoint ? "crash-pick-btn active" : "crash-pick-btn"}
                      disabled={busy}
                      onClick={() => onRequestPointPick((pt) => setWallPoint(pt.join(", ")))}
                    >
                      {pickingPoint ? "Modelde bir noktaya tıkla…" : "⌖ Modelden seç"}
                    </button>
                  )}
                </div>
              </>
            )}
            <label className="crash-grav-check">
              <input type="checkbox" checked={gravOn} disabled={busy} onChange={(e) => setGravOn(e.target.checked)} />
              <span>yerçekimi</span>
            </label>
            {gravOn && (
              <div className="crash-unit-row">
                <UnitField label="g" unit="m/s²" value={gravAccel} onChange={setGravAccel} disabled={busy} ariaLabel="Yerçekimi ivmesi" />
                <label className="crash-unit-field">
                  <span>eksen</span>
                  <select aria-label="Yerçekimi ekseni" value={gravDir} disabled={busy} onChange={(e) => setGravDir(e.target.value as "X" | "Y" | "Z")}>
                    <option>X</option>
                    <option>Y</option>
                    <option>Z</option>
                  </select>
                </label>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="crash-acc" aria-label="Parçalar">
        <AccHead n={2} title="Parçalar" summary={partsSummary} state={partsState} open={openGroup === 2} onToggle={() => toggleGroup(2)} />
        {openGroup === 2 && (
          <div className="crash-acc-body crash-behaviors" data-testid="crash-parts">
            {partOptions.map((pid) => {
              const mat = materialAssignments.find((a) => a.part_id === pid)?.material_name;
              const role = partRoles[pid] ?? "moving";
              const selected = selectedPartIds.includes(pid);
              return (
                <div
                  key={pid}
                  className={selected ? "crash-behavior crash-part-selected" : "crash-behavior"}
                  onMouseEnter={() => onPartHover?.(pid)}
                  onMouseLeave={() => onPartHover?.(null)}
                >
                  <div className="crash-behavior-head">
                    <button type="button" className="crash-part-pick" aria-pressed={selected} title="Viewport'ta göster" onClick={() => onPartSelect?.(pid)}>
                      #{pid}
                    </button>
                    <span className={mat ? "crash-behavior-mat" : "crash-behavior-mat crash-part-missing"}>
                      {mat ?? "malzeme yok"}
                      {isShell ? ` · t ${componentThickness[pid] ?? "yok"} mm` : ""}
                    </span>
                    <span className="doe-seg crash-role-seg" role="group" aria-label={`Parça ${pid} rolü`}>
                      {ROLE_OPTIONS.map((o) => (
                        <button
                          key={o.id}
                          type="button"
                          className={role === o.id ? "doe-seg-opt active" : "doe-seg-opt"}
                          aria-pressed={role === o.id}
                          title={o.hint}
                          disabled={busy}
                          onClick={() => setPartRoles((r) => ({ ...r, [pid]: o.id }))}
                        >
                          {o.label}
                        </button>
                      ))}
                    </span>
                  </div>
                  <p className="crash-behavior-hint">{ROLE_OPTIONS.find((o) => o.id === role)?.hint}</p>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="crash-acc" aria-label="Temaslar">
        <AccHead n={3} title="Temaslar" summary={contactsSummary} state={contactsState} open={openGroup === 3} onToggle={() => toggleGroup(3)} />
        {openGroup === 3 && (
          <div className="crash-acc-body">
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
                    placeholder="varsayılan"
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
            <p className="crash-behavior-hint">
              TYPE7: bir parçanın düğümleri diğerinin yüzeyine çarpar. TYPE24: iki yüzey karşılıklı.
              Aynı parça iki tarafta = kendi kendine (katlanan kutu). Boş bayrak = Radioss varsayılanı.
            </p>
          </div>
        )}
      </section>

      {blockers.length > 0 && (
        <div className="crash-blockers" role="status" data-testid="crash-blockers">
          {blockers.map((b) => (
            <p key={b}>⚠ {b}</p>
          ))}
        </div>
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
        disabled={!canRun || blockers.length > 0}
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


      <p className="crash-q-title crash-other-title">Diğer ayarlar</p>
      <p className="crash-behavior-hint">Çoğu koşuda dokunulmaz. Boş alan = OpenRadioss varsayılanı.</p>
      <details className="crash-advanced">
        <summary>Ek tanımlar — yüzey kilitleme, ek kütle, rijit gövde, parça başına hız</summary>
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

      {material ? (
        <div className="crash-mat-summary" data-testid="crash-mat-summary">
          <span className="ml-k">Malzeme modeli</span>
          <span>
            {matCardSummary(matCard)}
            {Object.keys(partCards).length > 0 ? ` · ${Object.keys(partCards).length} parçaya ayrı model` : ""}
          </span>
          <span className="crash-behavior-hint">3 · Material adımından değiştirilir.</span>
        </div>
      ) : (
        <CrashMaterialSection
          partIds={partOptions}
          matCard={matCard}
          setMatCard={setMatCard}
          partCards={partCards}
          setPartCards={setPartCards}
          disabled={busy}
        />
      )}

      <details className="crash-advanced">
        <summary>Çözücü ayarları — eleman formülasyonu, hourglass</summary>
        <p className="crash-behavior-hint">
          Elemanın nasıl hesaplandığı (Ishell/Isolid) ve "kum saati" kontrolü (hourglass: indirgenmiş
          integrasyonlu elemanlarda sahte, enerji yemeyen zikzak deformasyonu bastırır). Sonuçlarda
          HG/IE oranı %5'i aşıyorsa buraya bakılır.
        </p>
      {isShell ? (
        <>
          <p className="material-assignments-title">Kabuk — /PROP/TYPE1</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>Ishell</span>
              <input placeholder="varsayılan" value={ishell} onChange={(e) => setIshell(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ish3n</span>
              <input placeholder="varsayılan" value={ish3n} onChange={(e) => setIsh3n(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Ismstr (kabuk)</span>
              <input placeholder="varsayılan" value={shellIsmstr} onChange={(e) => setShellIsmstr(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>N</span>
              <input placeholder="varsayılan" value={shellNip} onChange={(e) => setShellNip(e.target.value)} />
            </label>
          </div>
          <p className="material-assignments-title">Hourglass kontrolü — /PROP/TYPE1</p>
          <div className="mesh-grid">
            <label className="mesh-field">
              <span>Hm</span>
              <input aria-label="Hourglass Hm" placeholder="varsayılan" value={hgHm} onChange={(e) => setHgHm(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Hf</span>
              <input aria-label="Hourglass Hf" placeholder="varsayılan" value={hgHf} onChange={(e) => setHgHf(e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Hr</span>
              <input aria-label="Hourglass Hr" placeholder="varsayılan" value={hgHr} onChange={(e) => setHgHr(e.target.value)} />
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
            <input placeholder="varsayılan" value={ismstr} onChange={(e) => setIsmstr(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>NIP</span>
            <input value={nip} onChange={(e) => setNip(e.target.value)} />
          </label>
          <label className="mesh-field">
            <span>h (hourglass)</span>
            <input aria-label="Hourglass h" placeholder="varsayılan" value={hgSolid} onChange={(e) => setHgSolid(e.target.value)} />
          </label>
        </div>
        <p className="material-assign-hint">
          h: hourglass viskozite katsayısı, aralık 0…0.15, 0 = Radioss varsayılanı (0.10).
        </p>
        </>
      )}
      </details>

      <details className="crash-advanced">
        <summary>Çıktı — kayıt aralığı, kesit kuvvetleri, filtre (CFC), zaman adımı</summary>
        <p className="crash-behavior-hint">
          Hangi eğrilerin ne sıklıkla kaydedileceği ve kuvvet / ivme sinyallerinin filtresi. Boş = varsayılan
          (süre/200 aralık).
        </p>
        <CrashOutputCard value={output} onChange={setOutput} partOptions={partOptions} disabled={busy} />
      </details>

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
