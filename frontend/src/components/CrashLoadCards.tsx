/**
 * Crash "4 · Ek tanımlar" kartları (TODO 11.9; Claude Design taslağı
 * "Crash Ek Tanımlar", 2026-10-08).
 *
 * Parça rolü bütün parçaya uygulanır; buradaki kartlar bir bölgeye
 * (Physical Group) ya da parçaya ek tanım ekler: Bölgeyi kilitle (/BCS),
 * Kütle / kızak (/RBODY [+ ray /BCS]), Sabit hızla it (/IMPVEL), Parçaya
 * ayrı ilk hız (/INIVEL), Ek kütle (/ADMAS; 1.23 C4 — rijitlik yok, tek noktalık
 * bölgede nokta kütle). Her kart kapalıyken tek cümleyle özetlenir.
 * "Hazır kurulumlar" yalnız kartı ekler — değerleri (kütle vb.) mühendis
 * girer; öneri yok.
 */
import { useState } from "react";
import Kw from "./Kw";

export type CardKind = "inivel" | "bcs" | "impvel" | "rbody" | "admas" | "spring";
/** 1.24b2 — yay ucu: Kütle / kızak kartı (rijit gövde ana düğümü) ya da nokta (mm). */
export interface SpringEnd {
  mode: "rbody" | "point";
  /** rbody kartının id'si (mode rbody) */
  rbody: number | null;
  point: [string, string, string];
  /** mode point: düğüm sabit (zemin) */
  fixed: boolean;
}
/** /ADMAS: toplam kütle düğümlere eşit dağıtılır (Iflag 1) ya da her düğüme bu kütle (0). */
export type MassDist = "total" | "per_node";
export type RbMotion = "rail" | "free" | "custom";
export type Axis = "X" | "Y" | "Z";

export interface LoadCard {
  id: number;
  kind: CardKind;
  /** "part:0" | "region:taban" */
  target: string;
  speed: string;
  dir: [string, string, string];
  /** Kilitli serbestlikler, Tx Ty Tz Rx Ry Rz (1 = kilitli). */
  dofs: string;
  axis: Axis;
  velocity: string;
  tStart: string;
  tStop: string;
  mass: string;
  /** Kütle / kızak: rayda (yalnız çarpma ekseni serbest) | serbest | özel DOF. */
  rbMotion: RbMotion;
  /** Ana düğüm ivmesi TH'ye (HIC kanalı). */
  hic: boolean;
  /** 1.23 C4 — Ek kütle dağılımı */
  massDist: MassDist;
  /** 1.23 C4 — /RBODY Ikrem: false (0) = rijit gövde düğümleri rijit duvardan çıkarılır
   * (Radioss varsayılanı; WARNING 446), true (1) = duvarda kalır. */
  keepWall: boolean;
  /** 1.24b2 — Yay: uçlar, K (N/mm), C (N·s/mm); kütle `mass` (kg) */
  springA: SpringEnd;
  springB: SpringEnd;
  springK: string;
  springC: string;
}

export type PartRole = "moving" | "fixed" | "free";

export const CARD_LABEL: Record<CardKind, string> = {
  bcs: "Bölgeyi kilitle",
  rbody: "Kütle / kızak",
  impvel: "Sabit hızla it",
  inivel: "Parçaya ayrı ilk hız",
  admas: "Ek kütle",
  spring: "Yay",
};

/** Ekleme düğmesinin "ne zaman" satırı. */
const CARD_WHEN: Record<CardKind, string> = {
  bcs: "Kenar / yüz tutulur. Ankastre kenar, simetri düzlemi.",
  rbody: "Bölge rijit + kütle. Kızak, impaktör, araç kütlesi.",
  impvel: "Hız çözüm boyunca sabit. ROPS, kapı intrüzyonu.",
  inivel: "Parçalar farklı hızla gelir. 1 · Çarpma hızı yerine geçer.",
  admas: "Kütle eklenir, rijitlik yok. Tek noktalık bölge = nokta kütle (motor, akü).",
  spring: "İki uç arası doğrusal yay (K, C). Kızak ↔ zemin, kütle ↔ sabit nokta.",
};

