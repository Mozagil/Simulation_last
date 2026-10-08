/**
 * Crash · 3 Material adımı — BC paneli gibi akordeon (kullanıcı 2026-10-08):
 * 1 Kütüphane malzemesi · 2 Parçalara ata · 3 Davranış ve kopma. Her grup
 * kapalıyken tek satırla özetlenir; eksik varsa sayaç "x eksik" der.
 * Durability'nin malzeme adımına dokunulmaz.
 */
import { useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import type { Material, MaterialAssignment } from "../api/materials";
import CrashMaterialSection, { matCardSummary } from "./CrashMaterialSection";
import type { MatCardState } from "./CrashMaterialCard";
import { DynaToggle } from "./Kw";

function gpa(pa: number) {
  return `${(pa / 1e9).toFixed(1)} GPa`;
}
function mpa(pa: number) {
  return `${(pa / 1e6).toFixed(0)} MPa`;
}

function Head({
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
  state: string;
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
      <span className="crash-acc-chev" aria-hidden="true">
        {open ? "▴" : "▾"}
      </span>
    </button>
  );
}

export default function CrashMaterialStep({
  materials,
  selectedMaterialId,
  onSelectMaterial,
  partIds,
  assignments,
  thicknessByPart,
  isShell,
  hasModel = true,
  busy,
  onAssign,
  onCustom,
  crashCurves,
  treeEditor,
  matCard,
  setMatCard,
  partCards,
  setPartCards,
}: {
  materials: Material[];
  selectedMaterialId: number | null;
  onSelectMaterial: (id: number) => void;
  partIds: number[];
  assignments: MaterialAssignment[];
  /** Kabuk kalınlığı (ürün ağacı), parça → mm. */
  thicknessByPart: Record<number, number | null | undefined>;
  isShell: boolean;
  /** Geometri + mesh var mı — yoksa atama grubu "eksik" değil "bekliyor". */
  hasModel?: boolean;
  busy: boolean;
  /** Seçili kütüphane malzemesini bu parçalara ata. */
  onAssign: (partIds: number[]) => void;
  onCustom: () => void;
  /** Kütüphane malzemesinin LAW36 eğrileri (MaterialCrashCurves). */
  crashCurves?: ReactNode;
  /** Ürün ağacı (kalınlık / malzeme düzenleme). */
  treeEditor?: ReactNode;
  matCard: MatCardState;
  setMatCard: (m: MatCardState) => void;
  partCards: Record<number, MatCardState>;
  setPartCards: Dispatch<SetStateAction<Record<number, MatCardState>>>;
}) {
  const [open, setOpen] = useState<1 | 2 | 3 | null>(1);
  const toggle = (g: 1 | 2 | 3) => setOpen((cur) => (cur === g ? null : g));
  const sel = materials.find((m) => m.id === selectedMaterialId) ?? null;
  const parts = partIds.length ? partIds : [0];
  const assignedOf = (pid: number) => assignments.find((a) => a.part_id === pid) ?? null;
  const unassigned = parts.filter((pid) => !assignedOf(pid));
  const noThickness = isShell ? parts.filter((pid) => !(Number(thicknessByPart[pid]) > 0)) : [];

  const libState = sel ? "hazır" : "1 eksik";
  const libSummary = sel
    ? `${sel.name} · E ${gpa(sel.youngs_modulus)} · σy ${mpa(sel.yield_strength)} · ρ ${sel.density.toFixed(0)}`
    : "kütüphaneden malzeme seçin";
  const assignMissing = unassigned.length + noThickness.length;
  const assignState = !hasModel ? "bekliyor" : assignMissing ? `${assignMissing} eksik` : "hazır";
  const assignSummary = !hasModel
    ? "önce geometri yükle ve mesh üret (1 · Geometry, 2 · Mesh)"
    : parts
    .map((pid) => {
      const a = assignedOf(pid);
      const t = thicknessByPart[pid];
      return `#${pid} ${a ? a.material_name : "atanmadı"}${isShell && t ? ` · ${t} mm` : ""}`;
    })
    .join(" · ");
  const behaviorSummary =
    matCardSummary(matCard) +
    (Object.keys(partCards).length ? ` · ${Object.keys(partCards).length} parçaya ayrı model` : "");
  const ready = [libState, assignState, "hazır"].filter((s) => s === "hazır").length;
  const total = hasModel ? 3 : 2;

  return (
    <div className="crash-mat-step" data-testid="crash-material-step">
      <p className="lead material-lead">
        Üç adım: kütüphaneden malzemeyi seç, parçalara ata, çarpışmadaki davranışını (akma, kopma) belirle.
      </p>
      <DynaToggle />
      <div className="crash-acc-head">
        <span className="crash-q-title">Malzeme</span>
        <span className={ready === total ? "crash-acc-count ok" : "crash-acc-count"} data-testid="crash-mat-ready">
          {ready} / {total} hazır
        </span>
      </div>

      <section className="crash-acc" aria-label="Kütüphane malzemesi">
        <Head n={1} title="Kütüphane malzemesi" summary={libSummary} state={libState} open={open === 1} onToggle={() => toggle(1)} />
        {open === 1 && (
          <div className="crash-acc-body">
            <p className="crash-behavior-hint">
              OpenRadioss malzeme kartına giden değerler. Davranış modeli (3. grup) bunları kullanır; LAW2'de σy boşsa
              buradaki akma alınır.
            </p>
            <button type="button" className="crash-law-jump" onClick={() => setOpen(3)}>
              Malzeme modeli (LAW1 / LAW2 / LAW36) → 3. grupta seç · şu an: {behaviorSummary}
            </button>
            <label className="crash-expert-field">
              <span>Malzeme</span>
              <select
                aria-label="Kütüphane malzemesi"
                value={selectedMaterialId ?? ""}
                disabled={busy}
                onChange={(e) => onSelectMaterial(Number(e.target.value))}
              >
                {materials.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.category})
                  </option>
                ))}
              </select>
            </label>
            {sel && (
              <div className="crash-mat-props" data-testid="crash-mat-props">
                <span>E · elastisite modülü</span>
                <b>{gpa(sel.youngs_modulus)}</b>
                <code>/MAT E</code>
                <span>ν · Poisson</span>
                <b>{sel.poisson_ratio.toFixed(2)}</b>
                <code>/MAT ν</code>
                <span>ρ · yoğunluk</span>
                <b>{sel.density.toFixed(0)} kg/m³</b>
                <code>/MAT ρ</code>
                <span>σy · akma (Rp0.2)</span>
                <b>{mpa(sel.yield_strength)}</b>
                <code>LAW2 a</code>
              </div>
            )}
            <p className="crash-behavior-hint">
              Explicit (OpenRadioss) yalnız bu dört değeri ve LAW36 eğrilerini kullanır. Çekme dayanımı, uzama ve S-N
              durability'ye aittir; burada gösterilmez.
            </p>
            {crashCurves}
            <button type="button" className="doe-btn doe-btn-ghost" disabled={busy} onClick={onCustom}>
              + Özel malzeme
            </button>
          </div>
        )}
      </section>

      <section className="crash-acc" aria-label="Parçalara ata">
        <Head n={2} title="Parçalara ata" summary={assignSummary} state={assignState} open={open === 2} onToggle={() => toggle(2)} />
        {open === 2 && (
          <div className="crash-acc-body">
            <p className="crash-behavior-hint">
              Seçili kütüphane malzemesi ({sel?.name ?? "—"}) parçaya atanır.
              {isShell ? " Kabuk kalınlığı ürün ağacındaki bileşenden gelir (aşağıda düzenlenir)." : ""}
            </p>
            {!hasModel && (
              <p className="doe-empty" data-testid="crash-mat-no-model">
                Henüz parça yok. 1 · Geometry'de model yükle, 2 · Mesh'te mesh üret; parçalar burada listelenir.
              </p>
            )}
            {hasModel && (
            <div className="crash-mat-parts">
              {parts.map((pid) => {
                const a = assignedOf(pid);
                const t = thicknessByPart[pid];
                return (
                  <div key={pid} className="crash-mat-part" data-testid={`crash-mat-part-${pid}`}>
                    <code>#{pid}</code>
                    <span className="crash-mat-part-text">
                      <strong>{a ? a.material_name : "atanmadı"}</strong>
                      {isShell && <span>{t ? `kalınlık ${t} mm` : "kalınlık yok"}</span>}
                    </span>
                    <button
                      type="button"
                      className="doe-chip"
                      disabled={busy || !sel || a?.material_name === sel.name}
                      onClick={() => onAssign([pid])}
                    >
                      {a?.material_name === sel?.name ? "atandı" : `${sel?.name ?? "—"} ata`}
                    </button>
                  </div>
                );
              })}
            </div>
            )}
            {hasModel && parts.length > 1 && (
              <button
                type="button"
                className="doe-btn doe-btn-ghost"
                disabled={busy || !sel}
                onClick={() => onAssign(parts)}
              >
                Tüm parçalara {sel?.name ?? "—"} ata
              </button>
            )}
            {treeEditor}
          </div>
        )}
      </section>

      <section className="crash-acc" aria-label="Malzeme modeli ve kopma">
        <Head n={3} title="Malzeme modeli (LAW) ve kopma" summary={behaviorSummary} state="hazır" open={open === 3} onToggle={() => toggle(3)} />
        {open === 3 && (
          <div className="crash-acc-body">
            <CrashMaterialSection
              partIds={parts}
              matCard={matCard}
              setMatCard={setMatCard}
              partCards={partCards}
              setPartCards={setPartCards}
              disabled={busy}
              hideToggle
            />
          </div>
        )}
      </section>
    </div>
  );
}
