import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  fetchCompositePlyField,
  fetchCompositeRuns,
  type CompositePlyField,
  type CompositePlySet,
  type CompositeRun,
} from "../../api/composite";
import { jet } from "../CrashAnimationViewer";

/** Faz 3.13 kompozit sonuç: koşu → katman seçici, gerilme / IRF konturu,
 * en büyük IRF (en küçük RF = 1/IRF). Eleman başına tek renk: gerilme katman
 * IP ortalaması, IRF katman IP'lerinin en büyüğü. Araç eşik koymaz. */

export type PlyQuantity = "tsai_wu" | "hashin" | "s11" | "s22" | "s12";
/** Katman indeksi (0 tabanlı) ya da "env" = tüm katmanlar zarfı. */
export type PlyPick = number | "env";

export const QUANTITIES: { key: PlyQuantity; label: string; unit: string }[] = [
  { key: "tsai_wu", label: "Tsai-Wu IRF", unit: "" },
  { key: "hashin", label: "Hashin IRF", unit: "" },
  { key: "s11", label: "σ11", unit: "MPa" },
  { key: "s22", label: "σ22", unit: "MPa" },
  { key: "s12", label: "τ12", unit: "MPa" },
];

export const MODE_LABEL: Record<string, string> = {
  fiber_tension: "lif çekme",
  fiber_compression: "lif basma",
  matrix_tension: "matris çekme",
  matrix_compression: "matris basma",
};

function grid(set: CompositePlySet, q: PlyQuantity): (number | null)[][] {
  if (q === "tsai_wu") return set.tsai_wu_irf;
  if (q === "hashin") return set.hashin_irf;
  return set[q];
}

/** Eleman başına değer. Zarf: IRF'te en büyük, gerilmede mutlak değeri en büyük (işaretli). */
export function elementValues(set: CompositePlySet, q: PlyQuantity, pick: PlyPick): (number | null)[] {
  const g = grid(set, q);
  const irf = q === "tsai_wu" || q === "hashin";
  return g.map((row) => {
    if (pick !== "env") return row[pick] ?? null;
    let best: number | null = null;
    for (const v of row) {
      if (v == null) continue;
      if (best == null || (irf ? v > best : Math.abs(v) > Math.abs(best))) best = v;
    }
    return best;
  });
}

export interface PlyRow {
  index: number;
  angle: number;
  material: string;
  twMax: number | null;
  hsMax: number | null;
  hsMode: number;
}

/** Katman başına en büyük IRF ve o elemandaki Hashin kipi. */
export function plyRows(set: CompositePlySet): PlyRow[] {
  return set.plies.map((p, k) => {
    let tw: number | null = null;
    let hs: number | null = null;
    let mode = -1;
    set.element_ids.forEach((_, e) => {
      const t = set.tsai_wu_irf[e]?.[k];
      const h = set.hashin_irf[e]?.[k];
      if (t != null && (tw == null || t > tw)) tw = t;
      if (h != null && (hs == null || h > hs)) {
        hs = h;
        mode = set.hashin_mode[e]?.[k] ?? -1;
      }
    });
    return { index: k, angle: p.angle_deg, material: p.material, twMax: tw, hsMax: hs, hsMode: mode };
  });
}

export function valueRange(vals: (number | null)[], irf: boolean): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of vals) {
    if (v == null) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo)) return [0, 1];
  if (irf) lo = 0;
  return hi > lo ? [lo, hi] : [lo, lo + 1];
}

export function fmtVal(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a === 0) return "0";
  if (a >= 100) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  return v.toFixed(3);
}

function rf(irf: number | boolean | undefined): string {
  return typeof irf === "number" && irf > 0 ? fmtVal(1 / irf) : "—";
}

function num(v: number | boolean | undefined): number | undefined {
  return typeof v === "number" ? v : undefined;
}

const NO_DATA = new THREE.Color(0xb8bec7);

