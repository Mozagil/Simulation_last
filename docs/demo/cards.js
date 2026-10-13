/* Kapak kartları: 1920×1080 PNG (Playwright ile HTML'den). */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const OUT = path.join(__dirname, "out", "cards");
fs.mkdirSync(OUT, { recursive: true });

const CARDS = [
  {
    file: "card-surrogate.png",
    kicker: "SIMSURROGATE · VEKİL MODEL",
    title: "FEA'yı bir kez koştur,\nsonra saniyeler içinde tahmin et.",
    sub: "Şablon geometri → DOE ile çözüm → şablona özel model → anında tahmin\nCalculiX · açık kaynak yığın · tarayıcıda",
    meta: "192 çözüm · |Δu| %0.11 · |Δσ| %0.38",
  },
  {
    file: "card-manual.png",
    kicker: "SIMSURROGATE · MANUEL AKIŞ",
    title: "Aynı tezgahta, adım adım:\nklasik durability analizi.",
    sub: "Geometri → mesh → malzeme → sınır koşulu → CalculiX çözümü → sonuç\nKullanıcıda CAE yazılımı yok, tarayıcı yeter",
    meta: "Teori 7.143 mm · FEA 7.144 mm · vekil model 7.211 mm",
  },
];

const html = (c) => `<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@600;700&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;width:1920px;height:1080px;background:#f2f2f3;font-family:"Barlow","Segoe UI",sans-serif;color:#1d1f20}
  .grid{position:absolute;inset:0;background-image:linear-gradient(rgba(29,31,32,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(29,31,32,.06) 1px,transparent 1px);background-size:60px 60px}
  .bar{position:absolute;left:0;top:0;bottom:0;width:18px;background:#5980a6}
  .wrap{position:absolute;left:140px;top:170px;right:140px}
  .kicker{font-family:"Barlow Condensed";font-weight:700;font-size:30px;letter-spacing:.16em;color:#416180}
  h1{font-family:"Barlow Condensed";font-weight:700;font-size:112px;line-height:1.02;letter-spacing:.01em;margin:28px 0 36px;white-space:pre-line}
  .sub{font-size:38px;line-height:1.35;color:#424244;white-space:pre-line;max-width:1500px}
  .meta{position:absolute;left:140px;bottom:120px;display:inline-flex;gap:18px;align-items:center;padding:16px 26px;background:#1d1f20;color:#fff;font-size:30px;font-weight:600;border-left:6px solid #5980a6}
  .brand{position:absolute;right:140px;bottom:120px;display:flex;align-items:center;gap:16px;font-family:"Barlow Condensed";font-weight:700;font-size:40px;letter-spacing:.14em;color:#416180}
  .beam{position:absolute;right:140px;top:190px;width:520px;height:220px}
</style></head><body>
<div class="grid"></div><div class="bar"></div>
<svg class="beam" viewBox="0 0 520 220" fill="none" stroke="#5980a6" stroke-width="3">
  <rect x="40" y="70" width="360" height="40" fill="#eef6ff"/>
  <path d="M400 70 Q470 95 500 150" stroke="#8a5a1f" stroke-dasharray="8 6"/>
  <path d="M40 40 v100 M28 50 l12 -10 l12 10 M28 80 l12 -10 l12 10 M28 110 l12 -10 l12 10" />
  <path d="M400 60 v-40 M392 32 l8 -12 l8 12" stroke="#1d1f20"/>
  <text x="414" y="30" font-family="Barlow" font-size="22" fill="#1d1f20" stroke="none">F</text>
</svg>
<div class="wrap">
  <div class="kicker">${c.kicker}</div>
  <h1>${c.title}</h1>
  <div class="sub">${c.sub}</div>
</div>
<div class="meta">${c.meta}</div>
<div class="brand"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#5980a6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 6.5l10 4.7M7 17.5l10-4.7"/></svg>SIMSURROGATE</div>
</body></html>`;

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  for (const c of CARDS) {
    await page.setContent(html(c), { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(OUT, c.file) });
    console.log("CARD", path.join(OUT, c.file));
  }
  await browser.close();
})();
