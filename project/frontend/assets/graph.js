/* ABÜ KDS — gezinme haritası.
   Tek gezinme aracı budur: ABÜ → fakülte → bölüm → kategori zinciri
   tamamen düğümlere tıklayarak yürütülür. Tablo/panel ancak bir kategori
   seçildiğinde açılır. */

const HARITA = (() => {
  const G = 460, M = G / 2;
  let svg = null;

  const yaricapHesap = n => (n <= 3 ? 128 : n <= 5 ? 146 : n <= 7 ? 158 : 168);

  /* tema şekli: daire · altıgen (siber) · kare (piyasa) · elmas (atölye) */
  function sekilCiz(sekil, cx, cy, r, attr) {
    if (sekil === "altigen") {
      const p = [];
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 180 * (60 * i - 30);
        p.push(`${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`);
      }
      return `<polygon points="${p.join(" ")}" ${attr}/>`;
    }
    if (sekil === "kare")
      return `<rect x="${(cx - r).toFixed(1)}" y="${(cy - r).toFixed(1)}" width="${(2 * r).toFixed(1)}"
        height="${(2 * r).toFixed(1)}" rx="${(r * .2).toFixed(1)}" ${attr}/>`;
    if (sekil === "elmas") {
      const p = [[cx, cy - r], [cx + r * .92, cy], [cx, cy + r], [cx - r * .92, cy]]
        .map(q => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
      return `<polygon points="${p}" ${attr}/>`;
    }
    return `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" ${attr}/>`;
  }

  function boyut(u, maks, kategoriMi) {
    if (kategoriMi) return 30;
    const oran = maks ? Math.sqrt((u.deger || 0) / maks) : 0;
    return 22 + oran * 26;
  }

  /* merkez: {kisa, ad, renk, altYazi}
     uydular: [{id, kisa, ad, deger, altYazi, renk, tur, aktif, ikon}]
     tur: "birim" | "kategori" | "analiz" | "geri"                          */
  function ciz(merkez, uydular, tikla, tema = {}) {
    const n = uydular.length || 1;
    const R = yaricapHesap(n);
    const sekil = tema.sekil || "daire";
    const maks = Math.max(...uydular.map(u => u.deger || 0), 1);
    let bag = "", dugum = "";

    uydular.forEach((u, i) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
      const x = M + Math.cos(a) * R, y = M + Math.sin(a) * R;
      const r = boyut(u, maks, u.tur !== "birim");
      const gecikme = (i * 45);

      bag += `<line class="bag" x1="${M}" y1="${M}" x2="${x}" y2="${y}"
        stroke="${u.renk}" stroke-width="${u.tur === "birim" ? (1 + (u.deger / maks) * 2.4).toFixed(2) : 1.4}"
        opacity="0" stroke-linecap="round" stroke-dasharray="4 4"
        style="animation: bagAc .5s ${gecikme}ms forwards"/>`;

      const aktif = u.aktif ? ' aktif' : '';
      dugum += `<g class="dugum ${u.tur}${aktif}" data-id="${u.id}" data-tur="${u.tur}"
                   style="animation: dugumAc .45s ${gecikme + 60}ms backwards cubic-bezier(.34,1.4,.64,1)">
        ${sekilCiz(sekil, x, y, r + 7, `class="halka" fill="none"
          stroke="${u.renk}" stroke-width="${u.aktif ? 2 : 1}" opacity="${u.aktif ? .85 : .22}"`)}
        ${sekilCiz(sekil, x, y, r, `class="govde"
          fill="${u.renk}" fill-opacity="${u.aktif ? .38 : .20}"
          stroke="${u.renk}" stroke-width="${u.aktif ? 2.4 : 1.8}"`)}
        ${u.ikon
          ? `<text class="ikon" x="${x}" y="${y + 5}" text-anchor="middle" style="font-size:16px">${u.ikon}</text>`
          : `<text class="ad" x="${x}" y="${y + 1}" text-anchor="middle"
               style="font-size:${u.kisa.length > 6 ? 9.5 : 11.5}px">${u.kisa}</text>
             <text class="deger" x="${x}" y="${y + 13}" text-anchor="middle">${fmtSayi(u.deger || 0)}</text>`}
        <text class="etiket" x="${x}" y="${y + r + 15}" text-anchor="middle">${u.altYazi || u.ad}</text>
        ${u.rozet ? `<circle cx="${x + r * .72}" cy="${y - r * .72}" r="5"
            fill="${u.rozet}" stroke="var(--bg)" stroke-width="1.6" style="pointer-events:all">
            <title>Doluluk oranı: ${u.rozetMetin || ""}</title></circle>` : ""}
      </g>`;
    });

    const mr = 46;
    const desen = tema.desen && DESENLER[tema.desen] ? DESENLER[tema.desen] : "";
    svg.innerHTML = `
      <defs>
        <radialGradient id="grMerkez">
          <stop offset="0%" stop-color="${merkez.renk}" stop-opacity=".45"/>
          <stop offset="100%" stop-color="${merkez.renk}" stop-opacity=".10"/>
        </radialGradient>
        ${desen}
      </defs>
      ${desen ? `<rect x="0" y="0" width="${G}" height="${G}" fill="url(#dsn)" class="desen"/>` : ""}
      ${bag}
      <g class="dugum merkez" data-tur="merkez">
        ${sekilCiz(sekil, M, M, mr + 16, `fill="none" stroke="${merkez.renk}" stroke-width="1" opacity=".16" class="nabiz"`)}
        ${sekilCiz(sekil, M, M, mr + 8, `class="halka" fill="none" stroke="${merkez.renk}" stroke-width="1.5" opacity=".32"`)}
        ${sekilCiz(sekil, M, M, mr, `class="govde" fill="url(#grMerkez)" stroke="${merkez.renk}" stroke-width="2.4"`)}
        <text class="ad" x="${M}" y="${M - 2}" text-anchor="middle"
          style="font-size:${merkez.kisa.length > 8 ? 11 : 15}px;font-weight:800">${merkez.kisa}</text>
        <text class="deger" x="${M}" y="${M + 14}" text-anchor="middle">${merkez.altYazi}</text>
      </g>
      ${dugum}`;

    svg.querySelectorAll(".dugum[data-id]").forEach(el =>
      el.addEventListener("click", () => tikla(el.dataset.id, el.dataset.tur)));
  }

  return {
    baslat(el) {
      svg = el;
      svg.setAttribute("viewBox", `0 0 ${G} ${G}`);
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    },
    ciz,
  };
})();
