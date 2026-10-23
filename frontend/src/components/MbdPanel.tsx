/**
 * MBD sekmesi — çeyrek araç tümsek geçişi (Faz 5.2b).
 * Parametreler mühendisindir; panel yalnız koşar ve zaman serisini gösterir.
 */
import { useState } from "react";
import { postMbdSolve, type MbdResult, type MbdSolveRequest } from "../api/mbd";

const COLORS = ["#2b6cb0", "#c05621", "#2f855a", "#9b2c2c"];

type RoadKind = MbdSolveRequest["road"]["kind"];

interface FormState {
  sprung_mass_kg: string;
  unsprung_mass_kg: string;
  suspension_k_n_per_m: string;
  suspension_c_n_s_per_m: string;
  tire_k_n_per_m: string;
  speed_m_s: string;
  height_mm: string;
  length_m: string;
  start_m: string;
  t_end_s: string;
  dt_s: string;
  kind: RoadKind;
}

const INITIAL: FormState = {
  sprung_mass_kg: "400",
  unsprung_mass_kg: "40",
  suspension_k_n_per_m: "20000",
  suspension_c_n_s_per_m: "1500",
  tire_k_n_per_m: "180000",
  speed_m_s: "10",
  height_mm: "50",
  length_m: "1",
  start_m: "2",
  t_end_s: "3",
  dt_s: "0.001",
  kind: "cosine_bump",
};

function num(v: string): number {
  return Number(String(v).replace(",", "."));
}

function fmt(n: number | undefined): string {
  if (n === undefined || !Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1000) return n.toFixed(0);
  if (a >= 10) return n.toFixed(2);
  return n.toPrecision(3);
}

function Field({
  label,
  unit,
  value,
  onChange,
  disabled,
}: {
  label: string;
  unit?: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="crash-unit-field">
      <span>{label}</span>
      <span className="crash-unit-box">
        <input aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        {unit && <em>{unit}</em>}
      </span>
    </label>
  );
}

