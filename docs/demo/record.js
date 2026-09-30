/* SimSurrogate LinkedIn demo — Playwright ile 1920×1080 video kaydı.
 * Akış: tezgahta kiriş üret → ML Stüdyo: DOE → Veri seti → Model → Tahmin
 * (uzay içi, uzay dışı + sınıra çek, tek parametre tarama).
 * Sahte imleç + alt yazı şeridi sayfaya enjekte edilir (sessiz izleme için).
 */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const OUT = path.join(__dirname, "out");
fs.mkdirSync(OUT, { recursive: true });
const URL = "http://localhost:5173/";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(60000);

  // ---- overlay: imleç + alt yazı ----
  const overlay = async () => {
    await page.evaluate(() => {
      if (document.getElementById("demo-cursor")) return;
      const st = document.createElement("style");
      st.textContent = `
        #demo-cursor{position:fixed;left:0;top:0;width:22px;height:22px;pointer-events:none;z-index:99999;
          transform:translate(-3px,-2px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
        #demo-cursor.click::after{content:"";position:absolute;left:-14px;top:-14px;width:44px;height:44px;border-radius:50%;
          border:2px solid #5980a6;animation:demo-ripple .45s ease-out forwards}
        @keyframes demo-ripple{from{transform:scale(.3);opacity:1}to{transform:scale(1);opacity:0}}
        #demo-cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);max-width:1400px;padding:12px 22px;
          background:rgba(29,31,32,.88);color:#fff;font:600 24px/1.3 "Barlow","Segoe UI",sans-serif;letter-spacing:.01em;
          border-left:4px solid #5980a6;z-index:99998;opacity:0;transition:opacity .35s;pointer-events:none;white-space:pre-line}
        #demo-cap.on{opacity:1}
        #demo-brand{position:fixed;right:22px;bottom:34px;font:700 16px "Barlow Condensed","Segoe UI",sans-serif;letter-spacing:.12em;
          color:#5980a6;z-index:99998;pointer-events:none;opacity:.9}
      `;
      document.head.appendChild(st);
      const c = document.createElement("div");
      c.id = "demo-cursor";
      c.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 3l14 9-6 1.5L16 20l-3 1.5-3-6.5L5 19z" fill="#fff" stroke="#1d1f20" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
      document.body.appendChild(c);
      const cap = document.createElement("div");
      cap.id = "demo-cap";
      document.body.appendChild(cap);
      const b = document.createElement("div");
      b.id = "demo-brand";
      b.textContent = "SIMSURROGATE";
      document.body.appendChild(b);
      window.addEventListener("mousemove", (e) => {
        c.style.left = e.clientX + "px";
        c.style.top = e.clientY + "px";
      });
      window.addEventListener("mousedown", () => {
        c.classList.remove("click");
        void c.offsetWidth;
        c.classList.add("click");
      });
    });
  };
  let cur = { x: 960, y: 540 };
  const caption = async (text) => {
    await page.evaluate((t) => {
      const cap = document.getElementById("demo-cap");
      if (!cap) return;
      cap.classList.remove("on");
      if (!t) return;
      setTimeout(() => {
        cap.textContent = t;
        cap.classList.add("on");
      }, 250);
    }, text);
  };
  const moveTo = async (loc, opts = {}) => {
    await loc.scrollIntoViewIfNeeded();
    const box = await loc.boundingBox();
    if (!box) throw new Error("no box");
    const x = box.x + box.width * (opts.fx ?? 0.5);
    const y = box.y + box.height * (opts.fy ?? 0.5);
    const steps = 28;
    await page.mouse.move(x, y, { steps });
    cur = { x, y };
    await sleep(opts.settle ?? 350);
    return { x, y };
  };
  const click = async (loc, opts = {}) => {
    await moveTo(loc, opts);
    await page.mouse.down();
    await sleep(80);
    await page.mouse.up();
    await sleep(opts.after ?? 500);
  };
  const type = async (loc, text) => {
    await click(loc, { after: 150 });
    await page.keyboard.press("Control+A");
    await page.keyboard.type(String(text), { delay: 55 });
    await sleep(250);
  };
  const setVal = async (loc, text) => {
    // React kontrollü input: tıkla, seç, yaz.
    await type(loc, text);
  };

  // ================= 1. TEZGAH =================
  await page.goto(URL, { waitUntil: "networkidle" });
  await overlay();
  await page.mouse.move(960, 540);
  await sleep(600);
  await caption("SimSurrogate — parametrik CAE tezgahı + FEA'dan öğrenen vekil model\nAçık kaynak yığın: Gmsh · CalculiX · scikit-learn");
  await sleep(3200);

  const tpl = page.locator(".template-panel-fields");
  const fld = (name) => tpl.locator("label", { hasText: name }).locator("input").first();
  await caption("1 · Şablondan geometri: ankastre kiriş, üç parametre");
  await setVal(fld("Length"), "550");
  await setVal(fld("Thickness"), "12");
  await setVal(fld("Width"), "50");
  await sleep(500);
  await click(page.getByRole("button", { name: "Model üret" }));
  const confirm = page.getByRole("dialog").getByRole("button", { name: "Modeli üret" });
  await confirm.waitFor();
  await sleep(700);
  await click(confirm);
  await caption("STEP üretildi, 3B önizleme — tam çözüm sunucuda mesh'lenip CalculiX ile koşar");
  await page.locator("canvas").first().waitFor({ timeout: 90000 });
  await sleep(1200);
  // viewer'a bir tur: sürükleyerek döndür
  const canvas = page.locator("canvas").first();
  const cb = await canvas.boundingBox();
  if (cb) {
    const cx = cb.x + cb.width / 2, cy = cb.y + cb.height / 2;
    await page.mouse.move(cx, cy, { steps: 20 });
    await page.mouse.down();
    await page.mouse.move(cx + 160, cy - 60, { steps: 40 });
    await page.mouse.up();
  }
  await sleep(2200);

  // ================= 2. ML STÜDYO · DOE =================
  await click(page.getByRole("button", { name: /ML Stüdyo/ }));
  await page.getByTestId("doe-stage").waitFor();
  await caption("2 · ML Stüdyo — DOE: Latin Hypercube ile tasarım uzayı taranır,\nher örnek CalculiX ile çözülür (150 örnek · 148 ok)");
  await sleep(1500);
  await moveTo(page.locator(".doe-line").nth(0));
  await sleep(900);
  await moveTo(page.locator(".doe-line").nth(2));
  await sleep(900);
  await moveTo(page.locator("[data-testid=strip-vm]").first());
  await sleep(1400);
  await moveTo(page.locator(".doe-outlier").first());
  await caption("Sonuç dağılımı: her nokta bir çözüm · en çok sapan örnekler analitik referansa göre");
  await sleep(3200);

  // ================= 3. VERİ SETİ =================
  await click(page.locator(".ml-stage").nth(1));
  await page.getByTestId("dataset-stage").waitFor();
  await caption("3 · Veri seti: 666 çözülmüş run, şablona göre dağılım,\ndonmuş eğitim setleri (korpus) ve arşiv");
  await sleep(1200);
  await moveTo(page.locator(".ds-trow").first());
  await sleep(1000);
  await moveTo(page.locator(".ds-corpus").first());
  await sleep(1000);
  await moveTo(page.locator(".ds-card-primary"));
  await sleep(2200);

  // ================= 4. MODEL =================
  await click(page.locator(".ml-stage").nth(3));
  await page.getByTestId("model-stage").waitFor();
  await caption("4 · Vekil model: şablon başına ayrı model — hybrid (log-log iskelet + RF artık)\ntest MAPE u %0.20 · σ %1.74");
  await sleep(1500);
  await moveTo(page.locator("[data-testid=model-card-hybrid]"));
  await sleep(1200);
  await page.locator("[data-testid=validate-result]").waitFor({ timeout: 60000 });
  await moveTo(page.locator(".sg-scatter"));
  await caption("Tahmin ↔ FEA: 192 çözülmüş run'da |Δu| ort. %0.11 · |Δσ| %0.38 — ccx çalışmadan");
  await sleep(3600);
  await moveTo(page.locator(".sg-exps"));
  await caption("Öğrenilen üsler: log-log modelin katsayıları — kiriş teorisiyle yan yana okunur");
  await sleep(3000);

  // ================= 5. TAHMİN =================
  await click(page.locator(".ml-stage").nth(4));
  await page.getByTestId("predict-stage").waitFor();
  await caption("5 · Parametreden tahmin: bant = eğitim kutusu, ■ = girilen değer");
  await sleep(1200);
  await setVal(page.getByLabel("L · Length"), "550");
  await setVal(page.getByLabel("T · Thickness"), "12");
  await setVal(page.getByLabel("W · Width"), "50");
  await setVal(page.getByLabel("Fy (N)"), "-150");
  await click(page.getByRole("group", { name: "Malzeme (akma kontrolü)" }).getByRole("button", { name: "S235" }));
  await sleep(400);
  await click(page.getByRole("button", { name: "Tahmin et" }));
  await page.locator(".sg-res-grid").waitFor();
  await caption("Sonuç saniyeler içinde: maks deplasman, maks von Mises, akma kullanımı");
  await moveTo(page.locator(".sg-res").nth(2));
  await sleep(3600);

  // uzay dışı
  await setVal(page.getByLabel("L · Length"), "900");
  await sleep(500);
  await caption("Eğitim uzayı dışı: model uydurmaz, söyler — ve sınıra çekmeyi önerir");
  await click(page.getByRole("button", { name: "Tahmin et" }));
  await page.locator("[data-testid=ood-section]").waitFor();
  await moveTo(page.locator("[data-testid=ood-section] .sg-ood").first());
  await sleep(2600);
  await click(page.locator("[data-testid=ood-section] button").first());
  await sleep(600);
  await click(page.getByRole("button", { name: "Tahmin et" }));
  await sleep(2200);
  await caption("Sınıra çekildi → uzay içi tahmin");
  await sleep(2000);

  // tarama
  await caption("Tek istekte 20 tahmin: σ_max'ın L ile değişimi, akma çizgisi ve uzay dışı bölge");
  const sweepBox = page.getByTestId("sweep-section");
  await moveTo(sweepBox.getByLabel("Parametre"));
  await sweepBox.getByLabel("Parametre").selectOption("length");
  await sleep(400);
  await setVal(sweepBox.getByLabel("Min"), "350");
  await setVal(sweepBox.getByLabel("Max"), "800");
  await setVal(sweepBox.getByLabel("Adım sayısı (2–200)"), "20");
  await click(sweepBox.getByRole("button", { name: "Tara" }));
  await page.getByTestId("sweep-result").waitFor();
  await moveTo(page.locator(".sg-sweep-svg"));
  await sleep(4500);

  await caption("SimSurrogate — FEA'yı bir kez koştur, sonra saniyeler içinde tahmin et.\nDurability şablonları · DOE · vekil model · WeWeb'e hazır API");
  await moveTo(page.locator(".app-brand").first());
  await sleep(4200);
  await caption("");
  await sleep(800);

  await ctx.close();
  await browser.close();
  const files = fs.readdirSync(OUT).filter((f) => f.endsWith(".webm"));
  console.log("VIDEO", files.map((f) => path.join(OUT, f)).join("\n"));
}

main().catch((e) => {
  console.error("DEMO FAILED:", e);
  process.exit(1);
});
