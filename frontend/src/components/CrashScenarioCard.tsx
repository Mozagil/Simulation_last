import { useEffect, useMemo, useState } from "react";
import {
  fetchCrashCatalog,
  fetchCrashJob,
  postCrashScenario,
  type CrashCatalogEntry,
  type CrashScenarioRequest,
  type CrashScenarioResponse,
} from "../api/crash";
import { fetchMaterials, type Material } from "../api/materials";
import { fetchTemplates, type GeometryTemplateInfo } from "../api/templates";

/** Hızlı senaryo (1.17g-7 → K0): katalogdaki "hazır" örneklerden tek çağrıda
 * koşu (POST /crash/scenario) — geometri yüklemeden. Şablon listesi katalogdan,
 * geometri alanları şablonun parametre şemasından (sembol, birim, varsayılan);
 * yeni örnek = katalog maddesi + gerekiyorsa aşağıdaki EXTRAS kaydı.
 * Değerler mühendisin; kurulum (parça rolü, RBODY, BCS, temas) backend'de. */

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

interface ExtraField {
  key: string;
  label: string;
  initial: string;
  placeholder?: string;
}

/** Şablona özgü ek alanlar + istek parçası + kurulum açıklaması. */
interface Extras {
  hint: string;
  fields: ExtraField[];
  body: (v: Record<string, string>) => Partial<CrashScenarioRequest>;
  /** Koşu adının özel kısmı */
  tag: (v: Record<string, string>) => string;
}

function num(raw: string, what: string): number {
  const v = Number(raw.trim().replace(",", "."));
  if (!raw.trim() || !Number.isFinite(v)) throw new Error(`${what}: sayı geçersiz (${raw || "boş"})`);
  return v;
}

