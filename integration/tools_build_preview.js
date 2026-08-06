/**
 * Dinamik analiz panelinin STATİK önizlemesini üretir.
 *
 * Neden: paneli görmek için sunucu ayağa kaldırmak, giriş yapmak, asistana
 * soru sormak ve modelin cevap vermesini beklemek gerekir. Tasarım üzerinde
 * çalışırken bu döngü çok yavaş. Bu script gerçek builder çıktısını (backend
 * testlerinin ürettiği fixture) alıp tek bir HTML dosyasına gömer.
 *
 * Çalıştırma (integration/ dizininden):
 *     node tools_build_preview.js
 *
 * Önce backend testleri çalıştırılmalı; fixture'lar oradan gelir:
 *     python -m pytest backend/tests_integration/test_ui_spec.py
 */
const fs = require("fs");
const path = require("path");

const ASSETS = path.join(__dirname, "frontend", "assets");
const read = (p) => fs.readFileSync(p, "utf8");

const css = read(path.join(ASSETS, "style.css")) + "\n" +
            read(path.join(ASSETS, "integration.css"));
const api = read(path.join(ASSETS, "api.js"));
const renderer = read(path.join(ASSETS, "ai-view-renderer.js"));

const fixtures = path.join(__dirname, "tests_ui", "fixtures");
let spec, structured;
try {
  spec = read(path.join(fixtures, "ui_spec_sample.json"));
  structured = read(path.join(fixtures, "structured_result_sample.json"));
} catch {
  console.error(
    "Ornek dosyalar yok. Once backend testlerini calistirin:\n" +
    "  python -m pytest backend/tests_integration/test_ui_spec.py"
  );
  process.exit(2);
}

const html = `<!doctype html>
<html lang="tr" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dinamik Analiz Paneli — Önizleme</title>
<style>${css}
  body { background: var(--page); color: var(--ink); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 28px; }
  .preview-head { max-width: 1180px; margin: 0 auto 18px; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  .preview-head h1 { font-size: 1.05rem; margin: 0; }
  .preview-head p { margin: 4px 0 0; font-size: .8rem; color: var(--muted); }
  #root { max-width: 1180px; margin: 0 auto; }
  .theme-toggle { border:1px solid var(--border); background:var(--surface); color:var(--ink); border-radius:10px; padding:8px 14px; cursor:pointer; font:inherit; font-size:.8rem; }
</style>
</head>
<body>
<div class="preview-head">
  <div>
    <h1>Dinamik Analiz Paneli — statik önizleme</h1>
    <p>Gerçek builder çıktısıyla (ui_spec 2.0) çizildi. Sunucu gerekmez.</p>
  </div>
  <button class="theme-toggle" onclick="document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'">Aydınlık / Koyu</button>
</div>
<div id="root"></div>
<script>${api}</script>
<script>${renderer}</script>
<script>
  const SPEC = ${spec};
  const STRUCTURED = ${structured};
  document.getElementById("root").innerHTML = aiRenderView(SPEC, STRUCTURED);
  document.querySelector("[data-ai-close]").addEventListener("click", () => {
    alert("Gerçek uygulamada bu düğme paneli kapatır.");
  });
</script>
</body>
</html>`;

const out = path.join(__dirname, "docs", "preview", "analysis_panel_preview.html");
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, html);
console.log("Onizleme yazildi:", out, `(${(html.length / 1024).toFixed(0)} KB)`);
