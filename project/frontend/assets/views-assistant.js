// Akıllı Asistan — Gemini API'si üzerinden gerçek sohbet.
//
// Bu ekranda sabit, örnek veya kural tabanlı cevap YOKTUR. Gösterilen her
// yanıt backend üzerinden yerel modelden gelir. Model kapalıysa ekran bunu
// açıkça söyler ve boş bir cevap balonu göstermez.
//
// Modelin düşünme (reasoning) metni backend'de ayıklanır; bu dosyaya hiç
// ulaşmaz.

// Kullanıcı mesajı üst sınırı — backend ile aynı değer. Sunucuya boşuna
// istek göndermemek için burada da kontrol edilir.
const ASSISTANT_MAX_LENGTH = 4000;

// Ekranda gösterilecek durumlar. "API bağlı" gibi belirsiz metin kullanılmaz;
// kullanıcı ne yapması gerektiğini okuyabilmeli.
const ASSISTANT_STATES = {
  connecting: { kind: "info", text: "Bağlantı kuruluyor…" },
  ready: { kind: "good", text: "Yapay zekâ hazır" },
  service_down: {
    kind: "critical",
    text: "Gemini servisine ulaşılamıyor",
    hint: "İnternet bağlantısını ve GEMINI_API_KEY değerini kontrol edin.",
  },
  model_missing: {
    kind: "warning",
    text: "Model kullanılamıyor",
    hint: "backend/.env içindeki GEMINI_MODEL değerini kontrol edin.",
  },
  disabled: {
    kind: "warning",
    text: "Akıllı Asistan devre dışı",
    hint: "Yapılandırmada ASSISTANT_ENABLED=false.",
  },
  generating: { kind: "info", text: "Yanıt oluşturuluyor…" },
  error: { kind: "critical", text: "Hata oluştu" },
};

let ASSISTANT_STATUS = null;
let ASSISTANT_CONVERSATION = null;
let ASSISTANT_BUSY = false;

VIEWS["assistant"] = {
  title: "Akıllı Asistan",
  subtitle: "Yerel dil modeli · kurum verisine bağlı · veriler makineden çıkmaz",
  html: () => `
    <div class="card assistant-card">
      <div class="assistant-head">
        <div id="assistantState"></div>
        <button class="ghost" id="assistantReset" type="button">Yeni konuşma</button>
      </div>

      <div id="assistantThread" class="assistant-thread" aria-live="polite"></div>

      <form id="assistantForm" class="assistant-composer" autocomplete="off">
        <textarea id="assistantInput" rows="2"
          maxlength="${ASSISTANT_MAX_LENGTH}"
          placeholder="Sorunuzu yazın… (Enter ile gönder, Shift+Enter ile satır atla)"></textarea>
        <div class="composer-side">
          <button class="primary" id="assistantSend" type="submit">Gönder</button>
          <span class="counter" id="assistantCounter">0 / ${ASSISTANT_MAX_LENGTH}</span>
        </div>
      </form>

      <div class="note assistant-scope-note">
        Asistan kurum verisini <b>gerçek kayıtlardan</b> okur ve senaryoları
        mevcut hesaplama motoruyla çalıştırır. Sayıları kendi üretmez; veri
        bulunamazsa bunu açıkça söyler.
      </div>
    </div>

    <div id="assistantViewPanel" class="ai-panel" hidden></div>

    ${ux.details(
      "Bu asistan nasıl çalışıyor?",
      `<div id="assistantArchitecture">${ux.skeleton(3)}</div>`,
      { hint: "Mimari ve sonraki adımlar" }
    )}`,

  async init() {
    ASSISTANT_CONVERSATION = null;
    ASSISTANT_BUSY = false;

    renderState("connecting");
    renderThread([]);

    await refreshAssistantStatus();
    bindComposer();
    loadAssistantArchitecture();
  },
};

/* ------------------------------------------------------------------ */
/* Durum                                                               */
/* ------------------------------------------------------------------ */

