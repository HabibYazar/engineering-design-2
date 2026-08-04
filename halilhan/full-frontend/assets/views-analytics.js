// Analytics views: Students, Staff, Physical, Finance, Sustainability, KPIs, Rankings.

/* ==================== Student Analytics ==================== */
VIEWS["students"] = {
  title: "Student Analytics",
  subtitle: "Strategic education &amp; student indicators · YÖK Atlas comparisons · Excel-fed data",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Program occupancy — 2025–26</h3>
        <div class="note">Enrollment ÷ YÖK quota per program (Engineering faculty shown).</div>
        <div id="occ"></div>
      </div>
      <div class="card">
        <h3>Student demand trend</h3>
        <div class="note">Occupancy over the last 3 admission cycles — Computer Eng. decline flagged by early warning.</div>
        <div class="legend">
          <span><span class="swatch" style="background:var(--primary)"></span>Software Eng.</span>
          <span><span class="swatch" style="background:var(--accent)"></span>Computer Eng.</span>
          <span><span class="swatch" style="background:#8b93a1"></span>Electrical-Electronics</span>
        </div>
        <div id="demand"></div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Admission score benchmark</h3>
        <div class="note">Minimum admission scores vs Ankara foundation universities and Türkiye average (YÖK Atlas).</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Program</th><th>ABU</th><th>Full scholarship</th><th>Ankara avg</th><th>Türkiye avg</th><th>Gap</th></tr></thead>
          <tbody>
            <tr><td>Computer Engineering</td><td>412</td><td>489</td><td>465</td><td>487</td><td class="neg">−75</td></tr>
            <tr><td>Software Engineering</td><td>438</td><td>495</td><td>452</td><td>468</td><td class="neg">−30</td></tr>
            <tr><td>Electrical-Electronics</td><td>396</td><td>471</td><td>441</td><td>455</td><td class="neg">−59</td></tr>
            <tr><td>Industrial Engineering</td><td>405</td><td>468</td><td>428</td><td>442</td><td class="neg">−37</td></tr>
            <tr><td>Law</td><td>489</td><td>521</td><td>476</td><td>481</td><td class="pos">+8</td></tr>
          </tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Student body composition</h3>
        <div class="note">Scholarship structure per YÖK policy and internationalization.</div>
        <div id="mix"></div>
        <h4>Cohort distribution (university-wide)</h4>
        <div id="cohorts"></div>
      </div>
    </div>
    <div class="card">
      <h3>Program overview</h3>
      <div class="note">Combined indicators per program — graduation, attrition, employment (Modules 2–3 feed).</div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Program</th><th>Students</th><th>Quota</th><th>Occupancy</th><th>Graduation rate</th>
          <th>Avg time to degree</th><th>Attrition</th><th>Employment (12 mo)</th><th>Status</th>
        </tr></thead>
        <tbody id="progRows"></tbody>
      </table></div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the student-analytics endpoints (overview, programs, admission-scores, demand-trends, comparative) once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Total students", "4,010", "incl. 1,540 in Eng. prep", ""],
      ["New enrollment", "1,082", "▲ 6.5% vs last cycle", "up"],
      ["Graduates (2024–25)", "612", "", ""],
      ["Avg time to degree", "4.5 yrs", "target 4.2", ""],
      ["Attrition rate", "7.8%", "▼ 0.4 pts", "up"],
      ["International students", "13%", "target 15%", ""],
      ["Scholarship students", "68%", "15% full · 50% partial · 3% merit", ""],
      ["Graduate employment", "77%", "within 12 months", ""],
    ]);
    hbars("occ", [
      ["Software Eng.", 98.8], ["Business Admin.", 93.4], ["Law", 89.2],
      ["Industrial Eng.", 80.1], ["Computer Eng.", 78.3], ["Architecture", 76.5],
      ["Electrical-Electronics", 58.4], ["Graphic Design", 55.0], ["Metallurgy Eng.", 27.5, "var(--critical)"],
    ], { max: 100, fmt: v => v.toFixed(1) + "%" });
    lineChart("demand", ["2023–24", "2024–25", "2025–26"], [
      { label: "Software Eng.", color: "var(--primary)", values: [88, 95, 99] },
      { label: "Computer Eng.", color: "var(--accent)", values: [92, 61, 38] },
      { label: "Electrical-Electronics", color: "#8b93a1", values: [66, 61, 58] },
    ], { min: 20, max: 105, yfmt: v => Math.round(v) + "%" });
    hbars("mix", [
      ["Full scholarship (15%)", 602], ["Partial 50% (YÖK)", 3288, "var(--accent)"],
      ["Merit ≥3.90 GPA (3%)", 120, "#8b93a1"], ["International", 521, "#0ca30c"],
    ], { fmt: v => v.toLocaleString("en-US") });
    hbars("cohorts", [
      ["English prep", 400], ["1st year", 570], ["2nd year", 630], ["3rd year", 468], ["4th year", 402],
    ], { fmt: v => v.toLocaleString("en-US") });
    $("progRows").innerHTML = [
      ["Software Engineering", 248, 60, "98.8%", "86%", "4.1", "4.2%", "84%", ["good", "Healthy"]],
      ["Business Administration", 365, 95, "93.4%", "82%", "4.3", "6.1%", "76%", ["good", "Healthy"]],
      ["Law", 310, 85, "89.2%", "88%", "4.4", "3.9%", "81%", ["good", "Healthy"]],
      ["Industrial Engineering", 195, 60, "80.1%", "79%", "4.5", "7.4%", "78%", ["good", "Healthy"]],
      ["Computer Engineering", 265, 80, "78.3%", "81%", "4.6", "8.8%", "84%", ["warning", "Demand falling"]],
      ["Electrical-Electronics Eng.", 142, 60, "58.4%", "74%", "4.9", "10.2%", "72%", ["warning", "Low occupancy"]],
      ["Graphic Design", 82, 40, "55.0%", "71%", "4.7", "11.5%", "63%", ["warning", "Low occupancy"]],
      ["Metallurgy Engineering", 33, 30, "27.5%", "65%", "5.2", "16.3%", "58%", ["critical", "At risk"]],
    ].map(r => `<tr>
      <td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td>
      <td>${r[5]} yrs</td><td>${r[6]}</td><td>${r[7]}</td><td style="text-align:left">${chip(r[8][0], r[8][1])}</td></tr>`).join("");
  },
};