const DOF_NAMES = ["Tx", "Ty", "Tz", "Rx", "Ry", "Rz"] as const;

/** Rayda: çarpma ekseninde öteleme serbest, diğer beşi kilitli. */
export function railDofs(axis: Axis): string {
  return ["X", "Y", "Z"].map((a) => (a === axis ? "0" : "1")).join("") + "111";
}

export function newCard(id: number, kind: CardKind, target: string): LoadCard {
  return {
    id, kind, target,
    speed: "10", dir: ["-1", "0", "0"],
    dofs: "111111",
    axis: "X", velocity: "-1", tStart: "0", tStop: "0",
    mass: kind === "rbody" || kind === "admas" ? "" : "0",
    rbMotion: "free",
    hic: false,
    massDist: "total",
    keepWall: false,
    springA: { mode: "rbody", rbody: null, point: ["0", "0", "0"], fixed: true },
    springB: { mode: "point", rbody: null, point: ["0", "0", "0"], fixed: true },
    springK: "",
    springC: "0",
  };
}

/** Kart listesindeki Kütle / kızak kartlarının istek adı: `rbody_<sıra>` (cardsPayload ile aynı). */
export function rbodyName(cards: LoadCard[], cardId: number): string | null {
  const i = cards.findIndex((c) => c.id === cardId);
  return i >= 0 && cards[i].kind === "rbody" ? `rbody_${i + 1}` : null;
}

function springEndLabel(cards: LoadCard[], e: SpringEnd): string {
  if (e.mode === "rbody") {
    const i = cards.findIndex((c) => c.id === e.rbody);
    return i >= 0 ? `Kütle / kızak #${i + 1}` : "kızak seçilmedi";
  }
  return `nokta (${e.point.join(", ")})${e.fixed ? " sabit" : " serbest"}`;
}

function n(raw: string, label: string): number {
  const v = Number(raw);
  if (raw.trim() === "" || !Number.isFinite(v)) throw new Error(`${label}: sayı olmalı.`);
  return v;
}

function targetOf(card: LoadCard): { part_id: number } | { region: string } {
  const i = card.target.indexOf(":");
  const [kind, value] = [card.target.slice(0, i), card.target.slice(i + 1)];
  if (kind === "part") return { part_id: Number(value) };
  if (kind === "region" && value) return { region: value };
  throw new Error(`${CARD_LABEL[card.kind]} kartı: hedef seçilmedi.`);
}

function targetLabel(target: string): string {
  if (target.startsWith("part:")) return `parça #${target.slice(5)}`;
  if (target.startsWith("region:")) return target.slice(7);
  return "hedef yok";
}

function dofText(dofs: string): string {
  if (dofs === "111111") return "tamamen kilitli";
  if (dofs === "000000") return "serbest";
  const locked = DOF_NAMES.filter((_, k) => dofs[k] === "1");
  const free = DOF_NAMES.filter((_, k) => dofs[k] === "0");
  return locked.length <= free.length ? `${locked.join(" ")} kilitli` : `yalnız ${free.join(" ")} serbest`;
}

