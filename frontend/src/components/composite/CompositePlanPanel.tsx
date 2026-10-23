/**
 * KOMPOZIT sekmesi — Faz 3 iskeleti (2026-10-12). Henüz çözücü bağlı değil:
 * adımların planı ve verilen kararlar veri olarak gösterilir.
 * Geometri ve mesh adımları diğer analizlerle ortaktır. Yeni solver yok —
 * Dalga 1 CalculiX *SHELL SECTION, COMPOSITE üzerine katman.
 */

const STEPS: { id: string; title: string; what: string; status: "plan" | "karar" | "tamam" }[] = [
  { id: "3.0", title: "İskelet", what: "KOMPOZIT sekmesi, plan paneli, ROADMAP 3.0–3.14. Solver bağlı değil.", status: "tamam" },
  { id: "3.1", title: "Ply malzemesi", what: "composite_materials tablosu, tipik UD seed (T300/epoxy, E-glass/epoxy), GET/POST /composite/materials.", status: "tamam" },
  { id: "3.2", title: "Ply kütüphanesi (UI)", what: "3 · KOMPOZIT içinde liste + kullanıcı tanımlı ortotrop form (9 sabit + mukavemet).", status: "tamam" },
  { id: "3.3", title: "CLT", what: "Katman listesi → A, B, D matrisleri (saf Python/numpy). Bilinen [0/90/0] ve [±45]s.", status: "tamam" },
  { id: "3.4", title: "CLT önizleme", what: "POST /composite/clt + panelde ABD (sayı; yorum yok).", status: "tamam" },
  { id: "3.5", title: "Layup CRUD", what: "composite_layups (geometry + parça + ply satırları). GET/PUT /composite/layups.", status: "tamam" },
  { id: "3.6", title: "Layup tablosu (UI)", what: "Açı / kalınlık / malzeme / sıra; CLT canlı güncellenir.", status: "tamam" },
  { id: "3.7", title: "Rozet + OSS", what: "Paralel rozet (varsayılan global X = 0°); atama parça veya seçili yüzey.", status: "tamam" },
  { id: "3.8", title: "section_writer", what: "CalculiX *ELASTIC, TYPE=ENGINEERING CONSTANTS + *ORIENTATION + *SHELL SECTION, COMPOSITE.", status: "tamam" },
  { id: "3.9", title: "/composite/solve", what: "Mesh + layup + BC → CalculiXAdapter. /solve dokunulmaz. composite_runs.", status: "tamam" },
  { id: "3.10", title: "V-P1 doğrulama", what: "Klasik laminat kabuk plaka; CLT vs ccx (ccx yoksa atlanır). docs/COMPOSITE_VALIDATION.md.", status: "tamam" },
  { id: "3.11", title: "Katman gerilmesi", what: ".frd entegrasyon noktası / katman S → ply bazlı tensör.", status: "plan" },
  { id: "3.12", title: "Hasar", what: "Tsai-Wu + Hashin IRF; ResultSet.scalars + ply alanı. Puck yok.", status: "plan" },
  { id: "3.13", title: "Sonuç UI", what: "Katman seçici, gerilme / IRF kontur, min IRF sayısı.", status: "plan" },
  { id: "3.14", title: "Belgeler", what: "Belgeler penceresine Kompozit kitabı.", status: "plan" },
];

const DECIDED = [
  "Dalga 1 solver: CalculiX (implicit laminat kabuk). Yeni solver yok; Code_Aster yok (2026-10-12).",
  "Kapsam: ACP Pre çekirdeği — ortotrop ply, rozet, stackup, CLT, *SHELL SECTION COMPOSITE, Tsai-Wu/Hashin.",
  "/solve refaktör edilmez. Koşu 3.9’da POST /composite/solve üzerinden CalculiXAdapter.",
  "OpenRadioss kompozit (crash), draping, sandwich, katmanlı solid: Dalga 2+ (ayrı onay).",
];

const DECISIONS: string[] = [];

export default function CompositePlanPanel() {
  return (
    <div className="panel material-panel composite-plan" data-testid="composite-plan">
      <span className="eyebrow">Faz 3 · CalculiX katman</span>
      <h1>Kompozit</h1>
      <p className="lead material-lead">
        Kompozit, ayrı bir çözücü değil: CalculiX kabuk kesiti üzerine katman. Bu sekme ANSYS ACP Pre
        benzeri hazırlık bölümüdür. Ply kütüphanesi bu adımda. Geometri ve mesh ortak. Araç dizilim
        önermez — ABD, katman gerilmesi ve IRF sayı olarak gelir.
      </p>
      <p className="composite-expert-title">Kararlar</p>
      <ul className="composite-decisions">
        {DECIDED.map((d) => (
          <li key={d}>
            <span className="crash-acc-state ok">verildi</span> {d}
          </li>
        ))}
      </ul>
      {DECISIONS.length > 0 && <p className="composite-expert-title">Açık kararlar</p>}
      <ul className="composite-decisions">
        {DECISIONS.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <p className="composite-expert-title">Plan · ROADMAP Faz 3 Dalga 1</p>
      <ol className="composite-steps">
        {STEPS.map((s) => (
          <li key={s.id} className="composite-step">
            <span className="composite-step-id">{s.id}</span>
            <span className="composite-step-text">
              <strong>{s.title}</strong>
              <span className="crash-behavior-hint">{s.what}</span>
            </span>
            <span
              className={
                s.status === "tamam"
                  ? "crash-acc-state ok"
                  : s.status === "karar"
                    ? "crash-acc-state warn"
                    : "crash-acc-state muted"
              }
            >
              {s.status === "tamam" ? "tamam" : s.status === "karar" ? "karar bekliyor" : "planlandı"}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
