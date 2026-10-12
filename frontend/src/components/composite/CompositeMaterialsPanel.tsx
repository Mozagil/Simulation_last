import { useEffect, useMemo, useState } from "react";
import { formatGPa, formatMPa } from "../../api/materials";
import {
  createCompositeMaterial,
  fetchCompositeMaterials,
  type CompositeMaterial,
} from "../../api/composite";

function parsePositive(raw: string): number | null {
  const n = Number(raw.replace(",", "."));
  return Number.isFinite(n) && n > 0 ? n : null;
}

const EMPTY_FORM = {
  name: "",
  density: "",
  e1: "",
  e2: "",
  e3: "",
  nu12: "",
  nu13: "",
  nu23: "",
  g12: "",
  g13: "",
  g23: "",
  xt: "",
  xc: "",
  yt: "",
  yc: "",
  s12: "",
};

export default function CompositeMaterialsPanel() {
  const [materials, setMaterials] = useState<CompositeMaterial[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    let cancelled = false;
    fetchCompositeMaterials()
      .then((rows) => {
        if (cancelled) return;
        setMaterials(rows);
        setSelectedId((prev) => prev ?? rows[0]?.id ?? null);
        setLoadError(null);
        setLoaded(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Ply listesi alınamadı.");
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () => materials.find((m) => m.id === selectedId) ?? null,
    [materials, selectedId],
  );

  function setField(key: keyof typeof EMPTY_FORM, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreate() {
    const name = form.name.trim();
    const density = parsePositive(form.density);
    const e1 = parsePositive(form.e1);
    const e2 = parsePositive(form.e2);
    const e3 = parsePositive(form.e3);
    const nu12 = parsePositive(form.nu12);
    const nu13 = parsePositive(form.nu13);
    const nu23 = parsePositive(form.nu23);
    const g12 = parsePositive(form.g12);
    const g13 = parsePositive(form.g13);
    const g23 = parsePositive(form.g23);
    const xt = parsePositive(form.xt);
    const xc = parsePositive(form.xc);
    const yt = parsePositive(form.yt);
    const yc = parsePositive(form.yc);
    const s12 = parsePositive(form.s12);
    if (
      !name ||
      density == null ||
      e1 == null ||
      e2 == null ||
      e3 == null ||
      nu12 == null ||
      nu13 == null ||
      nu23 == null ||
      g12 == null ||
      g13 == null ||
      g23 == null ||
      xt == null ||
      xc == null ||
      yt == null ||
      yc == null ||
      s12 == null
    ) {
      setFormError("Ad ve tüm sayı alanları (pozitif) gerekli.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const created = await createCompositeMaterial({
        name,
        density,
        e1: e1 * 1e9,
        e2: e2 * 1e9,
        e3: e3 * 1e9,
        nu12,
        nu13,
        nu23,
        g12: g12 * 1e9,
        g13: g13 * 1e9,
        g23: g23 * 1e9,
        xt: xt * 1e6,
        xc: xc * 1e6,
        yt: yt * 1e6,
        yc: yc * 1e6,
        s12: s12 * 1e6,
      });
      setMaterials((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      setSelectedId(created.id);
      setForm(EMPTY_FORM);
      setShowForm(false);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Ply eklenemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel material-panel" data-testid="composite-materials">
      <span className="eyebrow">Faz 3 · Ply</span>
      <h1>Ply kütüphanesi</h1>
      <p className="lead material-lead">
        Ortotrop ply sabitleri (Pa cinsinden saklanır; burada GPa / MPa). Tipik seed değerler mill
        test değildir. Araç malzeme önermez.
      </p>
      {loadError && <p className="filename">{loadError}</p>}
      {!loaded && !loadError && <p className="filename">Ply listesi yükleniyor…</p>}
      {loaded && !loadError && materials.length === 0 && (
        <p className="filename">Kütüphane boş.</p>
      )}
      {materials.length > 0 && (
        <>
          <label className="mesh-field material-field">
            <span>Kütüphane</span>
            <select
              aria-label="Ply seç"
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}
            >
              {materials.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.category})
                </option>
              ))}
            </select>
          </label>
          {selected && (
            <div className="material-props composite-props">
              <p>
                <span>tür</span>
                {selected.ply_kind}
              </p>
              <p>
                <span>kaynak</span>
                {selected.source === "library" ? "kütüphane" : "kullanıcı"}
              </p>
              {selected.standard && (
                <p>
                  <span>not</span>
                  {selected.standard}
                </p>
              )}
              <p>
                <span>E1</span>
                {formatGPa(selected.e1)}
              </p>
              <p>
                <span>E2</span>
                {formatGPa(selected.e2)}
              </p>
              <p>
                <span>E3</span>
                {formatGPa(selected.e3)}
              </p>
              <p>
                <span>G12</span>
                {formatGPa(selected.g12)}
              </p>
              <p>
                <span>G13</span>
                {formatGPa(selected.g13)}
              </p>
              <p>
                <span>G23</span>
                {formatGPa(selected.g23)}
              </p>
              <p>
                <span>ν12</span>
                {selected.nu12.toFixed(2)}
              </p>
              <p>
                <span>ν13</span>
                {selected.nu13.toFixed(2)}
              </p>
              <p>
                <span>ν23</span>
                {selected.nu23.toFixed(2)}
              </p>
              <p>
                <span>ρ</span>
                {selected.density.toFixed(0)} kg/m³
              </p>
              <p>
                <span>Xt</span>
                {formatMPa(selected.xt)}
              </p>
              <p>
                <span>Xc</span>
                {formatMPa(selected.xc)}
              </p>
              <p>
                <span>Yt</span>
                {formatMPa(selected.yt)}
              </p>
              <p>
                <span>Yc</span>
                {formatMPa(selected.yc)}
              </p>
              <p>
                <span>S12</span>
                {formatMPa(selected.s12)}
              </p>
            </div>
          )}
        </>
      )}
      {loaded && (
        <div className="material-action-row">
          <button
            type="button"
            className="material-secondary-button"
            onClick={() => setShowForm((prev) => !prev)}
          >
            {showForm ? "Formu kapat" : "+ ÖZEL"}
          </button>
        </div>
      )}
      {showForm && (
        <div className="material-custom">
          <p className="material-assignments-title">Özel ply</p>
          <label className="mesh-field material-field">
            <span>Ad</span>
            <input
              aria-label="Ply adı"
              value={form.name}
              onChange={(e) => setField("name", e.target.value)}
              placeholder="Örn. T700/epoxy"
            />
          </label>
          <div className="material-custom-grid">
            <label className="mesh-field">
              <span>E1 (GPa)</span>
              <input aria-label="E1" value={form.e1} onChange={(e) => setField("e1", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>E2 (GPa)</span>
              <input aria-label="E2" value={form.e2} onChange={(e) => setField("e2", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>E3 (GPa)</span>
              <input aria-label="E3" value={form.e3} onChange={(e) => setField("e3", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>G12 (GPa)</span>
              <input aria-label="G12" value={form.g12} onChange={(e) => setField("g12", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>G13 (GPa)</span>
              <input aria-label="G13" value={form.g13} onChange={(e) => setField("g13", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>G23 (GPa)</span>
              <input aria-label="G23" value={form.g23} onChange={(e) => setField("g23", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>ν12</span>
              <input aria-label="nu12" value={form.nu12} onChange={(e) => setField("nu12", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>ν13</span>
              <input aria-label="nu13" value={form.nu13} onChange={(e) => setField("nu13", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>ν23</span>
              <input aria-label="nu23" value={form.nu23} onChange={(e) => setField("nu23", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>ρ (kg/m³)</span>
              <input aria-label="density" value={form.density} onChange={(e) => setField("density", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Xt (MPa)</span>
              <input aria-label="Xt" value={form.xt} onChange={(e) => setField("xt", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Xc (MPa)</span>
              <input aria-label="Xc" value={form.xc} onChange={(e) => setField("xc", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Yt (MPa)</span>
              <input aria-label="Yt" value={form.yt} onChange={(e) => setField("yt", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>Yc (MPa)</span>
              <input aria-label="Yc" value={form.yc} onChange={(e) => setField("yc", e.target.value)} />
            </label>
            <label className="mesh-field">
              <span>S12 (MPa)</span>
              <input aria-label="S12" value={form.s12} onChange={(e) => setField("s12", e.target.value)} />
            </label>
          </div>
          {formError && <p className="filename">{formError}</p>}
          <button
            type="button"
            className="material-secondary-button"
            disabled={saving}
            onClick={() => void handleCreate()}
          >
            {saving ? "Ekleniyor…" : "Özel ply ekle"}
          </button>
        </div>
      )}
    </div>
  );
}