/** Kapalı kartın tek satırlık özeti. `cards`: yay uçları için kızak sırası. */
export function cardSummary(c: LoadCard, impactAxis: Axis = "X", cards: LoadCard[] = []): string {
  if (c.kind === "spring") {
    const k = c.springK.trim() === "" ? "K girilmedi" : `K ${c.springK} N/mm`;
    const cc = Number(c.springC) > 0 ? ` · C ${c.springC} N·s/mm` : "";
    return `${springEndLabel(cards, c.springA)} ↔ ${springEndLabel(cards, c.springB)} · ${k}${cc}`;
  }
  const t = targetLabel(c.target);
  if (c.kind === "bcs") return `${t} → ${dofText(c.dofs)}`;
  if (c.kind === "impvel") {
    const until = Number(c.tStop) > 0 ? `${c.tStart}–${c.tStop} ms` : "çözüm boyunca";
    return `${t} → ${c.axis} yönünde ${c.velocity} m/s sabit · ${until}`;
  }
  if (c.kind === "inivel") return `${t} → ${c.speed} m/s · yön (${c.dir.join(", ")})`;
  if (c.kind === "admas") {
    const m = c.mass.trim() === "" ? "kütle girilmedi" : `+ ${c.mass} kg`;
    return `${t} → ${m} · ${c.massDist === "total" ? "düğümlere eşit dağıtılır" : "her düğüme"}`;
  }
  const mass = c.mass.trim() === "" ? "kütle girilmedi" : `+ ${c.mass} kg`;
  const motion =
    c.rbMotion === "rail" ? `rayda (yalnız ${impactAxis.toLowerCase()})` : c.rbMotion === "free" ? "serbest" : dofText(c.dofs);
  return `${t} → rijit ${mass} · ${motion}${c.hic ? " · ivme kaydı" : ""}${c.keepWall ? " · duvarda" : ""}`;
}

/** Kartlar → /crash/solve alanları. `impactAxis`: çarpma (hız) ekseni — ray için. */
export function cardsPayload(cards: LoadCard[], impactAxis: Axis = "X") {
  const out = {
    initial_velocities: [] as Record<string, unknown>[],
    boundary_conditions: [] as Record<string, unknown>[],
    imposed_velocities: [] as Record<string, unknown>[],
    rigid_bodies: [] as Record<string, unknown>[],
    added_masses: [] as Record<string, unknown>[],
    springs: [] as Record<string, unknown>[],
  };
  const springEnd = (e: SpringEnd, lab: string): Record<string, unknown> => {
    if (e.mode === "rbody") {
      const nm = e.rbody === null ? null : rbodyName(cards, e.rbody);
      if (!nm) throw new Error(`${lab}: Kütle / kızak kartı seçilmedi.`);
      return { rigid_body: nm };
    }
    return { point: e.point.map((v, k) => n(v, `${lab} nokta ${"xyz"[k]}`)), fixed: e.fixed };
  };
  cards.forEach((c, i) => {
    const name = `${c.kind}_${i + 1}`;
    const lab = `${CARD_LABEL[c.kind]} #${i + 1}`;
    if (c.kind === "spring") {
      const k = n(c.springK, `${lab} K`);
      if (!(k > 0)) throw new Error(`${lab}: K pozitif olmalı.`);
      const cval = c.springC.trim() === "" ? 0 : n(c.springC, `${lab} C`);
      const mass = c.mass.trim() === "" ? 0 : n(c.mass, `${lab} kütle`);
      out.springs.push({
        name, end_a: springEnd(c.springA, `${lab} A ucu`), end_b: springEnd(c.springB, `${lab} B ucu`),
        k_n_per_mm: k, c_n_s_per_mm: cval, mass_kg: mass,
      });
      return;
    }
    const t = targetOf(c);
    if (c.kind === "inivel") {
      out.initial_velocities.push({
        name, ...t, speed_m_s: n(c.speed, `${lab} hız`),
        direction: c.dir.map((d, k) => n(d, `${lab} yön ${"xyz"[k]}`)),
      });
    } else if (c.kind === "bcs") {
      if (!/^[01]{6}$/.test(c.dofs)) throw new Error(`${lab}: DOF 6 hane 0/1 olmalı (Tx Ty Tz Rx Ry Rz).`);
      out.boundary_conditions.push({ name, ...t, dofs: c.dofs });
    } else if (c.kind === "admas") {
      const mass = n(c.mass, `${lab} kütle`);
      if (!(mass > 0)) throw new Error(`${lab}: kütle pozitif olmalı.`);
      out.added_masses.push({ name, ...t, mass_kg: mass, distribution: c.massDist });
    } else if (c.kind === "impvel") {
      out.imposed_velocities.push({
        name, ...t, direction: c.axis, velocity_m_s: n(c.velocity, `${lab} hız`),
        t_start_ms: n(c.tStart, `${lab} t başlangıç`), t_stop_ms: n(c.tStop, `${lab} t bitiş`),
      });
    } else {
      out.rigid_bodies.push({
        name, ...t, mass_kg: n(c.mass, `${lab} kütle`), ...(c.hic ? { th_accel: true } : {}),
        ...(c.keepWall ? { ikrem: 1 } : {}),
      });
      const dofs = c.rbMotion === "rail" ? railDofs(impactAxis) : c.rbMotion === "custom" ? c.dofs : null;
      if (dofs !== null) {
        if (!/^[01]{6}$/.test(dofs)) throw new Error(`${lab}: DOF 6 hane 0/1 olmalı (Tx Ty Tz Rx Ry Rz).`);
        out.boundary_conditions.push({ name: `${name}_ray`, rigid_body: name, dofs });
      }
    }
  });
  return out;
}