/* ==================== Academic Staff ==================== */
VIEWS["staff"] = {
  title: "Academic Staff Performance",
  subtitle: "Teaching load · publications · research projects · configurable indicator weights",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Performance ranking</h3>
        <div class="note">Composite score from publications, citations, projects and teaching — weights configurable per department.</div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Staff member</th><th>Dept</th><th>Publications</th><th>Citations</th>
            <th>Projects</th><th>Load (req / actual)</th><th>Survey</th><th>Score</th>
          </tr></thead>
          <tbody id="staffRows"></tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Indicator weights</h3>
        <div class="note">Strategic priorities per department — editable by management (mock).</div>
        <div id="weights"></div>
        <h4>Rank distribution</h4>
        <div id="ranks"></div>
        <div class="callout" style="margin-top:12px">
          Faculty of Engineering staffing: 7 · 6 · 6 · 7 across departments + 6 assistants.
          Salary assumptions: Prof $3,000 · Assoc $2,600 · Asst Prof $2,200 · TA $2,000 / month.
        </div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Publication output — annual trend</h3>
        <div class="legend">
          <span><span class="swatch" style="background:var(--primary)"></span>Indexed publications</span>
          <span><span class="swatch" style="background:var(--accent)"></span>Research projects (TÜBİTAK + BAP + EU)</span>
        </div>
        <div id="pubTrend"></div>
      </div>
      <div class="card">
        <h3>Teaching load balance</h3>
        <div class="note">Required weekly hours vs actual — overload triggers extra-teaching payments (Module 6 cost link).</div>
        <div id="load"></div>
        <div class="callout warn">4 staff members exceed 140% of required load — flagged to the staffing scenario (7.5).</div>
      </div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the staff / ranking endpoints and the scoring service once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Academic staff", "63", "+ 21 teaching assistants", ""],
      ["Professors", "6", "", ""],
      ["Associate professors", "9", "", ""],
      ["Assistant professors", "48", "", ""],
      ["Avg publications / staff", "2.4", "▲ 18% YoY", "up"],
      ["Active research projects", "31", "12 TÜBİTAK · 14 BAP · 5 EU", ""],
      ["Avg course survey", "4.1 / 5", "univ. average 3.9", "up"],
      ["Monthly payroll", "$198K", "incl. assistants", ""],
    ]);
    $("staffRows").innerHTML = [
      ["Prof. L. Demirel", "CENG", 9, 214, "3 (2 TÜBİTAK)", "12 / 14", 4.4, 89],
      ["Assoc. Prof. S. Karaca", "SWE", 7, 168, "2 (1 EU)", "14 / 16", 4.5, 82],
      ["Prof. N. Yıldız", "EE", 8, 190, "2 (1 TÜBİTAK)", "10 / 10", 3.8, 78],
      ["Asst. Prof. B. Şahin", "SWE", 6, 121, "2 (BAP)", "16 / 21", 4.6, 71],
      ["Assoc. Prof. T. Aydın", "IE", 5, 96, "1 (BAP)", "14 / 15", 4.2, 63],
      ["Asst. Prof. G. Öztürk", "CENG", 4, 73, "1 (BAP)", "16 / 18", 4.0, 52],
      ["Asst. Prof. D. Acar", "EE", 2, 41, "—", "16 / 12", 3.6, 31],
    ].map(r => `<tr>
      <td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td style="text-align:left">${r[4]}</td>
      <td>${r[5]}</td><td>${r[6]}</td><td><b>${r[7]}</b></td></tr>`).join("");
    hbars("weights", [
      ["Publications", 30], ["Citations", 20], ["Research projects", 20],
      ["Teaching & surveys", 20], ["Admin duties", 10],
    ], { max: 40, fmt: v => v + "%" });
    hbars("ranks", [
      ["Asst. Professors", 48], ["Teaching assistants", 21, "#8b93a1"],
      ["Assoc. Professors", 9, "var(--accent)"], ["Professors", 6, "#0ca30c"],
    ], { fmt: v => v });
    lineChart("pubTrend", ["2021", "2022", "2023", "2024", "2025"], [
      { label: "Publications", color: "var(--primary)", values: [96, 104, 118, 128, 151] },
      { label: "Projects", color: "var(--accent)", values: [17, 19, 22, 26, 31] },
    ], { min: 0, max: 170 });
    hbars("load", [
      ["Within load (≤100%)", 34], ["Moderate overload (100–140%)", 25, "var(--warning)"],
      ["High overload (>140%)", 4, "var(--critical)"],
    ], { fmt: v => v + " staff" });
  },
};

