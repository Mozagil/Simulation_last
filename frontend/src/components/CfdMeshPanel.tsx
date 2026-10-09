/**
 * AKIŞ (CFD) · 2 · Mesh — Faz 2.7a. FEA mesh panelinden ayrı: parçanın değil
 * akışkan hacminin ağı (sanal rüzgâr tüneli). Ayarlar mühendisindir; sonuç
 * checkMesh / snappy / cfMesh verisi olarak gösterilir, öneri yok.
 */
import { useEffect, useRef, useState } from "react";
import {
  fetchCfdMesh,
  postCfdMesh,
  type CfdMeshMeta,
  type CfdMesher,
} from "../api/cfd";

type Fields = Record<string, string>;

const TUNNEL_DEFAULTS: Fields = {
  upstream: "3",
  downstream: "6",
  lateral: "3",
  ground_clearance_m: "0",
  base_cell_m: "0.05",
};

const SNAPPY_DEFAULTS: Fields = {
  surface_level_min: "2",
  surface_level_max: "3",
  feature_level: "3",
  wake_level: "1",
  wake_length: "2",
  n_layers: "3",
  expansion_ratio: "1.2",
  final_layer_thickness: "0.3",
  stl_size_mm: "",
};

function num(v: string): number {
  return Number(String(v).replace(",", "."));
}

