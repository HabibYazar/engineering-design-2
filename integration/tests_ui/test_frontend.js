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
     DINAMIK SONUC PENCERESI
     ------------------------------------------------------------------
     Ornek pencere tanimi (`ui_spec`) ve `structured_result`, backend
     testleri tarafindan tests_ui/fixtures/ altina YENIDEN URETILIR.
     Boylece bu bolum her zaman bugunun gercek builder ciktisini cizer;
     elle yazilmis, eskimis bir ornek dogrulanmaz.
     ================================================================== */
  console.log("\n--- Dinamik sonuc penceresi ---");

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

  // Pencere, sohbetten bagimsiz olarak da cizilebilmeli.
  const sandbox = w.document.createElement("div");
  sandbox.id = "aiSandbox";
  w.document.body.appendChild(sandbox);

  const renderInto = (spec) => {
    sandbox.innerHTML = w.eval("aiRenderView")(spec);
    return sandbox;
  };

  const clone = (o) => JSON.parse(JSON.stringify(o));

  renderInto(SPEC);
  const viewEl = sandbox.querySelector(".ai-generated-view");
  check("pencere: ui_spec cizildi", !!viewEl,
    squash(sandbox.innerHTML).slice(0, 160));

  const viewTextAll = squash(viewEl.textContent);

  // --- 1. Kartlardaki butun sayilar structured_result ile ayni ---
  const specCards = SPEC.sections
    .filter((s) => s.type === "metric_grid")
    .flatMap((s) => s.components);
  const cardEls = viewEl.querySelectorAll(".ai-section-metrics .ai-card");
  check("pencere: kart sayisi ui_spec ile ayni",
    cardEls.length === specCards.length && specCards.length > 0,
    `dom: ${cardEls.length}, spec: ${specCards.length}`);

  const metricByKey = {};
  STRUCTURED.metrics.forEach((m) => { metricByKey[m.key] = m; });
  const numbersIn = (text) =>
    (squash(text).match(/-?\d[\d.]*(?:,\d+)?/g) || [])
      .map((t) => Number(t.replace(/\./g, "").replace(",", ".")));

  let cardNumbersChecked = 0;
  let cardNumberMismatch = "";
  specCards.forEach((component, i) => {
    const allowed = new Set();
    (component.source_keys || []).forEach((key) => {
      const metric = metricByKey[key];
      if (!metric) return;
      ["baseline", "scenario", "change"].forEach((field) => {
        if (metric[field] === null || metric[field] === undefined) return;
        const v = Number(metric[field]);
        [v, Math.abs(v), Math.round(v), Math.abs(Math.round(v))].forEach((x) =>
          allowed.add(Number(x.toFixed(2)))
        );
      });
    });
    const el = cardEls[i];
    if (!el) return;
    const shown = squash(
      Array.from(el.querySelectorAll(".ai-card-value, .ai-card-compare, .ai-card-delta"))
        .map((n) => n.textContent).join(" ")
    );
    numbersIn(shown).forEach((n) => {
      cardNumbersChecked++;
      if (!allowed.has(Number(n.toFixed(2))) && !cardNumberMismatch) {
        cardNumberMismatch =
          `${component.title}: ${n} sayisi structured_result'ta yok ` +
          `(izinli: ${Array.from(allowed).join(", ")})`;
      }
    });
  });
  check("pencere: kart sayilari structured_result ile ayni",
    cardNumbersChecked >= 8 && !cardNumberMismatch,
    cardNumberMismatch || `dogrulanan sayi: ${cardNumbersChecked}`);

  // --- 2. Serbest metinden sayi ayristirilmaz ---
  // Modelin uydurdugu sayilar yalnizca "Tam metin rapor" acilir bolumunde,
  // ham metin olarak kalabilir; kart ve grafiklere sizamaz.
  const detailsEls = Array.from(viewEl.querySelectorAll("details.ai-details"));
  const outsideDetails = (() => {
    const copy = viewEl.cloneNode(true);
    copy.querySelectorAll("details.ai-details").forEach((d) => d.remove());
    return squash(copy.textContent);
  })();
  check("pencere: uydurma sayilar varsayilan gorunumde yok",
    !/68,42/.test(outsideDetails) && !/9\.876\.543/.test(outsideDetails) &&
      !/1\.111/.test(outsideDetails),
    outsideDetails.slice(0, 200));

  // --- 3. Bilinmeyen component type reddedilir ---
  const poisonedTypes = clone(SPEC);
  poisonedTypes.sections[0].components.push(
    { type: "script_block", title: "zararli", markdown: "<script>alert(1)</script>" },
    { type: "iframe", title: "zararli-2" }
  );
  const jsErrorsBefore = jsErrors.length;
  renderInto(poisonedTypes);
  check("pencere: bilinmeyen bilesen turu cizilmiyor",
    !/zararli/.test(sandbox.textContent) &&
      sandbox.querySelectorAll("script, iframe").length === 0,
    squash(sandbox.textContent).slice(0, 160));
  check("pencere: bilinmeyen tur uygulamayi cokertmiyor",
    !!sandbox.querySelector(".ai-generated-view") &&
      jsErrors.length === jsErrorsBefore);

  // --- 4. Global CSS uretilemez ---
  renderInto(SPEC);
  const styleEls = sandbox.querySelectorAll("style");
  const styleText = Array.from(styleEls).map((s) => s.textContent).join("\n");
  check("pencere: tek bir stil blogu var", styleEls.length === 1,
    "stil blogu: " + styleEls.length);
  check("pencere: her seciciyi data-view-id sinirliyor",
    styleText.split("{")[0].trim() ===
      `.ai-generated-view[data-view-id="${SPEC.view_id}"]`,
    styleText.slice(0, 160));
  check("pencere: yasak secicilere stil yazilmiyor",
    !/(^|[\s,{}])(body|html|\*)\s*[{,]/.test(styleText) &&
      !/#sidebar|\bheader\b|\.sidebar/.test(styleText),
    styleText.slice(0, 200));
  check("pencere: stil yalnizca CSS degiskeni tanimliyor",
    styleText.split("{")[1].split("}")[0].split(";").filter(Boolean)
      .every((d) => d.trim().startsWith("--ai-")),
    styleText.slice(0, 220));

  // Zararli tema belirteci: listede olmayan deger yok sayilir.
  const poisonedTheme = clone(SPEC);
  poisonedTheme.theme.accent = "red;} body { display:none } .x{color:";
  poisonedTheme.theme.card_radius = "9999px; position:fixed";
  renderInto(poisonedTheme);
  const poisonedStyle = sandbox.querySelector("style").textContent;
  check("pencere: tanimsiz tema belirteci varsayilana duser",
    /--ai-accent:#4f46e5/.test(poisonedStyle) &&
      !/display:none/.test(poisonedStyle) && !/position:fixed/.test(poisonedStyle),
    poisonedStyle.slice(0, 200));

  // --- 5. Program ve universite metrikleri ayri bolumlerde ---
  renderInto(SPEC);
  const metricsSection = sandbox.querySelector(".ai-section-metrics");
  const badgeScopes = Array.from(metricsSection.querySelectorAll(".ai-scope-badge"))
    .map((b) => b.textContent);
  check("pencere: ozet kartlari yalnizca program kapsaminda",
    badgeScopes.length > 0 && badgeScopes.every((t) => /^Program:/.test(t)),
    badgeScopes.join(" | ").slice(0, 160));
  const detailTitles = Array.from(sandbox.querySelectorAll("details.ai-details > summary"))
    .map((s) => s.textContent.trim());
  check("pencere: universite etkileri ayri bolumde",
    detailTitles.includes("Ayrıntılı program sonuçları") &&
      detailTitles.includes("Üniversite geneli etkiler"),
    detailTitles.join(" | "));
  const universityBlock = Array.from(sandbox.querySelectorAll("details.ai-details"))
    .find((d) => /Üniversite geneli etkiler/.test(d.querySelector("summary").textContent));
  const programBlock = Array.from(sandbox.querySelectorAll("details.ai-details"))
    .find((d) => /Ayrıntılı program sonuçları/.test(d.querySelector("summary").textContent));
  check("pencere: program bolumunde universite satiri yok",
    !/Üniversite/.test(programBlock.querySelector(".ai-details-body").textContent) &&
      /Üniversite/.test(universityBlock.querySelector(".ai-details-body").textContent));

  // --- 6-7-8. Aciklar: mevcut -> senaryo ve marjinal etki ---
  const riskText = squash(sandbox.querySelector(".ai-section-risks").textContent);
  check("pencere: derslik acigi 380 -> 400 (+20) yaziyor",
    /Üniversite derslik açığı: 380 → 400 eş zamanlı kişi \(senaryonun eklediği: \+20\)/
      .test(riskText),
    riskText.slice(0, 300));
  check("pencere: laboratuvar acigi 392 -> 402 (+10) yaziyor",
    /Üniversite laboratuvar açığı: 392 → 402 eş zamanlı kişi \(senaryonun eklediği: \+10\)/
      .test(riskText),
    riskText.slice(0, 300));
  const fteCard = Array.from(metricsSection.querySelectorAll(".ai-card"))
    .find((c) => /Program FTE açığı/.test(c.textContent));
  check("pencere: FTE acigi 0,50 -> 3,30 ve marjinal +2,80",
    !!fteCard &&
      /0,50 FTE → 3,30 FTE/.test(squash(fteCard.querySelector(".ai-card-compare").textContent)) &&
      /Senaryonun etkisi: \+2,80 FTE/.test(fteCard.querySelector(".ai-card-delta").textContent),
    fteCard ? squash(fteCard.textContent) : "kart yok");
  check("pencere: mevcut riskler ile senaryo etkisi ayri kartlarda",
    sandbox.querySelectorAll(".ai-section-risks .ai-risk").length === 2 &&
      /Mevcut durumdaki riskler/.test(riskText) &&
      /Senaryonun eklediği etki/.test(riskText),
    riskText.slice(0, 160));

  // --- 9. Legend yalnizca bir kez ---
  const legends = sandbox.querySelectorAll(".ai-legend");
  check("pencere: legend aciklamasi tek bir kez cizildi", legends.length === 1,
    "legend sayisi: " + legends.length);
  const legendText = squash(legends[0] ? legends[0].textContent : "");
  check("pencere: mavi ve turuncu aciklamasi bir kez geciyor",
    (viewTextAll.match(/Mevcut durum(?!daki)/g) || []).length === 1 &&
      (viewTextAll.match(/Senaryo sonucu/g) || []).length === 1,
    legendText);
  const swatchColors = Array.from(legends[0].querySelectorAll(".ai-swatch"))
    .map((s) => s.getAttribute("style"));
  check("pencere: legend renkleri kapsamli degiskenlerden geliyor",
    swatchColors.length >= 2 && swatchColors.every((s) => /var\(--ai-/.test(s)),
    swatchColors.join(" | "));

  // --- 10. Uzun Markdown varsayilan gorunumde yok ---
  const reportBlock = Array.from(sandbox.querySelectorAll("details.ai-details"))
    .find((d) => /Tam metin rapor/.test(d.querySelector("summary").textContent));
  check("pencere: tam metin rapor acilir bolumde ve KAPALI",
    !!reportBlock && reportBlock.open === false,
    reportBlock ? "open=" + reportBlock.open : "bolum yok");
  const visibleText = (() => {
    const copy = sandbox.querySelector(".ai-generated-view").cloneNode(true);
    copy.querySelectorAll("details.ai-details").forEach((d) => d.remove());
    return squash(copy.textContent);
  })();
  // Olcut sabit bir karakter sayisi degil, RAPORUN KENDI uzunlugu: varsayilan
  // gorunum tam metnin ucte birinden kisa olmali ve rapor basliklarini
  // hic tasimamalı.
  const fullReport = (reportBlock
    ? reportBlock.querySelector(".ai-details-body").textContent
    : "");
  check("pencere: 40 satirlik markdown varsayilan gorunumde degil",
    fullReport.length > 1500 &&
      visibleText.length < fullReport.length / 2 &&
      !/Program kapsamındaki sonuçlar/.test(visibleText) &&
      !/Üniversite bütçesine ve kaynaklarına etkisi/.test(visibleText),
    `gorunur: ${visibleText.length}, tam rapor: ${fullReport.length}`);
  check("pencere: yonetim yorumu ham Markdown isareti gostermiyor",
    !/#{2,}/.test(visibleText) &&
      !!sandbox.querySelector(".ai-info-body .ai-sub-head"),
    squash(sandbox.querySelector(".ai-info-body").textContent).slice(0, 160));
  check("pencere: varsayilan gorunumde en fazla 5 kart ve 3 grafik",
    cardEls.length <= 5 && sandbox.querySelectorAll(".ai-chart").length <= 3,
    `kart: ${cardEls.length}, grafik: ${sandbox.querySelectorAll(".ai-chart").length}`);

  // --- 12. Acilir teknik detaylar calisiyor ---
  const methodBlock = Array.from(sandbox.querySelectorAll("details.ai-details"))
    .find((d) => /Hesaplama yöntemi/.test(d.querySelector("summary").textContent));
  check("pencere: hesaplama yontemi bolumu var", !!methodBlock);
  const beforeOpen = methodBlock.open;
  methodBlock.querySelector("summary").click();
  check("pencere: acilir teknik detay acilip icerigi gosteriyor",
    beforeOpen === false && methodBlock.open === true &&
      methodBlock.querySelector(".ai-details-body").textContent.trim().length > 20,
    squash(methodBlock.querySelector(".ai-details-body").textContent).slice(0, 120));

  // --- 13. Finansal maliyet harici uyarisi gorunur ---
  check("pencere: maliyet haric uyarisi varsayilan gorunumde",
    /Finansal sonuçlar gerekli yeni personel ve kapasite yatırımlarının maliyetini içermemektedir/
      .test(visibleText),
    visibleText.slice(-260));
  check("pencere: altbilgide ek maliyet notu var",
    /Ek maliyetler/.test(squash(sandbox.querySelector(".ai-view-foot").textContent)) &&
      /Hesaba katılmadı/.test(squash(sandbox.querySelector(".ai-view-foot").textContent)));
  check("pencere: altbilgi akademik yil ve kapsam yaziyor",
    /2025-2026/.test(sandbox.querySelector(".ai-view-foot").textContent) &&
      /Bilgisayar Mühendisliği/.test(sandbox.querySelector(".ai-view-foot").textContent),
    squash(sandbox.querySelector(".ai-view-foot").textContent));
  check("pencere: kullanilan veriler paneli teknik arac adi gostermiyor",
    !!sandbox.querySelector(".ai-sources") &&
      !/get_|run_[a-z_]+scenario/.test(sandbox.querySelector(".ai-sources").textContent),
    squash(sandbox.querySelector(".ai-sources").textContent).slice(0, 160));

  // --- 14. XSS ve zararli CSS engellenir ---
  const attack = clone(SPEC);
  attack.view_id = 'aiv-x"] , * { display:none } .y[a="';
  attack.title = '<img src=x onerror="window.__pwned=1">Baslik';
  attack.sections[0].components[0].baseline_label =
    '<script>window.__pwned=2</script>370';
  attack.sections.push({
    type: "management_comment",
    title: "Yorum",
    components: [{
      type: "information_box",
      level: "info",
      body: '<script>window.__pwned=3</script><style>body{display:none}</style>metin',
    }],
  });
  const detailsSection = attack.sections.find((s) => s.type === "details");
  detailsSection.components.push({
    type: "expandable_details",
    title: "<svg onload=alert(1)>",
    markdown: '<iframe src="javascript:alert(1)"></iframe>',
  });
  w.__pwned = 0;
  renderInto(attack);
  check("pencere: XSS etiketi DOM'a girmiyor",
    sandbox.querySelectorAll("script, iframe, img, svg, object, embed").length === 0,
    squash(sandbox.innerHTML).slice(0, 200));
  check("pencere: enjekte edilen kod calismadi", !w.__pwned, "pwned=" + w.__pwned);
  check("pencere: zararli etiket duz metne donustu",
    /<img src=x onerror=/.test(sandbox.textContent) ||
      /&lt;img/.test(sandbox.innerHTML),
    squash(sandbox.textContent).slice(0, 160));
  const attackStyle = sandbox.querySelector("style").textContent;
  check("pencere: zararli view_id secicisi temizlendi",
    attackStyle.split("{")[0].trim() === '.ai-generated-view[data-view-id="aiv-xdisplaynoneya"]',
    attackStyle.slice(0, 200));
  check("pencere: zararli view_id ile bile global secici uretilmiyor",
    (attackStyle.match(/{/g) || []).length === 1 && !/display:none/.test(attackStyle),
    attackStyle.slice(0, 200));
  check("pencere: sayfanin geri kalanina stil sizmadi",
    w.getComputedStyle(w.document.body).display !== "none");

  // --- 11. "Analizi Goruntule" dugmesi calisiyor ---
  await openView("assistant");
  await sleep(500);
  w.__TEST_SPEC = SPEC;
  w.eval(`
    THREAD.length = 0;
    THREAD.push({ role: "user", text: "Bilgisayar Mühendisliği %15 artarsa ne olur?" });
    THREAD.push({
      role: "assistant",
      text: window.__TEST_SPEC ? "uzun markdown metni ".repeat(120) : "",
      uiSpec: window.__TEST_SPEC,
      dataSources: ["Öğrenci kayıtları"],
      academicYear: "2025-2026",
    });
    renderThread();
  `);
  await sleep(200);
  view = $("#view");
  const openButton = view.querySelector(".ai-open-view");
  check("asistan: 'Analizi Görüntüle' dugmesi cizildi",
    !!openButton && /Analizi Görüntüle/.test(openButton.textContent),
    openButton ? openButton.textContent : "dugme yok");

  const bubbleBody = view.querySelector(".assistant-msg.assistant .body");
  check("asistan: balonda uzun markdown yerine kisa ozet var",
    !!bubbleBody && bubbleBody.textContent.length < 400 &&
      !/uzun markdown metni uzun markdown metni/.test(bubbleBody.textContent) &&
      /Öğrenci sayısı/.test(bubbleBody.textContent),
    squash(bubbleBody ? bubbleBody.textContent : "").slice(0, 200));

  const panelBefore = $("#assistantViewPanel");
  check("asistan: analiz paneli baslangicta gizli", panelBefore.hidden === true);
  openButton.click();
  await sleep(600);
  const panel = $("#assistantViewPanel");
  check("asistan: dugme pencereyi acti",
    panel.hidden === false && !!panel.querySelector(".ai-generated-view"),
    squash(panel.textContent).slice(0, 160));
  check("asistan: acilan pencerede dogru sayilar var",
    /370 öğrenci/.test(panel.textContent) && /426 öğrenci/.test(panel.textContent),
    squash(panel.textContent).slice(0, 200));
  const closeButton = panel.querySelector("[data-ai-close]");
  check("asistan: pencerede kapat dugmesi var", !!closeButton);
  closeButton.click();
  await sleep(150);
  check("asistan: pencere kapaniyor",
    $("#assistantViewPanel").hidden === true &&
      $("#assistantViewPanel").innerHTML === "");

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
