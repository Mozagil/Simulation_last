/**
 * AKIŞ (CFD · OpenFOAM) sekmesi — Faz 2 iskeleti (kullanıcı 2026-10-08:
 * "ui'de ayrı sekme olarak yavaştan akışı da getirelim"). Henüz çözücü
 * bağlı değil: adımların planı ve açık kararlar veri olarak gösterilir.
 * Geometri ve mesh adımları diğer analizlerle ortaktır.
 */
const STEPS: { id: string; title: string; what: string; status: "plan" | "karar" }[] = [
  { id: "2.0", title: "Altyapı", what: "OpenFOAM Docker imajı + Codespace; resmi pitzDaily vakasıyla duman testi.", status: "karar" },
  { id: "2.1", title: "Case yazıcı", what: "Parametrelerden 0/U, 0/p, (k, ω, νt), constant/, system/ (controlDict, fvSchemes, fvSolution).", status: "karar" },
  { id: "2.2", title: "Koşu + ilerleme", what: "Docker'da koşu; log'dan iterasyon ve residual'lar (crash'teki canlı izleme deseni).", status: "plan" },
  { id: "2.3", title: "İlk doğrulama", what: "2B kanalda laminer akış (blockMesh) — basınç düşümü analitik değerle karşılaştırılır.", status: "plan" },
  { id: "2.4", title: "Sonuç okuma", what: "Kuvvet / Cd / Cl, ortalama basınç, debi, residual geçmişi; koşu kaydı (DB şeması ayrı onay).", status: "plan" },
  { id: "2.5", title: "CFD mesh", what: "STEP → Gmsh yüzey → snappyHexMesh (inceltme ve sınır tabakası değerleri mühendisin); checkMesh verisi.", status: "plan" },
  { id: "2.6", title: "Dış akış doğrulaması", what: "Silindir Cd (Re 20/40), pitzDaily yeniden bağlanma uzunluğu.", status: "plan" },
  { id: "2.7", title: "Arayüz adımları", what: "1 Geometry · 2 Mesh · 3 Akışkan (ρ, ν) · 4 Sınır koşulları (giriş, çıkış, duvar, simetri, türbülans) · 5 Sonuçlar.", status: "plan" },
  { id: "2.8", title: "Alan görselleştirme", what: "Yüzey basıncı ve kesit hız alanı viewport'ta.", status: "plan" },
  { id: "2.9", title: "CFD DOE + ML", what: "En sonda — crash ve durability ML tezgahı deseniyle.", status: "plan" },
];

const DECISIONS = [
  "OpenFOAM dağıtımı: ESI (openfoam.com, resmi Docker imajı) ya da Foundation (openfoam.org) — dosya biçimleri farklı.",
  "İlk hedef vaka: iç akış (boru / kanal — basınç düşümü) ya da dış akış (silindir / küre — Cd, Cl).",
];

export default function CfdPlanPanel() {
  return (
    <div className="panel material-panel cfd-plan" data-testid="cfd-plan">
      <span className="eyebrow">Faz 2 · OpenFOAM</span>
      <h1>Akış (CFD)</h1>
      <p className="lead material-lead">
        Akış analizi Faz 2'de adım adım geliyor. Şimdilik 1 · Geometry ve 2 · Mesh diğer analizlerle ortak; çözücü
        henüz bağlı değil. Aşağıdaki plan veri olarak gösterilir.
      </p>
      <p className="crash-expert-title">Açık kararlar (başlamadan önce)</p>
      <ul className="cfd-decisions">
        {DECISIONS.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <p className="crash-expert-title">Plan · ROADMAP Faz 2</p>
      <ol className="cfd-steps">
        {STEPS.map((s) => (
          <li key={s.id} className="cfd-step">
            <span className="cfd-step-id">{s.id}</span>
            <span className="cfd-step-text">
              <strong>{s.title}</strong>
              <span className="crash-behavior-hint">{s.what}</span>
            </span>
            <span className={s.status === "karar" ? "crash-acc-state warn" : "crash-acc-state muted"}>
              {s.status === "karar" ? "karar bekliyor" : "planlandı"}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
