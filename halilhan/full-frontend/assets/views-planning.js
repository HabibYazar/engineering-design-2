// Planning views: Scenario Cockpit + Early Warning.

/* ==================== Scenario Cockpit ==================== */
VIEWS["scenarios"] = {
  title: "Scenario Cockpit",
  subtitle: "What-if simulation of strategic decisions · executives can define custom scenarios",
  html: () => `
    <div class="grid cols-2-3">
      <div class="card">
        <h3>Simulation inputs</h3>
        <div class="note">Live demo: enrollment / tuition / scholarship simulation (scenarios 7.1 &amp; 7.2). Baseline: 4,010 students · $20,000 fee · 15% full + 3% merit + 82% half scholarship.</div>
        <label class="f">Enrollment change <b id="vEnroll" style="color:var(--primary)">0%</b>
          <input type="range" id="sEnroll" min="-20" max="20" value="0" step="1">
        </label>
        <label class="f" style="margin-top:10px">Annual tuition fee <b id="vFee" style="color:var(--primary)">$20,000</b>
          <input type="range" id="sFee" min="16000" max="26000" value="20000" step="500">
        </label>
        <label class="f" style="margin-top:10px">Full-scholarship share <b id="vSch" style="color:var(--primary)">15%</b>
          <input type="range" id="sSch" min="10" max="30" value="15" step="1">
        </label>
        <label class="f" style="margin-top:10px">New academic staff hires <b id="vHire" style="color:var(--primary)">0</b>
          <input type="range" id="sHire" min="0" max="20" value="0" step="1">
        </label>
        <div class="callout" style="margin-top:14px">
          Demand response is modeled: fees above $22,000 progressively reduce projected enrollment
          (elasticity from 3-cycle admission data).
        </div>
      </div>
      <div class="card">
        <h3>Projected outcome</h3>
        <div class="tiles" id="simResult" style="margin-bottom:14px"></div>
        <div id="verdict" class="callout"></div>
        <h4>Capacity check</h4>
        <div id="capacity"></div>
      </div>
    </div>
    <div class="card">
      <h3>Scenario library</h3>
      <div class="note">The seven executive scenario families from the brief — each opens a dedicated definition form in the full system.</div>
      <div class="grid cols-2" id="library"></div>
    </div>
    <footer class="demo">Design prototype — simulation math runs client-side on the ABU assumptions for demo purposes; the real engine is the scenario-analysis backend (Module 9).</footer>`,
  init() {
    const BASE = { students: 4010, merit: 0.03, overheadY: 13.8e6, payrollY: 2.376e6, otherY: 15.4e6, seats: 1450, staff: 63 };
    const simulate = () => {
      const dEnroll = +$("sEnroll").value / 100;
      const fee = +$("sFee").value;
      const full = +$("sSch").value / 100;
      const hires = +$("sHire").value;
      const feePenalty = Math.max(0, (fee - 22000) / 1000) * 0.025;
      const students = Math.round(BASE.students * (1 + dEnroll) * (1 - feePenalty));
      const payers = students * (1 - full - BASE.merit);
      const revenue = payers * fee * 0.5 + 3.4e6;
      const expenditure = BASE.overheadY + BASE.payrollY + BASE.otherY + hires * 2200 * 12;
      const balance = revenue - expenditure;
      const seatUse = students * 0.327 / BASE.seats;
      const ratio = students / (BASE.staff + hires);

      tiles("simResult", [
        ["Projected students", students.toLocaleString("en-US"), "", ""],
        ["Net revenue", fmtUSD(revenue), "", ""],
        ["Expenditure", fmtUSD(expenditure), "", ""],
        ["Balance", (balance >= 0 ? "+" : "−") + fmtUSD(Math.abs(balance)), balance >= 0 ? "surplus" : "deficit", balance >= 0 ? "up" : "down"],
        ["Cost / student", fmtK(expenditure / students), "", ""],
        ["Students / faculty", ratio.toFixed(1), "QS target ≤ 22", ratio <= 22 ? "up" : "down"],
      ]);
      const seatPct = Math.round(seatUse * 100);
      donuts("capacity", [
        ["Seat utilization", seatPct, seatPct > 95 ? "var(--critical)" : seatPct > 85 ? "var(--warning)" : "var(--good)"],
        ["Students / faculty vs QS cap", Math.round(ratio / 22 * 100), ratio <= 22 ? "var(--good)" : "var(--critical)"],
      ]);
      const v = $("verdict");
      if (balance < 0) {
        v.className = "callout warn";
        v.innerHTML = `<b>Deficit scenario.</b> Revenue does not cover costs — consider fee, scholarship or cost adjustments. Break-even at ≈ <b>${Math.ceil(expenditure / (fee * 0.5 * (1 - full - BASE.merit))).toLocaleString("en-US")}</b> students.`;
      } else if (seatUse > 0.95) {
        v.className = "callout warn";
        v.innerHTML = `<b>Capacity constraint.</b> Surplus of ${fmtUSD(balance)}, but seat utilization hits ${seatPct}% — new classrooms/labs required (investment scenario 7.6).`;
      } else {
        v.className = "callout";
        v.innerHTML = `<b>Sustainable scenario.</b> Surplus of ${fmtUSD(balance)} with ${seatPct}% seat utilization and ${ratio.toFixed(1)} students per faculty member.`;
      }
      $("vEnroll").textContent = (dEnroll >= 0 ? "+" : "") + Math.round(dEnroll * 100) + "%";
      $("vFee").textContent = "$" + fee.toLocaleString("en-US");
      $("vSch").textContent = Math.round(full * 100) + "%";
      $("vHire").textContent = hires;
    };
    ["sEnroll", "sFee", "sSch", "sHire"].forEach(id => $(id).addEventListener("input", simulate));

    $("library").innerHTML = [
      ["7.1 Student Enrollment", "Revenue, staffing, capacity and cost-per-student under enrollment shifts.", ["good", "Simulated above"]],
      ["7.2 Tuition & Scholarship", "Fee/scholarship policy vs revenue and demand; incentive schemes.", ["good", "Simulated above"]],
      ["7.3 New Academic Program", "Investment, staffing, break-even students, physical fit, strategic value.", ["info", "Saved: Data Science BSc — break-even 47 students"]],
      ["7.4 Program Restructuring", "Merging low-demand programs; closure impact on revenue and reputation.", ["warning", "Saved: Metallurgy merger → +$0.6M/yr"]],
      ["7.5 Academic Staff Planning", "Hiring, salary rises, overload teaching, TA-led recitations.", ["info", "Saved: +6 assistants → survey +0.2, cost +$144K"]],
      ["7.6 Investment", "New buildings/labs: cost, capacity gain, ROI period.", ["info", "Saved: 2 new labs → ROI 4.3 yrs"]],
      ["7.7 Economic Risk", "Inflation, FX exposure on technology costs, tuition revenue decline.", ["warning", "Saved: 20% FX shock → +$0.9M tech costs"]],
    ].map(([title, desc, tag]) => `
      <div class="card" style="box-shadow:none;border:1px solid var(--line)">
        <h3 style="font-size:.86rem">${title}</h3>
        <div class="note" style="margin-bottom:8px">${desc}</div>
        ${chip(tag[0], tag[1])}
      </div>`).join("");

    simulate();
  },
};

