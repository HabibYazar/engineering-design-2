/* ABÜ KDS — EKRAN YAPAY ZEKA BİLEŞENİ (Compact Assistant & Auto Insight Card)
   ==========================================================================
   Tüm analitik ekranlar için:
   1. Otomatik Yapay Zeka Yorumu ve Tavsiyesi Kartı (✦ Auto Insight Card)
   2. Kompakt Yönetici Yapay Zeka Asistanı (✦ Compact Assistant)
   3. Yapay Zeka Kokpitine Kesintisiz Bağlam Geçişi (✦ Cockpit Handoff)

   MİMARİ İLKELER:
   - Tek yapay zeka omurgası: /api/assistant uç noktaları kullanılır.
   - Sıfır yinelenen DOM ID / Event Bug: data-* öznitelikleri ve olay delegasyonu.
   - Akıllı önbellek ve bayat istek (stale request) iptali.
   - Enter ile tek gönderim, Shift+Enter ile yeni satır.
   ========================================================================== */

(function (root) {
  "use strict";

  // Ekran başına konuşma ve otomatik analiz durumu
  const _screenAIState = {
    cache: new Map(),           // fingerprint -> auto_insight_data
    reqTokens: new Map(),       // screen_id -> latest_token_number
    activeFindings: new Map(),  // screen_id -> active finding text
    messages: new Map(),        // screen_id -> [{rol, metin, grafikler, kaynaklar}]
    convIds: new Map(),         // screen_id -> conversation_id
    busy: new Map(),            // screen_id -> boolean
  };

  /** Ekranın analitik alanını tespit eder */
  function detectScreenDomain(screenId) {
    if (!screenId) return "overview";
    if (screenId.startsWith("akademik")) return "academic";
    if (screenId.startsWith("ogrenci")) return "student";
    if (screenId.startsWith("altyapi")) return "infrastructure";
    if (screenId.startsWith("finans")) return "finance";
    if (screenId === "fakulteler" || screenId === "karsilastirma" || screenId === "ozet") return "overview";
    return "general";
  }

  /** Ekrandaki seçili yapısal kapsamı ve bağlamı derler */
  function getStructuredScreenContext(screenId, screenTitle) {
    const k = typeof kapsam === "function" ? kapsam() : {};
    const d = typeof dugum === "function" ? dugum() : {};
    const zincir = (typeof agac !== "undefined" && agac.bul && agac.bul(K.birimId)) ? (agac.bul(K.birimId).zincir || []) : [];
    const seciliFak = zincir.find(n => n.tur === "fakulte");
    const seciliBol = zincir.find(n => n.tur === "bolum");
    const seciliProg = zincir.find(n => n.tur === "program");

    return {
      screen_id: screenId || K.ekran || "ozet",
      screen_title: screenTitle || (typeof EKRANLAR !== "undefined" && EKRANLAR[screenId]?.baslik) || screenId,
      academic_year: K.donem || "2025-2026",
      faculty_id: k.faculty_id || (seciliFak?.id ? Number(String(seciliFak.id).replace(/\D/g, "")) : null),
      department_id: k.department_id || (seciliBol?.id ? Number(String(seciliBol.id).replace(/\D/g, "")) : null),
      academic_program_id: k.academic_program_id || (seciliProg?.id ? Number(String(seciliProg.id).replace(/\D/g, "")) : null),
      domain: detectScreenDomain(screenId),
      active_finding: _screenAIState.activeFindings.get(screenId) || null,
      conversation_id: _screenAIState.convIds.get(screenId) || null,
    };
  }

  /** Kararlı bağlam parmak izi (cache fingerprint) */
  function getContextFingerprint(ctx) {
    return [
      ctx.screen_id || "",
      ctx.academic_year || "",
      ctx.faculty_id || "all",
      ctx.department_id || "all",
      ctx.academic_program_id || "all",
    ].join("::");
  }

  /** Her analitik ekrana kompakt asistan ve otomatik yorum kartını monte eder */
  function mountScreenAI(containerEl, screenId, screenTitle) {
    if (!containerEl || screenId === "kokpit") return;

    // Varsa eski ekran AI bileşenini temizle (tekil montaj)
    const existing = containerEl.querySelector(".ai-screen-wrapper");
    if (existing) existing.remove();

    const wrapper = document.createElement("div");
    wrapper.className = "ai-screen-wrapper";
    wrapper.dataset.screenId = screenId;

    wrapper.innerHTML = `
      <!-- ✦ 1. OTOMATİK YAPAY ZEKA YORUMU VE TAVSİYESİ KARTI -->
      <div class="panel ai-insight-panel" data-screen-ai-card="${fmt.esc(screenId)}" data-buyut-tasi="1">
        <div class="panel-baslik">
          <div class="sol">
            <span class="ai-rozet-ik">✦</span>
            <div>
              <h3>Yapay Zeka Yorumu ve Tavsiyesi</h3>
              <small>Güncel filtre ve verilere dayalı otomatik kurumsal değerlendirme</small>
            </div>
          </div>
          <div class="sag">
            <span class="ai-insight-status">◷ Analiz hazırlanıyor…</span>
            <button class="buyut-dugme" type="button" data-buyut title="Büyüt" aria-label="Yapay zeka yorumunu büyüt">⛶</button>
          </div>
        </div>
        <div class="govde-ic ai-screen-expand-body ai-insight-expand-body">
          <div class="ai-insight-body">
            <div class="ai-insight-loading">
              <div class="ai-shimmer-line" style="width: 85%;"></div>
              <div class="ai-shimmer-line" style="width: 70%;"></div>
              <div class="ai-shimmer-line" style="width: 50%;"></div>
            </div>
          </div>
          <div class="ai-insight-footer" style="display: none;">
            <div class="ai-insight-kaynak"></div>
            <div class="ai-insight-actions">
              <button class="dugme dugme-kucuk" type="button" data-screen-ai-action="detay" data-screen="${fmt.esc(screenId)}">🔍 Detaylı İncele</button>
              <button class="dugme dugme-kucuk" type="button" data-screen-ai-action="sor" data-screen="${fmt.esc(screenId)}">💬 Yapay Zekaya Sor</button>
              <button class="dugme dugme-kucuk" type="button" data-screen-ai-action="kokpitte-ac" data-screen="${fmt.esc(screenId)}">✦ Kokpitte Aç</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ✦ 2. KOMPAKT YAPAY ZEKA ASİSTANI -->
      <div class="panel ai-compact-panel" data-screen-ai-assistant="${fmt.esc(screenId)}" data-buyut-tasi="1">
        <div class="panel-baslik">
          <div class="sol">
            <span class="ai-rozet-ik">✦</span>
            <div>
              <h3>Yapay Zeka Asistanı</h3>
              <small>Bu ekran ve kurumsal veriler hakkında soru sorun…</small>
            </div>
          </div>
          <div class="sag">
            <span class="ai-durum-rozet">● Gemini bağlı</span>
            <button class="dugme dugme-kucuk" type="button" data-screen-ai-action="kokpitte-ac" data-screen="${fmt.esc(screenId)}">✦ Kokpitte Aç</button>
            <button class="buyut-dugme" type="button" data-buyut title="Büyüt" aria-label="Yapay zeka asistanını büyüt">⛶</button>
          </div>
        </div>
        <div class="govde-ic ai-screen-expand-body ai-compact-expand-body">
          <div class="ai-compact-body">
            <div class="ai-compact-stream" data-screen-ai-stream="${fmt.esc(screenId)}">
              ${renderCompactStream(screenId)}
            </div>
            <div class="ai-compact-giris-kutu">
              <textarea class="ai-compact-input" rows="1" placeholder="Bu ekran hakkında soru sorun… (Enter: gönder, Shift+Enter: yeni satır)" data-screen-ai-input="${fmt.esc(screenId)}"></textarea>
              <button class="dugme birincil dugme-kucuk" type="button" data-screen-ai-action="gonder" data-screen="${fmt.esc(screenId)}">Gönder</button>
            </div>
          </div>
        </div>
      </div>
    `;

    containerEl.appendChild(wrapper);
  }

  /** Kompakt konuşma akışını çizer */
  function renderCompactStream(screenId) {
    const msgs = _screenAIState.messages.get(screenId) || [];
    if (!msgs.length) {
      return `<div class="ai-compact-bos">Bu ekrandaki göstergeler veya kurum geneli hakkında soru sorabilirsiniz.</div>`;
    }

    return msgs.map(m => `
      <div class="ai-mesaj ${m.rol === 'user' ? 'kullanici' : 'asistan'}">
        <div class="ai-balon">
          <div class="ai-metin">${fmt.esc(m.metin)}</div>
          ${m.grafikler && m.grafikler.length ? m.grafikler.map(g => `<div class="ai-mini-chart">${typeof aiGrafikCiz === 'function' ? aiGrafikCiz(g) : ''}</div>`).join('') : ''}
        </div>
      </div>
    `).join('');
  }

  /** Ekran otomatik yorumunu günceller (debounced / cached / stale-safe) */
  async function refreshScreenAI(screenId) {
    if (!screenId || screenId === "kokpit") return;

    const cardEl = document.querySelector(`[data-screen-ai-card="${screenId}"]`);
    if (!cardEl) return;

    const ctx = getStructuredScreenContext(screenId);
    const fingerprint = getContextFingerprint(ctx);

    // Monotonik istek belirteci (stale response önleyici)
    const token = (_screenAIState.reqTokens.get(screenId) || 0) + 1;
    _screenAIState.reqTokens.set(screenId, token);

    // 1. Önbellekte varsa hemen çiz
    if (_screenAIState.cache.has(fingerprint)) {
      renderInsightCard(cardEl, _screenAIState.cache.get(fingerprint));
      return;
    }

    // 2. Yükleniyor durumu
    const statusEl = cardEl.querySelector(".ai-insight-status");
    const bodyEl = cardEl.querySelector(".ai-insight-body");
    const footerEl = cardEl.querySelector(".ai-insight-footer");

    if (statusEl) statusEl.textContent = "◷ Analiz hazırlanıyor…";
    if (bodyEl) {
      bodyEl.innerHTML = `
        <div class="ai-insight-loading">
          <div class="ai-shimmer-line" style="width: 88%;"></div>
          <div class="ai-shimmer-line" style="width: 72%;"></div>
          <div class="ai-shimmer-line" style="width: 48%;"></div>
        </div>
      `;
    }
    if (footerEl) footerEl.style.display = "none";

    try {
      const resp = await api.post("/api/assistant/screen-insight", {
        screen_context: ctx,
        academic_year: ctx.academic_year,
      });

      // Bayat istek kontrolü: Kullanıcı beklerken filtre değiştirdiyse eski cevabı yoksay!
      if (_screenAIState.reqTokens.get(screenId) !== token) {
        return;
      }

      // Başarılı sonucu önbelleğe al
      _screenAIState.cache.set(fingerprint, resp);
      if (resp.conversation_id) {
        _screenAIState.convIds.set(screenId, resp.conversation_id);
      }
      if (resp.findings && resp.findings[0]) {
        _screenAIState.activeFindings.set(screenId, resp.findings[0].finding);
      }

      renderInsightCard(cardEl, resp);
    } catch (err) {
      if (_screenAIState.reqTokens.get(screenId) !== token) return;

      if (statusEl) statusEl.textContent = "○ Servis çevrimdışı";
      if (bodyEl) {
        bodyEl.innerHTML = `
          <div class="ai-insight-hata">
            Yapay zeka analizi şu anda oluşturulamadı. Ekran verileri normal çalışmaya devam etmektedir.
          </div>
        `;
      }
    }
  }

  /** Otomatik yorum kartının içeriğini doldurur */
  function renderInsightCard(cardEl, data) {
    if (!cardEl || !data) return;

    const statusEl = cardEl.querySelector(".ai-insight-status");
    const bodyEl = cardEl.querySelector(".ai-insight-body");
    const footerEl = cardEl.querySelector(".ai-insight-footer");
    const kaynakEl = cardEl.querySelector(".ai-insight-kaynak");

    if (statusEl) statusEl.textContent = `● Güncel (${data.academic_year || '2025-2026'})`;

    const obsHtml = (data.observations || []).map(o => `<li>${fmt.esc(o)}</li>`).join("");
    const recHtml = (data.recommendations || []).map(r => `
      <div class="ai-rec-box">
        <span class="ai-rec-tag">Tavsiye</span>
        <span class="ai-rec-txt">${fmt.esc(r)}</span>
      </div>
    `).join("");

    if (bodyEl) {
      bodyEl.innerHTML = `
        <ul class="ai-obs-list">${obsHtml}</ul>
        ${recHtml}
      `;
    }

    if (kaynakEl) {
      const kList = (data.data_sources || []).join(" · ");
      const provList = (data.provenance_notes || []).join(" ");
      kaynakEl.innerHTML = `
        <span class="ai-src-txt">Kaynak: ${fmt.esc(kList || 'Kurumsal Kayıtlar')}</span>
        ${provList ? `<span class="ai-prov-txt">ⓘ ${fmt.esc(provList)}</span>` : ''}
      `;
    }

    if (footerEl) footerEl.style.display = "flex";
  }

  /** Kompakt asistandan mesaj gönderimi */
  async function sendCompactMessage(screenId) {
    if (!screenId) return;
    if (_screenAIState.busy.get(screenId)) return;

    const inputEl = document.querySelector(`[data-screen-ai-input="${screenId}"]`);
    const streamEl = document.querySelector(`[data-screen-ai-stream="${screenId}"]`);
    if (!inputEl) return;

    const soru = (inputEl.value || "").trim();
    if (!soru) return;

    inputEl.value = "";
    inputEl.disabled = true;
    _screenAIState.busy.set(screenId, true);

    const msgs = _screenAIState.messages.get(screenId) || [];
    msgs.push({ rol: "user", metin: soru });
    _screenAIState.messages.set(screenId, msgs);

    if (streamEl) {
      streamEl.innerHTML = renderCompactStream(screenId) + `<div class="ai-mesaj asistan"><div class="ai-balon ai-yukleniyor">Yanıt hazırlanıyor…</div></div>`;
      streamEl.scrollTop = streamEl.scrollHeight;
    }

    const ctx = getStructuredScreenContext(screenId);

    try {
      const yanit = await api.post("/api/assistant/chat", {
        message: soru,
        conversation_id: _screenAIState.convIds.get(screenId) || null,
        academic_year: ctx.academic_year,
        screen_context: ctx,
      });

      if (yanit.conversation_id) {
        _screenAIState.convIds.set(screenId, yanit.conversation_id);
      }

      msgs.push({
        rol: "assistant",
        metin: yanit.answer || "Yanıt alınamadı.",
        grafikler: yanit.charts || [],
        kaynaklar: yanit.data_sources || [],
      });
      _screenAIState.messages.set(screenId, msgs);
    } catch (err) {
      msgs.push({
        rol: "assistant",
        metin: (err && (err.userMessage || err.detail || err.message)) || "Yerel yapay zeka servisine ulaşılamıyor.",
      });
      _screenAIState.messages.set(screenId, msgs);
    } finally {
      _screenAIState.busy.set(screenId, false);
      inputEl.disabled = false;
      if (streamEl) {
        streamEl.innerHTML = renderCompactStream(screenId);
        streamEl.scrollTop = streamEl.scrollHeight;
      }
      inputEl.focus();
    }
  }

  /** Kokpite tam geçiş / Handoff */
  function openInCockpit(screenId, initialQuery, activeFinding) {
    const convId = _screenAIState.convIds.get(screenId) || null;
    const msgs = _screenAIState.messages.get(screenId) || [];

    // Ana ASISTAN durumunu güncelle
    if (typeof ASISTAN !== "undefined") {
      if (convId) ASISTAN.konusmaId = convId;
      if (msgs.length) {
        ASISTAN.mesajlar = msgs.map(m => ({
          rol: m.rol,
          metin: m.metin,
          grafikler: m.grafikler || [],
          kaynaklar: m.kaynaklar || [],
        }));
      } else if (activeFinding) {
        ASISTAN.mesajlar = [{
          rol: "assistant",
          metin: `✦ Ekran Değerlendirmesi Bulgusu:\n${activeFinding}`,
          grafikler: [],
          kaynaklar: ["Otomatik Ekran Analizi"],
        }];
      }
    }

    // Kokpit ekranına geç
    K.ekran = "kokpit";
    if (typeof ciz === "function") {
      ciz();
    }

    // Varsa başlangıç sorusunu girişe yaz
    setTimeout(() => {
      const g = document.querySelector("#aiGiris, .ai-giris textarea");
      if (g) {
        if (initialQuery) g.value = initialQuery;
        g.focus();
      }
    }, 50);
  }

  /** Detaylı modal gösterimi */
  function openInsightDetails(screenId) {
    const ctx = getStructuredScreenContext(screenId);
    const fingerprint = getContextFingerprint(ctx);
    const data = _screenAIState.cache.get(fingerprint);
    if (!data) return;

    const obsHtml = (data.observations || []).map(o => `<li>${fmt.esc(o)}</li>`).join("");
    const recHtml = (data.recommendations || []).map(r => `<div class="ai-rec-box"><b>Tavsiye:</b> ${fmt.esc(r)}</div>`).join("");
    const findingsHtml = (data.findings || []).map(f => `
      <div class="ai-evidence-card">
        <h4>${fmt.esc(f.title || 'Bulgu')}</h4>
        <p><b>Bulgu:</b> ${fmt.esc(f.finding)}</p>
        <p><b>Kanıt ve Sayılar:</b> ${fmt.esc(f.evidence)}</p>
        ${f.recommendation ? `<p><b>Öneri:</b> ${fmt.esc(f.recommendation)}</p>` : ''}
      </div>
    `).join("");

    const chartHtml = (data.charts && data.charts.length && typeof aiGrafikCiz === 'function')
      ? data.charts.map(g => aiGrafikCiz(g)).join("")
      : "";

    const govde = `
      <div class="ai-modal-content">
        <div class="ai-modal-section">
          <h3>Kurumsal Gözlemler</h3>
          <ul class="ai-obs-list">${obsHtml}</ul>
        </div>
        ${findingsHtml ? `<div class="ai-modal-section"><h3>Yapılandırılmış Kanıtlar</h3>${findingsHtml}</div>` : ''}
        ${recHtml ? `<div class="ai-modal-section"><h3>Stratejik Öneriler</h3>${recHtml}</div>` : ''}
        ${chartHtml ? `<div class="ai-modal-section"><h3>Destekleyici Görselleştirme</h3>${chartHtml}</div>` : ''}
        <div class="ai-modal-section ai-modal-src">
          <small>Kaynaklar: ${(data.data_sources || []).join(' · ')}</small>
        </div>
      </div>
    `;

    if (typeof grafikModalAc === "function") {
      grafikModalAc(`Yapay Zeka Analiz Detayı — ${data.screen_title || 'Genel Bakış'}`, govde, "");
    }
  }

  // =========================================================================
  // OLAY DELEGASYONU (Tekil Dinleyici — Çift POST ve ID çakışması engellenir)
  // =========================================================================
  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-screen-ai-action]");
    if (!btn) return;

    const action = btn.dataset.screenAiAction;
    const screenId = btn.dataset.screen || K.ekran;

    if (action === "gonder") {
      e.preventDefault();
      sendCompactMessage(screenId);
    } else if (action === "sor") {
      e.preventDefault();
      const inputEl = document.querySelector(`[data-screen-ai-input="${screenId}"]`);
      if (inputEl) {
        inputEl.scrollIntoView({ behavior: "smooth", block: "center" });
        inputEl.placeholder = "Bu bulgu hakkında soru sorun (örn. Neden?, Detaylandır)…";
        inputEl.focus();
      }
    } else if (action === "detay") {
      e.preventDefault();
      openInsightDetails(screenId);
    } else if (action === "kokpitte-ac") {
      e.preventDefault();
      const activeF = _screenAIState.activeFindings.get(screenId);
      openInCockpit(screenId, null, activeF);
    }
  });

  document.addEventListener("keydown", function (e) {
    const inputEl = e.target.closest("[data-screen-ai-input]");
    if (!inputEl) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const screenId = inputEl.dataset.screenAiInput || K.ekran;
      sendCompactMessage(screenId);
    }
  });

  // Dışa aktar
  root.mountScreenAI = mountScreenAI;
  root.refreshScreenAI = refreshScreenAI;
  root.openInCockpit = openInCockpit;

})(typeof window !== "undefined" ? window : globalThis);
