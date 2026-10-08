/**
 * AKIŞ (CFD · OpenFOAM) sekmesi — Faz 2 iskeleti (kullanıcı 2026-10-08:
 * "ui'de ayrı sekme olarak yavaştan akışı da getirelim"). Henüz çözücü
 * bağlı değil: adımların planı ve açık kararlar veri olarak gösterilir.
 * Geometri ve mesh adımları diğer analizlerle ortaktır.
 */
const STEPS: { id: string; title: string; what: string; status: "plan" | "karar" | "tamam" }[] = [
  { id: "2.0", title: "Altyapı", what: "OpenFOAM ESI v2412 resmi Docker imajı; resmi pitzDaily vakası simpleFoam ile koştu (281 iterasyonda yakınsadı, ~13 s).", status: "tamam" },
  { id: "2.1", title: "Case yazıcı", what: "Parametrelerden 0/U, 0/p, (k, ω, νt), constant/, system/ — laminer ya da k-ω SST. pitzDaily ağında k-ω SST 382 iterasyonda yakınsadı.", status: "tamam" },
  { id: "2.2", title: "Koşu + ilerleme", what: "Docker'da koşu; canlı iterasyon ve residual'lar (/cfd/solve, /cfd/jobs, ws). pitzDaily 382 iterasyonda yakınsadı (~12 s).", status: "tamam" },
  { id: "2.3", title: "İlk doğrulama", what: "2B kanal (blockMesh), laminer Re 10: Δp analitikten %+2.9 (giriş bölgesi dahil), u_max %−0.5.", status: "tamam" },
  { id: "2.4", title: "Sonuç okuma", what: "Cd / Cl / Cm, CdA, yama başına kuvvet ve moment, kuvvet geçmişi (son N ortalama + std); cfd_runs koşu kaydı ve /cfd/runs.", status: "tamam" },
  { id: "2.5", title: "CFD mesh", what: "STEP → bölge başına STL → sanal rüzgâr tüneli → snappyHexMesh + checkMesh verisi (2.5a tamam). cfMesh seçeneği (2.5b) sırada.", status: "tamam" },
  { id: "2.6", title: "Dış akış doğrulaması", what: "Silindir Cd (Re 20/40), pitzDaily yeniden bağlanma uzunluğu.", status: "plan" },
  { id: "2.7", title: "Arayüz adımları", what: "1 Geometry · 2 Mesh · 3 Akışkan (ρ, ν) · 4 Sınır koşulları (giriş, çıkış, duvar, simetri, türbülans) · 5 Sonuçlar.", status: "plan" },
  { id: "2.8", title: "Alan görselleştirme", what: "Yüzey basıncı ve kesit hız alanı viewport'ta.", status: "plan" },
  { id: "2.9", title: "CFD DOE + ML", what: "En sonda — crash ve durability ML tezgahı deseniyle.", status: "plan" },
];

const DECIDED = ["OpenFOAM dağıtımı: ESI (openfoam.com) — resmi Docker imajı opencfd/openfoam-default:2412 (2026-10-08)."];

const DECISIONS = [
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
      <p className="crash-expert-title">Kararlar</p>
      <ul className="cfd-decisions">
        {DECIDED.map((d) => (
          <li key={d}>
            <span className="crash-acc-state ok">verildi</span> {d}
          </li>
        ))}
      </ul>
      <p className="crash-expert-title">Açık kararlar</p>
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
            <span
              className={
                s.status === "tamam" ? "crash-acc-state ok" : s.status === "karar" ? "crash-acc-state warn" : "crash-acc-state muted"
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