export interface PartCoverage {
  partId: number;
  role: PartRole;
  cards: string[];
  /** Kart modunda (ilk hız kartı var) hareketli rollü parça hız almıyor. */
  noVelocity: boolean;
}

/** Her parça: rol + doğrudan o parçayı hedefleyen kartlar. */
export function coverage(partIds: number[], roles: Record<number, PartRole>, cards: LoadCard[]): PartCoverage[] {
  const cardMode = cards.some((c) => c.kind === "inivel");
  return partIds.map((pid) => {
    const mine = cards.filter((c) => c.target === `part:${pid}`);
    const role = roles[pid] ?? "moving";
    return {
      partId: pid,
      role,
      cards: mine.map((c) => CARD_LABEL[c.kind]),
      noVelocity: cardMode && role === "moving" && !mine.some((c) => c.kind === "inivel" || c.kind === "impvel"),
    };
  });
}

function KindIcon({ kind }: { kind: CardKind }) {
  const common = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", strokeWidth: 1.6, "aria-hidden": true };
  if (kind === "bcs")
    return (
      <svg {...common} stroke="#c94a4a">
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
      </svg>
    );
  if (kind === "rbody")
    return (
      <svg {...common} stroke="#a16207">
        <rect x="2" y="5" width="12" height="7" rx="1.5" />
        <path d="M4 14h8" />
      </svg>
    );
  if (kind === "admas")
    return (
      <svg {...common} stroke="#6b4c9a">
        <circle cx="8" cy="9" r="4" />
        <path d="M8 2v3" />
      </svg>
    );
  if (kind === "impvel")
    return (
      <svg {...common} stroke="#3f5f8a">
        <path d="M2 8h10M9 5l3 3-3 3M14 3v10" />
      </svg>
    );
  if (kind === "spring")
    return (
      <svg {...common} stroke="#2f7a5a">
        <path d="M1 8h2l1.5-3 2 6 2-6 2 6 2-6L13 8h2" />
      </svg>
    );
  return (
    <svg {...common} stroke="#a16207">
      <path d="M2 11l5-5 3 3 4-4M10 5h4v4" />
    </svg>
  );
}

const ADD_ORDER: CardKind[] = ["bcs", "rbody", "admas", "impvel", "inivel", "spring"];
const KIND_CARD: Record<CardKind, string> = {
  bcs: "/BCS",
  rbody: "/RBODY",
  admas: "/ADMAS",
  impvel: "/IMPVEL",
  inivel: "/INIVEL",
  spring: "/SPRING",
};