/* ==================== Early Warning ==================== */
VIEWS["alerts"] = {
  title: "Risk &amp; Early Warning",
  subtitle: "Configurable rule engine · alerts ranked by severity",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Active alerts</h3>
        <div class="note">Generated by threshold rules over live indicators; each links to its source screen.</div>
        <ul class="plain" id="alertList"></ul>
      </div>
      <div class="card">
        <h3>Rule engine</h3>
        <div class="note">15 rules defined in configuration — thresholds editable by management.</div>
        <div id="rules"></div>
        <h4>Example rule (configurable)</h4>
        <div class="callout" style="font-family:ui-monospace,monospace;font-size:.76rem">
          IF program.occupancy &lt; 60% FOR 2 consecutive cycles<br>
          THEN alert(severity=critical, action="review quota &amp; marketing")
        </div>
        <h4>Most-triggered rules this term</h4>
        <div id="topRules"></div>
      </div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the early-warning endpoints (alerts, summary, rules) once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Active alerts", "27", "", ""],
      ["Critical", "6", "", "", "critical"],
      ["Serious", "9", "", "", "serious"],
      ["Warning", "12", "", "", "warning"],
      ["Rules active", "8 / 15", "7 await other modules' data", ""],
    ]);
    $("alertList").innerHTML = [
      ["critical", "Metallurgy Eng. occupancy 27.5% — below 30% closure-review threshold", "students"],
      ["critical", "Computer Eng. demand fell 92% → 38% over three cycles", "students"],
      ["critical", "Fine Arts & Architecture faculty deficit $1.0M and widening", "finance"],
      ["warning", "Lab utilization 118% in morning bands — sessions displaced", "physical"],
      ["warning", "Research income share 9.0% vs 15% target", "kpi"],
      ["warning", "CE admission score 75 pts below Türkiye average", "students"],
      ["warning", "4 staff members above 140% teaching load", "staff"],
      ["warning", "MÜDEK accreditation renewal due Oct 2026 — 3 programs", "kpi"],
    ].map(([lvl, text, route]) => `<li>
      <span class="chip ${lvl}">${lvl === "critical" ? "▲ Critical" : "! Warning"}</span>
      <span>${text}</span><a class="push" href="#/${route}" style="font-size:.72rem">source →</a></li>`).join("");
    hbars("rules", [
      ["Occupancy thresholds", 3, "var(--critical)"], ["Financial balance", 2, "var(--critical)"],
      ["Demand trends", 2, "var(--warning)"], ["Capacity limits", 1, "var(--warning)"],
    ], { max: 4, fmt: v => v + " firing" });
    hbars("topRules", [
      ["occupancy_below_threshold", 9], ["demand_trend_decline", 6],
      ["budget_deficit", 5], ["capacity_exceeded", 4], ["kpi_at_risk", 3],
    ], { fmt: v => v + "×" });
  },
};