function renderState(key, extra = "") {
  const state = ASSISTANT_STATES[key] || ASSISTANT_STATES.error;
  const hint = extra || state.hint || "";
  const govde = ux.statusBadge(state.kind, state.text) +
    (hint ? `<div class="assistant-hint">${fmt.esc(hint)}</div>` : "");

  // Durum üç yerde birden görünebilir: asistan sayfası, tam ekran yan
  // sütunu ve balonun başlığı. Biri yoksa atlanır.
  ["assistantState", "asistanDurum"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = govde;
  });
  const kucuk = document.getElementById("asistanDurumKucuk");
  if (kucuk) kucuk.innerHTML = ux.statusBadge(state.kind, state.text);
}

/** Sunucu durumunu ekran durumuna çevirir. */
function statusKey(status) {
  if (!status) return "error";
  if (!status.enabled) return "disabled";
  if (!status.service_available) return "service_down";
  if (!status.model_available) return "model_missing";
  return "ready";
}

async function refreshAssistantStatus() {
  try {
    ASSISTANT_STATUS = await api.get("/api/assistant/status");
  } catch (err) {
    ASSISTANT_STATUS = null;
    renderState("error", err.userMessage || err.message);
    setComposerEnabled(false);
    return;
  }

  const key = statusKey(ASSISTANT_STATUS);
  // Hazır durumda model adı da yazılır: kullanıcı hangi modelle konuştuğunu bilsin.
  const suffix = key === "ready" ? ` — ${ASSISTANT_STATUS.model}` : "";
  const el = document.getElementById("assistantState");
  if (el) {
    const state = ASSISTANT_STATES[key];
    const hint =
      key === "model_missing"
        ? `GEMINI_MODEL değerini değiştirin (şu an: ${ASSISTANT_STATUS.model})`
        : state.hint || "";
    el.innerHTML =
      ux.statusBadge(state.kind, state.text + suffix) +
      (hint ? `<div class="assistant-hint">${fmt.esc(hint)}</div>` : "");
  }

  setComposerEnabled(key === "ready");
  if (key !== "ready") {
    renderThread([
      {
        role: "system",
        text: ASSISTANT_STATUS.message,
      },
    ]);
  }
}

function setComposerEnabled(enabled) {
  // Üç yazma alanı: asistan sayfası, balon ve tam ekran.
  [["assistantInput", "assistantSend"], ["soru", "gonder"], ["tamSoru", "tamGonder"]]
    .forEach(([girisId, dugmeId]) => {
      const input = document.getElementById(girisId);
      const send = document.getElementById(dugmeId);
      if (input) input.disabled = !enabled;
      if (send) send.disabled = !enabled;
    });
}

/* ------------------------------------------------------------------ */
/* Sohbet akışı                                                        */
/* ------------------------------------------------------------------ */

// Konuşma balonları. Model çıktısı asla ham HTML olarak basılmaz.
const THREAD = [];

function renderThread(initial) {
  if (initial) {
    THREAD.length = 0;
    THREAD.push(...initial);
  }

  // AYNI SOHBET, ÜÇ KAP: tam ekran asistan sayfası (#assistantThread),
  // sağ alttaki balon (#akis) ve tam ekran çalışma alanı (#tamAkis).
  // Hepsi `data-thread` taşır; biri ekranda yoksa sessizce atlanır.
  const kaplar = Array.from(document.querySelectorAll("[data-thread]"));
  const eski = document.getElementById("assistantThread");
  if (eski && !kaplar.includes(eski)) kaplar.push(eski);
  if (!kaplar.length) return;

  const govde = !THREAD.length
    ? `<div class="assistant-empty">Yerel model hazır. Bir soru yazarak başlayın.</div>`
    : THREAD.map(bubble).join("");

  kaplar.forEach((el) => {
    el.innerHTML = govde;
    el.scrollTop = el.scrollHeight;
    // Her çizimden sonra düğmeler yeniden bağlanır (innerHTML dinleyicileri siler).
    el.querySelectorAll(".ai-open-view").forEach((button) =>
      button.addEventListener("click", () =>
        openAssistantView(Number(button.dataset.viewIndex))
      )
    );
  });
}

/* ------------------------------------------------------------------ */
/* Dinamik sonuç penceresi                                             */
/* ------------------------------------------------------------------ */