function ContourView({
  set,
  values,
  range,
  label,
}: {
  set: CompositePlySet;
  values: (number | null)[];
  range: [number, number];
  label: string;
}) {
  const holderRef = useRef<HTMLDivElement>(null);
  const colorRef = useRef<((vals: (number | null)[], r: [number, number]) => void) | null>(null);
  const triElemRef = useRef<number[]>([]);
  const valsRef = useRef(values);
  valsRef.current = values;
  const [hover, setHover] = useState<{ e: number; x: number; y: number } | null>(null);

  useEffect(() => {
    const holder = holderRef.current;
    if (!holder) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      return; // WebGL yok (test ortamı)
    }
    const width = holder.clientWidth || 640;
    const height = holder.clientHeight || 360;
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(width, height);
    renderer.setClearColor(0xf4f6f8);
    holder.appendChild(renderer.domElement);
    const scene = new THREE.Scene();

    // Eleman başına düz renk: üçgenler indekssiz, köşe renkleri eleman rengiyle
    const pos: number[] = [];
    const triElem: number[] = [];
    const edge: number[] = [];
    set.faces.forEach((f, e) => {
      if (f.length < 3) return;
      for (let i = 1; i < f.length - 1; i++) {
        for (const n of [f[0], f[i], f[i + 1]]) pos.push(...set.nodes[n]);
        triElem.push(e);
      }
      f.forEach((n, i) => edge.push(...set.nodes[n], ...set.nodes[f[(i + 1) % f.length]]));
    });
    triElemRef.current = triElem;
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(pos), 3));
    const col = new Float32Array(pos.length);
    geom.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const mat = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(geom, mat);
    scene.add(mesh);
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(edge), 3));
    const em = new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.35 });
    scene.add(new THREE.LineSegments(eg, em));

    geom.computeBoundingBox();
    const box = geom.boundingBox ?? new THREE.Box3();
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const diag = size.length() || 1;
    const camera = new THREE.PerspectiveCamera(30, width / height, diag / 500, diag * 50);
    // En ince eksen boyunca bak (düz plaka → üstten)
    const axes = [size.x, size.y, size.z];
    const thin = axes.indexOf(Math.min(...axes));
    const dir = new THREE.Vector3(thin === 0 ? 1 : 0, thin === 1 ? -1 : 0, thin === 2 ? 1 : 0.25).normalize();
    camera.up.set(0, thin === 2 ? 1 : 0, thin === 2 ? 0 : 1);
    // Görünüm düzlemindeki iki eksene sığdır (dikey ↔ yatay en-boy oranı)
    const inPlane = axes.filter((_, i) => i !== thin);
    const [horiz, vert] = thin === 2 ? [size.x, size.y] : [Math.max(...inPlane), Math.min(...inPlane)];
    const halfTan = Math.tan((camera.fov * Math.PI) / 360);
    const dist = (Math.max(vert, horiz / camera.aspect) / 2 / halfTan) * 1.12 + size.getComponent(thin) / 2;
    camera.position.copy(center).addScaledVector(dir, dist);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.update();
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render);

    colorRef.current = (vals, [lo, hi]) => {
      const span = hi - lo || 1;
      triElem.forEach((e, t) => {
        const v = vals[e];
        const c = v == null ? [NO_DATA.r, NO_DATA.g, NO_DATA.b] : jet((v - lo) / span);
        for (let k = 0; k < 3; k++) col.set(c, (t * 3 + k) * 3);
      });
      geom.attributes.color.needsUpdate = true;
      render();
    };

    const ray = new THREE.Raycaster();
    const onMove = (ev: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      const p = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(p, camera);
      const hit = ray.intersectObject(mesh)[0];
      setHover(hit?.faceIndex != null ? { e: triElemRef.current[hit.faceIndex], x: ev.clientX - r.left, y: ev.clientY - r.top } : null);
    };
    const onLeave = () => setHover(null);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const ro = new ResizeObserver(() => {
      const w = holder.clientWidth;
      const h = holder.clientHeight;
      if (w < 2 || h < 2) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    });
    ro.observe(holder);
    return () => {
      ro.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      controls.dispose();
      geom.dispose();
      mat.dispose();
      eg.dispose();
      em.dispose();
      renderer.dispose();
      holder.removeChild(renderer.domElement);
      colorRef.current = null;
    };
  }, [set]);

  useEffect(() => {
    colorRef.current?.(values, range);
  }, [values, range, set]);

  const [lo, hi] = range;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo));
  return (
    <div className="composite-contour">
      <div className="composite-contour-view" ref={holderRef} data-testid="composite-contour">
        {hover && (
          <div className="composite-contour-tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
            Eleman {set.element_ids[hover.e]} · {label} {fmtVal(valsRef.current[hover.e])}
          </div>
        )}
      </div>
      <div className="composite-contour-legend">
        <div className="composite-contour-scale" aria-hidden="true" />
        <div className="composite-contour-ticks">
          {ticks.map((t, i) => (
            <span key={i}>{fmtVal(t)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function CompositeResultsPanel({
  geometryId,
  refreshKey = 0,
}: {
  geometryId: number | null;
  refreshKey?: number;
}) {
  const [runs, setRuns] = useState<CompositeRun[] | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [field, setField] = useState<CompositePlyField | null>(null);
  const [setName, setSetName] = useState<string>("");
  const [quantity, setQuantity] = useState<PlyQuantity>("tsai_wu");
  const [pick, setPick] = useState<PlyPick>("env");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (geometryId == null) return;
    let alive = true;
    setRuns(null);
    setError(null);
    fetchCompositeRuns(geometryId)
      .then((rs) => {
        if (!alive) return;
        const solved = rs.filter((r) => r.has_ply_field);
        setRuns(solved);
        setRunId((cur) => (cur != null && solved.some((r) => r.id === cur) ? cur : (solved[0]?.id ?? null)));
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [geometryId, refreshKey]);

  useEffect(() => {
    if (runId == null) {
      setField(null);
      return;
    }
    let alive = true;
    setField(null);
    fetchCompositePlyField(runId)
      .then((f) => {
        if (!alive) return;
        setField(f);
        setSetName(Object.keys(f.sets)[0] ?? "");
        setPick("env");
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [runId]);

  const set = field?.sets[setName];
  const irf = quantity === "tsai_wu" || quantity === "hashin";
  const values = useMemo(() => (set ? elementValues(set, quantity, pick) : []), [set, quantity, pick]);
  const range = useMemo(() => valueRange(values, irf), [values, irf]);
  const rows = useMemo(() => (set ? plyRows(set) : []), [set]);
  const qInfo = QUANTITIES.find((q) => q.key === quantity)!;
  const sc = field?.scalars ?? {};
  const modeName = (m: number) => MODE_LABEL[field?.hashin_modes[m] ?? ""] ?? "—";
  const hsMode = num(sc.hashin_mode);
  const shownMax = values.reduce<number | null>((b, v) => (v != null && (b == null || v > b) ? v : b), null);
  const shownMin = values.reduce<number | null>((b, v) => (v != null && (b == null || v < b) ? v : b), null);
  const noStrength = irf && values.every((v) => v == null);
  const barMax = Math.max(1e-12, ...rows.map((r) => (quantity === "hashin" ? r.hsMax : r.twMax) ?? 0));

  return (
    <div className="panel material-panel composite-results" data-testid="composite-results">
      <span className="eyebrow">Faz 3 · Sonuç</span>
      <h1>Katman sonuçları</h1>
      <p className="lead material-lead">
        Ply ekseninde gerilme (1 lif, 2 enine) ve hasar indeksi. IRF = 1 ölçütün sağlandığı yük; RF = 1/IRF.
      </p>
      {geometryId == null && <p className="filename">Önce geometri yükleyin.</p>}
      {error && <p className="filename">{error}</p>}
      {geometryId != null && runs == null && !error && <p className="filename">Koşular yükleniyor…</p>}
      {runs != null && runs.length === 0 && (
        <p className="filename" data-testid="composite-results-empty">
          Bu geometride ccx ile çözülmüş kompozit koşu yok.
        </p>
      )}
      {runs != null && runs.length > 0 && (
        <div className="composite-results-bar">
          <label>
            Koşu
            <select aria-label="Koşu" value={runId ?? ""} onChange={(e) => setRunId(Number(e.target.value))}>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} {r.name ?? ""}
                </option>
              ))}
            </select>
          </label>
          {field && Object.keys(field.sets).length > 1 && (
            <label>
              Parça
              <select aria-label="Parça" value={setName} onChange={(e) => setSetName(e.target.value)}>
                {Object.keys(field.sets).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
      {runId != null && !field && !error && <p className="filename">Katman alanı yükleniyor…</p>}
      {field && set && (
        <>
          <div className="composite-kpis" data-testid="composite-kpis">
            <div className="composite-kpi">
              <span className="composite-kpi-label">Tsai-Wu IRF en büyük</span>
              <strong>{fmtVal(num(sc.tsai_wu_irf_max))}</strong>
              <span className="composite-kpi-sub">
                RF en küçük {rf(sc.tsai_wu_irf_max)} · eleman {num(sc.tsai_wu_element) ?? "—"} · katman {num(sc.tsai_wu_ply) ?? "—"}
              </span>
            </div>
            <div className="composite-kpi">
              <span className="composite-kpi-label">Hashin IRF en büyük</span>
              <strong>{fmtVal(num(sc.hashin_irf_max))}</strong>
              <span className="composite-kpi-sub">
                RF en küçük {rf(sc.hashin_irf_max)} · {hsMode != null ? modeName(hsMode) : "—"} · eleman {num(sc.hashin_element) ?? "—"} · katman{" "}
                {num(sc.hashin_ply) ?? "—"}
              </span>
            </div>
            <div className="composite-kpi">
              <span className="composite-kpi-label">Model</span>
              <strong>
                {set.element_ids.length} eleman · {set.plies.length} katman
              </strong>
              <span className="composite-kpi-sub">
                F12* = {field.f12_star} · Hashin matris basma {sc.hashin_mc_s23 === 1 ? "S23 ile" : "S23 yok → (σ2/Yc)²"}
              </span>
            </div>
          </div>

          <div className="composite-results-body">
            <div className="composite-ply-list" role="listbox" aria-label="Katman seçici">
              <button
                type="button"
                role="option"
                aria-selected={pick === "env"}
                className={pick === "env" ? "composite-ply-row active" : "composite-ply-row"}
                onClick={() => setPick("env")}
              >
                <span className="composite-ply-id">Σ</span>
                <span className="composite-ply-name">Zarf (tümü)</span>
                <span className="composite-ply-val">{fmtVal(quantity === "hashin" ? num(sc.hashin_irf_max) : num(sc.tsai_wu_irf_max))}</span>
              </button>
              {[...rows].reverse().map((r) => {
                const v = quantity === "hashin" ? r.hsMax : r.twMax;
                return (
                  <button
                    key={r.index}
                    type="button"
                    role="option"
                    aria-selected={pick === r.index}
                    className={pick === r.index ? "composite-ply-row active" : "composite-ply-row"}
                    onClick={() => setPick(r.index)}
                    title={`${r.material} · Hashin kip: ${r.hsMode >= 0 ? modeName(r.hsMode) : "—"}`}
                  >
                    <span className="composite-ply-id">{r.index + 1}</span>
                    <span className="composite-ply-name">
                      {r.angle}°
                    </span>
                    <span className="composite-ply-bar" aria-hidden="true">
                      <span style={{ width: `${Math.max(0, ((v ?? 0) / barMax) * 100)}%` }} />
                    </span>
                    <span className="composite-ply-val">{fmtVal(v)}</span>
                  </button>
                );
              })}
              <p className="composite-ply-hint">
                Üst → alt · {set.plies[0]?.material}
                {new Set(set.plies.map((p) => p.material)).size > 1 && " ve diğerleri (ipucunda)"}. Çubuk: katmanın en büyük{" "}
                {quantity === "hashin" ? "Hashin" : "Tsai-Wu"} IRF'i.
              </p>
            </div>

            <div className="composite-results-view">
              <div className="composite-quantity" role="tablist" aria-label="Büyüklük">
                {QUANTITIES.map((q) => (
                  <button
                    key={q.key}
                    type="button"
                    role="tab"
                    aria-selected={quantity === q.key}
                    className={quantity === q.key ? "composite-quantity-tab active" : "composite-quantity-tab"}
                    onClick={() => setQuantity(q.key)}
                  >
                    {q.label}
                  </button>
                ))}
              </div>
              <p className="composite-view-caption" data-testid="composite-view-caption">
                {qInfo.label}
                {qInfo.unit && ` (${qInfo.unit})`} ·{" "}
                {pick === "env" ? "zarf" : `katman ${pick + 1} (${set.plies[pick].angle_deg}°)`} · min {fmtVal(shownMin)} · maks {fmtVal(shownMax)}
                {irf && shownMax != null && shownMax > 0 && ` · RF ${fmtVal(1 / shownMax)}`}
              </p>
              {noStrength ? (
                <p className="filename">Bu katmanın malzemesinde dayanım yok — IRF hesaplanmadı.</p>
              ) : (
                <ContourView set={set} values={values} range={range} label={qInfo.label} />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