/* ==================== Physical Resources ==================== */
VIEWS["physical"] = {
  title: "Physical Resources &amp; Capacity",
  subtitle: "Classrooms · laboratories · offices · shared spaces — 20,000 m² campus",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Classroom occupancy by room type</h3>
        <div class="note">Average weekly scheduled hours ÷ available hours.</div>
        <div id="rooms"></div>
        <h4>Space allocation</h4>
        <div id="space"></div>
      </div>
      <div class="card">
        <h3>Utilization heat — weekday × time band</h3>
        <div class="note">Share of rooms in use; mornings run over capacity, late afternoons sit idle.</div>
        <div class="table-wrap"><table>
          <thead><tr><th></th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th></tr></thead>
          <tbody id="heat"></tbody>
        </table></div>
        <div class="callout warn" style="margin-top:12px">
          6 × 30-seat labs at 118% demand in morning bands — flagged to the Investment scenario (7.6).
        </div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Under / over-utilized facilities</h3>
        <ul class="plain" id="flags"></ul>
      </div>
      <div class="card">
        <h3>Capacity forecast</h3>
        <div class="note">Seats required vs available under the current enrollment trend (+4%/yr).</div>
        <div class="legend">
          <span><span class="swatch" style="background:var(--primary)"></span>Seats required</span>
          <span><span class="swatch" style="background:#8b93a1"></span>Seats available (1,450)</span>
        </div>
        <div id="forecast"></div>
      </div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the classrooms / capacity endpoints once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Campus area", "20,000 m²", "8,000 shared · 3,500 admin", ""],
      ["Classrooms", "27", "8×70 · 7×50 · 12×30 seats", ""],
      ["Laboratories", "6", "30 seats each", ""],
      ["Total teaching seats", "1,450", "", ""],
      ["Avg classroom occupancy", "76%", "▲ 3 pts vs last year", ""],
      ["Lab utilization", "94%", "118% in morning bands", "down"],
      ["Space / student", "5.0 m²", "excl. shared areas", ""],
      ["Idle capacity (Fri pm)", "41%", "consolidation candidate", ""],
    ]);
    hbars("rooms", [
      ["70-seat classrooms (8)", 81], ["50-seat classrooms (7)", 74],
      ["30-seat classrooms (12)", 69], ["Laboratories (6)", 94, "var(--warning)"],
      ["Conference halls", 48, "#8b93a1"],
    ], { max: 100, fmt: v => v + "%" });
    hbars("space", [
      ["Teaching areas", 8500], ["Shared / common", 8000, "#8b93a1"],
      ["Administrative", 3500, "var(--accent)"],
    ], { fmt: v => v.toLocaleString("en-US") + " m²" });
    $("heat").innerHTML = [
      ["09–12", [96, 92, 98, 94, 88]],
      ["12–15", [84, 81, 86, 82, 74]],
      ["15–18", [62, 66, 64, 58, 41]],
    ].map(([band, vals]) => `<tr><td>${band}</td>` + vals.map(v => {
      const bg = v > 90 ? "var(--critical-soft)" : v > 70 ? "var(--warning-soft)" : "var(--good-soft)";
      return `<td style="background:${bg}">${v}%</td>`;
    }).join("") + "</tr>").join("");
    $("flags").innerHTML = [
      ["critical", "Labs 1–4 (30 seats)", "118% morning demand — sessions turned away"],
      ["warning", "Classroom C-204 (70 seats)", "avg 23 students/session — oversized allocation"],
      ["warning", "Graphic Design studio", "34% utilization — share with Architecture?"],
      ["good", "50-seat block B", "balanced 74% across all bands"],
    ].map(([lvl, name, txt]) => `<li>${chip(lvl, name)}<span>${txt}</span></li>`).join("");
    lineChart("forecast", ["2025–26", "2026–27", "2027–28", "2028–29"], [
      { label: "Required", color: "var(--primary)", values: [1310, 1365, 1420, 1478] },
      { label: "Available", color: "#8b93a1", values: [1450, 1450, 1450, 1450] },
    ], { min: 1200, max: 1550 });
  },
};