/**
 * Bir sohbet balonuna ait analiz penceresini açar.
 *
 * Pencere `structured_result`tan üretilmiş `ui_spec` ile çizilir; konuşma
 * geçmişindeki tanım korunduğu için aynı sonuç sonradan yeniden açılabilir.
 */
/** Analiz penceresi hangi kapta açılacak: görünür olan öncelikli. */
function assistantPanelTarget() {
  const tam = document.getElementById("asistan-tam");
  if (tam && tam.classList.contains("acik")) {
    return document.getElementById("tamPanel");
  }
  return document.getElementById("assistantViewPanel")
    || document.getElementById("tamPanel");
}

function openAssistantView(index) {
  const panel = assistantPanelTarget();
  const item = THREAD[index];
  if (!panel) return;

  if (!item || !item.uiSpec) {
    panel.hidden = false;
    panel.innerHTML = `<div class="state error">
      Bu cevap için görüntülenecek bir analiz sonucu bulunamadı.
    </div>`;
    return;
  }

  panel.hidden = false;
  panel.innerHTML = ui.loading("Analiz penceresi hazırlanıyor…");

  // Çizim senkron; yükleme durumu bir kare görünsün diye bir sonraki
  // çerçeveye bırakılıyor.
  requestAnimationFrame(() => {
    try {
      panel.innerHTML = aiRenderView(item.uiSpec, item.structured);
      const close = panel.querySelector("[data-ai-close]");
      if (close) {
        close.addEventListener("click", () => {
          panel.hidden = true;
          panel.innerHTML = "";
        });
      }
    } catch (error) {
      panel.innerHTML = `<div class="state error">
        Analiz penceresi çizilemedi: ${fmt.esc(error.message)}
      </div>`;
      return;
    }

    // Kaydırma ÇİZİMDEN SONRA ve ayrı bir denemede yapılır. Aynı try
    // bloğunda olsaydı, kaydırma desteklenmeyen bir ortamda çizilmiş
    // pencere silinip yerine hata kutusu geçerdi — çalışan bir özelliği
    // yardımcı bir davranış yüzünden kaybetmek olurdu.
    if (typeof panel.scrollIntoView === "function") {
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

function bubble(item) {
  if (item.role === "system") {
    return `<div class="assistant-note">${fmt.esc(item.text)}</div>`;
  }
  const who = item.role === "user" ? "Siz" : "Asistan";
  // UZUN MARKDOWN VARSAYILAN OLARAK GÖSTERİLMEZ.
  // Dinamik pencere varsa balonda yalnızca kısa özet + düğme durur; tam
  // metin pencerenin içindeki açılır bölümdedir.
  const hasView = Boolean(item.uiSpec);
  const bodyText = hasView ? assistantSummaryOf(item) : item.text;

  return `<div class="assistant-msg ${item.role}">
    <div class="who">${who}</div>
    <div class="body">${
      item.pending ? `<span class="typing">Yanıt oluşturuluyor…</span>` : safeText(bodyText)
    }</div>
    ${hasView && !item.pending ? assistantViewButton(item) : ""}
    ${item.pending ? "" : sourceBlock(item)}
  </div>`;
}

/** Balonda gösterilecek kısa özet. Tam rapor pencerededir. */
function assistantSummaryOf(item) {
  const spec = item.uiSpec;
  const cards = (spec.sections || [])
    .filter((s) => s.type === "metric_grid")
    .flatMap((s) => s.components || [])
    .slice(0, 2)
    .map((c) => {
      if (c.baseline_label && c.scenario_label) {
        return `${c.title}: ${c.baseline_label} → ${c.scenario_label}`;
      }
      return `${c.title}: ${c.value || ""}`;
    });
  const lines = [spec.title];
  if (spec.subtitle) lines.push(spec.subtitle);
  return lines.join(" · ") + (cards.length ? "\n\n- " + cards.join("\n- ") : "");
}

function assistantViewButton(item) {
  return `<div class="ai-open-row">
    <button class="primary ai-open-view" type="button"
            data-view-index="${THREAD.indexOf(item)}">Analizi Görüntüle</button>
  </div>`;
}

/**
 * "Kullanılan veriler" bölümü.
 *
 * Teknik araç adları (get_program_summary gibi) KULLANICIYA GÖSTERİLMEZ;
 * backend bunların Türkçe veri kaynağı karşılıklarını `data_sources` alanında
 * gönderir. Kapsam ve akademik yıl da burada yazar: kullanıcı cevabın hangi
 * yıla ve hangi birime ait olduğunu görmeden rakama güvenemez.
 */
function sourceBlock(item) {
  const sources = item.dataSources || [];
  if (!sources.length) {
    // Araç kullanılmamış: cevap modelin genel bilgisine dayanıyor.
    return item.role === "assistant" && item.generalKnowledge
      ? `<div class="assistant-basis general">
           Bu cevap kurum verisine değil, modelin genel bilgisine dayanıyor.
         </div>`
      : "";
  }

  const chips = [];
  if (item.academicYear) chips.push(`${fmt.esc(item.academicYear)} akademik yılı`);
  if (item.scope) {
    const scopeText = item.scope.program || item.scope.department || item.scope.faculty;
    chips.push(fmt.esc(scopeText || "Üniversite geneli"));
  }

  return `<div class="assistant-basis">
    ${chips.length ? `<div class="basis-scope">${chips.join(" · ")}</div>` : ""}
    ${ux.details(
      "Kullanılan veriler",
      `<ul class="source-list">${sources
        .map((s) => `<li>${fmt.esc(s)}</li>`)
        .join("")}</ul>`,
      { hint: `${sources.length} kaynak` }
    )}
  </div>`;
}

/**
 * Model çıktısını güvenli biçimde HTML'e çevirir.
 *
 * Sıra önemli: ÖNCE her şey kaçırılır, SONRA sınırlı bir biçimlendirme
 * uygulanır. Tersi yapılsaydı modelin ürettiği bir <script> etiketi sayfaya
 * girerdi. Desteklenen tek biçimler: paragraf, satır sonu, madde listesi,
 * **kalın** ve `kod`.
 */
function safeText(raw) {
  const escaped = fmt.esc(String(raw || ""));

  const inline = (line) =>
    line
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const blocks = escaped.split(/\n{2,}/);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      const isList = lines.every((l) => /^\s*[-*•]\s+/.test(l) || !l.trim());
      if (isList && lines.some((l) => l.trim())) {
        return (
          "<ul>" +
          lines
            .filter((l) => l.trim())
            .map((l) => `<li>${inline(l.replace(/^\s*[-*•]\s+/, ""))}</li>`)
            .join("") +
          "</ul>"
        );
      }
      return `<p>${inline(lines.join("<br>"))}</p>`;
    })
    .join("");
}

function bindComposer() {
  const form = document.getElementById("assistantForm");
  const input = document.getElementById("assistantInput");
  const counter = document.getElementById("assistantCounter");
  const reset = document.getElementById("assistantReset");
  if (!form || !input) return;

  input.addEventListener("input", () => {
    counter.textContent = `${input.value.length} / ${ASSISTANT_MAX_LENGTH}`;
  });

  // Enter gönderir, Shift+Enter satır atlar — sohbet arayüzlerinin beklenen davranışı.
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await sendMessage(input.value);
  });

  reset.addEventListener("click", () => {
    ASSISTANT_CONVERSATION = null;
    renderThread([]);
    ui.toast("Yeni konuşma başlatıldı.", "success");
  });
}

