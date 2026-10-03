import { useEffect, useState } from "react";
import { fetchCrashJob, postCrashScenario, type CrashScenarioResponse } from "../api/crash";
import { fetchMaterials, type Material } from "../api/materials";

/** Hızlı senaryo (1.17g-7): crash_box_shell şablonundan tek çağrıda koşu
 * (POST /crash/scenario, 1.17a) — geometri yüklemeden. Değerler mühendisin;
 * varsayılanlar 1.13–1.16 kurulumuyla aynı. Kızak kütlesi boşsa kızak yok. */

const TERMINAL = new Set(["rad_only", "solved", "failed", "done"]);

interface Fields {
  L: string;
  h: string;
  b: string;
  t: string;
  elem: string;
  speed: string;
  tEnd: string;
  sled: string;
  forceCfc: string;
}

const DEFAULTS: Fields = { L: "300", h: "50", b: "40", t: "3", elem: "5", speed: "10", tEnd: "4", sled: "", forceCfc: "" };

function num(raw: string, what: string): number {
  const v = Number(raw.trim().replace(",", "."));
  if (!raw.trim() || !Number.isFinite(v)) throw new Error(`${what}: sayı geçersiz (${raw || "boş"})`);
  return v;
}

export default function CrashScenarioCard({ onDone }: { onDone?: () => void }) {
  const [f, setF] = useState<Fields>(DEFAULTS);
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
  }, []);

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

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const sled = f.sled.trim() ? num(f.sled, "Kızak kütlesi") : null;
      const body = {
        name: `Senaryo L${f.L} h${f.h} b${f.b} t${f.t} · ${f.speed} m/s${sled ? ` · kızak ${sled} kg` : ""}`,
        geometry: { box_length: num(f.L, "L"), box_height: num(f.h, "h"), box_width: num(f.b, "b"), wall: num(f.t, "t") },
        element_size_mm: num(f.elem, "Eleman boyutu"),
        material_id: materialId ?? undefined,
        speed_m_s: num(f.speed, "Hız"),
        t_end_ms: num(f.tEnd, "t_end"),
        rigid_bodies: sled ? [{ name: "kizak", region: "kutu_arka", mass_kg: sled }] : [],
        filters: { force_cfc: f.forceCfc ? Number(f.forceCfc) : null, acc_cfc: null },
        wait: false,
      };
      const r = await postCrashScenario(body);
      setRes(r);
      setStatus(r.crash.status);
      setPercent(0);
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Senaryo başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof Fields, label: string, placeholder?: string) => (
    <label className="mesh-field">
      <span>{label}</span>
      <input
        value={f[key]}
        placeholder={placeholder}
        disabled={busy}
        onChange={(e) => setF((x) => ({ ...x, [key]: e.target.value }))}
      />
    </label>
  );

  return (
    <details className="crash-mat-section crash-scenario" data-testid="crash-scenario">
      <summary>Hızlı senaryo — crash box şablonu</summary>
      <p className="material-assign-hint">
        Geometri yüklemeden: şablon → kabuk mesh → malzeme → OpenRadioss (rijit duvar x = 0, ön uç).
        Sonuç aşağıdaki koşu geçmişinde.
      </p>
      <div className="mesh-grid">
        {field("L", "L (mm)")}
        {field("h", "h (mm)")}
        {field("b", "b (mm)")}
        {field("t", "t (mm)")}
        {field("elem", "Eleman (mm)")}
        {field("speed", "v₀ (m/s)")}
        {field("tEnd", "Süre (ms)")}
        {field("sled", "Kızak (kg)", "yok")}
        <label className="mesh-field">
          <span>CFC (F)</span>
          <select aria-label="Senaryo kuvvet CFC" value={f.forceCfc} disabled={busy}
            onChange={(e) => setF((x) => ({ ...x, forceCfc: e.target.value }))}>
            <option value="">Yok (ham)</option>
            {[60, 180, 600, 1000].map((c) => (
              <option key={c} value={String(c)}>
                CFC {c}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="mesh-field">
        <span>Malzeme</span>
        <select aria-label="Senaryo malzemesi" value={materialId ?? ""} disabled={busy}
          onChange={(e) => setMaterialId(Number(e.target.value))}>
          {materials.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="material-assign-button" disabled={busy} onClick={() => void run()}>
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