/* ==================== Financial Analysis ==================== */
VIEWS["finance"] = {
  title: "Strategic Financial Analysis",
  subtitle: "Revenue · expenditure · per-student economics · tuition optimization (USD)",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Revenue by source</h3>
        <div class="note">Net of scholarship discounts (15% full + 3% merit pay $0; remaining pay 50% of $20,000).</div>
        <div id="rev"></div>
      </div>
      <div class="card">
        <h3>Expenditure by category</h3>
        <div class="note">Per the ABU cost structure — includes internal / external overload teaching and publication incentives.</div>
        <div id="exp"></div>
      </div>
    </div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Financial status by faculty</h3>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Faculty</th><th>Students</th><th>Net revenue</th><th>Expenditure</th>
            <th>Balance</th><th>Revenue / student</th><th>Cost / student</th><th>Status</th>
          </tr></thead>
          <tbody id="facRows"></tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Tuition optimization</h3>
        <div class="note">Annual fee recommendation engine (mock output).</div>
        <div class="callout">
          <b>Recommended 2026–27 fee: $21,500 (+7.5%)</b><br>
          Demand elasticity permits +7–9% before projected occupancy drops below 80%.
          Estimated net revenue impact: <b>+$2.4M</b>.
        </div>
        <h4>Key ratios</h4>
        <dl class="kv">
          <dt>Personnel / total expenditure</dt><dd>38%</dd>
          <dt>Scholarship discount / gross tuition</dt><dd>57%</dd>
          <dt>Research income share</dt><dd>9.0%</dd>
          <dt>Overhead / total expenditure</dt><dd>44%</dd>
          <dt>Cost per graduate</dt><dd>$51,600</dd>
          <dt>Break-even students (univ.)</dt><dd>3,705</dd>
        </dl>
        <h4>Program actions suggested</h4>
        <div class="pill-row">
          <span class="chip good">✓ Strengthen · SWE</span>
          <span class="chip info">• Expand · Business</span>
          <span class="chip warning">! Reorganize · EE</span>
          <span class="chip critical">▲ Merge · Metallurgy</span>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>Revenue vs expenditure — 4-year trend</h3>
      <div class="legend">
        <span><span class="swatch" style="background:var(--primary)"></span>Net revenue</span>
        <span><span class="swatch" style="background:var(--accent)"></span>Expenditure</span>
      </div>
      <div id="finTrend"></div>
    </div>
    <footer class="demo">Design prototype — mock data using ABU assumptions ($20,000 tuition, $1.15M/month overhead, USD salary scale).</footer>`,
  init() {
    tiles("headline", [
      ["Gross tuition", "$80.2M", "4,010 × $20,000", ""],
      ["Scholarship discounts", "−$46.0M", "57% of gross", ""],
      ["Net revenue", "$34.2M", "incl. non-tuition income", ""],
      ["Total expenditure", "$31.6M", "", ""],
      ["Balance", "+$2.6M", "▲ surplus", "up"],
      ["Revenue / student", "$8,530", "", ""],
      ["Cost / student", "$7,880", "▲ 5.2% YoY", "down"],
      ["Cost / graduate", "$51,600", "", ""],
    ]);
    hbars("rev", [
      ["Tuition (net of scholarships)", 30.8], ["Research project revenues", 1.6],
      ["Certificate & continuing ed.", 0.9], ["Other operational", 0.9],
    ], { fmt: v => "$" + v.toFixed(1) + "M" });
    hbars("exp", [
      ["Indirect (overhead) costs", 13.8, "var(--accent)"], ["Academic staff salaries", 8.6, "var(--accent)"],
      ["Internal overload teaching", 1.4, "var(--accent)"], ["External adjunct teaching", 1.1, "var(--accent)"],
      ["R&D incl. BAP projects", 1.9, "var(--accent)"], ["Publication incentives", 0.6, "var(--accent)"],
      ["Technology & laboratory", 1.7, "var(--accent)"], ["Capital investment", 1.6, "var(--accent)"],
      ["Scholarship admin & other", 0.9, "var(--accent)"],
    ], { fmt: v => "$" + v.toFixed(1) + "M" });
    $("facRows").innerHTML = [
      ["Engineering & Architecture", "850", 11.9, 10.8, "$14,000", "$12,700", ["good", "Surplus"]],
      ["Law", "310", 5.4, 4.6, "$17,420", "$14,840", ["good", "Surplus"]],
      ["Economics, Admin. & Social Sci.", "960", 12.6, 10.9, "$13,130", "$11,350", ["good", "Surplus"]],
      ["Fine Arts, Design & Architecture", "350", 4.3, 5.3, "$12,290", "$15,140", ["critical", "Deficit"]],
    ].map(r => {
      const bal = r[2] - r[3];
      return `<tr><td>${r[0]}</td><td>${r[1]}</td><td>$${r[2].toFixed(1)}M</td><td>$${r[3].toFixed(1)}M</td>
        <td class="${bal >= 0 ? "pos" : "neg"}">${bal >= 0 ? "+" : "−"}$${Math.abs(bal).toFixed(1)}M</td>
        <td>${r[4]}</td><td>${r[5]}</td><td style="text-align:left">${chip(r[6][0], r[6][1])}</td></tr>`;
    }).join("");
    lineChart("finTrend", ["2022–23", "2023–24", "2024–25", "2025–26"], [
      { label: "Net revenue", color: "var(--primary)", values: [27.4, 29.8, 31.9, 34.2] },
      { label: "Expenditure", color: "var(--accent)", values: [26.9, 28.7, 30.4, 31.6] },
    ], { min: 24, max: 37, yfmt: v => "$" + v.toFixed(0) + "M" });
  },
};

/* ==================== Program Sustainability ==================== */
VIEWS["sustainability"] = {
  title: "Program Sustainability",
  subtitle: "Multi-criteria weighted scoring · ABU 4-category classification",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Sustainability scores by program</h3>
        <div class="note">11-criteria weighted score (0–100) with data completeness — criteria missing from other modules are re-normalized, never invented.</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Program</th><th>Score</th><th>Data completeness</th><th>Trend</th><th>Category (ABU)</th></tr></thead>
          <tbody id="scoreRows"></tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Criteria &amp; weights</h3>
        <div class="note">Configurable by management; re-normalized over available criteria.</div>
        <div id="criteria"></div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>ABU classification</h3>
        <div class="note">The four action categories from the ABU KDS brief.</div>
        <ul class="plain">
          <li><span class="chip good">✓ Strengthen</span>Software Eng. · Law · Business Admin.</li>
          <li><span class="chip info">• Expand</span>Political Science &amp; IR · Industrial Eng.</li>
          <li><span class="chip warning">! Reorganize</span>Computer Eng. · Electrical-Electronics · Graphic Design</li>
          <li><span class="chip critical">▲ Consolidate / merge</span>Metallurgy Eng.</li>
        </ul>
      </div>
      <div class="card">
        <h3>Cross-module effect</h3>
        <div class="note">When staff-quality and research inputs arrive from Modules 4–5, scores are re-evaluated.</div>
        <div class="callout">
          <b>Computer Engineering — external inputs applied</b><br>
          Score 34.7 → <b>55.3</b> · data completeness 40% → 87% · category changes from
          "Reorganize" to <b>"Strategic institutional support"</b>. Low occupancy is a demand problem,
          not a quality problem — staff and research indicators are strong.
        </div>
        <h4>What drives the low scores</h4>
        <ul class="plain">
          <li><span class="chip critical">▲</span>Metallurgy: occupancy 27.5%, employment 58%, negative balance</li>
          <li><span class="chip warning">!</span>Graphic Design: demand trend −21 pts in two cycles</li>
          <li><span class="chip warning">!</span>EE: cost/student $16,900 — highest in faculty</li>
        </ul>
      </div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the program-sustainability endpoints (weights, scores, categories) once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Programs scored", "12", "", ""],
      ["Strengthen", "3", "", ""],
      ["Expand", "2", "", ""],
      ["Reorganize", "3", "", ""],
      ["Consolidate / merge", "1", "", ""],
      ["Avg data completeness", "71%", "8 of 11 criteria external", ""],
    ]);
    $("scoreRows").innerHTML = [
      ["Software Engineering", 85.2, 87, "▲", ["good", "Strengthen"]],
      ["Law", 79.8, 82, "▲", ["good", "Strengthen"]],
      ["Business Administration", 76.4, 84, "▲", ["good", "Strengthen"]],
      ["Political Science & IR", 68.9, 76, "▲", ["info", "Expand"]],
      ["Industrial Engineering", 64.2, 79, "→", ["info", "Expand"]],
      ["Computer Engineering", 55.3, 87, "▼", ["warning", "Reorganize"]],
      ["Electrical-Electronics Eng.", 47.6, 73, "▼", ["warning", "Reorganize"]],
      ["Graphic Design", 41.8, 64, "▼", ["warning", "Reorganize"]],
      ["Metallurgy Engineering", 28.2, 69, "▼", ["critical", "Merge"]],
    ].map(r => `<tr>
      <td>${r[0]}</td><td><b>${r[1].toFixed(1)}</b></td>
      <td>${r[2]}%</td><td>${r[3]}</td><td style="text-align:left">${chip(r[4][0], r[4][1])}</td></tr>`).join("");
    hbars("criteria", [
      ["Student demand", 14], ["Occupancy rate", 12], ["Graduation rate", 10],
      ["Graduate employability", 10], ["Staff quality", 10], ["Research performance", 10],
      ["Revenue–expenditure balance", 10], ["Physical resource needs", 8],
      ["Strategic contribution", 6], ["Regional contribution", 5], ["Reputation & brand", 5],
    ], { max: 16, fmt: v => v + "%" });
  },
};

/* ==================== Performance & KPIs ==================== */
const KPI_DATA = [
  ["Course evaluation score (/5)", "Education & Teaching", "4.1", "4.3", "4.0", 95, ["good", "On Track"]],
  ["Graduation rate", "Education & Teaching", "81%", "85%", "79%", 95, ["warning", "Delayed"]],
  ["Publications per faculty member", "Research & Development", "2.4", "3.0", "2.0", 80, ["warning", "Delayed"]],
  ["External research funding", "Research & Development", "$3.1M", "$4.0M", "$2.4M", 78, ["warning", "Delayed"]],
  ["Budget realization", "Financial Sustainability", "96%", "100%", "91%", 96, ["good", "On Track"]],
  ["Research income share", "Financial Sustainability", "9.0%", "15%", "8.1%", 60, ["critical", "At Risk"]],
  ["Faculty positions filled", "Human Resources", "91%", "95%", "88%", 96, ["good", "On Track"]],
  ["International student ratio", "Internationalization", "13%", "18%", "12%", 72, ["critical", "At Risk"]],
  ["International partnerships", "Internationalization", "34", "40", "29", 85, ["good", "On Track"]],
  ["Outreach events / year", "Community Engagement", "58", "50", "41", 116, ["good", "On Track"]],
  ["Graduate employment (12 mo)", "Student Success", "77%", "85%", "74%", 91, ["warning", "Delayed"]],
  ["Industry-funded projects", "Univ.–Industry", "21", "30", "19", 70, ["critical", "At Risk"]],
  ["Accredited programs", "Quality Assurance", "64%", "75%", "60%", 85, ["warning", "Delayed"]],
  ["Lab modernization progress", "Infrastructure", "45%", "60%", "30%", 75, ["warning", "Delayed"]],
];

VIEWS["kpi"] = {
  title: "Performance &amp; KPIs",
  subtitle: "Strategic objectives · targets · achievement rates · risk status",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="card">
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:12px">
        <label class="f" style="flex:none;min-width:230px">Strategic dimension
          <select id="dimFilter"><option value="">All dimensions</option></select>
        </label>
        <label class="f" style="flex:none;min-width:150px">Status
          <select id="statusFilter"><option value="">All</option><option>On Track</option><option>Delayed</option><option>At Risk</option></select>
        </label>
        <span class="note" style="margin:0">Statuses derive from achievement vs per-KPI configurable thresholds — computed, never stored.</span>
      </div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>KPI</th><th>Current</th><th>Target</th><th>Prev. year</th><th style="width:220px">Achievement</th><th>Status</th>
        </tr></thead>
        <tbody id="kpiRows"></tbody>
      </table></div>
    </div>
    <div class="grid cols-2">
      <div class="card"><h3>Objectives by status</h3><div id="statusBars"></div></div>
      <div class="card">
        <h3>Recommended corrective actions</h3>
        <ul class="plain">
          <li><span class="chip critical">▲</span>International ratio: open English-taught sections; target 3 recruitment markets</li>
          <li><span class="chip critical">▲</span>Research income: submit 6 TÜBİTAK / EU applications this cycle</li>
          <li><span class="chip warning">!</span>Graduation rate: expand year-1/2 academic advising</li>
          <li><span class="chip warning">!</span>Employment: extend career-center partnerships beyond engineering</li>
        </ul>
      </div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the KPI monitoring backend (Part 8) once integrated.</footer>`,
  init() {
    const COLORS = { good: "var(--good)", warning: "var(--warning)", critical: "var(--critical)" };
    const dimSel = $("dimFilter"), stSel = $("statusFilter");
    [...new Set(KPI_DATA.map(k => k[1]))].sort().forEach(d => dimSel.add(new Option(d, d)));
    const render = () => {
      const list = KPI_DATA.filter(k =>
        (!dimSel.value || k[1] === dimSel.value) && (!stSel.value || k[6][1] === stSel.value));
      const count = s => list.filter(k => k[6][1] === s).length;
      tiles("headline", [
        ["KPIs tracked", list.length, "", ""],
        ["On track", count("On Track"), "", "", "good"],
        ["Delayed", count("Delayed"), "", "", "warning"],
        ["At risk", count("At Risk"), "", "", "critical"],
      ]);
      $("kpiRows").innerHTML = list.map(k => `<tr>
        <td><div>${k[0]}</div><div style="font-size:.72rem;color:var(--muted)">${k[1]}</div></td>
        <td>${k[2]}</td><td>${k[3]}</td><td>${k[4]}</td>
        <td><div style="display:flex;align-items:center;gap:8px">
          <div style="flex:1;background:var(--track);height:12px;border-radius:4px">
            <div style="height:100%;border-radius:0 4px 4px 0;width:${Math.min(k[5], 100)}%;background:${COLORS[k[6][0]]}"></div>
          </div><span style="width:38px;text-align:right">${k[5]}%</span></div></td>
        <td style="text-align:left">${chip(k[6][0], k[6][1])}</td></tr>`).join("") ||
        `<tr><td colspan="6" style="text-align:center;color:var(--muted)">No KPIs match the current filters.</td></tr>`;
      hbars("statusBars", [
        ["On Track", count("On Track"), "var(--good)"],
        ["Delayed", count("Delayed"), "var(--warning)"],
        ["At Risk", count("At Risk"), "var(--critical)"],
      ], { max: 8, fmt: v => v + " KPIs" });
    };
    dimSel.onchange = render;
    stSel.onchange = render;
    render();
  },
};

