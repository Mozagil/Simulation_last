/**
 * Kart tabanlı yükleme / tutma (TODO 11.9).
 *
 * Her kart bir hedefe (parça #n ya da bölge = Physical Group) uygulanır:
 * İlk hız (/INIVEL), Sabitle (/BCS), Dayatılmış hız (/IMPVEL), Rijit gövde
 * (/RBODY). Kapsama özeti her parçanın hangi rol + kartla tanımlı olduğunu
 * gösterir — yanlış kurulan crash modeli hata vermez, saçma sonuç verir;
 * bütünlük görünür kalmalı. Öneri yok: yalnız durum.
 */
export type CardKind = "inivel" | "bcs" | "impvel" | "rbody";

export interface LoadCard {
  id: number;
  kind: CardKind;
  /** "part:0" | "region:taban" */
  target: string;
  speed: string;
  dir: [string, string, string];
  dofs: string;
  axis: "X" | "Y" | "Z";
  velocity: string;
  tStart: string;
  tStop: string;
  mass: string;
}

export type PartRole = "moving" | "fixed" | "free";

export const CARD_LABEL: Record<CardKind, string> = {
  inivel: "İlk hız",
  bcs: "Sabitle",
  impvel: "Dayatılmış hız",
  rbody: "Rijit gövde",
};

export function newCard(id: number, kind: CardKind, target: string): LoadCard {
  return {
    id, kind, target,
    speed: "10", dir: ["-1", "0", "0"],
    dofs: "111111",
    axis: "X", velocity: "-1", tStart: "0", tStop: "0",
    mass: "0",
  };
}

function n(raw: string, label: string): number {
  const v = Number(raw);
  if (raw.trim() === "" || !Number.isFinite(v)) throw new Error(`${label}: sayı olmalı.`);
  return v;
}

function targetOf(card: LoadCard): { part_id: number } | { region: string } {
  const [kind, value] = [card.target.slice(0, card.target.indexOf(":")), card.target.slice(card.target.indexOf(":") + 1)];
  if (kind === "part") return { part_id: Number(value) };
  if (kind === "region" && value) return { region: value };
  throw new Error(`${CARD_LABEL[card.kind]} kartı: hedef seçilmedi.`);
}

