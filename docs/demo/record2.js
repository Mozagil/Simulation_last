/* SimSurrogate demo 2 — MANUEL durability akışı (Playwright, 1920×1080).
 * Geometri → mesh (+kalite) → malzeme → sınır koşulları → CalculiX çözümü →
 * sonuçlar (kontur, animasyon, metrik kartlar) → kapanış: aynı tasarımın
 * vekil modelle FEA kıyası. Kilit anlarda PNG ekran görüntüsü alınır.
 */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const OUT = path.join(__dirname, "out2");
const SHOTS = path.join(OUT, "shots");
fs.mkdirSync(SHOTS, { recursive: true });
for (const f of fs.readdirSync(OUT)) if (f.endsWith(".webm")) fs.unlinkSync(path.join(OUT, f));
const URL = "http://localhost:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    colorScheme: "light",
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(90000);

  const overlay = async () => {
    await page.evaluate(() => {
      if (document.getElementById("demo-cursor")) return;
      const st = document.createElement("style");
      st.textContent = `
        #demo-cursor{position:fixed;left:0;top:0;width:22px;height:22px;pointer-events:none;z-index:99999;transform:translate(-3px,-2px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
        #demo-cursor.click::after{content:"";position:absolute;left:-14px;top:-14px;width:44px;height:44px;border-radius:50%;border:2px solid #5980a6;animation:demo-ripple .45s ease-out forwards}
        @keyframes demo-ripple{from{transform:scale(.3);opacity:1}to{transform:scale(1);opacity:0}}
        #demo-cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);max-width:1400px;padding:12px 22px;background:rgba(29,31,32,.88);color:#fff;font:600 24px/1.3 "Barlow","Segoe UI",sans-serif;border-left:4px solid #5980a6;z-index:99998;opacity:0;transition:opacity .35s;pointer-events:none;white-space:pre-line}
        #demo-cap.on{opacity:1}
        #demo-brand{position:fixed;right:22px;bottom:34px;font:700 16px "Barlow Condensed","Segoe UI",sans-serif;letter-spacing:.12em;color:#5980a6;z-index:99998;pointer-events:none;opacity:.9}
        #demo-step{position:fixed;left:22px;top:60px;padding:6px 12px;background:#5980a6;color:#fff;font:700 15px "Barlow Condensed","Segoe UI",sans-serif;letter-spacing:.1em;z-index:99998;pointer-events:none;opacity:0;transition:opacity .3s}
        #demo-step.on{opacity:1}
      `;
      document.head.appendChild(st);
      const mk = (id, html) => { const d = document.createElement("div"); d.id = id; d.innerHTML = html; document.body.appendChild(d); return d; };
      const c = mk("demo-cursor", `<svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 3l14 9-6 1.5L16 20l-3 1.5-3-6.5L5 19z" fill="#fff" stroke="#1d1f20" stroke-width="1.5" stroke-linejoin="round"/></svg>`);
      mk("demo-cap", "");
      mk("demo-brand", "SIMSURROGATE · MANUEL AKIŞ");
      mk("demo-step", "");
      window.addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; });
      window.addEventListener("mousedown", () => { c.classList.remove("click"); void c.offsetWidth; c.classList.add("click"); });
    });
  };
  const caption = (t) => page.evaluate((t) => {
    const cap = document.getElementById("demo-cap"); if (!cap) return;
    cap.classList.remove("on"); if (!t) return;
    setTimeout(() => { cap.textContent = t; cap.classList.add("on"); }, 250);
  }, t);
  const step = (t) => page.evaluate((t) => {
    const s = document.getElementById("demo-step"); if (!s) return;
    if (!t) { s.classList.remove("on"); return; }
    s.textContent = t; s.classList.add("on");
  }, t);
  const hideOverlayFor = async (fn) => {
    await page.evaluate(() => { for (const id of ["demo-cursor", "demo-cap", "demo-brand", "demo-step"]) { const e = document.getElementById(id); if (e) e.style.visibility = "hidden"; } });
    await sleep(120);
    await fn();
    await page.evaluate(() => { for (const id of ["demo-cursor", "demo-cap", "demo-brand", "demo-step"]) { const e = document.getElementById(id); if (e) e.style.visibility = ""; } });
  };
  let shotN = 0;
  const shot = async (name) => {
    shotN += 1;
    const file = path.join(SHOTS, `${String(shotN).padStart(2, "0")}_${name}.png`);
    await hideOverlayFor(() => page.screenshot({ path: file }));
    console.log("SHOT", file);
  };
  const moveTo = async (loc, opts = {}) => {
    await loc.scrollIntoViewIfNeeded();
    const box = await loc.boundingBox();
    if (!box) throw new Error("no box: " + loc);
    const x = box.x + box.width * (opts.fx ?? 0.5), y = box.y + box.height * (opts.fy ?? 0.5);
    await page.mouse.move(x, y, { steps: 26 });
    await sleep(opts.settle ?? 350);
    return { x, y };
  };
  const click = async (loc, opts = {}) => {
    await moveTo(loc, opts);
    await page.mouse.down(); await sleep(80); await page.mouse.up();
    await sleep(opts.after ?? 500);
  };
  const type = async (loc, text) => {
    await click(loc, { after: 150 });
    await page.keyboard.press("Control+A");
    await page.keyboard.type(String(text), { delay: 55 });
    await sleep(250);
  };
  const clickXY = async (x, y) => {
    await page.mouse.move(x, y, { steps: 20 }); await sleep(200);
    await page.mouse.down(); await sleep(60); await page.mouse.up(); await sleep(400);
  };
  // Meşgul düğme kalmayana kadar bekle (arayüz iş bitince adım değiştirebiliyor,
  // düğme adı değişebiliyor; metne bağlanmak kırılgan).
  const busyGone = async () => {
    await sleep(400);
    await page.waitForFunction(() => {
      const re = /Üretiliyor|ÇALIŞIYOR|Atanıyor|Hazırlanıyor|Hesaplanıyor|Taranıyor/;
      return ![...document.querySelectorAll("button")].some((b) => re.test(b.textContent));
    }, null, { timeout: 300000 });
  };

  // ================= 1 · GEOMETRİ =================
  await page.goto(URL, { waitUntil: "networkidle" });
  await overlay();
  await page.mouse.move(960, 540);
  await sleep(500);
  await caption("SimSurrogate — aynı tezgahta MANUEL durability analizi:\ngeometri → mesh → malzeme → sınır koşulu → CalculiX çözümü → sonuç");
  await sleep(3400);
  await step("1 · GEOMETRİ");
  const tpl = page.locator(".template-panel-fields");
  const fld = (name) => tpl.locator("label", { hasText: name }).locator("input").first();
  await caption("Şablondan parametrik kiriş: L = 600, t = 12, b = 50 mm");
  await type(fld("Length"), "600");
  await type(fld("Thickness"), "12");
  await type(fld("Width"), "50");
  await click(page.getByRole("button", { name: "Model üret" }));
  const dlg = page.getByRole("dialog");
  await dlg.waitFor();
  await sleep(600);
  await caption("Yük şablonun BC'sine bağlı: yük yüzeyinde Fy = −150 N");
  await type(dlg.locator("label", { hasText: "Fy (N)" }).locator("input"), "-150");
  await shot("template_dialog");
  await click(dlg.getByRole("button", { name: "Modeli üret" }));
  await page.locator(".model-tree-leaf").first().waitFor({ timeout: 120000 });
  await sleep(1500);
  await caption("STEP üretildi; bölgeler (ankastre uç, yük yüzeyi) adıyla geldi");
  const canvas = page.locator("canvas").first();
  const cb = await canvas.boundingBox();
  const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
  await page.mouse.move(cx, cy, { steps: 15 });
  await page.mouse.down(); await page.mouse.move(cx + 140, cy - 50, { steps: 40 }); await page.mouse.up();
  await sleep(1200);
  await shot("geometry");
  await sleep(800);

  // ================= 2 · MESH =================
  await step("2 · MESH");
  await click(page.getByRole("button", { name: "2 · MESH" }));
  await sleep(600);
  await caption("Mesh: Gmsh ile 3D tetrahedral, eleman boyutu 6 mm");
  await click(page.getByRole("group", { name: "Mesh boyutu" }).getByRole("button", { name: "3D solid" }));
  await type(page.locator("label.mesh-field", { hasText: "Eleman boyutu" }).locator("input").first(), "6");
  await click(page.getByRole("button", { name: "Mesh üret" }));
  await busyGone();
  await sleep(1500);
  await shot("mesh");
  // Mesh bitince arayüz sonraki adıma geçebiliyor; kalite araçları mesh panelinde.
  let kalite = page.getByRole("group", { name: "Mesh araçları" }).getByRole("button", { name: /Kalite/ });
  if (!(await kalite.count())) {
    await click(page.getByRole("button", { name: "2 · MESH" }));
    await sleep(500);
    kalite = page.getByRole("group", { name: "Mesh araçları" }).getByRole("button", { name: /Kalite/ });
  }
  if (await kalite.count()) {
    await caption("Mesh kalitesi: Jacobian, aspect, skewness, warpage — sayı ve dağılım");
    await click(kalite);
    await sleep(2500);
    await shot("mesh_quality");
    await sleep(800);
  }

  // ================= 3 · MALZEME =================
  await step("3 · MALZEME");
  await click(page.getByRole("button", { name: "3 · MATERIAL" }));
  await sleep(500);
  await caption("Malzeme: parçayı seç, kütüphaneden S235 ata (E, ν, Rp0.2, Rm, S-N)");
  await click(page.getByRole("toolbar", { name: "Seçim modu" }).getByRole("button", { name: "Parça" }));
  const ata = page.getByRole("button", { name: "ATA" });
  const cands = [[0, 0], [-120, 20], [120, -20], [0, 40], [-60, -40], [200, 0], [-200, 0]];
  for (const [dx, dy] of cands) {
    await clickXY(cx + dx, cy + dy);
    if (await ata.isEnabled()) break;
  }
  if (!(await ata.isEnabled())) console.warn("UYARI: parça seçilemedi, ATA pasif");
  const lib = page.locator("label.material-field select");
  const opts = await lib.locator("option").allTextContents();
  const s235 = opts.find((t) => t.startsWith("S235"));
  if (s235) await lib.selectOption({ label: s235 });
  await moveTo(lib);
  await sleep(700);
  if (await ata.isEnabled()) {
    await click(ata);
    await page.getByText(/Malzeme atandı/).first().waitFor({ timeout: 30000 }).catch(() => undefined);
  }
  await sleep(1200);
  await shot("material");
  await sleep(600);

  // ================= 4 · SINIR KOŞULLARI =================
  await step("4 · SINIR KOŞULLARI");
  await click(page.getByRole("button", { name: "4 · BOUNDARY CONDITIONS" }));
  await sleep(600);
  await caption("Sınır koşulları şablondan hazır: ankastre uç sabit, yük yüzeyinde Fy = −150 N\nListeden sil, yenisini ekle: fixed, cload, pressure, displacement, gravity…");
  await moveTo(page.locator(".bc-card").first());
  await sleep(1200);
  await moveTo(page.locator(".bc-card").nth(1));
  await sleep(1200);
  await moveTo(page.locator(".bc-button-row"));
  await sleep(1000);
  await shot("boundary_conditions");
  await caption("Çözmeden önce kapalı form kontrolü: lineer teori beklenen sehim ve gerilme");
  const theory = page.getByText(/Lineer teori/).first();
  if (await theory.count()) { await moveTo(theory); await sleep(2200); }
  // ccx gerçekten koşsun (varsayılan yalnız .inp üretir).
  const ccx = page.getByLabel(/ccx çalıştır/);
  if (!(await ccx.isChecked())) await click(ccx);
  await sleep(500);

  // ================= 5 · ÇÖZ =================
  await step("5 · ÇÖZÜM · CALCULIX");
  await caption("RUN SIMULATION — .inp üretilir, CalculiX sunucuda koşar");
  await click(page.getByRole("button", { name: /RUN SIMULATION/ }));
  await sleep(800);
  await shot("running");
  await page.locator(".viewer-field-toggle").first().waitFor({ timeout: 300000 });
  await busyGone();
  await sleep(1500);
  await step("6 · SONUÇLAR");
  await caption("Sonuç: von Mises konturu");
  await click(page.locator(".viewer-field-toggle").getByRole("button", { name: "Von Mises" }));
  await sleep(2500);
  await shot("results_von_mises");
  await caption("Deplasman + animasyonlu deformasyon");
  await click(page.locator(".viewer-field-toggle").getByRole("button", { name: "Deplasman" }));
  await sleep(1200);
  await click(page.getByRole("button", { name: /Animasyon/ }));
  await sleep(4500);
  await shot("results_deformation");
  await click(page.getByRole("button", { name: /Durdur/ })).catch(() => undefined);
  await caption("Metrik kartlar: maks gerilme, emniyet katsayısı, yorulma ömrü, kritik düğüm\nAraç yorum yapmaz — karar mühendisin");
  const cards = page.locator(".metric-card");
  const n = await cards.count();
  for (let i = 0; i < Math.min(n, 4); i++) { await moveTo(cards.nth(i)); await sleep(700); }
  await sleep(600);
  await shot("results_metrics");
  await sleep(800);

  // ================= 7 · VEKİL MODEL KIYASI =================
  await step("7 · VEKİL MODEL KIYASI");
  await caption("Aynı tasarımı vekil modele soralım — çözücü çalışmadan");
  await click(page.getByRole("button", { name: /ML Stüdyo/ }));
  await page.getByTestId("doe-stage").waitFor();
  await click(page.locator(".ml-stage").nth(4));
  await page.getByTestId("predict-stage").waitFor();
  await type(page.getByLabel("L · Length"), "600");
  await type(page.getByLabel("T · Thickness"), "12");
  await type(page.getByLabel("W · Width"), "50");
  await type(page.getByLabel("Fy (N)"), "-150");
  await click(page.getByRole("group", { name: "Malzeme (akma kontrolü)" }).getByRole("button", { name: "S235" }));
  const cmp = page.locator(".doe-pfoot input[type=checkbox]");
  if (await cmp.count() && !(await cmp.isChecked()) && (await cmp.isEnabled())) await click(cmp);
  await click(page.getByRole("button", { name: "Tahmin et" }));
  await page.locator(".sg-res-grid").waitFor();
  await page.getByTestId("fea-compare").waitFor({ timeout: 20000 }).catch(() => undefined);
  await caption("Tahmin ↔ az önceki CalculiX çözümü: sapma yüzdeleri kartta");
  const fea = page.getByTestId("fea-compare");
  if (await fea.count()) await moveTo(fea);
  await sleep(3500);
  await shot("fea_vs_prediction");
  await caption("Manuel analiz istediğin kadar ayrıntılı; vekil model istediğin kadar hızlı.\nİkisi aynı tezgahta, aynı veriyle.");
  await moveTo(page.locator(".app-brand").first());
  await sleep(4200);
  await caption("");
  await step("");
  await sleep(700);

  await ctx.close();
  await browser.close();
  const [file] = fs.readdirSync(OUT).filter((f) => f.endsWith(".webm"));
  const final = path.join(OUT, "simsurrogate-manual-demo.webm");
  fs.renameSync(path.join(OUT, file), final);
  console.log("VIDEO", final);
}

main().catch((e) => { console.error("DEMO FAILED:", e); process.exit(1); });