async function sendMessage(rawMessage) {
  const message = (rawMessage || "").trim();
  if (ASSISTANT_BUSY) return;
  if (!message) {
    ui.toast("Önce bir mesaj yazın.", "error");
    return;
  }
  if (message.length > ASSISTANT_MAX_LENGTH) {
    ui.toast(`Mesaj en fazla ${ASSISTANT_MAX_LENGTH} karakter olabilir.`, "error");
    return;
  }

  ASSISTANT_BUSY = true;
  setComposerEnabled(false);
  renderState("generating");

  const input = document.getElementById("assistantInput");
  if (input) {
    input.value = "";
    document.getElementById("assistantCounter").textContent = `0 / ${ASSISTANT_MAX_LENGTH}`;
  }

  THREAD.push({ role: "user", text: message });
  const pending = { role: "assistant", text: "", pending: true };
  THREAD.push(pending);
  renderThread();

  try {
    const result = await api.post("/api/assistant/chat", {
      message,
      conversation_id: ASSISTANT_CONVERSATION,
      stream: false,
      academic_year: (typeof durum !== "undefined" ? durum.donem : null),
      // KAPSAM YAPISAL OLARAK TAŞINIR.
      // Eskiden seçili birimin ADI sorunun metnine ekleniyordu; bu, ad
      // tahminine dayalı kırılgan bir çözümdü. Artık kimlikler
      // gönderiliyor ve backend araçların eksik kapsam parametrelerini
      // bununla dolduruyor. Soruda başka bir birim adı geçerse o kazanır.
      scope: (typeof agac !== "undefined" && agac.hazir && typeof durum !== "undefined")
        ? (Object.keys(agac.kapsam(durum.birim)).length ? agac.kapsam(durum.birim) : null)
        : null,
    });
    ASSISTANT_CONVERSATION = result.conversation_id;
    pending.text = result.answer;
    pending.pending = false;
    // Teknik araç adları (result.used_tools) BİLİNÇLİ OLARAK kullanılmıyor.
    pending.dataSources = result.data_sources || [];
    pending.academicYear = result.academic_year || null;
    pending.scope = result.scope || null;
    pending.generalKnowledge = result.data_source === "general_model_knowledge";
    // Dinamik pencere tanımı balonla birlikte saklanır; konuşma geçmişinden
    // yeniden açılabilsin diye.
    pending.uiSpec = result.ui_spec || null;
    // Sayıların DOĞRULANABİLMESİ için ham sonuç da saklanır: renderer her
    // grafiği bu kaynağa göre denetler.
    pending.structured = result.structured_result || null;
    renderThread();
    await refreshAssistantStatus();
  } catch (err) {
    // Hata gizlenmez ve uydurma cevapla doldurulmaz: balon çıkarılır,
    // sebebi ayrı bir not olarak yazılır.
    THREAD.pop();
    THREAD.push({ role: "system", text: err.userMessage || err.message });
    renderThread();
    renderState("error", err.userMessage || err.message);
  } finally {
    ASSISTANT_BUSY = false;
    setComposerEnabled(statusKey(ASSISTANT_STATUS) === "ready");
  }
}

