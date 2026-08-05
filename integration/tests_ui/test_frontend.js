/**
 * Arayüz entegrasyon testi.
 *
 * Ne yapar: gerçek backend'i ayağa kaldırılmış varsayar, index.html'i jsdom
 * içinde ÇALIŞTIRIR ve 14 ekranın hepsini gezerek her birinin gerçek veriyle
 * dolduğunu doğrular. Ekran görüntüsü almadan da "ekran boş mu, hata kutusu
 * var mı, hâlâ yükleniyor mu" sorularını cevaplar.
 *
 * Çalıştırma:
 *   1) Backend'i başlatın:  cd integration/backend && python -m uvicorn main:app --port 8099
 *   2) Bağımlılık:          npm install jsdom
 *   3) Test:                node integration/tests_ui/test_frontend.js
 *
 * Çıkış kodu 0 = tüm kontroller geçti.
 */

const path = require("path");

const BASE = process.env.UI_TEST_BASE || "http://127.0.0.1:8099";
// Ekranların yüklenmesi sabit bir süre beklenerek değil, "yükleme göstergesi
// kalmayana kadar" beklenerek ölçülür. Sabit süre yavaş makinede yanlış
// hata verir, hızlı makinede boşuna bekletir.
const VIEW_TIMEOUT_MS = Number(process.env.UI_TEST_TIMEOUT || 12000);

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch {
  try {
    ({ JSDOM } = require(path.join("/tmp/node_modules", "jsdom")));
  } catch {
    console.error("jsdom bulunamadi. Kurulum: npm install jsdom");
    process.exit(2);
  }
}