/* ==================== THE · QS · YÖK ==================== */
VIEWS["rankings"] = {
  title: "THE · QS · YÖK Monitoring",
  subtitle: "Ranking framework readiness · benchmarking vs Ankara foundation universities",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Data readiness by framework</h3>
        <div class="note">Share of each framework's indicators with collected, validated data.</div>
        <div id="frameworks"></div>
        <h4>THE dimensions</h4><div id="the"></div>
      </div>
      <div class="card">
        <h3>QS indicator coverage</h3><div id="qs"></div>
        <h4>YÖK categories</h4><div id="yok"></div>
      </div>
    </div>
    <div class="card">
      <h3>Benchmark — Ankara foundation universities</h3>
      <div class="note">Illustrative comparison on shared indicators (mock values; sources: YÖK Atlas + public reports).</div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>University</th><th>Students / faculty</th><th>Publications / staff</th>
          <th>Intl. students</th><th>Research income share</th><th>Employment (12 mo)</th>
        </tr></thead>
        <tbody id="bench"></tbody>
      </table></div>
    </div>
    <div class="callout">
      <b>What-if link:</b> "How would +20% citations affect THE &amp; QS position?" — run it in the
      <a href="#/scenarios">Scenario Cockpit</a> or ask the <a href="#/assistant">AI Assistant</a>.
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the ranking-evaluations endpoints (frameworks, dimensions, metric sync) once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["THE readiness", "65%", "▲ 4 pts this term", "up"],
      ["QS readiness", "52%", "weakest: employer reputation", ""],
      ["YÖK readiness", "64%", "", ""],
      ["Indicators tracked", "42", "18 THE · 9 QS · 15 YÖK", ""],
      ["Data gaps", "11", "6 need external sources", ""],
    ]);
    donuts("frameworks", [["THE", 65], ["QS", 52, "var(--accent)"], ["YÖK", 64, "#0ca30c"]]);
    hbars("the", [
      ["Teaching environment", 74], ["Research environment", 61], ["Research quality", 58],
      ["International outlook", 71], ["Industry income & patents", 49, "var(--warning)"],
    ], { max: 100, fmt: v => v + "%" });
    hbars("qs", [
      ["Academic reputation", 55], ["Citations per faculty", 60], ["Employer reputation", 38, "var(--warning)"],
      ["Employment outcomes", 62], ["Faculty / student ratio", 78], ["Intl. faculty ratio", 44],
      ["Intl. student ratio", 58], ["Intl. research network", 41], ["Sustainability", 33, "var(--warning)"],
    ], { max: 100, fmt: v => v + "%" });
    hbars("yok", [
      ["Education & teaching", 72], ["Research & publications", 63], ["Internationalization", 60],
      ["Sustainability", 51], ["Community service", 74],
    ], { max: 100, fmt: v => v + "%" });
    $("bench").innerHTML = [
      ["<b>Ankara Bilim University</b>", "47.7", "2.4", "13%", "9.0%", "77%"],
      ["Bilkent", "11.2", "4.1", "17%", "22%", "88%"],
      ["TOBB ETÜ", "18.4", "3.2", "9%", "18%", "84%"],
      ["Atılım", "22.6", "2.6", "11%", "12%", "79%"],
      ["Başkent", "19.8", "2.2", "8%", "10%", "76%"],
    ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td><td>${r[5]}</td></tr>`).join("");
  },
};