/* ------------------------------------------------------------------ */
/* Mimari bölümü                                                       */
/* ------------------------------------------------------------------ */

async function loadAssistantArchitecture() {
  await load(
    "assistantArchitecture",
    () => api.get("/api/assistant/architecture"),
    (arch, el) => {
      el.innerHTML = `
        <p class="note">${fmt.esc(arch.summary)}</p>
        <div class="table-wrap"><table><thead><tr>
          <th>Bileşen</th><th>Sorumluluk</th><th>Durum</th></tr></thead><tbody>
          ${arch.components
            .map(
              (c) =>
                `<tr><td>${fmt.esc(c.file)}</td><td>${fmt.esc(
                  c.responsibility
                )}</td><td>${chip(
                  c.status === "hazır" ? "good" : "warning",
                  c.status
                )}</td></tr>`
            )
            .join("")}
        </tbody></table></div>
        <h4>Sonraki adımlar</h4>
        <ol class="plain">${arch.next_steps
          .map((s) => `<li>${fmt.esc(s)}</li>`)
          .join("")}</ol>`;
    }
  );
}

/* AI_QUICK_SEND_FIX */
if (typeof document !== "undefined") {

  document.addEventListener("click", function (e) {
    var target = e.target;
    var button = target && target.closest
      ? target.closest("#gonder, #tamGonder")
      : null;

    if (!button) return;

    e.preventDefault();

    var inputId = button.id === "tamGonder" ? "tamSoru" : "soru";
    var input = document.getElementById(inputId);

    if (input) {
      sendMessage(input.value);
    }
  });

  document.addEventListener("keydown", function (e) {
    var target = e.target;

    if (!target || (target.id !== "soru" && target.id !== "tamSoru")) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(target.value);
    }
  });

}
