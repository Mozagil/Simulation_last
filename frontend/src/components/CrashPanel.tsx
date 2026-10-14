import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import {
  crashJobWsUrl,
  fetchCrashJob,
  downloadCrashFile,
  fetchCrashRefilter,
  postCrashSolve,
  type CrashContactSpec,
  type CrashJobSnapshot,
  type CrashModelPayload,
  type CrashPartSpec,
  type CrashRunError,
  type CrashSolveRequest,
  type CrashSolveResponse,
  type CrashScenarioSetup,
} from "../api/crash";
import { defaultMatCard, matCardPayload, type MatCardState } from "./CrashMaterialCard";
import CrashMaterialSection from "./CrashMaterialSection";
import type { CrashMarkers } from "./GeometryViewer";
import CrashOutputCard, { defaultOutput, outputPayload, outputSummary, type OutputState } from "./CrashOutputCard";
import CrashForceChart, { energySeriesFromCurves, FORCE_CHART_NOTE, forceSeriesFromCurves } from "./CrashForceChart";
import Kw, { DynaToggle, KwRef } from "./Kw";
import CrashLoadCards, {
  CARD_LABEL,
  cardSummary,
  cardsPayload,
  newCard,
  type LoadCard,
  type PartRole,
} from "./CrashLoadCards";
import { RawCardsOpenRow } from "./CrashRawCardsEditor";
import CrashSolverControlCard, { solverSummary } from "./CrashSolverControlCard";
import CrashLiveProgress from "./CrashLiveProgress";
import CrashDeckViewer from "./CrashDeckViewer";
import { cardsFromRequest } from "../lib/crashSetupImport";
import { defaultWallName, readWallPresets, removeWallPreset, saveWallPreset, type WallPreset } from "../lib/wallPresets";

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

