// Overview views: Executive Dashboard + AI Assistant.

/* ==================== Executive Dashboard ==================== */
VIEWS["dashboard"] = {
  title: "Executive Dashboard",
  subtitle: "Consolidated university-wide view · drill-down to faculties and departments",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Enrollment — 5-year trend</h3>
        <div class="note">Total students across all faculties, including English preparatory programs.</div>
        <div id="trend"></div>
      </div>
      <div class="card">
        <h3>Ranking data readiness</h3>
        <div class="note">Share of THE / QS / YÖK indicator data collected &amp; validated (Module 10).</div>
        <div id="readiness"></div>
        <h4>Strong indicators</h4><ul class="plain" id="strong"></ul>
        <h4>Weak indicators</h4><ul class="plain" id="weak"></ul>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Net revenue vs expenditure by faculty</h3>
        <div class="note">USD millions, after scholarship discounts · 2025–26 projection (Module 6).</div>
        <div class="legend">
          <span><span class="swatch" style="background:var(--primary)"></span>Net revenue</span>
          <span><span class="swatch" style="background:var(--accent)"></span>Expenditure</span>
        </div>
        <div id="facChart"></div>
      </div>
      <div class="card">
        <h3>Critical risks &amp; early warnings</h3>
        <div class="note">Top alerts from the rule engine (Module 11) — 27 active in total.</div>
        <ul class="plain" id="risks"></ul>
      </div>
    </div>
    <div class="card">
      <h3>Drill-down — university → faculty → department</h3>
      <div class="note">Click a faculty row to expand its departments; click again to roll up.</div>
      <div class="table-wrap"><table id="drill">
        <thead><tr><th>Unit</th><th>Students</th><th>Occupancy</th><th>Net revenue</th><th>Expenditure</th><th>Cost / student</th></tr></thead>
        <tbody></tbody>
      </table></div>
    </div>
    <footer class="demo">Design prototype — all figures are mock data derived from the ABU KDS assumptions (≈4,000 students, $20,000 tuition, 15% full + 50% partial + 3% merit scholarships).</footer>`,
  init() {
    tiles("headline", [
      ["Total students", "4,010", "▲ 4.1% vs last year", "up"],
      ["Program occupancy", "84%", "▲ 2 pts vs last year", "up"],
      ["Net revenue", "$34.2M", "gross tuition $80.2M", ""],
      ["Expenditure", "$31.6M", "incl. $13.8M overhead", ""],
      ["Rev–exp balance", "+$2.6M", "▲ surplus", "up"],
      ["Cost / student", "$7,880", "▲ 5.2% vs last year", "down"],
      ["Graduation rate", "81%", "▲ 1.5 pts", "up"],
      ["Seat utilization", "76%", "1,450 seats · 27 rooms + 6 labs", ""],
    ]);
    lineChart("trend", ["2021–22", "2022–23", "2023–24", "2024–25", "2025–26"], [
      { label: "Students", color: "var(--primary)", values: [3390, 3540, 3710, 3852, 4010] },
    ], { min: 3200, max: 4200, yfmt: v => (v / 1000).toFixed(1) + "k" });
    donuts("readiness", [["THE", 65], ["QS", 52, "var(--accent)"], ["YÖK", 64, "#0ca30c"]]);
    $("strong").innerHTML = [
      "Software Eng. occupancy 98.8% — highest in faculty",
      "Graduate employment (Engineering) 84%",
      "Publication output ▲ 18% year-on-year",
    ].map(t => `<li><span class="chip good">✓</span>${t}</li>`).join("");
    $("weak").innerHTML = [
      "Metallurgy program occupancy 27.5%",
      "CE admission score 75 pts below Türkiye average",
      "Research income share 9% (target 15%)",
    ].map(t => `<li><span class="chip critical">▲</span>${t}</li>`).join("");
    hbars("facChart", [
      ["Engineering — revenue", 11.9, "var(--primary)"], ["Engineering — expenditure", 10.8, "var(--accent)"],
      ["Law — revenue", 5.4, "var(--primary)"], ["Law — expenditure", 4.6, "var(--accent)"],
      ["Econ. & Admin. Sci. — revenue", 12.6, "var(--primary)"], ["Econ. & Admin. Sci. — expenditure", 10.9, "var(--accent)"],
      ["Fine Arts & Arch. — revenue", 4.3, "var(--primary)"], ["Fine Arts & Arch. — expenditure", 5.3, "var(--accent)"],
    ], { fmt: v => "$" + v.toFixed(1) + "M" });
    $("risks").innerHTML = [
      ["critical", "Metallurgy Eng. enrollment below 30% threshold"],
      ["critical", "Computer Eng. demand fell 92% → 38% in three years"],
      ["warning", "Fine Arts & Architecture running a $1.0M deficit"],
      ["warning", "Lab utilization above 110% on weekday mornings"],
      ["warning", "MÜDEK accreditation renewals due Oct 2026 (3 programs)"],
    ].map(([lvl, t]) => `<li><span class="chip ${lvl}">${lvl === "critical" ? "▲ Critical" : "! Warning"}</span>${t}
      <a class="push" href="#/alerts" style="font-size:.72rem">view →</a></li>`).join("");

    const DRILL = [
      { name: "University (total)", st: "4,010", occ: "84%", rev: 34.2, exp: 31.6, cps: "$7,880" },
      { name: "Engineering & Architecture", st: "850", occ: "82%", rev: 11.9, exp: 10.8, cps: "$12,700", children: [
        ["Computer Engineering", "265", "78%", 3.9, 3.2, "$12,080"],
        ["Software Engineering", "248", "99%", 3.7, 2.9, "$11,690"],
        ["Electrical-Electronics Eng.", "142", "58%", 2.1, 2.4, "$16,900"],
        ["Industrial Engineering", "195", "80%", 2.2, 2.3, "$11,790"],
      ]},
      { name: "Law", st: "310", occ: "89%", rev: 5.4, exp: 4.6, cps: "$14,840" },
      { name: "Economics, Admin. & Social Sci.", st: "960", occ: "87%", rev: 12.6, exp: 10.9, cps: "$11,350", children: [
        ["Business Administration", "365", "93%", 4.8, 4.0, "$10,960"],
        ["Economics", "260", "82%", 3.4, 3.1, "$11,920"],
        ["Political Science & IR", "335", "85%", 4.4, 3.8, "$11,340"],
      ]},
      { name: "Fine Arts, Design & Architecture", st: "350", occ: "71%", rev: 4.3, exp: 5.3, cps: "$15,140", children: [
        ["Architecture", "150", "83%", 1.9, 2.1, "$14,000"],
        ["Interior Architecture", "118", "72%", 1.5, 1.7, "$14,400"],
        ["Graphic Design", "82", "55%", 0.9, 1.5, "$18,290"],
      ]},
      { name: "English Preparatory School", st: "1,540", occ: "—", rev: 0, exp: 0, cps: "shared" },
    ];
    const tbody = document.querySelector("#drill tbody");
    const open = new Set();
    const render = () => {
      tbody.innerHTML = DRILL.map((f, i) => {
        const has = f.children && f.children.length;
        let html = `<tr data-i="${i}" style="${has ? "cursor:pointer" : ""}${i === 0 ? ";font-weight:600" : ""}">
          <td>${has ? (open.has(i) ? "▾ " : "▸ ") : ""}${f.name}</td><td>${f.st}</td><td>${f.occ}</td>
          <td>${f.rev ? "$" + f.rev.toFixed(1) + "M" : "—"}</td><td>${f.exp ? "$" + f.exp.toFixed(1) + "M" : "—"}</td><td>${f.cps}</td></tr>`;
        if (has && open.has(i)) html += f.children.map(c =>
          `<tr class="sub"><td>${c[0]}</td><td>${c[1]}</td><td>${c[2]}</td><td>$${c[3].toFixed(1)}M</td><td>$${c[4].toFixed(1)}M</td><td>${c[5]}</td></tr>`).join("");
        return html;
      }).join("");
      tbody.querySelectorAll("tr[data-i]").forEach(tr => tr.onclick = () => {
        const i = +tr.dataset.i;
        if (!DRILL[i].children) return;
        open.has(i) ? open.delete(i) : open.add(i);
        render();
      });
    };
    render();
  },
};

/* ==================== AI Assistant ==================== */
const assistantState = { threadHTML: null };

const _factor = (name, pct) => `<div class="factor"><span>${name}</span><div class="track"><div class="fill" style="width:${pct}%"></div></div><span>${pct}%</span></div>`;
const _sources = arr => `<div class="sources">${arr.map(s => `<span class="chip neutral">${s}</span>`).join("")}</div>`;

const ASSISTANT_ANSWERS = [
  {
    q: "Why has the occupancy rate of Computer Engineering declined over the last five years?",
    a: `<b>Computer Engineering occupancy: 92% → 38% (2021–2026)</b>
        The decline is driven by a combination of factors, ranked by estimated contribution:
        ${_factor("Competing new programs in Ankara", 34)}
        ${_factor("Admission score gap (−75 vs TR avg)", 27)}
        ${_factor("Tuition vs scholarship mix", 18)}
        ${_factor("Graduate employment perception", 12)}
        ${_factor("Program marketing reach", 9)}
        Since 2022, four Ankara foundation universities opened CS-adjacent programs with higher full-scholarship
        quotas. ABU's minimum score fell while peers' held steady — the program now competes on price rather than
        selectivity.<ul><li>Recommendation: raise full-scholarship quota for CENG by 10 seats and co-market with
        the strong Software Engineering brand (98.8% occupancy).</li><li>Run scenario 7.4 before considering
        restructuring — the sustainability module suggests strategic support, not closure.</li></ul>
        ${_sources(["YÖK Atlas 2021–26", "Admission scores DB", "Competitor programs", "Sustainability scores"])}`,
  },
  {
    q: "If tuition fees increase 10%, how are revenue, scholarship cost and enrollment affected?",
    a: `<b>Tuition +10% → $22,000 (simulation)</b>
        <ul>
        <li><b>Net revenue:</b> +$2.9M (+8.7%) — scholarship discounts scale with the fee, so net gain is smaller than gross.</li>
        <li><b>Scholarship cost:</b> grows $4.6M in nominal discount value (57% of gross stays constant under YÖK policy).</li>
        <li><b>Enrollment:</b> projected −0% to −2% — $22,000 sits at the edge of the demand-elastic band; above it,
        each $1,000 costs ≈2.5% enrollment.</li>
        </ul>
        Verdict: a 7–8% rise captures most of the revenue with negligible demand risk; 10% is acceptable but
        monitor Computer Eng. and Graphic Design, whose demand is already fragile.
        ${_sources(["Finance module", "3-cycle demand elasticity", "Scenario engine 7.2"])}`,
  },
  {
    q: "Rank the faculties by research performance.",
    a: `<b>Research performance ranking (publications, citations, projects per staff member)</b>
        ${_factor("1. Engineering & Architecture", 86)}
        ${_factor("2. Economics, Admin. & Social Sci.", 61)}
        ${_factor("3. Law", 48)}
        ${_factor("4. Fine Arts, Design & Arch.", 33)}
        Engineering leads on all three components (2.9 pubs/staff, 12 TÜBİTAK + 5 EU projects). Law publishes
        less but holds the highest citation-per-paper ratio. Fine Arts' output is portfolio-based — consider a
        discipline-adjusted metric before comparing directly (the weighting is configurable per department).
        ${_sources(["Staff performance DB", "Publication records 2021–25", "Project portfolio"])}`,
  },
  {
    q: "Which programs should be considered for closure or restructuring?",
    a: `<b>Restructuring shortlist (sustainability scores + early-warning flags)</b>
        <ul>
        <li><b>Metallurgy Eng. (28.2/100):</b> occupancy 27.5%, employment 58%, negative balance → merger candidate
        with Materials track under Mechanical Eng. Scenario 7.4 estimates +$0.6M/yr.</li>
        <li><b>Graphic Design (41.8):</b> demand −21 pts in two cycles → reorganize; share studios with Architecture.</li>
        <li><b>Electrical-Electronics (47.6):</b> highest cost/student ($16.9K) → curriculum consolidation, not closure.</li>
        <li><b>Computer Eng. (55.3):</b> despite low occupancy, strong staff/research → strategic support, NOT closure.</li>
        </ul>
        Reputation note: closures affect sibling-program perception; phased restructuring is lower-risk than
        outright closure in all four cases.
        ${_sources(["Sustainability scores", "Early-warning alerts", "Scenario 7.4 results", "Finance module"])}`,
  },
  {
    q: "Which new academic programs should we open in the next three years?",
    a: `<b>New program opportunities (demand forecast + capacity + break-even)</b>
        <ul>
        <li><b>Data Science &amp; AI BSc</b> — projected 90%+ occupancy at 60-seat quota; breaks even at 47 students;
        reuses CENG/SWE staff (needs +3 hires). Strongest candidate.</li>
        <li><b>Cybersecurity BSc</b> — high demand, but requires 2 new labs → couple with investment scenario 7.6 (ROI 4.3 yrs).</li>
        <li><b>Digital Media Design</b> — could absorb Graphic Design's studio capacity and reverse its decline.</li>
        </ul>
        All three fit current classroom capacity until 2027–28, at which point seat utilization crosses 95% —
        plan the lab investment for the 2027 budget cycle.
        ${_sources(["Demand forecasts", "Capacity model", "Break-even calculator", "Competitor gap analysis"])}`,
  },
];

VIEWS["assistant"] = {
  title: "AI Strategic Decision Support Assistant",
  subtitle: "Natural-language analytics · RAG over internal + competitor data · explainable recommendations",
  html: () => `
    <div class="chat-layout">
      <div>
        <div class="card">
          <h3>Ask about…</h3>
          <div class="note">Example questions from the executive brief.</div>
          <div class="suggest" id="suggest"></div>
        </div>
        <div class="card" style="margin-top:16px">
          <h3>Knowledge sources</h3>
          <div class="pill-row" style="margin-top:8px">
            <span class="chip info">• Internal DSS data</span>
            <span class="chip info">• YÖK Atlas</span>
            <span class="chip info">• Competitor programs</span>
            <span class="chip info">• Historical trends 2020–26</span>
          </div>
          <div class="note" style="margin-top:10px">Retrieval-Augmented Generation: every answer cites the data it used and explains its reasoning (explainable AI).</div>
        </div>
      </div>
      <div class="chat">
        <div class="thread" id="thread"></div>
        <div class="composer">
          <input id="q" placeholder="e.g. Why has Computer Engineering occupancy declined?">
          <button class="primary" id="send">Send</button>
        </div>
      </div>
    </div>
    <footer class="demo">Design prototype — responses are scripted for demonstration; the production module uses a RAG pipeline over the university's databases and competitor data.</footer>`,
  init() {
    const thread = $("thread");
    thread.innerHTML = assistantState.threadHTML ?? `
      <div class="bubble ai"><b>ABU Strategic Assistant</b>
      Good morning. I have this term's data loaded — 4,010 students, 12 programs, 27 active alerts.
      Ask me anything about demand, finances, staffing or rankings, or pick a question on the left.</div>`;
    const save = () => { assistantState.threadHTML = thread.innerHTML; };
    save();

    const bubble = (cls, html) => {
      const d = document.createElement("div");
      d.className = "bubble " + cls;
      d.innerHTML = html;
      thread.appendChild(d);
      thread.scrollTop = thread.scrollHeight;
      return d;
    };
    let busy = false;
    const ask = (q, answerHtml) => {
      if (busy) return;
      busy = true;
      bubble("user", q);
      const t = bubble("ai typing", "Analyzing internal data and competitor benchmarks…");
      setTimeout(() => {
        t.classList.remove("typing");
        t.innerHTML = answerHtml ||
          `<b>ABU Strategic Assistant</b> I don't have a scripted answer for that in this design prototype —
           in the full system this query would run through the RAG pipeline over the DSS databases.
           Try one of the example questions on the left.${_sources(["Design prototype"])}`;
        busy = false;
        save();
        thread.scrollTop = thread.scrollHeight;
      }, 900);
      save();
    };

    ASSISTANT_ANSWERS.forEach(item => {
      const b = document.createElement("button");
      b.textContent = item.q;
      b.onclick = () => ask(item.q, item.a);
      $("suggest").appendChild(b);
    });
    $("send").onclick = () => {
      const v = $("q").value.trim();
      if (!v) return;
      const canned = ASSISTANT_ANSWERS.find(a => a.q.toLowerCase().slice(0, 18) === v.toLowerCase().slice(0, 18));
      $("q").value = "";
      ask(v, canned && canned.a);
    };
    $("q").addEventListener("keydown", e => { if (e.key === "Enter") $("send").click(); });
  },
};
