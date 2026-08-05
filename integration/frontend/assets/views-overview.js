// Akıllı Asistan ekranı.
// Yönetim Panosu artık assets/views-dashboard.js dosyasında; pano yeniden
// tasarlandığında bu dosyada kalması onu 400 satırlık karışık bir dosyaya
// çeviriyordu.

/* ==================================================================
   Akıllı Asistan — altyapı hazır, dil modeli BAĞLI DEĞİL
   ================================================================== */

VIEWS["assistant"] = {
  title: "Akıllı Asistan",
  subtitle: "Doğal dille soru sorma altyapısı · dil modeli henüz bağlı değil",
  html: () => `
    <div class="card">
      <h3>Durum</h3>
      <div id="assistantStatus">${ui.loading("Asistan durumu sorgulanıyor…")}</div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Bu ekran şu anda ne yapıyor?</h3>
        <p class="note">
          Asistan katmanının <b>veri erişimi ve bağlam hazırlama</b> bölümü çalışır durumda.
          Aşağıdaki düğmeye bastığınızda sistem, sorunuza cevap üretmek için hangi
          kurumsal verileri toplayacağını gösterir. Bu veriler gerçek veritabanından okunur.
        </p>
        <p class="note">
          <b>Cevap üretilmez.</b> Bir dil modeli (LLM) bağlı olmadığı için sistem
          uydurma bir cevap yazmaz. Model bağlandığında aynı bağlam modele gönderilecektir.
        </p>
        <label class="f">Örnek soru
          <select id="assistantSample"></select>
        </label>
        <label class="f">Kendi sorunuz
          <input id="assistantQuestion" placeholder="Örn: Hangi programların doluluk oranı düşüyor?">
        </label>
        <button class="primary" id="assistantRun">Bağlamı hazırla</button>
      </div>

      <div class="card">
        <h3>Hazırlanan bağlam</h3>
        <div class="note">Soruya göre toplanan kurumsal veri özeti.</div>
        <div id="assistantContext">${ui.empty("Henüz soru gönderilmedi.")}</div>
      </div>
    </div>

    <div class="card">
      <h3>Model bağlandığında ne olacak?</h3>
      <div id="assistantArchitecture"></div>
    </div>`,

  async init() {
    // Durum bilgisi sunucudan gelir; arayüzde sabit yazmak yerine backend'in
    // gerçek yapılandırmasını göstermek daha dürüst.
    await load(
      "assistantStatus",
      () => api.get("/api/assistant/status"),
      (status, el) => {
        const enabled = status.enabled;
        el.innerHTML = `
          <div class="tiles">
            <div class="tile"><div class="label">Asistan</div>
              <div class="value">${enabled ? "Etkin" : "Devre dışı"}</div>
              <div class="delta ${enabled ? "up" : "down"}">ASSISTANT_ENABLED=${enabled}</div></div>
            <div class="tile"><div class="label">Dil modeli sağlayıcı</div>
              <div class="value">${fmt.esc(status.provider || "seçilmedi")}</div>
              <div class="delta">LLM_PROVIDER</div></div>
            <div class="tile"><div class="label">Model</div>
              <div class="value">${fmt.esc(status.model || "seçilmedi")}</div>
              <div class="delta">LLM_MODEL</div></div>
            <div class="tile"><div class="label">API anahtarı</div>
              <div class="value">${status.api_key_configured ? "tanımlı" : "tanımsız"}</div>
              <div class="delta">kaynak koda yazılmaz</div></div>
          </div>
          <div class="state ${enabled ? "empty" : "warn"}">
            ${fmt.esc(status.message)}
          </div>`;
      }
    );

    // Örnek sorular da sunucudan gelir.
    try {
      const samples = await api.get("/api/assistant/sample-questions");
      const sel = document.getElementById("assistantSample");
      sel.innerHTML =
        `<option value="">— seçiniz —</option>` +
        samples
          .map((s) => `<option value="${fmt.esc(s.question)}">${fmt.esc(s.question)}</option>`)
          .join("");
      sel.addEventListener("change", () => {
        if (sel.value) document.getElementById("assistantQuestion").value = sel.value;
      });
    } catch (err) {
      ui.toast("Örnek sorular alınamadı: " + err.userMessage, "error");
    }

    document.getElementById("assistantRun").addEventListener("click", async () => {
      const question = document.getElementById("assistantQuestion").value.trim();
      if (!question) {
        ui.toast("Önce bir soru yazın veya örneklerden seçin.", "error");
        return;
      }
      await load(
        "assistantContext",
        () => api.post("/api/assistant/prepare-context", { question }),
        (ctx, el) => {
          el.innerHTML = `
            <div class="state warn"><b>Cevap üretilmedi.</b>
              <div class="msg">${fmt.esc(ctx.notice)}</div></div>
            <h4>Sorunun eşleştiği konu</h4>
            <p class="note">${fmt.esc(ctx.matched_topic || "genel")}</p>
            <h4>Toplanan veri (${ctx.context_items.length} başlık)</h4>
            <div class="table-wrap"><table><thead><tr>
              <th>Kaynak modül</th><th>Gösterge</th><th>Değer</th></tr></thead><tbody>
              ${ctx.context_items
                .map(
                  (i) =>
                    `<tr><td>${fmt.esc(i.source_module)}</td><td>${fmt.esc(
                      i.label
                    )}</td><td>${fmt.esc(i.value)}</td></tr>`
                )
                .join("")}
            </tbody></table></div>`;
        }
      );
    });

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
                  `<tr><td><code>${fmt.esc(c.file)}</code></td><td>${fmt.esc(
                    c.responsibility
                  )}</td><td>${chip(
                    c.status === "hazır" ? "good" : "warning",
                    c.status
                  )}</td></tr>`
              )
              .join("")}
          </tbody></table></div>
          <h4>Bağlamak için yapılması gerekenler</h4>
          <ol class="plain">${arch.next_steps
            .map((s) => `<li>${fmt.esc(s)}</li>`)
            .join("")}</ol>`;
      }
    );
  },
};