const EXTRAS: Record<string, Extras> = {
  crash_box_shell: {
    hint: "Kabuk mesh → malzeme → OpenRadioss (rijit duvar x = 0, ön uç). Kızak boşsa yok.",
    fields: [{ key: "sled", label: "Kızak (kg)", initial: "", placeholder: "yok" }],
    body: (v) => {
      const sled = v.sled.trim() ? num(v.sled, "Kızak kütlesi") : null;
      return { rigid_bodies: sled ? [{ name: "kizak", region: "kutu_arka", mass_kg: sled }] : [] };
    },
    tag: (v) => (v.sled.trim() ? ` · kızak ${v.sled} kg` : ""),
  },
  plate_ball_shell: {
    hint:
      "Plaka kenarı sabit (/BCS 111111), küre rijit gövde + −z ilk hız, küre → plaka TYPE7; rijit duvar yok. " +
      "Küre ek kütlesi kabuk kütlesine eklenir.",
    fields: [
      { key: "ballT", label: "Küre kabuk t (mm)", initial: "1" },
      { key: "ballMass", label: "Küre ek kütle (kg)", initial: "", placeholder: "yok" },
      { key: "ballTotal", label: "Küre toplam kütle (kg)", initial: "", placeholder: "—" },
    ],
    body: (v) => ({
      ball_thickness_mm: num(v.ballT, "Küre kabuk t"),
      ball_mass_kg: v.ballMass.trim() ? num(v.ballMass, "Küre ek kütlesi") : 0,
      // K5 — toplam verilirse ek kütle backend'de toplam − kabuk (ek kütle alanı yok sayılır)
      ...(v.ballTotal?.trim() ? { ball_total_mass_kg: num(v.ballTotal, "Küre toplam kütlesi") } : {}),
    }),
    tag: (v) =>
      v.ballTotal?.trim() ? ` · ${v.ballTotal} kg` : v.ballMass.trim() ? ` · +${v.ballMass} kg` : "",
  },
  drop_box_shell: {
    hint:
      "Zemin z = 0: F = 0 rijit duvar (/RWALL), F > 0 sabit F × F plaka + TYPE7 (g > t). /GRAV (g, −z). H verilince çarpma hızı √(2·g·H) — v₀ alanı yok sayılır. " +
      "Düşme yönü rx / ry (yüzey 0 / 0, kenar 45 / 0, köşe 35.26 / 45).",
    fields: [
      { key: "height", label: "H düşme (mm)", initial: "1000" },
      { key: "g", label: "g (m/s²)", initial: "9.81" },
    ],
    body: (v) => ({
      ...(v.height.trim() ? { drop_height_mm: num(v.height, "Düşme yüksekliği") } : {}),
      gravity: { accel_m_s2: -Math.abs(num(v.g, "g")), direction: "Z" },
    }),
    tag: (v) => (v.height.trim() ? ` · H ${v.height} mm` : ""),
  },
  // K7 — S-kiriş: kızak arka halkada (crash box deseni)
  s_rail_shell: {
    hint: "Kabuk S tüp → rijit duvar x = 0 (ön uç); arka halka kızak (rijit gövde + kütle, boşsa yok).",
    fields: [{ key: "sled", label: "Kızak (kg)", initial: "", placeholder: "yok" }],
    body: (v) => {
      const sled = v.sled.trim() ? num(v.sled, "Kızak kütlesi") : null;
      return { rigid_bodies: sled ? [{ name: "kizak", region: "arka_halka", mass_kg: sled }] : [] };
    },
    tag: (v) => (v.sled.trim() ? ` · kızak ${v.sled} kg` : ""),
  },
  // K8 — kapı intrüzyonu: impaktör zorlanmış +x hız (yavaş itme)
  door_beam_shell: {
    hint:
      "Kiriş uçları ankastre (/BCS), Ø D silindir impaktör rijit gövde + zorlanmış +x hız (yavaş itme), " +
      "impaktör → kiriş TYPE7; intrüzyon = v·Süre. v₀ alanı kullanılmaz. FMVSS 214 kriterleri mühendisin.",
    fields: [{ key: "push", label: "İtme hızı (m/s)", initial: "1" }],
    body: (v) => ({ push_speed_m_s: num(v.push, "İtme hızı") }),
    tag: (v) => ` · itme ${v.push} m/s`,
  },
  // K10 — patlama yüklü plaka: Friedlander darbesi
  blast_plate_shell: {
    hint:
      "Kenarlar ankastre (/BCS); plaka yüzeyine Friedlander basıncı p(t) = Ps·(1 − t/td)·e^(−b·t/td) (/PLOAD, " +
      "kabuk normali boyunca — negatif Ps ters yön). v₀ alanı kullanılmaz.",
    fields: [
      { key: "ps", label: "Ps (MPa)", initial: "2" },
      { key: "td", label: "td (ms)", initial: "0.2" },
      { key: "b", label: "b (sönüm)", initial: "1" },
    ],
    body: (v) => ({
      blast_peak_mpa: num(v.ps, "Ps"),
      blast_duration_ms: num(v.td, "td"),
      blast_decay: num(v.b, "b"),
    }),
    tag: (v) => ` · Ps ${v.ps} MPa · td ${v.td} ms`,
  },
  // K11 — kepçe / taş: plaka–küre alanları (taş = rijit küre)
  get bucket_rock_shell(): Extras {
    return {
      ...EXTRAS.plate_ball_shell,
      hint:
        "Kepçe tabanının uzun kenarları sabit (/BCS), taş rijit gövde + −z ilk hız (ivme kanalı), taş → taban " +
        "TYPE7. Taş toplam kütlesi verilirse ek kütle = toplam − kabuk.",
    };
  },
  // K12 — kuş çarpması (SPH): ankastre plaka + kapsül SPH kuş
  bird_strike: {
    hint:
      "Kenarları ankastre plakanın ortasına SPH kuş (kapsül, su benzeri hidrodinamik, ρ 950, C1 2.2 GPa) −z ile " +
      "çarpar; kuş ölçüsü kütle ve boy/çap oranından. v₀ kuşun hızı.",
    fields: [
      { key: "birdKg", label: "Kuş kütlesi (kg)", initial: "1.82" },
      { key: "ld", label: "Boy / çap", initial: "2" },
    ],
    body: (v) => ({ bird_mass_kg: num(v.birdKg, "Kuş kütlesi"), bird_ld: num(v.ld, "Boy / çap") }),
    tag: (v) => ` · kuş ${v.birdKg} kg`,
  },
  // K13 — mayın / araç altı patlama: /LOAD/PBLAST (zemin yansımalı)
  underbody_blast: {
    hint:
      "Kenarları ankastre taban plakası; altında (−z) TNT eşdeğeri yük, zemin yansımalı ampirik patlama " +
      "(/LOAD/PBLAST, TM5-1300). Yük yüzeyi patlamaya bakacak şekilde yönlenir. v₀ kullanılmaz.",
    fields: [
      { key: "tnt", label: "TNT eşdeğeri (kg)", initial: "6" },
      { key: "standoff", label: "Mesafe (mm)", initial: "500" },
    ],
    body: (v) => ({ mine_tnt_kg: num(v.tnt, "TNT"), mine_standoff_mm: num(v.standoff, "Mesafe") }),
    tag: (v) => ` · ${v.tnt} kg TNT · ${v.standoff} mm`,
  },
  // K6 — FOPS: plaka–küre + düşme (H → v0, /GRAV −z)
  fops: {
    hint:
      "Kabin tavanı (plaka, kenar sabit) üstüne rijit cisim (küre) düşer: H'den v0 = √(2·g·H), /GRAV −z; " +
      "küre toplam kütlesi verilirse ek kütle = toplam − kabuk. v₀ alanı yok sayılır. ISO 3449 kriterleri mühendisin.",
    fields: [
      { key: "ballT", label: "Küre kabuk t (mm)", initial: "1" },
      { key: "ballMass", label: "Küre ek kütle (kg)", initial: "", placeholder: "yok" },
      { key: "ballTotal", label: "Küre toplam kütle (kg)", initial: "", placeholder: "—" },
      { key: "height", label: "H düşme (mm)", initial: "1000" },
      { key: "g", label: "g (m/s²)", initial: "9.81" },
    ],
    body: (v) => ({
      ball_thickness_mm: num(v.ballT, "Küre kabuk t"),
      ball_mass_kg: v.ballMass.trim() ? num(v.ballMass, "Küre ek kütlesi") : 0,
      ...(v.ballTotal?.trim() ? { ball_total_mass_kg: num(v.ballTotal, "Küre toplam kütlesi") } : {}),
      ...(v.height.trim() ? { drop_height_mm: num(v.height, "Düşme yüksekliği") } : {}),
      gravity: { accel_m_s2: -Math.abs(num(v.g, "g")), direction: "Z" },
    }),
    tag: (v) => ` · ${v.ballTotal || v.ballMass || "?"} kg · H ${v.height} mm`,
  },
  pole_beam_shell: {
    hint:
      "Silindirik rijit direk (/RWALL/CYL, eksen z) kirişin ortasında, ön yüzden g geride; uç halkaları rijit " +
      "gövde + ek kütle (araç kütlesi temsili); kiriş −x ile gelir.",
    fields: [
      { key: "pole", label: "Direk Ø (mm)", initial: "254" },
      { key: "endMass", label: "Uç kütlesi (kg, her biri)", initial: "10" },
    ],
    body: (v) => ({
      pole_diameter_mm: num(v.pole, "Direk çapı"),
      end_mass_kg: v.endMass.trim() ? num(v.endMass, "Uç kütlesi") : 0,
    }),
    tag: (v) => ` · Ø${v.pole}${v.endMass.trim() ? ` · ${v.endMass}+${v.endMass} kg` : ""}`,
  },
  rops_frame_shell: {
    hint:
      "Tabanlar sabit (/BCS), dikme 1 üst bükümü rijit gövde + yanal zorlanmış hız +y (yavaş itme); " +
      "deplasman = v·Süre, kuvvet iki dikmeyi z = H/2'de kesen /SECT'ten. v₀ alanı kullanılmaz. " +
      "ISO 3471 kriterleri mühendisin.",
    fields: [{ key: "push", label: "İtme hızı (m/s)", initial: "1" }],
    body: (v) => ({ push_speed_m_s: num(v.push, "İtme hızı") }),
    tag: (v) => ` · itme ${v.push} m/s`,
  },
};