/** Temas satırı: sayısal alanlar ham metin (input), gönderimde sayıya çevrilir. */
interface ContactRow {
  id: number;
  type: 7 | 24;
  /** 1.24a — genel temas (tüm model, öz temas; TYPE24) */
  all: boolean;
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

/** Oran → yüzde (1.23 C6 enerji özeti). */
function pct(v: number | undefined): string {
  return v == null || Number.isNaN(v) ? "—" : (v * 100).toFixed(1);
}

type DirPreset = "+X" | "-X" | "+Y" | "-Y" | "+Z" | "-Z" | "custom";
type GroupState = string;


const DIR_PRESETS: { id: DirPreset; v: number[] }[] = [
  { id: "+X", v: [1, 0, 0] },
  { id: "-X", v: [-1, 0, 0] },
  { id: "+Y", v: [0, 1, 0] },
  { id: "-Y", v: [0, -1, 0] },
  { id: "+Z", v: [0, 0, 1] },
  { id: "-Z", v: [0, 0, -1] },
  { id: "custom", v: [0, 0, 1] },
];

/** Ürün ağacı (kullanıcı 2026-10-08: "sınır koşullarının hepsi ürün ağacında
 * görünmeli"): 4 · Crash'teki tanımlar grup grup, tek satırlık özetlerle. */
export interface CrashTreeGroup {
  title: string;
  rows: { label: string; value: string }[];
}

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
  selectedPartIds = [],
  onPartSelect,
  onPartHover,
  regions = [],
  material,
  onMarkersChange,
  onTreeChange,
  onRequestPointPick,
  pickingPoint = false,
  view = "both",
  onRunStarted,
  onJobKey,
  externalJob = null,
  onSolved,
  rawCards = "",
  onOpenRawCards,
  onRequestBuilder,
  importRequest = null,
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
  /** TODO 11.7 — viewport / ürün ağacı ile ortak parça seçimi. */
  selectedPartIds?: number[];
  onPartSelect?: (partId: number) => void;
  onPartHover?: (partId: number | null) => void;
  /** Physical Group adları (şablon bölgeleri + kullanıcı grupları) — kart hedefi (11.3/11.9). */
  regions?: string[];
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
  /** Ürün ağacına sınır koşulu satırları (çarpma, roller, temaslar, ek tanımlar). */
  onTreeChange?: (groups: CrashTreeGroup[] | null) => void;
  /** "Modelden seç": viewport'ta tıklanan nokta geri verilir. */
  onRequestPointPick?: (done: (p: [number, number, number]) => void) => void;
  pickingPoint?: boolean;
  /** "setup" = 4 · Crash (kurulum + çalıştır), "results" = 5 · Sonuçlar, "both" = ikisi (bağımsız kullanım). */
  view?: "setup" | "results" | "both";
  /** İş başlatılınca (App Sonuçlar adımına geçer). */
  onRunStarted?: () => void;
  /** Koşu geçmişini yenilemek için iş anahtarı (job/status). */
  onJobKey?: (key: string) => void;
  /** Panel dışında başlatılan koşu (ör. "+ Yeni crash vakası" senaryosu) — sonuçlar burada izlenir. */
  externalJob?: { jobId: string; geometryId: number; runId?: number | null; setup?: CrashScenarioSetup } | null;
  /** Koşu çözülünce (kullanıcı 2026-10-08): viewport'ta 3B sonuç (deforme şekil) açılır. */
  onSolved?: (run: { id: number; title: string }) => void;
  /** 1.22d — ham kartlar (App'te ortak; 3 · Malzeme'den de düzenlenir). Boşsa istekte yok. */
  rawCards?: string;
  /** Verilirse "Ham kartlar" satırı editörü açar. */
  onOpenRawCards?: () => void;
  /** 1.22e: güncel /crash/solve gövdesini kuran fonksiyon (panel ayrılınca null). */
  onRequestBuilder?: (build: (() => CrashSolveRequest | null) | null) => void;
  /** 1.23 B1c: "Kurulumu yükle" — senaryonun /crash/solve gövdesi panele dolar (key değişince). */
  importRequest?: { key: number; req: CrashSolveRequest } | null;
}) {
  // Parça rolleri: mühendis seçer; varsayılan hepsi hareketli (tek parçalı
  // eski davranışla aynı). Sabit parça /BCS ile tutulur, ilk hız almaz.
  // Sadeleştirilmiş kurulum (kullanıcı 2026-10-07): her parça için tek soru —
  // "bu parça ne yapıyor?". Hız yalnız buradan girilir.
  const [partRoles, setPartRoles] = useState<Record<number, PartRole>>({});
  // Claude Design "Crash BC Sidebar" (2026-10-07): üç akordeon grubu.
  const [openGroup, setOpenGroup] = useState<1 | 2 | 3 | 4 | null>(1);
  const [impactMode, setImpactMode] = useState<"wall" | "free">("wall");
  const [speed, setSpeed] = useState("10");
  const [angle, setAngle] = useState("0");
  const [dirPreset, setDirPreset] = useState<DirPreset>("+Z");
  const [customDir, setCustomDir] = useState<[string, string, string]>(["0", "0", "1"]);
  const [wallPoint, setWallPoint] = useState("0, 0, 0");
  // 1.23 B2: kayıtlı duvarlar (tarayıcıda)
  const [wallPresets, setWallPresets] = useState<WallPreset[]>(readWallPresets);
  const [wallPresetSel, setWallPresetSel] = useState("");
  const [wallPresetName, setWallPresetName] = useState("");
  // TODO 11.9 — kart tabanlı yükleme / tutma
  const [loadCards, setLoadCards] = useState<LoadCard[]>([]);
  // Temas tanımları (1.12): varsayılan yok — mühendis satır ekler.
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const useRigidWall = impactMode === "wall";
  const [gravOn, setGravOn] = useState(false);
  const [gravAccel, setGravAccel] = useState("-9.81");
  const showSetup = view !== "results";
  const showResults = view !== "setup";
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
  const [expertOpen, setExpertOpen] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const [solverOpen, setSolverOpen] = useState(false);
  // 1.23 D1: üretilen deck görüntüleyici (açılışta panelin o anki isteği)
  const [deckRequest, setDeckRequest] = useState<CrashSolveRequest | null>(null);
  // 5 · Sonuçlar — koşu sonrası CFC (post-process)
  const [postForceCfc, setPostForceCfc] = useState("");
  const [postAccCfc, setPostAccCfc] = useState("");
  const [cfcBusy, setCfcBusy] = useState(false);
  const [cfcError, setCfcError] = useState<string | null>(null);
  const [radError, setRadError] = useState<string | null>(null);
  const [runSolver, setRunSolver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CrashSolveResponse | null>(null);
  const [snapshot, setSnapshot] = useState<CrashJobSnapshot | null>(null);

  // 2D mesh → kabuk parçalar (/SHELL, /SH3N, /PROP/TYPE1); 3D → solid (TYPE14).
  const isShell = meshDimension === 2;
  const jobId = result?.job_id ?? snapshot?.job_id ?? null;
  // Uzman ayarları: son koşunun hourglass / iç enerji oranı (veri; eşik yok).
  const hgRatio = (() => {
    const sc = snapshot?.scalars ?? result?.scalars;
    const hg = sc?.hourglass_energy_final;
    const ie = sc?.internal_energy_final;
    return hg != null && ie ? hg / ie : null;
  })();
  const status = snapshot?.status ?? result?.status ?? null;
  const polling = Boolean(jobId && status && !TERMINAL.has(status));

  // Geometri değişince önceki geometrinin koşu sonucu gösterilmez.
  const prevGeometryRef = useRef(geometryId);
  useEffect(() => {
    if (prevGeometryRef.current === geometryId) return;
    prevGeometryRef.current = geometryId;
    // Yeni geometriye ait koşu (ör. senaryo — geometri koşudan sonra yüklenir) korunur.
    setResult((r) => (r && r.geometry_id === geometryId ? r : null));
    setSnapshot((s) => (s && s.geometry_id === geometryId ? s : null));
  }, [geometryId]);
  // Dışarıda başlatılan koşu: sonuç paneline bağla (yoklama aşağıda başlar).
  useEffect(() => {
    if (!externalJob) return;
    setResult(null);
    setSnapshot({ job_id: externalJob.jobId, geometry_id: externalJob.geometryId, status: "pending" });
    // Senaryonun çarpma kurulumu panele (ve viewport işaretlerine) yansır.
    const su = externalJob.setup;
    if (!su) return;
    const wallMode = su.use_rigid_wall !== false;
    setImpactMode(wallMode ? "wall" : "free");
    if (su.speed_m_s != null) setSpeed(String(su.speed_m_s));
    if (su.t_end_ms != null) setTEnd(String(su.t_end_ms));
    if (su.wall?.point) setWallPoint(su.wall.point.join(", "));
    if (su.part_roles) {
      setPartRoles(Object.fromEntries(Object.entries(su.part_roles).map(([k, r]) => [Number(k), r])));
    }
    // Duvar modunda düğme = duvar normali; duvarsızda doğrudan hız yönü.
    const n = su.wall?.normal;
    const v = wallMode
      ? n
      : su.direction ?? (n ? n.map((c: number) => (c === 0 ? 0 : -c)) : undefined);
    if (v && v.length === 3) {
      const preset = DIR_PRESETS.find((d) => d.id !== "custom" && d.v.every((c, i) => c === v[i]));
      if (preset) setDirPreset(preset.id);
      else {
        setDirPreset("custom");
        setCustomDir([String(v[0]), String(v[1]), String(v[2])]);
      }
    }
  }, [externalJob]);

  // 1.23 B1c: senaryo kurulumu (koşmadan) panele: çarpma, duvar, yön, yerçekimi, süre,
  // roller, temaslar, ek tanımlar, eleman bayrakları. Malzeme kartları App'te.
  useEffect(() => {
    if (!importRequest) return;
    const rq = importRequest.req;
    const b = rq.barrier;
    const wallMode = rq.use_rigid_wall !== false;
    setImpactMode(wallMode ? "wall" : "free");
    if (b?.speed_m_s != null) setSpeed(String(b.speed_m_s));
    if (b?.angle_deg != null) setAngle(String(b.angle_deg));
    if (b?.wall?.point) setWallPoint(b.wall.point.join(", "));
    const v = wallMode ? b?.wall?.normal : (b?.direction ?? undefined);
    if (v && v.length === 3) {
      const preset = DIR_PRESETS.find((d) => d.id !== "custom" && d.v.every((c, i) => c === v[i]));
      if (preset) setDirPreset(preset.id);
      else {
        setDirPreset("custom");
        setCustomDir([String(v[0]), String(v[1]), String(v[2])]);
      }
    }
    setGravOn(!!rq.gravity);
    if (rq.gravity) {
      setGravAccel(String(rq.gravity.accel_m_s2));
      setGravDir(rq.gravity.direction);
    }
    if (rq.t_end_ms != null) setTEnd(String(rq.t_end_ms));
    if (rq.parts) setPartRoles(Object.fromEntries(rq.parts.map((p) => [p.part_id, (p.role ?? "moving") as PartRole])));
    setContacts(
      (rq.contacts ?? []).map((c) => {
        contactRowSeq += 1;
        return {
          id: contactRowSeq,
          type: c.type === 24 || c.all_parts ? 24 : 7,
          all: !!c.all_parts,
          master: c.master_part ?? partIds[0] ?? 0,
          slave: c.slave_part ?? partIds[0] ?? 0,
          fric: String(c.fric ?? 0),
          stfac: String(c.stfac ?? 1),
          gapmin: String(c.gapmin ?? 0),
          istf: String(c.istf ?? 0),
          inacti: String(c.inacti ?? 0),
          iedge: String(c.iedge ?? 0),
        };
      }),
    );
    // Ek tanımlar: "rayda" ekseni çarpma vektörünün baskın ekseni (panel ile aynı kural).
    const dv = v ? (wallMode ? v.map((c) => (c === 0 ? 0 : -c)) : v) : [1, 0, 0];
    const ax = dv.map((c) => Math.abs(Number(c) || 0));
    const axis = (["X", "Y", "Z"] as const)[Math.max(0, ax.indexOf(Math.max(...ax)))];
    setLoadCards(cardsFromRequest(rq as unknown as Record<string, unknown>, axis));
    const m = (rq.model ?? {}) as Record<string, unknown>;
    const s = (x: unknown) => (typeof x === "number" ? String(x) : "");
    if (m.isolid != null) setIsolid(s(m.isolid));
    if (m.ismstr != null) setIsmstr(s(m.ismstr));
    if (m.nip != null) setNip(s(m.nip));
    if (m.solid_hourglass_h != null) setHgSolid(s(m.solid_hourglass_h));
    const sh = (m.shell ?? null) as Record<string, unknown> | null;
    if (sh) {
      setIshell(s(sh.ishell));
      setIsh3n(s(sh.ish3n));
      setShellIsmstr(s(sh.ismstr));
      setShellNip(s(sh.nip));
      setHgHm(s(sh.hm));
      setHgHf(s(sh.hf));
      setHgHr(s(sh.hr));
    }
    setResult(null);
    setSnapshot(null);
    setOpenGroup(1);
  }, [importRequest]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // pending → solved geçişinde bir kez: 3B sonucu viewport'ta aç.
  const prevStatusRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (status !== "solved" || prev === "solved" || prev === null) return;
    const runId = result?.run_id ?? (externalJob?.jobId === jobId ? externalJob?.runId : null);
    if (runId != null) onSolved?.({ id: runId, title: `#${runId}` });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (jobId) onJobKey?.(`${jobId}:${status ?? ""}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, status]);

  // Tek parçalı mesh'te partIds boş gelir: parça 0 (self-contact mümkün).
  const partOptions = partIds.length > 0 ? partIds : [0];

  function addContact() {
    contactRowSeq += 1;
    setContacts((rows) => [
      ...rows,
      {
        id: contactRowSeq,
        type: 7,
        all: false,
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
    const flags = {
      fric: num(r.fric),
      stfac: num(r.stfac),
      gapmin: 0,
      istf: num(r.istf),
      inacti: num(r.inacti),
      iedge: num(r.iedge),
    };
    if (r.all) return { type: 24, all_parts: true, ...flags };
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

  /** Yön düğmesini vektörden kur (eksense hazır düğme, değilse Özel). */
  function applyDirVector(v: number[]) {
    const preset = DIR_PRESETS.find((d) => d.id !== "custom" && d.v.every((c, i) => c === v[i]));
    if (preset) setDirPreset(preset.id);
    else {
      setDirPreset("custom");
      setCustomDir([String(v[0]), String(v[1]), String(v[2])]);
    }
  }

  const toggleGroup = (g: 1 | 2 | 3 | 4) => setOpenGroup((cur) => (cur === g ? null : g));
  // Yön: duvar modunda düğme duvar normalidir (parça tersine gider); duvarsızda doğrudan hız yönü.
  const dirVec: number[] =
    dirPreset === "custom" ? customDir.map(Number) : DIR_PRESETS.find((d) => d.id === dirPreset)!.v;
  const approachDir = dirVec.map((c) => (c === 0 ? 0 : -c));
  // Ek tanımlar "rayda": çarpma (hız) vektörünün baskın ekseni.
  const impactAxis: "X" | "Y" | "Z" = (() => {
    const v = (impactMode === "wall" ? approachDir : dirVec).map((c) => Math.abs(Number(c) || 0));
    const i = v.indexOf(Math.max(...v));
    return (["X", "Y", "Z"] as const)[i < 0 ? 0 : i];
  })();
  const wallXYZ = parseTriple(wallPoint);

  // --- grup özetleri / hazır durumu (öneri değil: eksik bilginin listesi) ---
  const speedOk = Number.isFinite(Number(speed)) && speed.trim() !== "" && Number(speed) >= 0;
  const dirOk = dirVec.every(Number.isFinite) && dirVec.some((c) => c !== 0);
  const tEndOk = Number.isFinite(Number(tEnd)) && Number(tEnd) > 0;
  const impactMissing = [
    !speedOk && "Çarpma: hız sayı olmalı",
    !dirOk && "Çarpma: yön vektörü sıfır ya da geçersiz",
    impactMode === "wall" && !wallXYZ && "Çarpma: duvar konumu 'x, y, z' olmalı",
  ].filter(Boolean) as string[];
  // 1.23 D2: süre "Çözüm kontrolü" kartında
  const solverMissing = !tEndOk ? ["Çözüm kontrolü: süre pozitif olmalı"] : [];
  const impactState: GroupState = impactMissing.length ? `${impactMissing.length} eksik` : "hazır";
  const impactSummary =
    `${speed} m/s · ${vecLabel(impactMode === "wall" ? approachDir : dirVec)} yönü · ` +
    (impactMode === "wall" ? `rijit duvar ${wallLabel(dirVec, wallXYZ)}` : "duvarsız");
  const roleOfPart = (pid: number): PartRole => partRoles[pid] ?? "moving";
  const partsSummary = partOptions.map((pid) => `#${pid} ${ROLE_OPTIONS.find((o) => o.id === roleOfPart(pid))!.short}`).join(" · ");
  const noMaterial = partOptions.filter((pid) => materialAssignments.length > 0 && !materialAssignments.some((a) => a.part_id === pid && a.material_name));
  const partsMissing = [
    !partOptions.some((pid) => roleOfPart(pid) === "moving") &&
      !gravOn &&
      !loadCards.some((c) => c.kind === "inivel" || c.kind === "impvel") &&
      "Parçalar: hareketli parça yok",
    noMaterial.length > 0 && `Parçalar: malzemesiz ${noMaterial.map((p) => "#" + p).join(", ")}`,
  ].filter(Boolean) as string[];
  const partsState: GroupState = partsMissing.length ? `${partsMissing.length} eksik` : "hazır";
  const contactLabel = (c: ContactRow, sep: string) =>
    c.all ? "tüm model (genel)" : c.master === c.slave ? `#${c.master} kendi kendine` : `#${c.slave}${sep}#${c.master}`;
  const contactsSummary = contacts.length
    ? contacts.map((c) => contactLabel(c, "→")).join(" · ")
    : "temas yok";
  const contactsMissing =
    impactMode === "free" && contacts.length === 0 && partOptions.length > 1 ? ["Temaslar: duvarsız çarpmada parçalar arası temas yok"] : [];
  const contactsState: GroupState = contactsMissing.length ? `${contactsMissing.length} eksik` : contacts.length ? "hazır" : "isteğe bağlı";
  const readyCount = [impactState, partsState, contactsState].filter((st) => !st.endsWith("eksik")).length;
  // --- viewport işaretleri: panel değişince App'e bildir ---
  // Uzman ayarları özeti: yalnız değiştirilen alanlar (boş = varsayılan).
  const expertSet = (
    isShell
      ? ([["Ishell", ishell], ["Ish3n", ish3n], ["Ismstr", shellIsmstr], ["N", shellNip], ["Hm", hgHm], ["Hf", hgHf], ["Hr", hgHr]] as const)
      : ([["Isolid", isolid === "1" ? "" : isolid], ["Ismstr", ismstr], ["NIP", nip === "1" ? "" : nip], ["h", hgSolid]] as const)
  ).filter(([, v]) => v.trim() !== "");
  const expertChanged = expertSet.length > 0;
  const expertSummary = expertChanged
    ? expertSet.map(([k, v]) => `${k} ${v}`).join(" · ")
    : "Eleman formülasyonu, hourglass · hepsi varsayılan";
  const anyMoving = partOptions.some((pid) => roleOfPart(pid) === "moving");
  const markers: CrashMarkers = {
    wall: impactMode === "wall" && wallXYZ && dirOk ? { point: wallXYZ, normal: dirVec as [number, number, number] } : null,
    // Hız oku yalnız ilk hız alan bir parça varsa (hareketli rol): ör. kapı
    // senaryosunda iki parça serbest, impaktör dayatılmış hızla itilir — ok yok.
    velocity:
      speedOk && dirOk && anyMoving
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

  const treeGroups: CrashTreeGroup[] = [
    {
      title: "Çarpma",
      rows: [
        {
          label: impactMode === "wall" ? "Rijit duvar" : "Duvarsız",
          value: impactMode === "wall" ? wallLabel(dirVec, wallXYZ) : "yalnız ilk hız",
        },
        ...(anyMoving ? [{ label: "İlk hız", value: `${speed} m/s · ${vecLabel(impactMode === "wall" ? approachDir : dirVec)}` }] : []),
        { label: "Süre", value: `${tEnd} ms` },
        ...(gravOn ? [{ label: "Yerçekimi", value: `${gravAccel} m/s² · ${gravDir}` }] : []),
      ],
    },
    {
      title: "Parça rolleri",
      rows: partOptions.map((pid) => ({ label: `Parça #${pid}`, value: ROLE_OPTIONS.find((o) => o.id === roleOfPart(pid))!.short })),
    },
    {
      title: "Temaslar",
      rows: contacts.map((c) => ({
        label: `TYPE${c.type}`,
        value: contactLabel(c, " → "),
      })),
    },
    {
      title: "Ek tanımlar",
      rows: loadCards.map((c) => ({ label: CARD_LABEL[c.kind], value: cardSummary(c, impactAxis) })),
    },
  ];
  const treeKey = JSON.stringify(treeGroups);
  useEffect(() => {
    onTreeChange?.(JSON.parse(treeKey) as CrashTreeGroup[]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [treeKey]);
  useEffect(() => () => onTreeChange?.(null), []); // eslint-disable-line react-hooks/exhaustive-deps

  const blockers = [
    ...(meshDimension !== 2 && meshDimension !== 3 ? ["Önce mesh üretin (2 · Mesh)"] : []),
    ...impactMissing,
    ...solverMissing,
    ...partsMissing,
    ...contactsMissing,
  ];

  /** /crash/solve gövdesi (ham kartsız) — koşu ve ham kart kontrolü (1.22e) aynı gövdeyi kullanır. */
  function buildSolveBody(): CrashSolveRequest | null {
    if (geometryId == null) return null;
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
    return {
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
      ...cardsPayload(loadCards, impactAxis),
      model: modelFor(matCard, "Global"),
      ...outputPayload(output),
    };
  }

  // 1.22e: editör "Kontrol et" için güncel gövde kurucusunu App'e verir.
  useEffect(() => {
    onRequestBuilder?.(buildSolveBody);
  });
  useEffect(() => () => onRequestBuilder?.(null), []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit() {
    if (geometryId == null) return;
    setBusy(true);
    setError(null);
    try {
      const request = buildSolveBody();
      if (request == null) return;
      const body = await postCrashSolve({
        ...request,
        ...(rawCards.trim() ? { raw_cards: rawCards } : {}),
      });
      setResult(body);
      onRunStarted?.();
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

  async function applyPostCfc() {
    if (!jobId) return;
    setCfcBusy(true);
    setCfcError(null);
    try {
      const r = await fetchCrashRefilter(jobId, postForceCfc ? Number(postForceCfc) : null, postAccCfc ? Number(postAccCfc) : null);
      setSnapshot((prev) =>
        prev
          ? { ...prev, curves: { ...(prev.curves ?? {}), ...r.curves }, scalars: { ...(prev.scalars ?? {}), ...r.scalars } }
          : prev,
      );
    } catch (e) {
      setCfcError(e instanceof Error ? e.message : "Süzme yapılamadı.");
    } finally {
      setCfcBusy(false);
    }
  }

  const scalars = snapshot?.scalars ?? result?.scalars ?? {};
  const percent = snapshot?.percent ?? 0;
  const canRun = geometryId != null && (meshDimension === 2 || meshDimension === 3) && !busy;
  const curves = snapshot?.curves;
  const forceSeries = forceSeriesFromCurves(curves);
  const energySeries = energySeriesFromCurves(curves);
  const diagnostics = snapshot?.diagnostics ?? result?.diagnostics;
  // 2026-10-14 öncesi ıraksayan koşularda error yok, yalnız diverged metni var.
  const runError: CrashRunError | null =
    diagnostics?.error ??
    (diagnostics?.diverged
      ? { code: 1, title: "Çözüm ıraksadı", description: diagnostics.diverged, detail: "" }
      : null);
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
      <DynaToggle />
      {meshDimension !== 2 && meshDimension !== 3 && (
        <p className="material-assign-hint">Mesh yok — crash 3D (solid) ya da 2D (kabuk) mesh ister.</p>
      )}
      {geometryId == null && (
        <p className="material-assign-hint">Önce geometri yükleyin.</p>
      )}

      {showSetup && (
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
            </div>
            <div className="crash-field-label">
              <span>{impactMode === "wall" ? "Duvarın baktığı yön" : "Hız yönü"}</span>
              {impactMode === "wall" ? <Kw card="/RWALL" text="/RWALL normal" /> : <Kw card="/INIVEL" />}
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
                  <Kw card="/RWALL" text="/RWALL nokta" />
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
                <div className="crash-unit-row crash-wall-presets">
                  <select
                    aria-label="Kayıtlı duvar"
                    value={wallPresetSel}
                    disabled={busy || wallPresets.length === 0}
                    onChange={(e) => {
                      const p = wallPresets.find((q) => q.name === e.target.value);
                      setWallPresetSel(e.target.value);
                      if (!p) return;
                      setWallPoint(p.point.join(", "));
                      applyDirVector(p.normal);
                    }}
                  >
                    <option value="">{wallPresets.length ? "Kayıtlı duvar…" : "Kayıtlı duvar yok"}</option>
                    {wallPresets.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                  {wallPresetSel && (
                    <button
                      type="button"
                      className="crash-pick-btn"
                      aria-label="Kayıtlı duvarı sil"
                      title="Seçili kaydı listeden sil (paneldeki değerler kalır)"
                      disabled={busy}
                      onClick={() => {
                        setWallPresets(removeWallPreset(wallPresetSel));
                        setWallPresetSel("");
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
                <div className="crash-unit-row crash-wall-presets">
                  <input
                    aria-label="Duvar kaydı adı"
                    placeholder="ad (isteğe bağlı)"
                    value={wallPresetName}
                    disabled={busy}
                    onChange={(e) => setWallPresetName(e.target.value)}
                  />
                  <button
                    type="button"
                    className="crash-pick-btn"
                    disabled={busy || !wallXYZ || !dirOk}
                    title="Duvar noktası + yön (normal) kaydedilir; sonraki vakada listeden seçilir"
                    onClick={() => {
                      if (!wallXYZ) return;
                      const point = wallXYZ as [number, number, number];
                      const normal = dirVec.slice(0, 3) as [number, number, number];
                      const name = wallPresetName.trim() || defaultWallName(point, normal);
                      setWallPresets(saveWallPreset({ name, point, normal }));
                      setWallPresetSel(name);
                      setWallPresetName("");
                    }}
                  >
                    Duvarı kaydet
                  </button>
                </div>
              </>
            )}
            <label className="crash-grav-check">
              <input type="checkbox" checked={gravOn} disabled={busy} onChange={(e) => setGravOn(e.target.checked)} />
              <span>yerçekimi</span>
              <KwRef card="/GRAV" />
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
                  {/* 1.23 C4: parça rijit = parçayı hedefleyen kütlesiz /RBODY kartı (Ek tanımlar'da görünür) */}
                  <label className="crash-grav-check crash-part-rigid">
                    <input
                      type="checkbox"
                      aria-label={`Parça ${pid} rijit`}
                      checked={loadCards.some((c) => c.kind === "rbody" && c.target === `part:${pid}`)}
                      disabled={busy}
                      onChange={(e) =>
                        setLoadCards((cs) =>
                          e.target.checked
                            ? [
                                ...cs,
                                {
                                  ...newCard(cs.reduce((m, c) => Math.max(m, c.id), 0) + 1, "rbody", `part:${pid}`),
                                  mass: "0",
                                  // kullanıcı kararı A (2026-10-14): rijit parça rijit duvara çarpsın (Ikrem 1);
                                  // Radioss varsayılanı 0 düğümleri duvardan çıkarır (WARNING 446)
                                  keepWall: true,
                                },
                              ]
                            : cs.filter((c) => !(c.kind === "rbody" && c.target === `part:${pid}`)),
                        )
                      }
                    />
                    <span>Rijit gövde</span>
                    <KwRef card="/RBODY" />
                    <span className="crash-behavior-hint">esnek değil; kütle parçanın kendi kütlesi (+ ek yok); rijit duvarla temas kalır</span>
                  </label>
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
                          {c.all ? " · tüm model" : c.master === c.slave ? " · self" : ""}
                        </strong>
                        <span className="doe-seg" role="group" aria-label={`Temas ${k} tipi`}>
                          {([7, 24] as const).map((t) => (
                            <button
                              key={t}
                              type="button"
                              className={c.type === t ? "doe-seg-opt active" : "doe-seg-opt"}
                              aria-pressed={c.type === t}
                              disabled={busy || (c.all && t === 7)}
                              onClick={() => updateContact(c.id, { type: t })}
                            >
                              TYPE{t}
                            </button>
                          ))}
                        </span>
                        <KwRef card={`/INTER/TYPE${c.type}`} />
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
                      <div className="crash-contact-scope">
                        <span>Kapsam</span>
                        <span className="doe-seg crash-contact-scope-seg" role="group" aria-label={`Temas ${k} kapsamı`}>
                          {([false, true] as const).map((all) => (
                            <button
                              key={String(all)}
                              type="button"
                              className={c.all === all ? "doe-seg-opt active" : "doe-seg-opt"}
                              aria-pressed={c.all === all}
                              disabled={busy}
                              onClick={() => updateContact(c.id, all ? { all: true, type: 24 } : { all: false })}
                            >
                              {all ? "Tüm model" : "Parça çifti"}
                            </button>
                          ))}
                        </span>
                      </div>
                      {c.all ? (
                        <p className="crash-contact-all" data-testid={`crash-contact-${k}-all`}>
                          Tüm parçalar tek yüzey, öz temas. Kabuk ve solid birlikteyse üç TYPE24 yazılır
                          (kabuk öz, solid öz, kabuk ↔ solid).
                        </p>
                      ) : (
                        <div className="crash-contact-parts">
                          {partSelect("slave", c.type === 7 ? "slave (düğümler)" : "slave (yüzey)")}
                          <span className="crash-contact-arrow" aria-hidden="true">
                            {c.type === 7 ? "→" : "↔"}
                          </span>
                          {partSelect("master", "master (yüzey)")}
                        </div>
                      )}
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
              Aynı parça iki tarafta = kendi kendine (katlanan kutu). Tüm model = bütün parçalar tek
              yüzeyde öz temas (genel temas, TYPE24). Boş bayrak = Radioss varsayılanı.
            </p>
          </div>
        )}
      </section>

      <section className="crash-acc" aria-label="Ek tanımlar">
        <AccHead
          n={4}
          title="Ek tanımlar"
          summary={loadCards.length ? `${loadCards.length} tanım · rollerin yetmediği yerler` : "rollerin yetmediği yerler"}
          state="isteğe bağlı"
          open={openGroup === 4}
          onToggle={() => toggleGroup(4)}
        />
        {openGroup === 4 && (
          <div className="crash-acc-body">
            <p className="crash-behavior-hint">
              Parça rolü bütün parçaya uygulanır. Buradakiler bir bölgeye ya da parçaya ek tanım ekler.
            </p>
            <CrashLoadCards
              cards={loadCards}
              onChange={setLoadCards}
              partIds={partOptions}
              regions={regions}
              disabled={busy}
              impactAxis={impactAxis}
            />
          </div>
        )}
      </section>

      <section className="crash-acc crash-expert" aria-label="Uzman ayarları">
        <button
          type="button"
          className="crash-acc-toggle"
          aria-expanded={expertOpen}
          onClick={() => setExpertOpen((v) => !v)}
        >
          <span className="crash-acc-n crash-acc-gear" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="8" r="2.2" />
              <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
            </svg>
          </span>
          <span className="crash-acc-text">
            <strong>Uzman ayarları</strong>
            <span className="crash-acc-summary">{expertSummary}</span>
          </span>
          <span className={expertChanged ? "crash-acc-state ok" : "crash-acc-state muted"}>
            {expertChanged ? "değiştirildi" : "varsayılan"}
          </span>
          <span className="crash-acc-chev" aria-hidden="true">{expertOpen ? "▴" : "▾"}</span>
        </button>
        <div className="crash-acc-body" hidden={!expertOpen}>
          {hgRatio != null && (
            <div className="crash-hg-line" data-testid="crash-hg-line">
              <span>
                Son koşu: HG/IE <strong>%{(hgRatio * 100).toFixed(1)}</strong> (kayıtlı değer)
              </span>
              <button
                type="button"
                className="crash-link-btn"
                onClick={() => document.getElementById("crash-expert-hourglass")?.scrollIntoView({ block: "center" })}
              >
                hourglass alanları ↓
              </button>
            </div>
          )}
          <p className="crash-behavior-hint">
            Boş alan = OpenRadioss varsayılanı. Elemanın nasıl hesaplandığı ve "kum saati" (hourglass)
            kontrolü: indirgenmiş integrasyonlu elemanlarda enerji yemeyen sahte zikzak deformasyonu bastırır.
          </p>
          {isShell ? (
            <>
              <p className="crash-expert-title">
                Eleman · kabuk <Kw card="/PROP/TYPE1" />
              </p>
              <div className="crash-expert-grid cols-4">
              <label className="crash-expert-field">
                <span>Ishell</span>
                <input aria-label="Ishell" placeholder="varsayılan" value={ishell} disabled={busy} onChange={(e) => setIshell(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>Ish3n</span>
                <input aria-label="Ish3n" placeholder="varsayılan" value={ish3n} disabled={busy} onChange={(e) => setIsh3n(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>Ismstr</span>
                <input aria-label="Ismstr (kabuk)" placeholder="varsayılan" value={shellIsmstr} disabled={busy} onChange={(e) => setShellIsmstr(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>N</span>
                <input aria-label="N" placeholder="varsayılan" value={shellNip} disabled={busy} onChange={(e) => setShellNip(e.target.value)} />
              </label>
              </div>
              <p className="crash-behavior-hint">
                Kalınlık ürün ağacından (3 · Material → bileşen kalınlığı). 0 = Radioss /DEF_SHELL varsayılanı.
                N: 0, 1 ya da 3…10.
              </p>
              <p className="crash-expert-title" id="crash-expert-hourglass">
                Hourglass · 0…0.05
              </p>
              <div className="crash-expert-grid cols-3">
              <label className="crash-expert-field">
                <span>Hm membran</span>
                <input aria-label="Hourglass Hm" placeholder="0.01" value={hgHm} disabled={busy} onChange={(e) => setHgHm(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>Hf düzlem dışı</span>
                <input aria-label="Hourglass Hf" placeholder="0.01" value={hgHf} disabled={busy} onChange={(e) => setHgHf(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>Hr dönme</span>
                <input aria-label="Hourglass Hr" placeholder="0.01" value={hgHr} disabled={busy} onChange={(e) => setHgHr(e.target.value)} />
              </label>
              </div>
              <p className="crash-behavior-hint">Ishell 1–4 hourglass formülasyonlarında etkili.</p>
            </>
          ) : (
            <>
              <p className="crash-expert-title">
                Eleman · solid <Kw card="/PROP/TYPE14" />
              </p>
              <div className="crash-expert-grid cols-3">
              <label className="crash-expert-field">
                <span>Isolid</span>
                <input aria-label="Isolid" placeholder="1" value={isolid} disabled={busy} onChange={(e) => setIsolid(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>Ismstr</span>
                <input aria-label="Ismstr" placeholder="varsayılan" value={ismstr} disabled={busy} onChange={(e) => setIsmstr(e.target.value)} />
              </label>
              <label className="crash-expert-field">
                <span>NIP</span>
                <input aria-label="NIP" placeholder="1" value={nip} disabled={busy} onChange={(e) => setNip(e.target.value)} />
              </label>
              </div>
              <p className="crash-expert-title" id="crash-expert-hourglass">
                Hourglass · 0…0.15
              </p>
              <div className="crash-expert-grid cols-3">
              <label className="crash-expert-field">
                <span>h viskozite</span>
                <input aria-label="Hourglass h" placeholder="0.10" value={hgSolid} disabled={busy} onChange={(e) => setHgSolid(e.target.value)} />
              </label>
              </div>
            </>
          )}
          <p className="crash-behavior-hint">Çıktı (kayıt aralığı, kesit kuvveti, CFC): 5 · Sonuçlar → Çıktı.</p>
        </div>
      </section>

      <section className="crash-acc crash-expert" aria-label="Çözüm kontrolü">
        <button
          type="button"
          className="crash-acc-toggle"
          aria-expanded={solverOpen}
          onClick={() => setSolverOpen((v) => !v)}
        >
          <span className="crash-acc-n crash-acc-gear" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="8" cy="8" r="5.5" />
              <path d="M8 4.5V8l2.5 1.5" />
            </svg>
          </span>
          <span className="crash-acc-text">
            <strong>Çözüm kontrolü</strong>
            <span className="crash-acc-summary">{solverSummary(tEnd, output)}</span>
          </span>
          <span className={solverMissing.length ? "crash-acc-state warn" : output.dtKind ? "crash-acc-state ok" : "crash-acc-state muted"}>
            {solverMissing.length ? "1 eksik" : output.dtKind ? "değiştirildi" : "varsayılan Δt"}
          </span>
          <span className="crash-acc-chev" aria-hidden="true">{solverOpen ? "▴" : "▾"}</span>
        </button>
        <div className="crash-acc-body" hidden={!solverOpen}>
          <CrashSolverControlCard
            tEnd={tEnd}
            onTEnd={setTEnd}
            value={output}
            onChange={setOutput}
            lastScalars={snapshot?.scalars ?? result?.scalars}
            disabled={busy}
          />
        </div>
      </section>

      <section className="crash-acc crash-expert" aria-label="Çıktı ayarları">
        <button
          type="button"
          className="crash-acc-toggle"
          aria-expanded={outputOpen}
          onClick={() => setOutputOpen((v) => !v)}
        >
          <span className="crash-acc-n crash-acc-gear" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M2 13V3M2 13h12M5 10l3-4 2 2 4-5" />
            </svg>
          </span>
          <span className="crash-acc-text">
            <strong>Çıktı ayarları</strong>
            <span className="crash-acc-summary">
              {outputSummary(output, false) || "Kayıt aralığı, kanallar, kesitler · hepsi varsayılan"}
            </span>
          </span>
          <span className={outputSummary(output, false) ? "crash-acc-state ok" : "crash-acc-state muted"}>
            {outputSummary(output, false) ? "değiştirildi" : "varsayılan"}
          </span>
          <span className="crash-acc-chev" aria-hidden="true">{outputOpen ? "▴" : "▾"}</span>
        </button>
        <div className="crash-acc-body" hidden={!outputOpen}>
          <p className="crash-behavior-hint">
            Preprocess: koşudan önce deck'e yazılır — hangi eğriler ne sıklıkla kaydedilir, zaman adımı, kesitler.
            Boş alan = varsayılan. Filtre (CFC) koşudan sonra 5 · Sonuçlar'da uygulanır.
          </p>
          <CrashOutputCard
            value={output}
            onChange={setOutput}
            partOptions={partOptions}
            disabled={busy}
            showCfc={false}
            showTimestep={false}
          />
        </div>
      </section>

      {blockers.length > 0 && (
        <div className="crash-blockers" role="status" data-testid="crash-blockers">
          {blockers.map((b) => (
            <p key={b}>⚠ {b}</p>
          ))}
        </div>
      )}
      <button
        type="button"
        className="material-secondary-button crash-deck-open"
        disabled={!canRun || blockers.length > 0}
        title="Koşmadan, bu kurulumla üretilecek starter + engine deck'ini kart kart görüntüle / indir"
        onClick={() => {
          const rq = buildSolveBody();
          if (rq) setDeckRequest({ ...rq, ...(rawCards.trim() ? { raw_cards: rawCards } : {}) });
        }}
      >
        Deck'i görüntüle
      </button>
      {deckRequest && <CrashDeckViewer request={deckRequest} onClose={() => setDeckRequest(null)} />}
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





      {onOpenRawCards && <RawCardsOpenRow rawCards={rawCards} onOpen={onOpenRawCards} disabled={busy} />}

      {/* Kullanıcı 2026-10-08: malzeme modeli açıklaması yalnız 3 · Material'da. */}
      {!material && (
        <CrashMaterialSection
          partIds={partOptions}
          matCard={matCard}
          setMatCard={setMatCard}
          partCards={partCards}
          setPartCards={setPartCards}
          disabled={busy}
        />
      )}


      </>
      )}

      {showResults && (
        <section className="crash-results" aria-label="Sonuçlar">
          {!result && !snapshot && (
            <p className="doe-empty">Henüz koşu yok — 4 · Crash'te kurup "Çalıştır"a bas. Geçmiş koşular alttaki dock'ta.</p>
          )}
      {(result || snapshot) && (
        <div className="material-assignments">
          <p className="material-assignments-title">Job</p>
          <p className={`material-assign-hint${status === "failed" ? " crash-run-failed" : ""}`}>
            {snapshot?.job_id ?? result?.job_id} · {status} · {snapshot?.message ?? result?.message}
          </p>
          {polling && (
            <div className="crash-progress-track" role="progressbar" aria-valuenow={percent}>
              <div className="crash-progress-fill" style={{ width: `${Math.min(100, percent)}%` }} />
            </div>
          )}
          {/* 1.17g — iş bitince hub'ın son cycle değeri ("cycle 1") gösterilmez */}
          {polling && snapshot?.cycle != null && (
            <CrashLiveProgress
              cycle={snapshot.cycle}
              timeMs={snapshot.time_ms}
              dtMs={snapshot.dt_ms}
              tEndMs={Number(tEnd) > 0 ? Number(tEnd) : null}
              percent={percent}
              massAddedRel={snapshot.mass_added_rel}
              elapsedS={snapshot.elapsed_s}
              remainingS={snapshot.remaining_s}
            />
          )}
          {result?.starter_url && (
            <div className="crash-rad-downloads" aria-label=".rad indir">
              {/* 1.23 A7: OpenRadioss girdi dosyaları — starter = model (düğüm, eleman, malzeme, BC,
                  temas), engine = çözüm kontrolü (süre, Δt, çıktı). */}
              <button
                type="button"
                className="material-secondary-button"
                title="Starter dosyası: düğüm, eleman, malzeme, parça, sınır koşulu, temas, duvar (LS-DYNA .k karşılığı)"
                onClick={() =>
                  void downloadCrashFile(result.starter_url).catch((e) => setRadError(String(e?.message ?? e)))
                }
              >
                ⤓ Model .rad indir (starter)
              </button>
              {result.engine_url && (
                <button
                  type="button"
                  className="material-secondary-button"
                  title="Engine dosyası: bitiş süresi, zaman adımı, çıktı/animasyon kartları"
                  onClick={() =>
                    void downloadCrashFile(result.engine_url).catch((e) => setRadError(String(e?.message ?? e)))
                  }
                >
                  ⤓ Çözüm kontrolü .rad indir (engine)
                </button>
              )}
              {radError && <span className="error-message">{radError}</span>}
            </div>
          )}
          {Object.keys(scalars).length > 0 && (
            <ul className="crash-scalar-list">
              <li>HIC15 {fmt(scalars.hic15)}</li>
              <li>HIC36 {fmt(scalars.hic36)}</li>
              <li>acc_peak_g {fmt(scalars.acc_peak_g)}</li>
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
          {runError && (
            <div className="crash-error-band" role="alert" data-testid="crash-error">
              <p className="crash-error-title">
                Hata #{runError.code} — {runError.title}
                {runError.detail ? `: ${runError.detail}` : ""}
              </p>
              <p className="crash-error-desc">{runError.description}</p>
            </div>
          )}
          {(starterMsgs.errors.length > 0 || starterMsgs.warnings.length > 0) && (
            <p className="material-assign-hint" data-testid="crash-starter-msgs">
              Starter
              {starterMsgs.errors.length > 0 ? ` · hata ID ${starterMsgs.errors.join(", ")}` : " · 0 hata"}
              {starterMsgs.warnings.length > 0 ? ` · uyarı ID ${starterMsgs.warnings.join(", ")}` : ""}
            </p>
          )}
          {curves?.time && forceSeries.length > 0 && (
            <CrashForceChart time={curves.time} series={forceSeries} note={FORCE_CHART_NOTE} showMean />
          )}
          {curves?.time && energySeries.length > 0 && (
            <CrashForceChart
              time={curves.time}
              series={energySeries}
              title="Enerji · J"
              unit="J"
              yLabel="enerji"
              ariaLabel="Enerji–zaman grafiği"
            />
          )}
          {scalars.internal_energy_final != null && (
            <div className="crash-energy-summary" data-testid="crash-energy-summary">
              <p className="crash-expert-title">Enerji özeti · J</p>
              <ul className="crash-scalar-list">
                <li>
                  İç enerji son {fmt(scalars.internal_energy_final)} · maks {fmt(scalars.internal_energy_max)}
                </li>
                <li>
                  Kinetik enerji son {fmt(scalars.kinetic_energy_final)} · maks {fmt(scalars.kinetic_energy_max)}
                </li>
                {scalars.hourglass_energy_final != null && (
                  <li>
                    Hourglass son {fmt(scalars.hourglass_energy_final)} · HG / IE %{pct(scalars.hourglass_ratio)}
                  </li>
                )}
                {scalars.contact_energy_final != null && (
                  <li>
                    Temas son {fmt(scalars.contact_energy_final)} · temas / IE %{pct(scalars.contact_energy_ratio)}
                  </li>
                )}
                {scalars.external_work_final != null && <li>Dış iş son {fmt(scalars.external_work_final)}</li>}
                {scalars.energy_balance_rel != null && (
                  <li>Enerji dengesi |ΔE| / E %{pct(scalars.energy_balance_rel)}</li>
                )}
              </ul>
            </div>
          )}
          {jobId && status === "solved" && (
            <div className="crash-cfc-post" data-testid="crash-cfc-post">
              <p className="crash-expert-title">Filtre · CFC (SAE J211) · post-process</p>
              <p className="crash-behavior-hint">
                Ham kuvvet / ivme sinyali gürültülü; tepe değeri okumak için süzülür. Kayıtlı ham eğriden hesaplanır —
                çözücü yeniden koşmaz, ham eğri korunur. Kuvvet için genelde 60–600, kafa ivmesi (HIC) için 1000.
              </p>
              <div className="crash-expert-grid cols-3">
                {(
                  [
                    ["Kuvvet CFC", postForceCfc, setPostForceCfc],
                    ["İvme CFC", postAccCfc, setPostAccCfc],
                  ] as const
                ).map(([lab, v, setV]) => (
                  <label key={lab} className="crash-expert-field">
                    <span>{lab}</span>
                    <select aria-label={`Sonuç ${lab}`} value={v} onChange={(e) => setV(e.target.value)}>
                      <option value="">Yok (ham)</option>
                      {[60, 180, 600, 1000].map((c) => (
                        <option key={c} value={String(c)}>
                          CFC {c}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
                <button
                  type="button"
                  className="doe-btn crash-cfc-apply"
                  disabled={cfcBusy || (!postForceCfc && !postAccCfc)}
                  onClick={() => void applyPostCfc()}
                >
                  {cfcBusy ? "Süzülüyor…" : "Uygula"}
                </button>
              </div>
              {cfcError && <p className="material-assign-hint">{cfcError}</p>}
            </div>
          )}
        </div>
      )}

        </section>
      )}
    </div>
  );
}