// Ekran adı -> o ekranda mutlaka görünmesi gereken metin.
// Sadece "boş değil" demek yetmez; doğru modülün verisinin geldiğini de
// doğrulamak gerekiyor.
const VIEWS = [
  ["dashboard", /Toplam öğrenci/],
  ["assistant", /dil modeli/i],
  ["students", /Doluluk|doluluk/],
  ["success", /geçme oranı/i],
  ["staff", /Ağırlıklı puan|performans/i],
  ["physical", /Derslik|Laboratuvar/],
  ["finance", /\$/],
  ["sustainability", /Sonuçları Göster/],
  ["kpi", /Genel Bakış/],
  ["engagement", /endeks/i],
  ["rankings", /ÜRETMEZ/],
  ["scenarios", /taban|Senaryo/i],
  ["alerts", /uyarı/i],
  ["structure", /Fakülte|fakülte/],
  ["data-import", /Önizleme|önizle/i],
  ["users", /Rol|rol/],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let pass = 0;
let fail = 0;
const failures = [];

function check(label, condition, detail = "") {
  if (condition) {
    pass++;
    console.log("  OK   " + label);
  } else {
    fail++;
    failures.push(label);
    console.log("  HATA " + label + (detail ? "\n         " + detail : ""));
  }
}

(async () => {
  console.log("Arayuz entegrasyon testi — " + BASE + "\n");

  let html;
  try {
    html = await (await fetch(BASE + "/")).text();
  } catch {
    console.error(
      "Backend'e ulasilamadi: " + BASE + "\n" +
      "Once sunucuyu baslatin: cd integration/backend && python -m uvicorn main:app --port 8099"
    );
    process.exit(2);
  }

  const dom = new JSDOM(html, {
    url: BASE + "/#/login",
    runScripts: "dangerously",
    resources: "usable",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  // jsdom'da fetch yok; Node'un fetch'ini bagliyoruz.
  w.fetch = (url, opts) => fetch(url.startsWith("http") ? url : BASE + url, opts);

  const jsErrors = [];
  w.console.error = (...a) => jsErrors.push(a.join(" "));
  w.addEventListener("error", (e) => jsErrors.push("window.error: " + e.message));

  await new Promise((r) => w.addEventListener("load", r));
  await sleep(600);

  const $ = (s) => w.document.querySelector(s);
  const viewText = () => ($("#view") || {}).textContent || "";

  // ---------------- giriş ----------------
  console.log("--- Kimlik dogrulama ---");
  check("giris formu cizildi", !!$("#loginForm"));

  $("#loginUser").value = "admin";
  $("#loginPass").value = "kesinlikleyanlis";
  $("#loginForm").dispatchEvent(new w.Event("submit", { cancelable: true, bubbles: true }));
  await sleep(1000);
  check(
    "yanlis parola hata kutusu gosteriyor (sessizce basarisiz olmuyor)",
    !!$("#loginError .state.error"),
    ($("#loginError") || {}).innerHTML
  );
  check("oturum acilmadi", !w.sessionStorage.getItem("atu-token"));

  $("#loginUser").value = "admin";
  $("#loginPass").value = "demo1234";
  $("#loginForm").dispatchEvent(new w.Event("submit", { cancelable: true, bubbles: true }));
  await sleep(1400);
  check("gercek API ile giris basarili", !!w.sessionStorage.getItem("atu-token"));
  check("uygulama kabugu cizildi", !!$("#sidebar"));
  check(
    "16 menu ogesi var",
    w.document.querySelectorAll("#sidebar a[data-route]").length === 16,
    "bulunan: " + w.document.querySelectorAll("#sidebar a[data-route]").length
  );
  await sleep(500);
  check(
    "ust barda API durumu 'bagli'",
    (($("#apiStatus") || {}).textContent || "").includes("bağlı"),
    ($("#apiStatus") || {}).textContent
  );

  // Ekrana geçer ve tüm yükleme göstergeleri kaybolana kadar bekler.
  // Süreyi de döndürür; hangi ekranın yavaş olduğu raporlanabilsin diye.
  async function openView(name) {
    w.location.hash = "#/" + name;
    w.dispatchEvent(new w.Event("hashchange"));
    const started = Date.now();
    // İlk çizim + init'in yükleme göstergelerini basması için kısa bir an.
    await sleep(150);
    while (Date.now() - started < VIEW_TIMEOUT_MS) {
      const view = $("#view");
      if (view && view.querySelectorAll(".state.loading").length === 0) break;
      await sleep(150);
    }
    return Date.now() - started;
  }

  // ---------------- ekranlar ----------------
  console.log("\n--- 16 ekran ---");
  for (const [name, expected] of VIEWS) {
    const elapsed = await openView(name);

    const view = $("#view");
    const errorBoxes = view.querySelectorAll(".state.error");
    const loaders = view.querySelectorAll(".state.loading");
    const text = view.textContent.trim();

    check(
      `${name.padEnd(14)} ${String(elapsed).padStart(5)} ms · ${String(text.length).padStart(5)} karakter`,
      errorBoxes.length === 0 && loaders.length === 0 && expected.test(text),
      errorBoxes.length
        ? "hata kutusu: " + errorBoxes[0].textContent.replace(/\s+/g, " ").slice(0, 140)
        : loaders.length
        ? loaders.length + " bolum zaman asimina ugradi"
        : "beklenen icerik bulunamadi: " + expected
    );
  }

  // ---------------- durustluk kontrolleri ----------------
  console.log("\n--- Veri durustlugu ---");
  const go = async (n) => {
    await openView(n);
    return viewText();
  };

  let t = await go("dashboard");
  check("panoda ortak veri setinin ogrenci sayisi (4.000) gorunuyor", t.includes("4.000"));
  check("kullaniciya ham JSON gosterilmiyor", !t.includes('{"') && !t.includes('":'));
  check("'mock' / 'prototype' ifadesi kalmamis", !/mock|prototype|placeholder/i.test(t));

  t = await go("users");
  check("parola alanlari arayuze sizmiyor", !/password_hash|password_salt/i.test(t));

  t = await go("assistant");
  check("asistan: dil modeli bagli olmadigini soyluyor", /dil modeli/i.test(t));
  check("asistan: uydurma cevap uretmiyor", !/İşte cevabınız|Cevap:/i.test(t));

  t = await go("rankings");
  check("Modul 10: gercek siralama uretmedigi uyarisi var", /ÜRETMEZ/.test(t));

  t = await go("finance");
  check("mali ekranda USD gosteriliyor", /\$/.test(t) && !/₺|TL\b/.test(t), t.slice(0, 120));
  check("5 yillik degisim ozeti var", /Gelir değişimi/.test(t));

  t = await go("success");
  check("basari ekrani ders gecme oranini gosteriyor", /geçme oranı/i.test(t));
  check("basari ekraninda kirilim var", /Fakülte|fakülte/.test(t));

  // KPI künyesi artık ana ekranda değil, satır genişletilince görünür.
  // Bu bilinçli: formül ve kaynak ana tabloya yığılmıyor.

  t = await go("engagement");
  check("endeks bilesenleri gosteriliyor", /Endekse katkı|katkı/i.test(t));

  // Menude ic gelistirme ifadesi kalmamali
  const menuText = w.document.querySelector("#sidebar").textContent;
  check("menude modul numarasi yok", !/\bM\d|Modül \d/.test(menuText), menuText.slice(0, 100));

  // Senaryo simulasyonu
  await openView("scenarios");
  // Maas zammi senaryosunu sec ve hesapla
  const typeSel = $("#scType");
  typeSel.value = "academic-staffing";
  typeSel.dispatchEvent(new w.Event("change"));
  await sleep(300);
  $("#scPreview").click();
  await sleep(2500);
  const result = $("#scResult").textContent;
  check(
    "maas senaryosu gercek sonuc uretti",
    /Genel risk/.test(result) && /\d/.test(result) && !/Hesapla düğmesine/.test(result),
    result.slice(0, 150)
  );
  check("onceki/yeni deger karsilastirmasi var",
    /Önceki değer/.test(result) && /Yeni değer/.test(result));
  check("mali + akademik + kapasite etkileri gosteriliyor",
    /Mali etki/.test(result) && /Akademik etki/.test(result) && /Kapasite etkisi/.test(result));
  check("simulasyonun onizleme oldugu belirtiliyor", /önizleme/.test(result));
  check("USD gosteriliyor", /\$/.test(result));
  check("senaryo: ingilizce risk seviyesi gorunmuyor",
    !/\b(low|medium|high|critical)\b/.test(result),
    result.slice(0, 160));

  // ---------------- UX yeniden tasarim kontrolleri ----------------
  console.log("\n--- Asamali gosterim ve filtre akisi ---");

  // 1) Surdurulebilirlik: sayfa acilisinda program listesi GORUNMEMELI
  await openView("sustainability");
  let view = $("#view");
  check(
    "sustainability: acilista program listesi yok",
    !/Program karnesi/.test(view.textContent) &&
      /Sonuçları Göster/.test(view.textContent),
    view.textContent.slice(0, 140)
  );
  check(
    "sustainability: agirlik tablosu ana ekranda degil (kapali bolumde)",
    view.querySelectorAll("details.disclosure").length > 0 &&
      !view.querySelector("details.disclosure[open]"),
    "acik details sayisi: " + view.querySelectorAll("details.disclosure[open]").length
  );

  // 2) Hiyerarsik filtre: fakulte secilmeden bolum secilemez
  const facultySelect = view.querySelector('[data-org="faculty"]');
  const departmentSelect = view.querySelector('[data-org="department"]');
  const programSelect = view.querySelector('[data-org="program"]');
  check("sustainability: fakulte secimi var", !!facultySelect);
  check("sustainability: bolum baslangicta kilitli", departmentSelect.disabled === true);
  check("sustainability: program baslangicta kilitli", programSelect.disabled === true);

  // Fakulte sec -> bolum acilir, program hala kilitli
  facultySelect.value = String(
    (await (await fetch(BASE + "/api/faculties?limit=5")).json())[0].id
  );
  facultySelect.dispatchEvent(new w.Event("change"));
  await sleep(700);
  check("sustainability: fakulte secilince bolum acildi", departmentSelect.disabled === false);
  check("sustainability: program hala kilitli", programSelect.disabled === true);

  // Bolum sec -> program acilir
  const firstDepartmentOption = Array.from(departmentSelect.options).find((o) => o.value);
  departmentSelect.value = firstDepartmentOption.value;
  departmentSelect.dispatchEvent(new w.Event("change"));
  await sleep(700);
  check("sustainability: bolum secilince program acildi", programSelect.disabled === false);

  // Sonuclari goster -> sonuc gelir
  view.querySelector('[data-org="apply"]').click();
  await sleep(3500);
  const susText = $("#susResult").textContent;
  check(
    "sustainability: sonuc geldi",
    /Genel değerlendirme|Program karnesi/.test(susText),
    susText.slice(0, 140)
  );
  check(
    "sustainability: teknik alan adi gorunmuyor",
    !/student_demand|occupancy_rate|graduate_employability|snake_case/.test(susText),
    susText.slice(0, 200)
  );
  check(
    "sustainability: eksik kriterler tek satir ozet",
    !/graduate_employability, academic_staff_quality/.test(susText)
  );
  check(
    "sustainability: eksik kriter 0 puan olarak gosterilmiyor",
    !/Veri bulunamadı/.test(susText) || !/0 \/ 100/.test(susText),
    susText.slice(0, 160)
  );

  // 3) KPI: uc sekme
  await openView("kpi");
  view = $("#view");
  const tabButtons = view.querySelectorAll(".tab-btn");
  check("kpi: uc sekme var", tabButtons.length === 3,
    Array.from(tabButtons).map((b) => b.textContent).join(" | "));
  check("kpi: Genel Bakis varsayilan acik",
    view.querySelector(".tab-panel.is-active").dataset.panel === "overview");
  check("kpi: ana ekranda formul yigilmamis",
    !/Formül:/.test(view.querySelector(".tab-panel.is-active").textContent));

  // Tum Gostergeler sekmesine gec
  Array.from(tabButtons).find((b) => b.dataset.tab === "all").click();
  await sleep(2000);
  const allPanel = view.querySelector('[data-panel="all"]');
  check("kpi: tum gostergeler tablosu geldi", /Gösterge/.test(allPanel.textContent));
  check("kpi: tabloda 5 sutun (formul yok)",
    allPanel.querySelectorAll("thead th").length === 5,
    "sutun: " + allPanel.querySelectorAll("thead th").length);

  // 4) Turetilmis KPI'lar artik 0 degil
  const kpiRows = await (await fetch(BASE + "/api/kpi?academic_year=2025-2026")).json();
  const derived = kpiRows.filter((r) => r.value_source === "derived");
  check("kpi: turetilmis gostergeler gercek deger gosteriyor",
    derived.length === 2 && derived.every((r) => Number(r.current_value) > 0),
    JSON.stringify(derived.map((r) => [r.name, r.current_value])));
  check("kpi: turetilmis gostergeler riskli isaretlenmiyor",
    derived.every((r) => r.status !== "riskli"),
    JSON.stringify(derived.map((r) => [r.name, r.status])));

  // 5) Kurum geneli ekranlarda organizasyon filtresi OLMAMALI
  for (const [name, label] of [["finance", "Finansal Analiz"], ["alerts", "Erken Uyarı"]]) {
    await openView(name);
    check(
      `${name}: zorunlu fakulte/bolum filtresi yok`,
      !$("#view").querySelector('[data-org="faculty"]'),
      label
    );
  }

  console.log("\n--- JavaScript hatalari ---");
  check("konsolda JS hatasi yok", jsErrors.length === 0, jsErrors.slice(0, 3).join(" | "));

  console.log("\n" + "=".repeat(60));
  console.log(`SONUC: ${pass} basarili, ${fail} hatali`);
  if (fail) {
    console.log("Basarisiz kontroller:");
    failures.forEach((f) => console.log("  - " + f));
  }
  console.log("=".repeat(60));
  process.exit(fail ? 1 : 0);
})();