interface SchemaProp {
  default?: number;
  symbol?: string;
  unit?: string;
  description?: string;
}

function geometryProps(t: GeometryTemplateInfo | undefined): [string, SchemaProp][] {
  return Object.entries((t?.params_schema.properties ?? {}) as Record<string, SchemaProp>);
}

const COMMON = { elem: "5", speed: "10", tEnd: "4", forceCfc: "", ishell: "0" };

/** /PROP/SHELL Ishell (hm_cfg radioss2022 PROP etiketleri). 0 = /DEF_SHELL
 * değeri (Radioss varsayılanı). Seçim mühendisin; V7 düşme kontrol verisi raporda. */
const ISHELL_OPTIONS: [string, string][] = [
  ["0", "0 · varsayılan (/DEF_SHELL)"],
  ["1", "1 · Q4, visko-elastik HG, ortogonal (Belytschko)"],
  ["2", "2 · Q4, visko-elastik HG, ortogonalsiz (Hallquist)"],
  ["3", "3 · Q4, elasto-plastik HG, ortogonal"],
  ["4", "4 · Q4, geliştirilmiş tip 1 (çarpık eleman)"],
  ["12", "12 · QBAT / DKT18"],
  ["24", "24 · QEPH"],
];

export default function CrashScenarioCard({
  onDone,
  onGeometry,
  onJobStarted,
}: {
  onDone?: () => void;
  /** Senaryo koşusu başladı — App bunu 5 · Sonuçlar paneline bağlar. */
  onJobStarted?: (res: CrashScenarioResponse) => void;
  /** Senaryonun sunucuda ürettiği geometri — App viewport'a yükler (TODO 11.6). */
  onGeometry?: (geometryId: number, name: string) => void;
}) {
  const [entries, setEntries] = useState<CrashCatalogEntry[]>([]);
  const [templates, setTemplates] = useState<Record<string, GeometryTemplateInfo>>({});
  const [entryId, setEntryId] = useState<string | null>(null);
  const [geo, setGeo] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [common, setCommon] = useState(COMMON);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [materialId, setMaterialId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<CrashScenarioResponse | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [percent, setPercent] = useState(0);

  useEffect(() => {
    fetchMaterials()
      .then((ms) => {
        setMaterials(ms);
        setMaterialId(ms.find((m) => m.name === "S235")?.id ?? ms[0]?.id ?? null);
      })
      .catch(() => undefined);
    Promise.all([fetchCrashCatalog(), fetchTemplates()])
      .then(([cat, tpls]) => {
        const ready = cat.entries.filter((e) => e.status === "ready" && e.template_id);
        setEntries(ready);
        setTemplates(Object.fromEntries(tpls.map((t) => [t.id, t])));
        setEntryId((cur) => cur ?? ready[0]?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Katalog okunamadı."));
  }, []);

  const entry = entries.find((e) => e.id === entryId);
  const template = entry?.template_id ? templates[entry.template_id] : undefined;
  // Örneğe özgü kayıt (ör. fops) şablonunkini ezer.
  const extras = entry ? (EXTRAS[entry.id] ?? (entry.template_id ? EXTRAS[entry.template_id] : undefined)) : undefined;
  const props = useMemo(() => geometryProps(template), [template]);
  const isShell = !!template && !template.tags.includes("solid");

  // Örnek değişince geometri / ek / ortak alanlar: katalog örneğinin başlangıç
  // değerleri (K5), yoksa şablon varsayılanı.
  const defaults = entry?.defaults;
  useEffect(() => {
    const dg = defaults?.geometry ?? {};
    setGeo(
      Object.fromEntries(
        props.map(([k, p]) => [k, dg[k] != null ? String(dg[k]) : p.default != null ? String(p.default) : ""]),
      ),
    );
    setExtra(Object.fromEntries((extras?.fields ?? []).map((f) => [f.key, defaults?.extras?.[f.key] ?? f.initial])));
    setCommon({ ...COMMON, ...(defaults?.common ?? {}) });
  }, [props, extras, defaults]);

  const jobId = res?.crash.job_id ?? null;
  useEffect(() => {
    if (!jobId || !status || TERMINAL.has(status)) return;
    const id = window.setInterval(() => {
      fetchCrashJob(jobId)
        .then((s) => {
          setStatus(s.status ?? null);
          setPercent(s.percent ?? 0);
          if (s.status && TERMINAL.has(s.status)) onDone?.();
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(id);
  }, [jobId, status, onDone]);

  const label = (k: string, p: SchemaProp) => `${p.symbol ?? k}${p.unit ? ` (${p.unit})` : ""}`;

  async function run() {
    if (!entry?.template_id) return;
    setBusy(true);
    setError(null);
    try {
      const geometry = Object.fromEntries(props.map(([k, p]) => [k, num(geo[k] ?? "", p.symbol ?? k)]));
      const dims = props.map(([k, p]) => `${p.symbol ?? k}${geo[k]}`).join(" ")
        + (isShell && common.ishell !== "0" ? ` Ishell ${common.ishell}` : "");
      const body: CrashScenarioRequest = {
        template_id: entry.template_id,
        name: `${entry.title} · ${dims} · ${common.speed} m/s${extras?.tag(extra) ?? ""}`,
        geometry,
        ...(extras?.body(extra) ?? {}),
        element_size_mm: num(common.elem, "Eleman boyutu"),
        material_id: materialId ?? undefined,
        speed_m_s: num(common.speed, "Hız"),
        t_end_ms: num(common.tEnd, "t_end"),
        filters: { force_cfc: common.forceCfc ? Number(common.forceCfc) : null, acc_cfc: defaults?.acc_cfc ?? null },
        ...(isShell && common.ishell !== "0" ? { model: { law: "plastic", shell: { ishell: Number(common.ishell) } } } : {}),
        wait: false,
      };
      const r = await postCrashScenario(body);
      setRes(r);
      setStatus(r.crash.status);
      setPercent(0);
      onGeometry?.(r.geometry_id, `${entry.template_id}.step`);
      if (r.crash.job_id) onJobStarted?.(r);
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Senaryo başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  const input = (value: string, onChange: (v: string) => void, lab: string, title?: string, placeholder?: string) => (
    <label className="mesh-field" key={lab} title={title}>
      <span>{lab}</span>
      <input value={value} placeholder={placeholder} disabled={busy} onChange={(e) => onChange(e.target.value)} />
    </label>
  );

  return (
    <details className="crash-mat-section crash-scenario" data-testid="crash-scenario">
      <summary>Hızlı senaryo{entry ? ` — ${entry.title}` : ""}</summary>
      <label className="mesh-field">
        <span>Katalog örneği</span>
        <select
          aria-label="Senaryo şablonu"
          value={entryId ?? ""}
          disabled={busy}
          onChange={(e) => setEntryId(e.target.value)}
        >
          {entries.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
        </select>
      </label>
      {entry && (
        <p className="material-assign-hint">
          Geometri yüklemeden: {extras?.hint ?? template?.description} Referans: {entry.reference} — {entry.validation}.
          Sonuç aşağıdaki koşu geçmişinde.
        </p>
      )}
      <div className="mesh-grid">
        {props.map(([k, p]) =>
          input(geo[k] ?? "", (v) => setGeo((g) => ({ ...g, [k]: v })), label(k, p), p.description),
        )}
        {(extras?.fields ?? []).map((f) =>
          input(extra[f.key] ?? "", (v) => setExtra((x) => ({ ...x, [f.key]: v })), f.label, undefined, f.placeholder),
        )}
        {input(common.elem, (v) => setCommon((c) => ({ ...c, elem: v })), "Eleman (mm)")}
        {input(common.speed, (v) => setCommon((c) => ({ ...c, speed: v })), "v₀ (m/s)")}
        {input(common.tEnd, (v) => setCommon((c) => ({ ...c, tEnd: v })), "Süre (ms)")}
        <label className="mesh-field">
          <span>CFC (F)</span>
          <select aria-label="Senaryo kuvvet CFC" value={common.forceCfc} disabled={busy}
            onChange={(e) => setCommon((c) => ({ ...c, forceCfc: e.target.value }))}>
            <option value="">Yok (ham)</option>
            {[60, 180, 600, 1000].map((c) => (
              <option key={c} value={String(c)}>
                CFC {c}
              </option>
            ))}
          </select>
        </label>
        {isShell && (
          <label className="mesh-field" title="/PROP/SHELL Ishell — kabuk formülasyonu">
            <span>Ishell</span>
            <select aria-label="Senaryo Ishell" value={common.ishell} disabled={busy}
              onChange={(e) => setCommon((c) => ({ ...c, ishell: e.target.value }))}>
              {ISHELL_OPTIONS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <label className="mesh-field">
        <span>Malzeme (tüm parçalar)</span>
        <select aria-label="Senaryo malzemesi" value={materialId ?? ""} disabled={busy}
          onChange={(e) => setMaterialId(Number(e.target.value))}>
          {materials.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="material-assign-button" disabled={busy || !entry} onClick={() => void run()}>
        {busy ? "Başlatılıyor…" : "Senaryoyu koş"}
      </button>
      {error && <p className="material-assign-hint">{error}</p>}
      {res && (
        <p className="material-assign-hint" data-testid="crash-scenario-status">
          koşu #{res.crash.run_id} · geometri {res.geometry_id} · {status}
          {status && !TERMINAL.has(status) ? ` · %${percent.toFixed(0)}` : ""}
        </p>
      )}
    </details>
  );
}