export default function CrashLoadCards({
  cards,
  onChange,
  partIds,
  regions,
  disabled = false,
  impactAxis = "X",
}: {
  cards: LoadCard[];
  onChange: (cards: LoadCard[]) => void;
  partIds: number[];
  /** Physical Group adları — şablon bölgeleri de, kullanıcı grupları da (11.3). */
  regions: string[];
  disabled?: boolean;
  /** Çarpma (hız) ekseni — "rayda" seçeneği bu eksende serbest bırakır. */
  impactAxis?: Axis;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const nextId = cards.reduce((m, c) => Math.max(m, c.id), 0) + 1;
  const defaultTarget = partIds.length ? `part:${partIds[0]}` : regions.length ? `region:${regions[0]}` : "";
  const regionLike = (re: RegExp) => regions.find((r) => re.test(r));

  const addCard = (card: LoadCard) => {
    onChange([...cards, card]);
    setOpenId(card.id);
  };
  const add = (kind: CardKind) => addCard(newCard(nextId, kind, defaultTarget));
  const update = (id: number, patch: Partial<LoadCard>) =>
    onChange(cards.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  const remove = (id: number) => onChange(cards.filter((c) => c.id !== id));

  // Hazır kurulumlar: yalnız kart türü + bölge eşleşmesi; değerler mühendisin.
  const sledRegion = regionLike(/arka/i);
  const edgeRegion = regionLike(/kenar/i);
  const presets = [
    {
      id: "sled",
      label: "Kızak testi",
      hint: sledRegion ? `${sledRegion} rijit + kütle, rayda` : "arka bölge + kütle, rayda",
      make: () => ({
        ...newCard(nextId, "rbody", sledRegion ? `region:${sledRegion}` : defaultTarget),
        rbMotion: "rail" as RbMotion,
      }),
    },
    {
      id: "clamp",
      label: "Ankastre kenar",
      hint: edgeRegion ? `${edgeRegion} tamamen kilitli` : "kenar bölgesi tamamen kilitli",
      make: () => newCard(nextId, "bcs", edgeRegion ? `region:${edgeRegion}` : defaultTarget),
    },
  ];

  const field = (label: string, value: string, onValue: (v: string) => void, unit?: string) => (
    <label className="crash-card-field" key={label}>
      <span>{label}</span>
      <span className="crash-card-input">
        <input aria-label={label} value={value} disabled={disabled} onChange={(e) => onValue(e.target.value)} />
        {unit && <span className="crash-card-unit">{unit}</span>}
      </span>
    </label>
  );

  const dofEditor = (c: LoadCard, k: number) => (
    <div className="crash-dof" role="group" aria-label={`${CARD_LABEL[c.kind]} #${k} serbestlikler`}>
      <div className="crash-dof-quick">
        <button type="button" className="doe-chip" disabled={disabled} onClick={() => update(c.id, { dofs: "111111" })}>
          Tamamen kilitle
        </button>
        <button type="button" className="doe-chip" disabled={disabled} onClick={() => update(c.id, { dofs: "111000" })}>
          Yalnız öteleme
        </button>
      </div>
      <div className="crash-dof-grid">
        {DOF_NAMES.map((d, j) => (
          <label key={d} className="crash-dof-cell">
            <input
              type="checkbox"
              aria-label={`${d} kilitli`}
              checked={c.dofs[j] === "1"}
              disabled={disabled}
              onChange={(e) => {
                const arr = c.dofs.padEnd(6, "0").slice(0, 6).split("");
                arr[j] = e.target.checked ? "1" : "0";
                update(c.id, { dofs: arr.join("") });
              }}
            />
            {d}
          </label>
        ))}
      </div>
      <span className="crash-behavior-hint">İşaretli = kilitli. Tx Ty Tz öteleme, Rx Ry Rz dönme.</span>
    </div>
  );

  const rbodyCards = cards.map((c, i) => ({ c, k: i + 1 })).filter(({ c }) => c.kind === "rbody");
  const springEndEditor = (c: LoadCard, k: number, key: "springA" | "springB", label: string) => {
    const e = c[key];
    const set = (patch: Partial<SpringEnd>) => update(c.id, { [key]: { ...e, ...patch } });
    return (
      <div className="crash-spring-end" role="group" aria-label={`${CARD_LABEL[c.kind]} #${k} ${label} ucu`}>
        <span className="crash-card-sub">{label} ucu</span>
        <span className="doe-seg">
          {(
            [
              ["rbody", "Kütle / kızak"],
              ["point", "Nokta"],
            ] as const
          ).map(([m, t]) => (
            <button
              key={m}
              type="button"
              className={e.mode === m ? "doe-seg-opt active" : "doe-seg-opt"}
              aria-pressed={e.mode === m}
              disabled={disabled}
              onClick={() => set({ mode: m })}
            >
              {t}
            </button>
          ))}
        </span>
        {e.mode === "rbody" ? (
          <label className="crash-card-field">
            <span>Kart</span>
            <select
              aria-label={`${label} ucu kızak`}
              value={e.rbody ?? ""}
              disabled={disabled}
              onChange={(ev) => set({ rbody: ev.target.value === "" ? null : Number(ev.target.value) })}
            >
              <option value="">seç…</option>
              {rbodyCards.map(({ c: rc, k: rk }) => (
                <option key={rc.id} value={rc.id}>
                  Kütle / kızak #{rk} · {targetLabel(rc.target)}
                </option>
              ))}
            </select>
            {!rbodyCards.length && <span className="crash-behavior-hint">Önce bir Kütle / kızak kartı ekleyin.</span>}
          </label>
        ) : (
          <>
            {(["x", "y", "z"] as const).map((ax, j) =>
              field(`${label} ${ax}`, e.point[j], (v) => {
                const point = [...e.point] as [string, string, string];
                point[j] = v;
                set({ point });
              }, "mm"),
            )}
            <label className="material-check">
              <input
                type="checkbox"
                aria-label={`${label} ucu sabit`}
                checked={e.fixed}
                disabled={disabled}
                onChange={(ev) => set({ fixed: ev.target.checked })}
              />
              Sabit (zemin, /BCS 111 111)
            </label>
          </>
        )}
      </div>
    );
  };
  const springEditor = (c: LoadCard, k: number) => (
    <>
      {springEndEditor(c, k, "springA", "A")}
      {springEndEditor(c, k, "springB", "B")}
      {field("K", c.springK, (v) => update(c.id, { springK: v }), "N/mm")}
      {field("C (sönüm)", c.springC, (v) => update(c.id, { springC: v }), "N·s/mm")}
      {field("Yay kütlesi", c.mass, (v) => update(c.id, { mass: v }), "kg")}
      <span className="crash-behavior-hint">
        Eksenel doğrusal yay (/PROP/TYPE4). Uçlar rijit gövde ana düğümü ya da yeni düğüm; esnek parçaya doğrudan
        bağlanmaz. Kuvvet çıktısı /TH/SPRING.
      </span>
    </>
  );

  return (
    <section className="crash-cards" data-testid="crash-load-cards">
      <div className="crash-presets" role="group" aria-label="Hazır kurulumlar">
        <span className="crash-cards-label">Hazır kurulumlar</span>
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            className="doe-chip"
            title={p.hint}
            disabled={disabled || (!defaultTarget && !regions.length)}
            onClick={() => addCard(p.make())}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="crash-cards-add" role="group" aria-label="Kart ekle">
        {ADD_ORDER.map((k) => (
          <button
            key={k}
            type="button"
            className="crash-add-tile"
            aria-label={`+ ${CARD_LABEL[k]}`}
            disabled={disabled || (!defaultTarget && k !== "spring")}
            onClick={() => add(k)}
          >
            <span className="crash-add-tile-head">
              <KindIcon kind={k} />
              {CARD_LABEL[k]}
            </span>
            <span className="crash-add-tile-when">{CARD_WHEN[k]}</span>
            <Kw card={KIND_CARD[k]} />
          </button>
        ))}
      </div>
      {!regions.length && (
        <p className="crash-doe-sub">
          Bölge yok — kart yalnız parçaya uygulanabilir. Bölge için viewport'ta yüzey seçip grup oluşturun
          (Geometri adımı · Bölgeler).
        </p>
      )}
      {cards.length > 0 && <span className="crash-cards-label">Tanımlı ({cards.length})</span>}
      {cards.map((c, i) => {
        const k = i + 1;
        const open = openId === c.id;
        return (
          <div key={c.id} className={`crash-card crash-card-${c.kind}${open ? " open" : ""}`} data-testid={`crash-card-${c.kind}`}>
            <div className="crash-card-head">
              <KindIcon kind={c.kind} />
              <span className="crash-card-text">
                <span className="crash-card-kind">{CARD_LABEL[c.kind]}</span>
                <span className="crash-card-summary" data-testid="crash-card-summary">
                  {cardSummary(c, impactAxis, cards)}
                </span>
              </span>
              <button
                type="button"
                className="crash-card-icon"
                aria-label={`${CARD_LABEL[c.kind]} #${k} ${open ? "kapat" : "düzenle"}`}
                aria-expanded={open}
                disabled={disabled}
                onClick={() => setOpenId(open ? null : c.id)}
              >
                {open ? "▴" : "✎"}
              </button>
              <button
                type="button"
                className="crash-card-icon"
                aria-label={`${CARD_LABEL[c.kind]} #${k} sil`}
                disabled={disabled}
                onClick={() => remove(c.id)}
              >
                ×
              </button>
            </div>
            {open && (
              <div className="crash-card-body">
                {c.kind === "spring" && springEditor(c, k)}
                {c.kind !== "spring" && (
                <div className="crash-card-targets" role="group" aria-label={`${CARD_LABEL[c.kind]} #${k} hedef`}>
                  <span className="crash-card-sub">Nereye</span>
                  {[...regions.map((r) => `region:${r}`), ...partIds.map((p) => `part:${p}`)].map((tg) => (
                    <button
                      key={tg}
                      type="button"
                      className={c.target === tg ? "doe-chip active" : "doe-chip"}
                      aria-pressed={c.target === tg}
                      disabled={disabled}
                      onClick={() => update(c.id, { target: tg })}
                    >
                      {tg.startsWith("region:") ? `bölge: ${tg.slice(7)}` : `parça #${tg.slice(5)}`}
                    </button>
                  ))}
                </div>
                )}
                {c.kind === "bcs" && dofEditor(c, k)}
                {c.kind === "admas" && (
                  <>
                    {field("Kütle", c.mass, (v) => update(c.id, { mass: v }), "kg")}
                    <div className="crash-card-radios" role="radiogroup" aria-label={`${CARD_LABEL[c.kind]} #${k} dağılım`}>
                      <span className="crash-card-sub">Dağılım</span>
                      {(
                        [
                          ["total", "Toplam — düğümlere eşit dağıtılır", "bölgenin toplam ek kütlesi bu değer (Iflag 1)"],
                          ["per_node", "Düğüm başına", "her düğüme bu kütle eklenir (Iflag 0)"],
                        ] as [MassDist, string, string][]
                      ).map(([m, title, sub]) => (
                        <label key={m} className={c.massDist === m ? "crash-radio-row active" : "crash-radio-row"}>
                          <input
                            type="radio"
                            name={`admas-${c.id}`}
                            checked={c.massDist === m}
                            disabled={disabled}
                            onChange={() => update(c.id, { massDist: m })}
                          />
                          <span>
                            <strong>{title}</strong>
                            <span className="crash-behavior-hint">{sub}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                    <p className="crash-behavior-hint">
                      Rijitlik eklemez; bölgedeki düğümler esnek kalır. Kütle ağırlık merkezinde, rijit bağlı isteniyorsa
                      "Kütle / kızak".
                    </p>
                  </>
                )}
                {c.kind === "rbody" && (
                  <>
                    {field("Ek kütle", c.mass, (v) => update(c.id, { mass: v }), "kg")}
                    <div className="crash-card-radios" role="radiogroup" aria-label={`${CARD_LABEL[c.kind]} #${k} hareket`}>
                      <span className="crash-card-sub">Hareket</span>
                      {(
                        [
                          ["rail", "Rayda — yalnız çarpma yönünde", `${impactAxis} ötelemesi serbest, diğer 5 serbestlik kilitli (kızak testi)`],
                          ["free", "Serbest", "6 serbestlik açık; cisim dönebilir"],
                          ["custom", "Özel", "serbestlikleri tek tek seç"],
                        ] as [RbMotion, string, string][]
                      ).map(([m, title, sub]) => (
                        <label key={m} className={c.rbMotion === m ? "crash-radio-row active" : "crash-radio-row"}>
                          <input
                            type="radio"
                            name={`rb-motion-${c.id}`}
                            checked={c.rbMotion === m}
                            disabled={disabled}
                            onChange={() => update(c.id, { rbMotion: m })}
                          />
                          <span>
                            <strong>{title}</strong>
                            <span className="crash-behavior-hint">{sub}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                    <label className="crash-grav-check">
                      <input
                        type="checkbox"
                        aria-label={`${CARD_LABEL[c.kind]} #${k} rijit duvarla temas`}
                        checked={c.keepWall}
                        disabled={disabled}
                        onChange={(e) => update(c.id, { keepWall: e.target.checked })}
                      />
                      <span>Rijit duvarla temas kalsın (Ikrem 1)</span>
                      <span className="crash-behavior-hint">
                        kapalı = Radioss varsayılanı: rijit gövde düğümleri rijit duvardan çıkarılır (WARNING 446)
                      </span>
                    </label>
                    {c.rbMotion === "custom" && dofEditor(c, k)}
                    <label className="material-check">
                      <input
                        type="checkbox"
                        checked={c.hic}
                        disabled={disabled}
                        onChange={(e) => update(c.id, { hic: e.target.checked })}
                      />
                      İvmeyi kaydet (HIC kanalı)
                    </label>
                  </>
                )}
                {c.kind === "impvel" && (
                  <>
                    <label className="crash-card-field">
                      <span>Eksen</span>
                      <select
                        aria-label="eksen"
                        value={c.axis}
                        disabled={disabled}
                        onChange={(e) => update(c.id, { axis: e.target.value as Axis })}
                      >
                        <option>X</option>
                        <option>Y</option>
                        <option>Z</option>
                      </select>
                    </label>
                    {field("Hız (işaretli)", c.velocity, (v) => update(c.id, { velocity: v }), "m/s")}
                    {field("Başlangıç", c.tStart, (v) => update(c.id, { tStart: v }), "ms")}
                    {field("Bitiş (0 = sonuna kadar)", c.tStop, (v) => update(c.id, { tStop: v }), "ms")}
                  </>
                )}
                {c.kind === "inivel" && (
                  <>
                    {field("Hız", c.speed, (v) => update(c.id, { speed: v }), "m/s")}
                    {(["x", "y", "z"] as const).map((ax, j) =>
                      field(`Yön ${ax}`, c.dir[j], (v) => {
                        const dir = [...c.dir] as [string, string, string];
                        dir[j] = v;
                        update(c.id, { dir });
                      }),
                    )}
                    <span className="crash-behavior-hint">Bu kart varsa 1 · Çarpma hızı hiçbir parçaya uygulanmaz.</span>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
