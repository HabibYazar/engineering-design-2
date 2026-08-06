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
  ["assistant", /Ollama|Yapay zekâ|yerel/i],
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
// Metni tek satira indirger; hata mesajlarini okunur kilar.
const squash = (s) => (s || "").replace(/\s+/g, " ");

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

  // Hangi uç noktaların çağrıldığını kaydeder. "İlk yüklemede ayrıntı
  // endpointleri çağrılmıyor" kriteri ancak böyle doğrulanabilir.
  const requested = [];
  const rawFetch = w.fetch;
  w.fetch = (url, opts) => {
    requested.push(String(url));
    return rawFetch(url, opts);
  };
  const requestedSince = (mark) => requested.slice(mark);

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
  check("asistan: uydurma cevap uretmiyor", !/İşte cevabınız|Örnek cevap/i.test(t));
  check("asistan: modelin dusunme metni gorunmuyor", !/<think|thinking/i.test(t));
  check("asistan: belirsiz 'API bagli' metni yok", !/API bağlı/.test(t), t.slice(0, 160));

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

  // ---------------- Yonetim Panosu yeniden tasarimi ----------------
  console.log("\n--- Akilli Asistan (yerel model) ---");
  await openView("assistant");
  await sleep(900);
  view = $("#view");
  const assistantText = view.textContent;

  // Ollama bu test ortaminda kapali: ekran bunu ACIKCA soylemeli.
  check(
    "asistan: durum rozeti cizildi",
    !!view.querySelector("#assistantState .status-badge, #assistantState .chip"),
    view.querySelector("#assistantState")
      ? view.querySelector("#assistantState").innerHTML.slice(0, 160)
      : "durum alani yok"
  );
  check(
    "asistan: Ollama kapaliyken anlasilir durum gosteriyor",
    /Ollama servisine ulaşılamıyor|Model kurulu değil|Yapay zekâ hazır/.test(assistantText),
    assistantText.slice(0, 200)
  );
  check(
    "asistan: sohbet alani var",
    !!view.querySelector("#assistantThread") && !!view.querySelector("#assistantInput")
  );
  // Ollama bu makinede acik olabilir de olmayabilir de. Test iki durumu da
  // dogrular: hazir degilken giris kilitli, hazirken gercek cevap geliyor.
  const assistantReady = !/Ollama servisine ulaşılamıyor|Model kurulu değil/.test(
    assistantText
  );
  if (!assistantReady) {
    check(
      "asistan: model hazir degilken giris kilitli",
      view.querySelector("#assistantInput").disabled === true
    );
  } else {
    check("asistan: model hazirken giris acik",
      view.querySelector("#assistantInput").disabled === false);

    // Kurumsal bir soru sorulur: "Merhaba" genel sohbettir ve araç
    // kullanmaz, dolayısıyla "Kullanılan veriler" bölümü de çıkmaz.
    view.querySelector("#assistantInput").value =
      "Bilgisayar Mühendisliği programının mevcut öğrenci sayısı nedir?";
    view.querySelector("#assistantForm").dispatchEvent(
      new w.Event("submit", { cancelable: true, bubbles: true })
    );
    await sleep(3000);
    const thread = $("#assistantThread").textContent;
    check("asistan: gercek model cevabi balona yazildi",
      /Asistan/.test(thread) && thread.length > 40 && !/Yanıt oluşturuluyor/.test(thread),
      thread.replace(/\s+/g, " ").slice(0, 180));
    check("asistan: cevapta dusunme metni yok",
      !/<think|muhakeme|gizli/i.test(thread),
      thread.replace(/\s+/g, " ").slice(0, 180));

    // Arac kullanildiysa "Kullanilan veriler" bolumu cikmali, teknik arac
    // adlari GORUNMEMELI.
    const basis = $("#assistantThread").querySelector(".assistant-basis");
    if (basis) {
      check("asistan: kullanilan veriler bolumu var",
        /Kullanılan veriler/.test(basis.textContent), basis.textContent.slice(0, 120));
      check("asistan: teknik arac adi gorunmuyor",
        !/get_program_summary|get_financial_summary|run_[a-z_]+scenario/.test(thread),
        thread.slice(0, 200));
      check("asistan: veri kaynagi turkce yazilmis",
        /Öğrenci kayıtları|Mali dönem kayıtları|Senaryo motoru|Akademik personel|Fiziksel kapasite/
          .test(basis.textContent),
        basis.textContent.slice(0, 160));
    }

    // UCTAN UCA: gercek /chat cevabindaki ui_spec ile pencere aciliyor mu?
    // Yukaridaki pencere testleri kaydedilmis ornekle calisir; burasi
    // zincirin tamamini (backend -> API -> renderer) dogrular.
    const liveButton = $("#assistantThread").querySelector(".ai-open-view");
    if (liveButton) {
      liveButton.click();
      await sleep(700);
      const livePanel = $("#assistantViewPanel");
      check("asistan: canli cevabin analiz penceresi aciliyor",
        livePanel.hidden === false &&
          !!livePanel.querySelector(".ai-generated-view") &&
          !/çizilemedi|okunamadı/.test(livePanel.textContent),
        squash(livePanel.textContent).slice(0, 160));
      check("asistan: canli pencere kapsamli stil uretiyor",
        !!livePanel.querySelector("style") &&
          /^\.ai-generated-view\[data-view-id="aiv-[0-9a-f]+"\]\{/
            .test(livePanel.querySelector("style").textContent),
        (livePanel.querySelector("style") || {}).textContent);
      livePanel.querySelector("[data-ai-close]").click();
      await sleep(150);
    }
  }
  // Araç entegrasyonu sonrası model kurum verisine ERİŞİYOR. Ekran artık
  // "erişemez" demiyor; sayıları kendi üretmediğini söylüyor.
  check(
    "asistan: sayilari kendi uretmedigini soyluyor",
    /gerçek kayıtlardan|Sayıları kendi üretmez/.test(assistantText),
    assistantText.slice(0, 220)
  );

  // Durum uc noktasi Ollama kapaliyken bile 200 donmeli.
  const assistantStatus = await (await fetch(BASE + "/api/assistant/status")).json();
  check(
    "asistan: durum ucu ollama kapaliyken de cevap veriyor",
    assistantStatus.provider === "ollama" && typeof assistantStatus.ready === "boolean",
    JSON.stringify(assistantStatus).slice(0, 200)
  );
  check(
    "asistan: sahte 'hazir' bildirmiyor",
    assistantStatus.ready === assistantStatus.service_available && assistantStatus.model,
    JSON.stringify(assistantStatus).slice(0, 200)
  );

  // Bos mesaj sunucuya gitse bile reddedilmeli.
  const emptyResponse = await fetch(BASE + "/api/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "   " }),
  });
  check("asistan: bos mesaj reddediliyor", emptyResponse.status === 422,
    "durum: " + emptyResponse.status);

  /* ==================================================================
     DINAMIK ANALIZ PANELI
     ------------------------------------------------------------------
     Ornek pencere tanimi (`ui_spec`) ve `structured_result`, backend
     testleri tarafindan tests_ui/fixtures/ altina YENIDEN URETILIR.
     Boylece bu bolum her zaman bugunun gercek builder ciktisini cizer;
     elle yazilmis, eskimis bir ornek dogrulanmaz.
     ================================================================== */
  console.log("\n--- Dinamik analiz paneli ---");

  const fs = require("fs");
  const fixtureDir = path.join(__dirname, "fixtures");
  let SPEC = null;
  let STRUCTURED = null;
  try {
    SPEC = JSON.parse(fs.readFileSync(path.join(fixtureDir, "ui_spec_sample.json"), "utf8"));
    STRUCTURED = JSON.parse(
      fs.readFileSync(path.join(fixtureDir, "structured_result_sample.json"), "utf8")
    );
  } catch (e) {
    console.error(
      "Ornek pencere tanimi bulunamadi. Once backend testlerini calistirin:\n" +
      "  python -m pytest integration/backend/tests_integration/test_ui_spec.py"
    );
    process.exit(2);
  }

  const sandbox = w.document.createElement("div");
  sandbox.id = "aiSandbox";
  w.document.body.appendChild(sandbox);

  const render = (spec, structured) => {
    sandbox.innerHTML = w.eval("aiRenderView")(spec, structured || STRUCTURED);
    return sandbox.querySelector(".ai-generated-view");
  };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const sectionOf = (cls) => sandbox.querySelector(cls);
  const typesIn = (root) =>
    Array.from((root || sandbox).querySelectorAll("[data-ai-type]"))
      .map((el) => el.getAttribute("data-ai-type"));

  // Acilir bolumlerin DISINDA kalan metin = kullanicinin ilk gordugu ekran.
  const defaultViewText = () => {
    const copy = sandbox.querySelector(".ai-generated-view").cloneNode(true);
    copy.querySelectorAll("details.ai-accordion").forEach((d) => d.remove());
    return squash(copy.textContent);
  };

  view = render(SPEC);
  check("panel: ui_spec cizildi", !!view, squash(sandbox.innerHTML).slice(0, 160));
  check("panel: karar ozeti en ustte",
    !!sandbox.querySelector('[data-ai-type="decision_summary"]') &&
      sandbox.querySelector(".ai-section").classList.contains("ai-section-decision"),
    typesIn().slice(0, 4).join(", "));
  const summaryText = squash(sandbox.querySelector(".ai-decision-text").textContent);
  check("panel: karar ozeti tek cumle ve iki satiri asmiyor",
    summaryText.length > 40 && summaryText.length <= 220,
    `${summaryText.length} karakter: ${summaryText.slice(0, 120)}`);
  check("panel: ozetin yaninda rozetler var",
    sandbox.querySelectorAll(".ai-badge").length >= 3 &&
      /Yüksek risk|Orta risk|Düşük risk/.test(sandbox.querySelector(".ai-badges").textContent),
    squash(sandbox.querySelector(".ai-badges").textContent));

  // --- 1. Ana gorunumde uzun Markdown YOK ---
  const visible = defaultViewText();
  check("1) ana gorunumde uzun Markdown raporu yok",
    !/Program kapsamındaki sonuçlar/.test(visible) &&
      !/Üniversite bütçesine ve kaynaklarına etkisi/.test(visible) &&
      !/#{2,}/.test(visible),
    `gorunur uzunluk: ${visible.length}`);
  check("1b) ham rapor DOM'da yalnizca acilir bolum icinde",
    sandbox.querySelectorAll(".ai-markdown").length > 0 &&
      Array.from(sandbox.querySelectorAll(".ai-markdown"))
        .every((m) => m.closest("details.ai-accordion")),
    "markdown blogu: " + sandbox.querySelectorAll(".ai-markdown").length);

  // --- 2. Uzun rapor yalnizca accordion acilinca gorunur ---
  const accordions = Array.from(sandbox.querySelectorAll("details.ai-accordion"));
  check("2) sekiz ayrinti bolumu var ve hepsi KAPALI",
    accordions.length === 8 && accordions.every((d) => d.open === false),
    accordions.map((d) => d.querySelector("summary").textContent.trim()).join(" | "));
  const rawBlock = accordions.find((d) => /Ham asistan cevabı/.test(d.textContent));
  const beforeOpenLength = defaultViewText().length;
  rawBlock.querySelector("summary").click();
  check("2b) accordion acilinca uzun metin goruntuleniyor",
    rawBlock.open === true &&
      rawBlock.querySelector(".ai-markdown").textContent.length > 1500 &&
      defaultViewText().length === beforeOpenLength,
    "acilan metin: " + rawBlock.querySelector(".ai-markdown").textContent.length);
  rawBlock.querySelector("summary").click();
  check("2c) accordion tekrar kapaniyor", rawBlock.open === false);

  // --- 3. En fazla 5 KPI karti ---
  const kpiCards = sandbox.querySelectorAll('.ai-section-metrics [data-ai-type="kpi_card"]');
  check("3) ana gorunumde en fazla 5 KPI karti var",
    kpiCards.length > 0 && kpiCards.length <= 5, "kart: " + kpiCards.length);
  // Yalnizca DEGISIM olcen bir gostergenin (ek gelir etkisi) "onceki
  // degeri" yoktur; oraya 0 yazmak uydurma sayi olurdu. Bu yuzden kosul
  // "buyuk deger + (onceki deger VEYA degisim VEYA aciklama)".
  check("3b) her KPI kartinda buyuk deger ve baglam bilgisi var",
    Array.from(kpiCards).every(
      (c) => c.querySelector(".ai-kpi-value") &&
        (c.querySelector(".ai-kpi-prev") || c.querySelector(".ai-kpi-delta") ||
         c.querySelector(".ai-kpi-caption"))
    ));
  check("3b2) karsilastirmali kartlarda onceki deger ve degisim birlikte",
    Array.from(kpiCards).filter((c) => c.querySelector(".ai-kpi-prev"))
      .every((c) => !!c.querySelector(".ai-kpi-delta")) &&
      Array.from(kpiCards).filter((c) => c.querySelector(".ai-kpi-prev")).length === 4,
    "karsilastirmali kart: " +
      Array.from(kpiCards).filter((c) => c.querySelector(".ai-kpi-prev")).length);
  check("3c) KPI aciklamalari tek satir",
    Array.from(sandbox.querySelectorAll(".ai-kpi-caption"))
      .every((el) => el.textContent.trim().length <= 70),
    Array.from(sandbox.querySelectorAll(".ai-kpi-caption"))
      .map((e) => e.textContent.trim()).join(" | ").slice(0, 160));

  // --- 4. Ayni grafik turu tekrarlanmiyor ---
  const chartTypes = Array.from(
    sandbox.querySelectorAll(".ai-section-charts figure.ai-chart")
  ).map((el) => el.getAttribute("data-ai-type"));
  check("4) ayni grafik turu gereksiz tekrarlanmiyor",
    chartTypes.length > 0 && new Set(chartTypes).size === chartTypes.length,
    chartTypes.join(", "));
  check("4b) ana gorunumde en fazla 4 grafik var",
    chartTypes.length <= 4, chartTypes.join(", "));

  // --- 5-8. Dogru grafik, dogru veri ---
  const chartByType = (t) => sandbox.querySelector(`figure.ai-chart[data-ai-type="${t}"]`);
  const acceptedChain = {
    dumbbell_chart: ["dumbbell_chart", "horizontal_comparison_bar", "bar_chart"],
    bullet_chart: ["bullet_chart", "grouped_bar_chart", "bar_chart"],
    gauge_group: ["gauge_group", "grouped_bar_chart", "bar_chart"],
    waterfall_chart: ["waterfall_chart", "grouped_bar_chart", "bar_chart"],
  };
  const oneOf = (chain) => chain.map(chartByType).find(Boolean);

  const dumbbell = oneOf(acceptedChain.dumbbell_chart);
  check("5) ogrenci degisimi dumbbell (veya gecerli fallback) ile cizildi",
    !!dumbbell && /370/.test(dumbbell.textContent) && /426/.test(dumbbell.textContent) &&
      /\+56/.test(dumbbell.textContent),
    dumbbell ? squash(dumbbell.textContent).slice(0, 160) : "grafik yok");
  check("5b) dumbbell iki uc nokta ve baglanti cizgisi cizdi",
    !!dumbbell && dumbbell.querySelectorAll("circle.ai-dot").length === 2 &&
      !!dumbbell.querySelector(".ai-dumbbell-link"));

  const bullet = oneOf(acceptedChain.bullet_chart);
  check("6) FTE karsilastirmasi bullet (veya gecerli fallback) ile cizildi",
    !!bullet && /18/.test(bullet.textContent) && /18,5/.test(bullet.textContent) &&
      /21,3/.test(bullet.textContent),
    bullet ? squash(bullet.textContent).slice(0, 160) : "grafik yok");
  check("6b) bullet grafiginde kapasite sinir isareti var",
    !!bullet && (!!bullet.querySelector(".ai-marker") ||
      bullet.getAttribute("data-ai-type") !== "bullet_chart"));

  const gauges = oneOf(acceptedChain.gauge_group);
  const gaugeCells = gauges
    ? gauges.querySelectorAll('[data-ai-type="radial_gauge"]') : [];
  check("7) derslik ve laboratuvar oranlari gauge ile cizildi",
    !!gauges && gaugeCells.length === 2 &&
      /%38,96/.test(gauges.textContent) && /%65,87/.test(gauges.textContent),
    gauges ? squash(gauges.textContent).slice(0, 200) : "grafik yok");
  check("7b) gauge merkezinde senaryo, altinda mevcut oran ve degisim",
    !!gauges &&
      /%38,96/.test(gauges.querySelector(".ai-gauge-main").textContent) &&
      /Mevcut: %44,86/.test(squash(gauges.textContent)) &&
      /5,90 puan/.test(squash(gauges.textContent)),
    gauges ? squash(gauges.textContent).slice(0, 200) : "");

  const waterfall = oneOf(acceptedChain.waterfall_chart);
  check("8) mali etki waterfall (veya gecerli fallback) ile cizildi",
    !!waterfall && /2\.900\.000/.test(waterfall.textContent) &&
      /3\.157\.040/.test(waterfall.textContent) &&
      /\+329\.840/.test(waterfall.textContent),
    waterfall ? squash(waterfall.textContent).slice(0, 220) : "grafik yok");
  // GERCEK KADEMELI SELALE: ilk sutun mevcut butce, son sutun senaryo
  // butcesi; aradaki kalemler o seviyeden hareket eder ve sutunlar
  // birbirine baglanti cizgileriyle baglidir.
  check("8b) selale baslangic butcesinden sonuc butcesine iniyor",
    !!waterfall &&
      /mevcut/i.test(waterfall.querySelector(".ai-values").textContent) &&
      /senaryo/i.test(waterfall.querySelector(".ai-values").textContent) &&
      waterfall.querySelectorAll(".ai-wf-link").length >= 2,
    waterfall ? "baglanti: " + waterfall.querySelectorAll(".ai-wf-link").length : "");
  check("8c) toplam sutunlari isaretli degil MUTLAK deger yaziyor",
    !!waterfall && !/\+2\.900\.000/.test(waterfall.textContent),
    waterfall ? squash(waterfall.textContent).slice(0, 200) : "");

  // --- 9. Butun sayilar structured_result ile ayni ---
  const metricIndex = {};
  STRUCTURED.metrics.forEach((m) => {
    ["baseline", "scenario", "change"].forEach((f) => {
      if (m[f] !== null && m[f] !== undefined) metricIndex[m.key + "." + f] = Number(m[f]);
    });
  });
  const numbersIn = (text) =>
    (squash(text).match(/-?\d[\d.]*(?:,\d+)?/g) || [])
      .map((t) => Number(t.replace(/\./g, "").replace(",", ".")));

  let checkedNumbers = 0;
  let mismatch = "";
  SPEC.sections
    .filter((s) => s.type === "metric_grid")
    .flatMap((s) => s.components)
    .forEach((component, i) => {
      const allowed = new Set();
      (component.source_metric_ids || []).forEach((id) => {
        if (metricIndex[id] === undefined) return;
        allowed.add(Number(metricIndex[id].toFixed(2)));
        allowed.add(Number(Math.abs(metricIndex[id]).toFixed(2)));
      });
      const ids = component.source_metric_ids || [];
      if (ids.length >= 2 && metricIndex[ids[0]] !== undefined &&
          metricIndex[ids[1]] !== undefined) {
        const d = metricIndex[ids[1]] - metricIndex[ids[0]];
        allowed.add(Number(d.toFixed(2)));
        allowed.add(Number(Math.abs(d).toFixed(2)));
      }
      const el = kpiCards[i];
      if (!el) return;
      const shown = Array.from(
        el.querySelectorAll(".ai-kpi-value, .ai-kpi-prev b, .ai-kpi-delta")
      ).map((n) => n.textContent).join(" ");
      numbersIn(shown).forEach((n) => {
        checkedNumbers++;
        if (!allowed.has(Number(n.toFixed(2))) && !allowed.has(Number(Math.abs(n).toFixed(2)))
            && !mismatch) {
          mismatch = `${component.title}: ${n} structured_result'ta yok ` +
            `(izinli: ${Array.from(allowed).join(", ")})`;
        }
      });
    });
  check("9) KPI kartlarindaki butun sayilar structured_result ile ayni",
    checkedNumbers >= 8 && !mismatch, mismatch || `dogrulanan: ${checkedNumbers}`);

  // ui_spec bozulursa KAYNAK kazanir.
  const tampered = clone(SPEC);
  const studentCard = tampered.sections
    .find((s) => s.type === "metric_grid").components
    .find((c) => c.title === "Öğrenci sayısı");
  const tamperedChart = tampered.sections
    .find((s) => s.type === "chart_grid").components
    .find((c) => c.type === "dumbbell_chart");
  tamperedChart.series[0].values[0] = 99999;
  tamperedChart.data.baseline = 99999;
  render(tampered);
  const fixedChart = chartByType("dumbbell_chart");
  check("9b) ui_spec ile structured_result celisirse KAYNAK esas alinir",
    !!fixedChart && !/99\.999/.test(fixedChart.textContent) &&
      /370/.test(fixedChart.textContent),
    fixedChart ? squash(fixedChart.textContent).slice(0, 160) : "grafik yok");
  render(SPEC);

  // --- 10. Ham LLM metninden sayi ayristirilmaz ---
  check("10) uydurma sayilar ana gorunumde yok",
    !/68,42/.test(defaultViewText()) && !/9\.876\.543/.test(defaultViewText()) &&
      !/1\.111/.test(defaultViewText()),
    defaultViewText().slice(0, 200));

  // --- 11. Hesaplanmayan maliyetler sifir olarak gosterilmez ---
  const costWarning = sandbox.querySelector('.ai-section-charts [data-ai-type="information_box"]');
  check("11) hesaplanmayan maliyetler ayri uyarida, sifir kalem degil",
    !!costWarning &&
      /Ek personel maliyeti hesaplanmadı/.test(costWarning.textContent) &&
      /Fiziksel yatırım maliyeti hesaplanmadı/.test(costWarning.textContent) &&
      !!waterfall && !/\b0 USD\b/.test(waterfall.textContent),
    costWarning ? squash(costWarning.textContent).slice(0, 200) : "uyari yok");
  check("11b) uyari ana ekranda, acilir bolumun disinda",
    !!costWarning && !costWarning.closest("details"));

  // --- 12-13. Legend ---
  const legends = sandbox.querySelectorAll(".ai-legend");
  check("13) legend panelde tek bir kez cizildi", legends.length === 1,
    "legend sayisi: " + legends.length);
  // "Tekrar etmiyor" olcutu: legend metni yalnizca legend panelinde gecer.
  // Grafiklerin kendi veri tablolari ve tooltiplari legend DEGILDIR — onlar
  // erisilebilirlik icin zorunlu metinsel karsiliklardir ve farkli
  // etiketler kullanir.
  const panelLegendLabels = Array.from(legends[0].querySelectorAll(".ai-legend-item"))
    .map((el) => squash(el.textContent));
  const chartsText = squash(sandbox.querySelector(".ai-section-charts").textContent);
  check("13b) legend etiketleri grafik kartlarinda tekrar edilmiyor",
    panelLegendLabels.length >= 2 &&
      panelLegendLabels.every(
        (label) => (chartsText.split(label).length - 1) === 1
      ),
    panelLegendLabels
      .map((l) => `${l}=${chartsText.split(l).length - 1}`).join(", "));
  check("13c) hicbir grafik kendi legend'ini cizmiyor",
    sandbox.querySelectorAll(".ai-section-charts figure.ai-chart .ai-legend").length === 0);

  // Renk anlami butun grafiklerde ayni: her renk kapsamli degiskenden gelir
  // ve rol adiyla birebir eslesir.
  const colourUses = Array.from(
    sandbox.querySelectorAll("[style*='--ai-'], [fill^='var(--ai-'], [stroke^='var(--ai-']")
  );
  const roleColours = {};
  let colourConflict = "";
  Array.from(legends[0].querySelectorAll(".ai-legend-item")).forEach((item) => {
    const swatch = item.querySelector(".ai-swatch").getAttribute("style");
    const label = item.textContent.trim();
    const colour = (swatch.match(/var\(--ai-[a-z]+\)/) || [""])[0];
    if (roleColours[colour] && roleColours[colour] !== label) {
      colourConflict = `${colour} iki anlam tasiyor: ${roleColours[colour]} / ${label}`;
    }
    roleColours[colour] = label;
  });
  check("12) legend renkleri tek anlam tasiyor ve kapsamli degiskenden geliyor",
    !colourConflict && Object.keys(roleColours).every((c) => /^var\(--ai-/.test(c)),
    colourConflict || Object.entries(roleColours).map(([c, l]) => `${c}=${l}`).join(", "));
  check("12b) grafiklerde dogrudan renk kodu yazilmamis",
    !/#[0-9a-f]{6}/i.test(
      sandbox.querySelector(".ai-section-charts").innerHTML
    ),
    (sandbox.querySelector(".ai-section-charts").innerHTML.match(/#[0-9a-f]{6}/i) || [""])[0]);

  // --- 14. Bilinmeyen grafik tipi reddedilir ---
  const bogus = clone(SPEC);
  bogus.sections.find((s) => s.type === "chart_grid").components.push(
    { type: "sankey_chart", title: "zararli-grafik" },
    { type: "script_block", title: "zararli-kod" }
  );
  const jsErrorsBefore = jsErrors.length;
  render(bogus);
  check("14) bilinmeyen grafik tipi cizilmiyor",
    !/zararli/.test(sandbox.textContent) &&
      sandbox.querySelectorAll("script, iframe").length === 0,
    squash(sandbox.textContent).slice(0, 120));
  check("14b) bilinmeyen tur paneli cokertmiyor",
    !!sandbox.querySelector(".ai-generated-view") &&
      jsErrors.length === jsErrorsBefore &&
      sandbox.querySelectorAll("figure.ai-chart").length >= 3);

  // --- 15. Zararli HTML, JavaScript ve CSS ---
  const attack = clone(SPEC);
  attack.view_id = 'aiv-x"] , * { display:none } .y[a="';
  attack.title = '<img src=x onerror="window.__pwned=1">Baslik';
  attack.theme.accent = "red;} body { display:none } .x{color:";
  attack.sections.find((s) => s.type === "decision_summary").components[0].title =
    '<script>window.__pwned=2</script>Karar';
  attack.sections.find((s) => s.type === "accordion").components.push({
    type: "expandable_details",
    title: "<svg onload=alert(1)>",
    markdown: '<iframe src="javascript:alert(1)"></iframe>',
  });
  w.__pwned = 0;
  render(attack);
  check("15) XSS etiketi DOM'a girmiyor",
    sandbox.querySelectorAll("script, iframe, img, svg[onload], object, embed").length === 0,
    squash(sandbox.innerHTML).slice(0, 200));
  check("15b) enjekte edilen kod calismadi", !w.__pwned, "pwned=" + w.__pwned);
  const attackStyle = sandbox.querySelector("style").textContent;
  check("15c) zararli view_id secicisi temizlendi",
    attackStyle.split("{")[0].trim() ===
      '.ai-generated-view[data-view-id="aiv-xdisplaynoneya"]',
    attackStyle.slice(0, 200));
  check("15d) global CSS uretilemiyor",
    (attackStyle.match(/{/g) || []).length === 1 &&
      !/display:none/.test(attackStyle) &&
      !/(^|[\s,{}])(body|html|\*)\s*[{,]/.test(attackStyle) &&
      !/#sidebar|\.sidebar/.test(attackStyle),
    attackStyle.slice(0, 220));
  check("15e) stil yalnizca --ai- degiskeni tanimliyor",
    attackStyle.split("{")[1].split("}")[0].split(";").filter(Boolean)
      .every((d) => d.trim().startsWith("--ai-")),
    attackStyle.slice(0, 220));
  check("15f) tanimsiz tema belirteci varsayilana dusuyor",
    /--ai-accent:#6366f1/.test(attackStyle));
  check("15g) sayfanin geri kalanina stil sizmadi",
    w.getComputedStyle(w.document.body).display !== "none");

  // --- 16. Bir grafik hata verdiginde digerleri calisir ---
  const broken = clone(SPEC);
  const chartSection = broken.sections.find((s) => s.type === "chart_grid");
  const brokenChart = chartSection.components.find((c) => c.type === "bullet_chart");
  brokenChart.series = [];          // cizilemez hale getir
  brokenChart.data = {};
  brokenChart.fallback = null;
  render(broken);
  check("16) bozuk grafik yalnizca kendi kartini etkiliyor",
    sandbox.querySelectorAll("figure.ai-chart").length >= 3 &&
      !!chartByType("dumbbell_chart") &&
      !!sandbox.querySelector('[data-ai-type="gauge_group"]'),
    typesIn(sectionOf(".ai-section-charts")).join(", "));
  check("16b) bozuk grafik ya fallback'e dustu ya da hata kutusu gosterdi",
    !!sandbox.querySelector('[data-ai-type="failed"]') ||
      !!sandbox.querySelector('figure.ai-chart[data-ai-type="grouped_bar_chart"]') ||
      !!sandbox.querySelector('figure.ai-chart[data-ai-type="bar_chart"]'),
    typesIn(sectionOf(".ai-section-charts")).join(", "));
  check("16c) panelin geri kalani hala calisiyor",
    sandbox.querySelectorAll('[data-ai-type="kpi_card"]').length === 5 &&
      sandbox.querySelectorAll('[data-ai-type="risk_summary_card"]').length === 3);
  render(SPEC);

  // --- 17. Mobil gorunum tek kolona duser ---
  const mobileRules = [];
  Array.from(w.document.styleSheets).forEach((sheet) => {
    let rules;
    try { rules = sheet.cssRules; } catch { return; }
    Array.from(rules || []).forEach((rule) => {
      if (rule.media && /max-width:\s*860px/.test(rule.conditionText || rule.media.mediaText)) {
        Array.from(rule.cssRules || []).forEach((inner) => mobileRules.push(inner.cssText));
      }
    });
  });
  check("17) mobil kirilim noktasi tanimli", mobileRules.length > 0,
    "kural: " + mobileRules.length);
  check("17b) mobilde grid tek kolona dusuyor",
    mobileRules.some((r) => /\.ai-grid/.test(r) && /grid-template-columns:\s*1fr/.test(r)) &&
      mobileRules.some((r) => /\.ai-cell/.test(r) && /grid-column:\s*1\s*\/\s*-1/.test(r)),
    mobileRules.filter((r) => /ai-grid|ai-cell/.test(r)).join(" || ").slice(0, 220));
  check("17c) masaustunde 12 kolonlu grid kullaniliyor",
    Array.from(sandbox.querySelectorAll(".ai-cell"))
      .every((el) => /--ai-span:\s*\d+/.test(el.getAttribute("style") || "")),
    (sandbox.querySelector(".ai-cell") || {}).outerHTML);

  // --- 18. Accordion klavyeyle kullanilabiliyor ---
  const firstAccordion = sandbox.querySelector("details.ai-accordion");
  const summary = firstAccordion.querySelector("summary");
  summary.focus();
  check("18) accordion basligi klavyeyle odaklanabiliyor",
    w.document.activeElement === summary &&
      !summary.hasAttribute("tabindex"),
    "aktif: " + (w.document.activeElement || {}).tagName);
  summary.click();
  check("18b) odaktayken acilip kapanabiliyor", firstAccordion.open === true);
  summary.click();
  check("18c) tekrar kapaniyor", firstAccordion.open === false);
  check("18d) kapat dugmesinde aria-label var",
    (sandbox.querySelector("[data-ai-close]") || {}).getAttribute?.("aria-label") ===
      "Analiz penceresini kapat");
  check("18e) grafiklerde metinsel aciklama var (renk tek tasiyici degil)",
    Array.from(sandbox.querySelectorAll("figure.ai-chart svg[role='img']"))
      .every((svg) => (svg.getAttribute("aria-label") || "").length > 5),
    Array.from(sandbox.querySelectorAll("figure.ai-chart svg[role='img']"))
      .map((s) => s.getAttribute("aria-label")).join(" | ").slice(0, 200));
  check("18f) risk seviyeleri metinle de yaziyor",
    Array.from(sandbox.querySelectorAll('[data-ai-type="risk_summary_card"]'))
      .every((c) => /Kritik|Yüksek|İzlenmeli|Uygun/.test(c.textContent)),
    squash(sectionOf(".ai-section-risks").textContent).slice(0, 200));

  // --- 19. KPI kartlari birim ve kapsam tasiyor ---
  check("19) her KPI kartinda kapsam rozeti var",
    Array.from(kpiCards).length === 5 &&
      Array.from(sandbox.querySelectorAll('.ai-section-metrics [data-ai-type="kpi_card"]'))
        .every((c) => /^Program:/.test(
          (c.querySelector(".ai-scope-badge") || {}).textContent || "")),
    Array.from(sandbox.querySelectorAll(".ai-section-metrics .ai-scope-badge"))
      .map((b) => b.textContent).join(" | ").slice(0, 200));
  check("19b) KPI degerlerinde birim yaziyor",
    /öğrenci/.test(sandbox.querySelector(".ai-section-metrics").textContent) &&
      /FTE/.test(sandbox.querySelector(".ai-section-metrics").textContent) &&
      /USD/.test(sandbox.querySelector(".ai-section-metrics").textContent) &&
      /%/.test(sandbox.querySelector(".ai-section-metrics").textContent));
  check("19c) her KPI kartinda ikon var",
    Array.from(sandbox.querySelectorAll('.ai-section-metrics [data-ai-type="kpi_card"]'))
      .every((c) => !!c.querySelector("svg.ai-icon")));

  // --- risk ve karar bolumleri ---
  const riskCards = sandbox.querySelectorAll('[data-ai-type="risk_summary_card"]');
  check("risk: uc kompakt risk karti var", riskCards.length === 3,
    "kart: " + riskCards.length);
  check("risk: her kartta ikon, seviye rozeti ve buyuk metrik var",
    Array.from(riskCards).every(
      (c) => c.querySelector("svg.ai-icon") && c.querySelector(".ai-chip") &&
        c.querySelector(".ai-risk-value")
    ));
  check("risk: uzun paragraf yok",
    Array.from(riskCards).every((c) => squash(c.textContent).length < 180),
    Array.from(riskCards).map((c) => squash(c.textContent).length).join(", "));

  const decisions = sandbox.querySelectorAll(".ai-decisions li");
  check("karar: en fazla dort kisa madde var",
    decisions.length > 0 && decisions.length <= 4, "madde: " + decisions.length);
  check("karar: hicbir madde iki satiri asmiyor",
    Array.from(decisions).every((li) => squash(li.textContent).length <= 130),
    Array.from(decisions).map((li) => squash(li.textContent).length).join(", "));

  // --- "Analizi Goruntule" akisi ---
  await openView("assistant");
  await sleep(500);
  w.__TEST_SPEC = SPEC;
  w.__TEST_STRUCTURED = STRUCTURED;
  w.eval(`
    THREAD.length = 0;
    THREAD.push({ role: "user", text: "Bilgisayar Mühendisliği %15 artarsa ne olur?" });
    THREAD.push({
      role: "assistant",
      text: "uzun markdown metni ".repeat(120),
      uiSpec: window.__TEST_SPEC,
      structured: window.__TEST_STRUCTURED,
      dataSources: ["Öğrenci kayıtları"],
      academicYear: "2025-2026",
    });
    renderThread();
  `);
  await sleep(200);
  view = $("#view");
  const openButton = view.querySelector(".ai-open-view");
  check("akis: 'Analizi Görüntüle' dugmesi cizildi",
    !!openButton && /Analizi Görüntüle/.test(openButton.textContent));

  const bubbleBody = view.querySelector(".assistant-msg.assistant .body");
  check("akis: balonda uzun markdown yerine kisa ozet var",
    !!bubbleBody && bubbleBody.textContent.length < 400 &&
      !/uzun markdown metni uzun markdown metni/.test(bubbleBody.textContent),
    squash(bubbleBody ? bubbleBody.textContent : "").slice(0, 200));

  check("akis: panel baslangicta gizli", $("#assistantViewPanel").hidden === true);
  openButton.click();
  await sleep(600);
  const panel = $("#assistantViewPanel");
  check("akis: dugme paneli acti",
    panel.hidden === false && !!panel.querySelector(".ai-generated-view"),
    squash(panel.textContent).slice(0, 160));
  check("akis: KPI kartlari, dumbbell, bullet, gauge ve waterfall gorunuyor",
    panel.querySelectorAll('[data-ai-type="kpi_card"]').length === 5 &&
      !!panel.querySelector('[data-ai-type="dumbbell_chart"]') &&
      !!panel.querySelector('[data-ai-type="bullet_chart"]') &&
      !!panel.querySelector('[data-ai-type="gauge_group"]') &&
      !!panel.querySelector('[data-ai-type="waterfall_chart"]'),
    typesIn(panel).join(", "));
  check("akis: detayli rapor baslangicta kapali",
    Array.from(panel.querySelectorAll("details.ai-accordion")).every((d) => !d.open));
  const panelAccordion = panel.querySelector("details.ai-accordion");
  panelAccordion.querySelector("summary").click();
  check("akis: accordion acilinca ayrintili metin gorunuyor",
    panelAccordion.open === true &&
      panelAccordion.querySelector(".ai-acc-body").textContent.trim().length > 20,
    squash(panelAccordion.querySelector(".ai-acc-body").textContent).slice(0, 140));
  panel.querySelector("[data-ai-close]").click();
  await sleep(150);
  check("akis: pencere kapaniyor",
    $("#assistantViewPanel").hidden === true &&
      $("#assistantViewPanel").innerHTML === "");

  /* ==================================================================
     MAAS SENARYOSU — semantik ve mali sunum
     ------------------------------------------------------------------
     Bulunan hata: %10 zam senaryosunda selale grafigi 612.000 USD'yi
     once "ek brut gelir" olarak gosteriyor, sonra ayni tutari gider
     tarafinda bir kez daha sayiyordu. Maas artisi gelir degildir ve
     ayni tutar iki kez sayilmaz.
     ================================================================== */
  console.log("\n--- Maas senaryosu paneli ---");

  let SALARY_SPEC = null;
  let SALARY_STRUCTURED = null;
  try {
    SALARY_SPEC = JSON.parse(
      fs.readFileSync(path.join(fixtureDir, "ui_spec_salary_sample.json"), "utf8"));
    SALARY_STRUCTURED = JSON.parse(
      fs.readFileSync(path.join(fixtureDir, "structured_result_salary_sample.json"), "utf8"));
  } catch (e) {
    console.error("Maas senaryosu ornegi bulunamadi; once backend testlerini calistirin.");
    process.exit(2);
  }

  const salaryBox = w.document.createElement("div");
  w.document.body.appendChild(salaryBox);
  salaryBox.innerHTML = w.eval("aiRenderView")(SALARY_SPEC, SALARY_STRUCTURED);
  const salaryView = salaryBox.querySelector(".ai-generated-view");
  const salaryText = squash(salaryView.textContent);
  const salaryChart = (t) => salaryBox.querySelector(`figure.ai-chart[data-ai-type="${t}"]`);
  const cardText = squash(salaryBox.querySelector(".ai-section-metrics").textContent);

  check("maas: panel cizildi ve basligi zammi soyluyor",
    !!salaryView && /%10 Zam/.test(salaryBox.querySelector(".ai-view-title").textContent),
    salaryBox.querySelector(".ai-view-title").textContent);

  check("maas: karar ozeti karar odakli",
    !/hesaplanan sonuçlar aşağıdadır/i.test(salaryText) &&
      /612\.000 USD/.test(salaryBox.querySelector(".ai-decision-text").textContent),
    squash(salaryBox.querySelector(".ai-decision-text").textContent).slice(0, 180));
  check("maas: risk seviyesinin SEBEBI ekranda yaziyor",
    !!salaryBox.querySelector(".ai-decision-reason") &&
      /eşik/i.test(salaryBox.querySelector(".ai-decision-reason").textContent),
    squash((salaryBox.querySelector(".ai-decision-reason") || {}).textContent || ""));

  const salaryCards = salaryBox.querySelectorAll(
    '.ai-section-metrics [data-ai-type="kpi_card"]');
  check("maas: sorulan butun metrikler kart olarak var",
    salaryCards.length <= 5 &&
      /Akademik personel gideri/.test(cardText) && /Net bütçe/.test(cardText) &&
      /Personel gideri payı/.test(cardText) && /Toplam kurum harcaması/.test(cardText),
    cardText.slice(0, 220));
  check("maas: gider 6.120.000 -> 6.732.000 ve +612.000 gosteriliyor",
    /6\.120\.000 USD/.test(cardText) && /6\.732\.000 USD/.test(cardText) &&
      /\+612\.000 USD/.test(cardText) && /%10 artış/.test(cardText),
    cardText.slice(0, 220));
  check("maas: net butce 2.900.000 -> 2.288.000",
    /2\.900\.000 USD/.test(cardText) && /2\.288\.000 USD/.test(cardText) &&
      /-612\.000 USD/.test(cardText));
  check("maas: personel gideri orani ekranda",
    /%18,51/.test(cardText) && /%19,99/.test(cardText) && /puan/.test(cardText),
    cardText.slice(0, 220));
  check("maas: idari personel gideri AYRI kart ve degismedi",
    /İdari personel gideri/.test(cardText) && /2\.090\.000 USD/.test(cardText) &&
      /Değişmedi/.test(cardText),
    cardText.slice(0, 260));

  const salaryWaterfall = salaryChart("waterfall_chart");
  check("maas: gercek kademeli selale cizildi",
    !!salaryWaterfall &&
      /2\.900\.000/.test(salaryWaterfall.textContent) &&
      /2\.288\.000/.test(salaryWaterfall.textContent) &&
      /-612\.000/.test(salaryWaterfall.textContent),
    salaryWaterfall ? squash(salaryWaterfall.textContent).slice(0, 220) : "grafik yok");
  check("maas: selale sutunlari baglanti cizgileriyle bagli",
    !!salaryWaterfall && salaryWaterfall.querySelectorAll(".ai-wf-link").length >= 2,
    salaryWaterfall
      ? "baglanti: " + salaryWaterfall.querySelectorAll(".ai-wf-link").length : "");
  check("maas: selalede GELIR sutunu yok",
    !!salaryWaterfall && !/gelir/i.test(salaryWaterfall.textContent),
    salaryWaterfall ? squash(salaryWaterfall.textContent).slice(0, 200) : "");
  // Olcut metinde kac kez GECTIGI degil, kac SUTUN oldugudur: ayni tutar
  // tooltip'te, deger etiketinde ve erisilebilirlik tablosunda da yazar.
  check("maas: 612.000 selalede tek bir SUTUN olarak var",
    !!salaryWaterfall &&
      Array.from(salaryWaterfall.querySelectorAll(".ai-wf-bar"))
        .filter((g) => /612\.000/.test(g.textContent)).length === 1,
    salaryWaterfall
      ? "sutun: " + Array.from(salaryWaterfall.querySelectorAll(".ai-wf-bar"))
          .filter((g) => /612\.000/.test(g.textContent)).length
      : "");
  check("maas: gider artisi selalede ASAGI iniyor",
    !!salaryWaterfall && !/\+612\.000/.test(salaryWaterfall.textContent),
    salaryWaterfall ? squash(salaryWaterfall.textContent).slice(0, 200) : "");

  // Kural ANA EKRANDAKI bilesenler icindir. "Öğrenci başına maliyet"
  // metrigi maas senaryosunda da anlamlidir ve acilir bolumde durur;
  // orayi kapsam disi tutmak testi anlamsiz kilardi.
  const salaryMainText = (() => {
    const copy = salaryView.cloneNode(true);
    copy.querySelectorAll("details.ai-accordion").forEach((d) => d.remove());
    return squash(copy.textContent);
  })();
  check("maas: ana ekranda ogrenci/derslik/laboratuvar bileseni yok",
    !/öğrenci/i.test(salaryMainText) && !/derslik/i.test(salaryMainText) &&
      !/laboratuvar/i.test(salaryMainText),
    salaryMainText.slice(0, 220));
  check("maas: kapasite yatirim uyarisi HICBIR YERDE gosterilmiyor",
    !/Fiziksel yatırım maliyeti hesaplanmadı/.test(salaryText) &&
      !/Ek personel maliyeti hesaplanmadı/.test(salaryText));

  const scopeBox = salaryBox.querySelector('[data-ai-type="information_box"]');
  check("maas: senaryonun kendi varsayimlari gorunuyor",
    !!scopeBox && /kadro sayısı sabit/i.test(scopeBox.textContent) &&
      /ek ders/i.test(scopeBox.textContent) && /yan haklar/i.test(scopeBox.textContent) &&
      /döviz kuru sabit/i.test(scopeBox.textContent),
    scopeBox ? squash(scopeBox.textContent).slice(0, 240) : "kutu yok");

  const salaryTypes = Array.from(
    salaryBox.querySelectorAll(".ai-section-charts figure.ai-chart")
  ).map((el) => el.getAttribute("data-ai-type"));
  check("maas: grafik turleri verinin anlamina uygun",
    salaryTypes.includes("dumbbell_chart") &&
      salaryTypes.includes("waterfall_chart") &&
      salaryTypes.length <= 4 &&
      new Set(salaryTypes).size === salaryTypes.length,
    salaryTypes.join(", "));
  check("maas: oran gauge grubu cizildi",
    !!salaryBox.querySelector('[data-ai-type="gauge_group"]') &&
      /%19,99/.test(salaryBox.querySelector('[data-ai-type="gauge_group"]').textContent),
    squash((salaryBox.querySelector('[data-ai-type="gauge_group"]') || {}).textContent || "")
      .slice(0, 160));
  check("maas: butun sayilar structured_result ile ayni",
    (() => {
      const idx = {};
      SALARY_STRUCTURED.metrics.forEach((m) => {
        ["baseline", "scenario", "change"].forEach((f) => {
          if (m[f] !== null && m[f] !== undefined) idx[m.key + "." + f] = Number(m[f]);
        });
      });
      let ok = true;
      SALARY_SPEC.sections.forEach((sec) => sec.components.forEach((c) => {
        (c.series || []).forEach((sr) => (sr.values || []).forEach((v, i) => {
          const id = (sr.source_metric_ids || [])[i];
          if (!id || idx[id] === undefined || v === null) return;
          const sign = (sr.value_signs || [])[i] || 1;
          if (Math.abs(v - idx[id] * sign) > 0.005) ok = false;
        }));
      }));
      return ok;
    })());

  salaryBox.remove();
  sandbox.remove();


  console.log("\n--- Yonetim Panosu ---");

  const mark = requested.length;
  await openView("dashboard");
  await sleep(1200);
  view = $("#view");
  let dashText = view.textContent;
  const firstLoad = requestedSince(mark).join(" ");

  // 1) Ilk acilista bolum/program listesi yok
  check(
    "pano: acilista bolum/program listesi yok",
    !view.querySelector("[data-department]") && !view.querySelector("[data-program]"),
    dashText.slice(0, 160)
  );

  // 2) "Bolum bazli gelir ve gider" uzun listesi universite genelinde yok
  check(
    "pano: bolum bazli gelir-gider listesi universite genelinde yok",
    !/Bölüm bazlı gelir ve gider/.test(dashText) && /Gelir ve gider özeti/.test(dashText)
  );

  // 3-4) Ilk yuklemede bolum/program ayrinti uc noktalari cagrilmiyor
  check(
    "pano: ilk yuklemede bolum ayrinti ucu cagrilmiyor",
    !/finance\/[^ ]*\/departments/.test(firstLoad),
    firstLoad.slice(0, 300)
  );
  check(
    "pano: ilk yuklemede program ayrinti ucu cagrilmiyor",
    !/by-program|sustainability\/scores/.test(firstLoad),
    firstLoad.slice(0, 300)
  );

  // 5) Yalnizca ilk 5 risk gosteriliyor
  const riskItems = view.querySelectorAll("#dashRisks .risk-list li");
  check("pano: en fazla 5 risk gosteriliyor", riskItems.length > 0 && riskItems.length <= 5,
    "gosterilen: " + riskItems.length);
  check("pano: riskler kategoriye gore gruplanmis",
    view.querySelectorAll("#dashRisks .risk-summary tr").length >= 3,
    "kategori satiri: " + view.querySelectorAll("#dashRisks .risk-summary tr").length);

  // 6) "Tum riskleri incele" baglantisi
  const allRisksLink = view.querySelector('[data-risk="all"]');
  check("pano: tum riskleri incele baglantisi Erken Uyari sayfasina gidiyor",
    !!allRisksLink && allRisksLink.getAttribute("href") === "#/alerts",
    allRisksLink ? allRisksLink.getAttribute("href") : "baglanti yok");

  // 8) Ingilizce program isimleri gorunmuyor
  check("pano: ingilizce birim adi gorunmuyor",
    !/Bachelor's Program|Faculty of |Business Administration/.test(dashText),
    dashText.slice(0, 200));

  // 9) Grafik legend'lari tekrarlanmiyor
  const trendLegends = view.querySelectorAll("#dashTrend .legend, #dashTrendChart .legend");
  check("pano: egilim grafiginde tek legend var", trendLegends.length === 1,
    "legend sayisi: " + trendLegends.length);
  const legendLabels = Array.from(view.querySelectorAll(".legend span span"))
    .map((n) => (n.parentElement.textContent || "").trim());
  check("pano: ayni legend etiketi iki kez yazilmamis",
    new Set(legendLabels).size === legendLabels.length,
    legendLabels.join(" | "));

  // 10) Sol menu acilir gruplardan olusuyor
  const navGroups = w.document.querySelectorAll("#navGroups .nav-group");
  check("menu: acilir gruplardan olusuyor", navGroups.length === 6,
    "grup sayisi: " + navGroups.length);
  const openGroups = w.document.querySelectorAll("#navGroups .nav-group.open");
  check("menu: ayni anda tek grup acik", openGroups.length === 1,
    "acik grup: " + openGroups.length);
  check("menu: bulunulan grup otomatik acildi",
    openGroups[0] && openGroups[0].dataset.group === "Ana Sayfa",
    openGroups[0] ? openGroups[0].dataset.group : "-");

  // 11) Ozet kartlari drill-down
  const cards = view.querySelectorAll("#dashCards .tile[data-card]");
  check("pano: 6 ozet karti var", cards.length === 6, "kart: " + cards.length);
  const cardTargets = Array.from(cards).map((c) => c.getAttribute("href"));
  check("pano: kartlar ayrinti sayfalarina baglaniyor",
    cardTargets.includes("#/students") && cardTargets.includes("#/finance") &&
      cardTargets.includes("#/success") && cardTargets.includes("#/alerts"),
    cardTargets.join(" "));

  // 13) Breadcrumb universite genelinde tek seviye
  check("pano: breadcrumb universite genelini gosteriyor",
    (view.querySelector(".breadcrumb") || {}).textContent.trim() === "Üniversite Geneli",
    (view.querySelector(".breadcrumb") || {}).textContent);
  check("pano: universite genelinde donus dugmesi gizli",
    view.querySelector('[data-scope="reset"]').hidden === true);
  check("pano: bolum ve program alanlari cizilmemis",
    !view.querySelector('[data-scope="department"]') &&
      !view.querySelector('[data-scope="program"]'));

  // --- Fakulteye in ---
  const facultyMark = requested.length;
  const facultyRow = view.querySelector("#dashFaculties [data-faculty]");
  check("pano: fakulte karsilastirmasi cizildi", !!facultyRow);
  facultyRow.click();
  await sleep(2200);
  view = $("#view");
  dashText = view.textContent;

  check("pano: fakulteye tiklayinca kapsam degisti",
    /Fakültesi/.test((view.querySelector(".breadcrumb") || {}).textContent || ""),
    (view.querySelector(".breadcrumb") || {}).textContent);
  check("pano: fakulte secilince bolum alani cikti",
    !!view.querySelector('[data-scope="department"]'));
  check("pano: bolum secilmeden program alani cikmiyor",
    !view.querySelector('[data-scope="program"]'));
  check("pano: fakulte kapsaminda bolum karsilastirmasi yuklendi",
    requestedSince(facultyMark).some((u) => /finance\/[^ ]*\/departments/.test(u)),
    "istek yok");

  // 7) Gelir ve gider ayni bolum icin TEK satirda
  // Ana ekranda gorunen satirlar (acilir bolumdekiler haric) en fazla 5 olmali.
  const unitRows = view.querySelectorAll("#dashUnits > .unit-row");
  const hiddenUnitRows = view.querySelectorAll("#dashUnits details .unit-row");
  check("pano: bolum karsilastirmasi en fazla 5 satir gosteriyor",
    unitRows.length > 0 && unitRows.length <= 5, "satir: " + unitRows.length);
  check("pano: kalan bolumler acilir bolumde",
    hiddenUnitRows.length > 0 && !!view.querySelector("#dashUnits details"),
    "gizli satir: " + hiddenUnitRows.length);
  const firstUnit = unitRows[0];
  check("pano: gelir ve gider ayni satirda",
    /Gelir/.test(firstUnit.textContent) && /Gider/.test(firstUnit.textContent) &&
      /Net/.test(firstUnit.textContent),
    firstUnit.textContent.replace(/\s+/g, " ").slice(0, 120));
  check("pano: bolum adlari kesilmemis (tam ad yaziyor)",
    !/…|\.\.\./.test(firstUnit.querySelector(".unit-name").textContent),
    firstUnit.querySelector(".unit-name").textContent);

  // Bolume in -> program alani acilir
  const scopeDepartment = view.querySelector('[data-scope="department"]');
  const firstDept = Array.from(scopeDepartment.options).find((o) => o.value);
  scopeDepartment.value = firstDept.value;
  scopeDepartment.dispatchEvent(new w.Event("change"));
  await sleep(2200);
  view = $("#view");
  check("pano: bolum secilince program alani cikti",
    !!view.querySelector('[data-scope="program"]'));
  check("pano: breadcrumb uc seviyeyi gosteriyor",
    (view.querySelector(".breadcrumb") || {}).textContent.split("›").length === 3,
    (view.querySelector(".breadcrumb") || {}).textContent);

  // 12) Universite geneline donus
  view.querySelector('[data-scope="reset"]').click();
  await sleep(2200);
  view = $("#view");
  check("pano: universite geneline donus calisiyor",
    (view.querySelector(".breadcrumb") || {}).textContent.trim() === "Üniversite Geneli" &&
      !view.querySelector('[data-scope="department"]'),
    (view.querySelector(".breadcrumb") || {}).textContent);

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