function Field({ label, unit, value, onChange, disabled }: { label: string; unit?: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
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

function Acc({ n, title, summary, open, onToggle, children }: { n: number; title: string; summary: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <section className="crash-acc" aria-label={title}>
      <button type="button" className="crash-acc-toggle" aria-expanded={open} onClick={onToggle}>
        <span className="crash-acc-n">{n}</span>
        <span className="crash-acc-text">
          <strong>{title}</strong>
          <span className="crash-acc-summary">{summary}</span>
        </span>
        <span className="crash-acc-chev" aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && <div className="crash-acc-body">{children}</div>}
    </section>
  );
}

function fmt(v: number | undefined, digits = 3): string {
  return v === undefined || v === null || Number.isNaN(v) ? "—" : Number(v).toPrecision(digits);
}

export default function CfdMeshPanel({
  geometryId,
  onMeshReady,
  pollMs = 2000,
}: {
  geometryId: number | null;
  /** Mesh hazır olunca (çözüm adımı yamaları buradan alır). */
  onMeshReady?: (meta: CfdMeshMeta) => void;
  pollMs?: number;
}) {
  const [mesher, setMesher] = useState<CfdMesher>("snappy");
  const [tunnel, setTunnel] = useState<Fields>(TUNNEL_DEFAULTS);
  const [ground, setGround] = useState(false);
  const [snappy, setSnappy] = useState<Fields>(SNAPPY_DEFAULTS);
  const [open, setOpen] = useState<1 | 2 | 3 | null>(1);
  const [meta, setMeta] = useState<CfdMeshMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);
  useEffect(() => {
    setMeta(null);
    setError(null);
  }, [geometryId]);

  const toggle = (g: 1 | 2 | 3) => setOpen((cur) => (cur === g ? null : g));
  const setT = (k: string) => (v: string) => setTunnel((t) => ({ ...t, [k]: v }));
  const setS = (k: string) => (v: string) => setSnappy((s) => ({ ...s, [k]: v }));

  function poll(id: string) {
    timer.current = window.setTimeout(async () => {
      try {
        const m = await fetchCfdMesh(id);
        setMeta(m);
        if (m.status === "pending") {
          poll(id);
          return;
        }
        setBusy(false);
        if (m.status === "meshed") onMeshReady?.(m);
        else setError(m.message);
      } catch (e) {
        setBusy(false);
        setError((e as Error).message);
      }
    }, pollMs);
  }

  async function submit() {
    if (geometryId == null) return;
    setBusy(true);
    setError(null);
    setMeta(null);
    try {
      const m = await postCfdMesh({
        geometry_id: geometryId,
        mesher,
        tunnel: {
          upstream: num(tunnel.upstream),
          downstream: num(tunnel.downstream),
          lateral: num(tunnel.lateral),
          ground,
          ground_clearance_m: num(tunnel.ground_clearance_m),
          base_cell_m: num(tunnel.base_cell_m),
        },
        snappy: {
          surface_level_min: num(snappy.surface_level_min),
          surface_level_max: num(snappy.surface_level_max),
          feature_level: num(snappy.feature_level),
          wake_level: num(snappy.wake_level),
          wake_length: num(snappy.wake_length),
          n_layers: num(snappy.n_layers),
          expansion_ratio: num(snappy.expansion_ratio),
          final_layer_thickness: num(snappy.final_layer_thickness),
          stl_size_mm: snappy.stl_size_mm.trim() === "" ? null : num(snappy.stl_size_mm),
        },
      });
      setMeta(m);
      setOpen(3);
      poll(m.mesh_id);
    } catch (e) {
      setBusy(false);
      setError((e as Error).message);
    }
  }

  const surfCell = num(tunnel.base_cell_m) / 2 ** num(snappy.surface_level_max);
  const check = meta?.check ?? {};
  const layers = meta?.snappy?.layers ?? {};

  return (
    <div className="panel material-panel cfd-mesh-panel" data-testid="cfd-mesh-panel">
      <span className="eyebrow">Faz 2 · CFD mesh</span>
      <h1>Mesh (akışkan hacmi)</h1>
      <p className="lead material-lead">
        Parçanın değil etrafındaki akışkanın ağı: geometrinin sınır kutusundan rüzgâr tüneli kurulur, gövde
        yüzeyleri ayrı yamalar olur. Akış +x yönünde.
      </p>
      {geometryId == null && <p className="crash-behavior-hint">Önce 1 · Geometry'de bir STEP yükleyin ya da şablondan üretin.</p>}

      <Acc
        n={1}
        title="Rüzgâr tüneli"
        summary={`önde ${tunnel.upstream}L · arkada ${tunnel.downstream}L · yan ${tunnel.lateral}L · taban ${tunnel.base_cell_m} m${ground ? " · zemin" : ""}`}
        open={open === 1}
        onToggle={() => toggle(1)}
      >
        <p className="crash-behavior-hint">L = gövdenin x boyu. Mesafeler L'nin katı; taban hücre arka plan ağının boyu.</p>
        <div className="crash-expert-grid cols-3">
          <Field label="Önde" unit="× L" value={tunnel.upstream} onChange={setT("upstream")} disabled={busy} />
          <Field label="Arkada" unit="× L" value={tunnel.downstream} onChange={setT("downstream")} disabled={busy} />
          <Field label="Yan / üst" unit="× L" value={tunnel.lateral} onChange={setT("lateral")} disabled={busy} />
          <Field label="Taban hücre" unit="m" value={tunnel.base_cell_m} onChange={setT("base_cell_m")} disabled={busy} />
        </div>
        <label className="material-check">
          <input type="checkbox" checked={ground} disabled={busy} onChange={(e) => setGround(e.target.checked)} />
          <span>Zemin (alt yüz duvar — araç)</span>
        </label>
        {ground && (
          <div className="crash-expert-grid cols-3">
            <Field label="Gövde altı açıklık" unit="m" value={tunnel.ground_clearance_m} onChange={setT("ground_clearance_m")} disabled={busy} />
          </div>
        )}
      </Acc>

      <Acc
        n={2}
        title="Mesh'leyici, inceltme, sınır tabakası"
        summary={`${mesher === "snappy" ? "snappyHexMesh" : "cfMesh"} · yüzey seviyesi ${snappy.surface_level_min}–${snappy.surface_level_max} (≈ ${fmt(surfCell * 1000, 3)} mm) · ${snappy.n_layers} katman`}
        open={open === 2}
        onToggle={() => toggle(2)}
      >
        <span className="doe-seg" role="group" aria-label="Mesh'leyici">
          {(["snappy", "cfmesh"] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={mesher === m ? "doe-seg-opt active" : "doe-seg-opt"}
              aria-pressed={mesher === m}
              disabled={busy}
              onClick={() => setMesher(m)}
            >
              {m === "snappy" ? "snappyHexMesh" : "cfMesh"}
            </button>
          ))}
        </span>
        <p className="crash-behavior-hint">
          Seviye n → hücre = taban / 2ⁿ. cfMesh gövdede en yüksek seviyeyi kullanır; kenar seviyesi yalnız snappy'de.
        </p>
        <div className="crash-expert-grid cols-3">
          <Field label="Yüzey seviyesi min" value={snappy.surface_level_min} onChange={setS("surface_level_min")} disabled={busy} />
          <Field label="Yüzey seviyesi maks" value={snappy.surface_level_max} onChange={setS("surface_level_max")} disabled={busy} />
          <Field label="Kenar seviyesi" value={snappy.feature_level} onChange={setS("feature_level")} disabled={busy || mesher === "cfmesh"} />
          <Field label="İz kutusu seviyesi" value={snappy.wake_level} onChange={setS("wake_level")} disabled={busy} />
          <Field label="İz kutusu boyu" unit="× L" value={snappy.wake_length} onChange={setS("wake_length")} disabled={busy} />
          <Field label="STL üçgen boyu" unit="mm" value={snappy.stl_size_mm} onChange={setS("stl_size_mm")} disabled={busy} />
          <Field label="Katman sayısı" value={snappy.n_layers} onChange={setS("n_layers")} disabled={busy} />
          <Field label="Büyüme oranı" value={snappy.expansion_ratio} onChange={setS("expansion_ratio")} disabled={busy} />
          <Field label="Son katman kalınlığı" unit="× hücre" value={snappy.final_layer_thickness} onChange={setS("final_layer_thickness")} disabled={busy || mesher === "cfmesh"} />
        </div>
      </Acc>

      <button type="button" className="material-assign-button" disabled={busy || geometryId == null} onClick={() => void submit()}>
        {busy ? "Mesh üretiliyor…" : "Mesh üret"}
      </button>
      {error && <p className="error-message" role="alert">{error}</p>}

      {meta && (
        <Acc
          n={3}
          title="Sonuç (checkMesh)"
          summary={meta.status === "meshed" ? `${check.cells ?? "—"} hücre · ${check.mesh_ok ? "Mesh OK" : `${check.failed_checks ?? "?"} kontrol başarısız`}` : meta.status === "failed" ? "başarısız" : "üretiliyor…"}
          open={open === 3}
          onToggle={() => toggle(3)}
        >
          <p className="crash-behavior-hint" data-testid="cfd-mesh-status">{meta.message}</p>
          <table className="cfd-table">
            <tbody>
              <tr><th>Yüzey</th><td>{meta.surface.triangles} üçgen · açık kenar {meta.surface.open_edges}</td></tr>
              <tr><th>Tünel</th><td>{meta.domain.background_cells.join(" × ")} arka plan hücresi · L = {fmt(meta.domain.body_length_m)} m</td></tr>
              {meta.status === "meshed" && (
                <>
                  <tr><th>Hücre</th><td>{check.cells} (hex {check.hexahedra ?? "—"} · polihedra {check.polyhedra ?? "—"})</td></tr>
                  <tr><th>Non-orthogonality</th><td>maks {fmt(check.non_orthogonality_max)}° · ort. {fmt(check.non_orthogonality_avg)}°</td></tr>
                  <tr><th>Skewness maks</th><td>{fmt(check.skewness_max)}</td></tr>
                  <tr><th>Aspect ratio maks</th><td>{fmt(check.aspect_ratio_max)}</td></tr>
                  <tr><th>checkMesh</th><td className={check.mesh_ok ? "cfd-ok" : "cfd-warn"}>{check.mesh_ok ? "Mesh OK" : `${check.failed_checks} kontrol başarısız`}</td></tr>
                  {meta.cfmesh && <tr><th>cfMesh katman hücresi</th><td>{meta.cfmesh.layer_cells_added}</td></tr>}
                </>
              )}
            </tbody>
          </table>
          {Object.keys(layers).length > 0 && (
            <>
              <p className="crash-expert-title">Sınır tabakası kapsaması</p>
              <table className="cfd-table">
                <thead>
                  <tr><th>Yama</th><th>Hedef</th><th>Ort. katman</th><th>Kalınlık</th></tr>
                </thead>
                <tbody>
                  {Object.entries(layers).map(([name, l]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{l.target_layers}</td>
                      <td>{l.layers}</td>
                      <td>%{l.thickness_percent}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {meta.status === "meshed" && (
            <>
              <p className="crash-expert-title">Yamalar</p>
              <span className="docs-chips" data-testid="cfd-mesh-patches">
                {meta.patches.map((p) => (
                  <span key={p} className="docs-chip">
                    {p}
                    {check.patch_faces?.[p] !== undefined ? ` · ${check.patch_faces[p]} yüz` : ""}
                  </span>
                ))}
              </span>
            </>
          )}
        </Acc>
      )}
    </div>
  );
}