function MbdChart({
  time,
  values,
  label,
  unit,
  color,
}: {
  time: number[];
  values: number[];
  label: string;
  unit: string;
  color: string;
}) {
  const n = Math.min(time.length, values.length);
  if (n < 2) return null;
  const w = 320;
  const height = 150;
  const pad = { l: 42, r: 8, t: 8, b: 22 };
  const ys = values.slice(0, n).filter((v) => Number.isFinite(v));
  const mn = Math.min(...ys);
  const mx = Math.max(...ys);
  const m = (mx - mn || Math.abs(mx) || 1) * 0.08;
  const lo = mn - m;
  const hi = mx + m;
  const t0 = time[0];
  const t1 = time[n - 1] || 1;
  const x = (t: number) => pad.l + ((w - pad.l - pad.r) * (t - t0)) / (t1 - t0 || 1);
  const y = (v: number) => pad.t + ((height - pad.t - pad.b) * (hi - v)) / (hi - lo);
  const ticks = Array.from({ length: 4 }, (_, i) => hi - ((hi - lo) * i) / 3);
  const d = values
    .slice(0, n)
    .map((v, i) => `${i ? "L" : "M"}${x(time[i]).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  return (
    <figure className="cfd-chart" data-testid={`mbd-chart-${label}`}>
      <svg viewBox={`0 0 ${w} ${height}`} role="img" aria-label={`${label} (${unit})`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} className="cfd-chart-grid" />
            <text x={pad.l - 4} y={y(t) + 3} textAnchor="end" className="cfd-chart-tick">
              {fmt(t)}
            </text>
          </g>
        ))}
        <text x={w - pad.r} y={height - 4} textAnchor="end" className="cfd-chart-tick">
          {t1.toFixed(2)} s
        </text>
        <path d={d} fill="none" stroke={color} strokeWidth="1.3" />
      </svg>
      <figcaption className="cfd-chart-legend">
        <span>
          <i style={{ background: color }} /> {label} ({unit})
        </span>
      </figcaption>
    </figure>
  );
}

function buildRequest(f: FormState): MbdSolveRequest | string {
  const sprung = num(f.sprung_mass_kg);
  const unsprung = num(f.unsprung_mass_kg);
  const k = num(f.suspension_k_n_per_m);
  const c = num(f.suspension_c_n_s_per_m);
  const kt = num(f.tire_k_n_per_m);
  const speed = num(f.speed_m_s);
  const height = num(f.height_mm);
  const length = num(f.length_m);
  const start = num(f.start_m);
  const tEnd = num(f.t_end_s);
  const dt = num(f.dt_s);
  if (![sprung, unsprung, k, kt, speed, length, tEnd, dt].every((v) => Number.isFinite(v) && v > 0)) {
    return "Kütle, yay, hız, tümsek boyu, süre ve adım sıfırdan büyük olmalı.";
  }
  if (!Number.isFinite(c) || c < 0) return "Sönüm sıfır veya pozitif olmalı.";
  if (!Number.isFinite(height) || height < 0) return "Tümsek yüksekliği sıfır veya pozitif olmalı.";
  if (!Number.isFinite(start) || start < 0) return "Tümsek başlangıcı sıfır veya pozitif olmalı.";
  if (dt > 0.1 || tEnd > 60) return "Adım en çok 0.1 s, süre en çok 60 s.";
  return {
    sprung_mass_kg: sprung,
    unsprung_mass_kg: unsprung,
    suspension_k_n_per_m: k,
    suspension_c_n_s_per_m: c,
    tire_k_n_per_m: kt,
    speed_m_s: speed,
    road: { kind: f.kind, height_mm: height, length_m: length, start_m: start },
    t_end_s: tEnd,
    dt_s: dt,
  };
}

export default function MbdPanel() {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MbdResult | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function run() {
    const body = buildRequest(form);
    if (typeof body === "string") {
      setError(body);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await postMbdSolve(body));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const curves = result?.curves;
  const time = curves?.time ?? [];
  const sc = result?.scalars;
  const wall = result?.diagnostics.summary?.wall_s;

  return (
    <div className="panel material-panel mbd-panel" data-testid="mbd-panel">
      <span className="eyebrow">Faz 5 · Project Chrono</span>
      <h1>Çeyrek araç</h1>
      <p className="lead material-lead">
        2 serbestlik, sabit hız, yol profili. Geometri yok. Birimler SI.
      </p>

      <div className="crash-expert-grid cols-2">
        <Field label="Gövde kütlesi" unit="kg" value={form.sprung_mass_kg} disabled={busy} onChange={(v) => set("sprung_mass_kg", v)} />
        <Field label="Tekerlek kütlesi" unit="kg" value={form.unsprung_mass_kg} disabled={busy} onChange={(v) => set("unsprung_mass_kg", v)} />
        <Field label="Süspansiyon yayı" unit="N/m" value={form.suspension_k_n_per_m} disabled={busy} onChange={(v) => set("suspension_k_n_per_m", v)} />
        <Field label="Süspansiyon sönümü" unit="N·s/m" value={form.suspension_c_n_s_per_m} disabled={busy} onChange={(v) => set("suspension_c_n_s_per_m", v)} />
        <Field label="Lastik yayı" unit="N/m" value={form.tire_k_n_per_m} disabled={busy} onChange={(v) => set("tire_k_n_per_m", v)} />
        <Field label="Hız" unit="m/s" value={form.speed_m_s} disabled={busy} onChange={(v) => set("speed_m_s", v)} />
      </div>

      <label className="crash-unit-field wide">
        <span>Yol profili</span>
        <span className="crash-unit-box">
          <select aria-label="Yol profili" value={form.kind} disabled={busy} onChange={(e) => set("kind", e.target.value as RoadKind)}>
            <option value="cosine_bump">Kosinüs tümsek</option>
            <option value="step">Basamak</option>
          </select>
        </span>
      </label>
      <div className="crash-expert-grid cols-3">
        <Field label="Tümsek yüksekliği" unit="mm" value={form.height_mm} disabled={busy} onChange={(v) => set("height_mm", v)} />
        <Field label="Tümsek boyu" unit="m" value={form.length_m} disabled={busy} onChange={(v) => set("length_m", v)} />
        <Field label="Tümsek başlangıcı" unit="m" value={form.start_m} disabled={busy} onChange={(v) => set("start_m", v)} />
        <Field label="Süre" unit="s" value={form.t_end_s} disabled={busy} onChange={(v) => set("t_end_s", v)} />
        <Field label="Zaman adımı" unit="s" value={form.dt_s} disabled={busy} onChange={(v) => set("dt_s", v)} />
      </div>

      <button type="button" className="material-assign-button" disabled={busy} onClick={() => void run()}>
        {busy ? "Çözülüyor…" : "Çeyrek aracı çalıştır"}
      </button>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      {sc && (
        <>
          <dl className="mbd-scalars" data-testid="mbd-scalars">
            <div>
              <dt>İvme</dt>
              <dd>
                {fmt(sc.body_acc_m_s2_max)} / {fmt(sc.body_acc_m_s2_min)}
              </dd>
              <dd className="mbd-scalar-unit">m/s² tepe / taban</dd>
            </div>
            <div>
              <dt>Süspansiyon kuvveti</dt>
              <dd>
                {fmt(sc.susp_force_n_max)} / {fmt(sc.susp_force_n_min)}
              </dd>
              <dd className="mbd-scalar-unit">N tepe / taban</dd>
            </div>
            <div>
              <dt>Sıkışma</dt>
              <dd>
                {fmt(sc.susp_deflection_m_max)} / {fmt(sc.susp_deflection_m_min)}
              </dd>
              <dd className="mbd-scalar-unit">m tepe / taban</dd>
            </div>
          </dl>
          {wall !== undefined && (
            <p className="crash-behavior-hint">
              {result?.diagnostics.summary?.steps ?? "—"} adım · {wall} s
            </p>
          )}
          <MbdChart time={time} values={curves?.body_acc_m_s2 ?? []} label="Gövde ivmesi" unit="m/s²" color={COLORS[0]} />
          <MbdChart time={time} values={curves?.susp_force_n ?? []} label="Süspansiyon kuvveti" unit="N" color={COLORS[1]} />
          <MbdChart time={time} values={curves?.susp_deflection_m ?? []} label="Sıkışma" unit="m" color={COLORS[2]} />
        </>
      )}
    </div>
  );
}