/** Kartlar → /crash/solve alanları. */
export function cardsPayload(cards: LoadCard[]) {
  const out = {
    initial_velocities: [] as Record<string, unknown>[],
    boundary_conditions: [] as Record<string, unknown>[],
    imposed_velocities: [] as Record<string, unknown>[],
    rigid_bodies: [] as Record<string, unknown>[],
  };
  cards.forEach((c, i) => {
    const name = `${c.kind}_${i + 1}`;
    const t = targetOf(c);
    const lab = `${CARD_LABEL[c.kind]} #${i + 1}`;
    if (c.kind === "inivel") {
      out.initial_velocities.push({
        name, ...t, speed_m_s: n(c.speed, `${lab} hız`),
        direction: c.dir.map((d, k) => n(d, `${lab} yön ${"xyz"[k]}`)),
      });
    } else if (c.kind === "bcs") {
      if (!/^[01]{6}$/.test(c.dofs)) throw new Error(`${lab}: DOF 6 hane 0/1 olmalı (Tx Ty Tz Rx Ry Rz).`);
      out.boundary_conditions.push({ name, ...t, dofs: c.dofs });
    } else if (c.kind === "impvel") {
      out.imposed_velocities.push({
        name, ...t, direction: c.axis, velocity_m_s: n(c.velocity, `${lab} hız`),
        t_start_ms: n(c.tStart, `${lab} t başlangıç`), t_stop_ms: n(c.tStop, `${lab} t bitiş`),
      });
    } else {
      out.rigid_bodies.push({ name, ...t, mass_kg: n(c.mass, `${lab} kütle`) });
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

/** Her parça: rol + doğrudan o parçayı hedefleyen kartlar. Bölge kartları
 * parçaya çözülemez (düğüm eşlemesi sunucuda) — ayrıca listelenir. */
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

const ROLE_LABEL: Record<PartRole, string> = { moving: "hareketli", fixed: "sabit", free: "serbest" };

export default function CrashLoadCards({
  cards,
  onChange,
  partIds,
  regions,
  roles,
  disabled = false,
}: {
  cards: LoadCard[];
  onChange: (cards: LoadCard[]) => void;
  partIds: number[];
  /** Physical Group adları — şablon bölgeleri de, kullanıcı grupları da (11.3). */
  regions: string[];
  roles: Record<number, PartRole>;
  disabled?: boolean;
}) {
  const nextId = cards.reduce((m, c) => Math.max(m, c.id), 0) + 1;
  const defaultTarget = partIds.length ? `part:${partIds[0]}` : regions.length ? `region:${regions[0]}` : "";
  const add = (kind: CardKind) => onChange([...cards, newCard(nextId, kind, defaultTarget)]);
  const update = (id: number, patch: Partial<LoadCard>) =>
    onChange(cards.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  const remove = (id: number) => onChange(cards.filter((c) => c.id !== id));
  const cov = coverage(partIds, roles, cards);
  const regionCards = cards.filter((c) => c.target.startsWith("region:"));

  const field = (label: string, value: string, onValue: (v: string) => void, width = 64) => (
    <label className="crash-card-field" key={label}>
      <span>{label}</span>
      <input
        aria-label={label}
        value={value}
        disabled={disabled}
        style={{ width }}
        onChange={(e) => onValue(e.target.value)}
      />
    </label>
  );

  return (
    <section className="crash-cards" data-testid="crash-load-cards">
      <p className="material-assignments-title">Yükleme / tutma kartları</p>
      <div className="crash-cards-add" role="group" aria-label="Kart ekle">
        {(Object.keys(CARD_LABEL) as CardKind[]).map((k) => (
          <button key={k} type="button" className="doe-chip" disabled={disabled || !defaultTarget} onClick={() => add(k)}>
            + {CARD_LABEL[k]}
          </button>
        ))}
      </div>
      {!regions.length && (
        <p className="crash-doe-sub">
          Bölge yok — kart yalnız parçaya uygulanabilir. Bölge için viewport'ta yüzey seçip grup oluşturun
          (Geometri adımı · Bölgeler).
        </p>
      )}
      {cards.map((c, i) => (
        <div key={c.id} className="crash-card" data-testid={`crash-card-${c.kind}`}>
          <div className="crash-card-head">
            <span className="crash-card-kind">{CARD_LABEL[c.kind]} #{i + 1}</span>
            <select
              aria-label={`${CARD_LABEL[c.kind]} #${i + 1} hedef`}
              value={c.target}
              disabled={disabled}
              onChange={(e) => update(c.id, { target: e.target.value })}
            >
              {partIds.map((p) => (
                <option key={`p${p}`} value={`part:${p}`}>parça #{p}</option>
              ))}
              {regions.map((r) => (
                <option key={`r${r}`} value={`region:${r}`}>bölge · {r}</option>
              ))}
            </select>
            <button
              type="button"
              className="crash-doe-x"
              aria-label={`${CARD_LABEL[c.kind]} #${i + 1} sil`}
              disabled={disabled}
              onClick={() => remove(c.id)}
            >
              ×
            </button>
          </div>
          <div className="crash-card-body">
            {c.kind === "inivel" && (
              <>
                {field("v (m/s)", c.speed, (v) => update(c.id, { speed: v }))}
                {(["x", "y", "z"] as const).map((ax, k) =>
                  field(`yön ${ax}`, c.dir[k], (v) => {
                    const dir = [...c.dir] as [string, string, string];
                    dir[k] = v;
                    update(c.id, { dir });
                  }, 48),
                )}
              </>
            )}
            {c.kind === "bcs" && field("DOF (TxTyTzRxRyRz)", c.dofs, (v) => update(c.id, { dofs: v }), 80)}
            {c.kind === "impvel" && (
              <>
                <label className="crash-card-field">
                  <span>eksen</span>
                  <select
                    aria-label="eksen"
                    value={c.axis}
                    disabled={disabled}
                    onChange={(e) => update(c.id, { axis: e.target.value as LoadCard["axis"] })}
                  >
                    <option>X</option>
                    <option>Y</option>
                    <option>Z</option>
                  </select>
                </label>
                {field("v (m/s, işaretli)", c.velocity, (v) => update(c.id, { velocity: v }))}
                {field("t başlangıç (ms)", c.tStart, (v) => update(c.id, { tStart: v }), 56)}
                {field("t bitiş (ms, 0=∞)", c.tStop, (v) => update(c.id, { tStop: v }), 56)}
              </>
            )}
            {c.kind === "rbody" && field("ek kütle (kg)", c.mass, (v) => update(c.id, { mass: v }))}
          </div>
        </div>
      ))}
      {partIds.length > 0 && (
        <div className="crash-coverage" aria-label="Kapsama özeti">
          <span className="ml-k">Kapsama</span>
          {cov.map((p) => (
            <div key={p.partId} className={p.noVelocity ? "crash-coverage-row warn" : "crash-coverage-row"}>
              <code>#{p.partId}</code>
              <span>rol: {ROLE_LABEL[p.role]}</span>
              <span>{p.cards.length ? `kart: ${p.cards.join(", ")}` : "kart yok"}</span>
              {p.noVelocity && <span>⚠ ilk hız kartı yok — kart modunda bariyer hızı verilmez, parça hızsız başlar</span>}
            </div>
          ))}
          {regionCards.length > 0 && (
            <div className="crash-coverage-row">
              <span>
                bölge kartları: {regionCards.map((c) => `${CARD_LABEL[c.kind]} → ${c.target.slice(7)}`).join(" · ")}
              </span>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
