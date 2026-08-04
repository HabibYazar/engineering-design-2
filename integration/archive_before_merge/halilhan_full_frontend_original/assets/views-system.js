// System views: University Structure + Data Import + Users & Roles.

/* ==================== University Structure (Module 1 — core data) ==================== */
const STRUCTURE = [
  {
    code: "ENG", name: "Engineering & Architecture", dean: "Prof. F. Erdoğan", founded: 2009,
    students: 850, staff: "26 faculty · 6 TAs",
    departments: [
      ["Computer Engineering", "Assoc. Prof. A. Doğan", 7, 265],
      ["Software Engineering", "Assoc. Prof. S. Karaca", 6, 248],
      ["Electrical-Electronics Eng.", "Prof. N. Yıldız", 6, 142],
      ["Industrial Engineering", "Assoc. Prof. T. Aydın", 7, 195],
    ],
    programs: [
      ["CENG-BSc", "Computer Engineering", "BSc", 80, "78%", 52, ["warning", "Demand falling"]],
      ["SWE-BSc", "Software Engineering", "BSc", 60, "99%", 49, ["good", "Healthy"]],
      ["SWE-MSc", "Software Engineering (Grad.)", "MSc", 25, "88%", 21, ["good", "Healthy"]],
      ["EE-BSc", "Electrical-Electronics Eng.", "BSc", 60, "58%", 54, ["warning", "Low occupancy"]],
      ["IE-BSc", "Industrial Engineering", "BSc", 60, "80%", 48, ["good", "Healthy"]],
      ["MET-BSc", "Metallurgy Engineering", "BSc", 30, "28%", 51, ["critical", "Merge review"]],
    ],
  },
  {
    code: "LAW", name: "Law", dean: "Prof. H. Güler", founded: 2011,
    students: 310, staff: "10 faculty · 6 TAs",
    departments: [["Law", "Prof. H. Güler", 10, 310]],
    programs: [["LAW-LLB", "Law", "LLB", 85, "89%", 46, ["good", "Healthy"]]],
  },
  {
    code: "EAS", name: "Economics, Admin. & Social Sciences", dean: "Prof. Z. Çelik", founded: 2009,
    students: 960, staff: "15 faculty · 5 TAs",
    departments: [
      ["Business Administration", "Assoc. Prof. M. Ercan", 5, 365],
      ["Economics", "Prof. D. Tekin", 5, 260],
      ["Political Science & IR", "Assoc. Prof. C. Uçar", 5, 335],
    ],
    programs: [
      ["BUS-BSc", "Business Administration", "BSc", 95, "93%", 44, ["good", "Healthy"]],
      ["ECON-BSc", "Economics", "BSc", 75, "82%", 42, ["good", "Healthy"]],
      ["PSIR-BSc", "Political Science & IR", "BSc", 90, "85%", 43, ["good", "Healthy"]],
    ],
  },
  {
    code: "FADA", name: "Fine Arts, Design & Architecture", dean: "Prof. E. Soylu", founded: 2012,
    students: 350, staff: "12 faculty · 4 TAs",
    departments: [
      ["Architecture", "Prof. E. Soylu", 4, 150],
      ["Interior Architecture", "Asst. Prof. L. Kaya", 4, 118],
      ["Graphic Design", "Asst. Prof. R. Ünal", 4, 82],
    ],
    programs: [
      ["ARCH-BArch", "Architecture", "BArch", 55, "83%", 58, ["good", "Healthy"]],
      ["IARCH-BSc", "Interior Architecture", "BSc", 50, "72%", 52, ["warning", "Watch"]],
      ["GD-BA", "Graphic Design", "BA", 40, "55%", 47, ["warning", "Low occupancy"]],
    ],
  },
];

VIEWS["structure"] = {
  title: "University Structure",
  subtitle: "Core data management — faculties · departments · academic programs · curricula (Module 1)",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-2-3">
      <div class="card">
        <h3>Faculties</h3>
        <div class="note">Select a faculty to manage its departments and programs.</div>
        <ul class="plain" id="facList"></ul>
        <h4>Administrative &amp; support units</h4>
        <div class="table-wrap"><table>
          <thead><tr><th>Unit</th><th>Head</th><th>Staff</th></tr></thead>
          <tbody>
            <tr><td>Student Affairs Office</td><td style="text-align:left">B. Aksu</td><td>9</td></tr>
            <tr><td>Erasmus &amp; International Office</td><td style="text-align:left">G. Polat</td><td>4</td></tr>
            <tr><td>Library &amp; Documentation</td><td style="text-align:left">S. Erol</td><td>6</td></tr>
            <tr><td>IT Directorate</td><td style="text-align:left">O. Yaman</td><td>7</td></tr>
            <tr><td>Financial Affairs</td><td style="text-align:left">N. Ada</td><td>8</td></tr>
          </tbody>
        </table></div>
      </div>
      <div class="card" id="facDetail"></div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the core-data CRUD endpoints (faculties, departments, programs, administrative-units) once integrated; bulk changes arrive via <a href="#/data-import">Data Import</a>.</footer>`,
  init() {
    tiles("headline", [
      ["Faculties", "4", "+ English Preparatory School", ""],
      ["Departments", "11", "", ""],
      ["Academic programs", "13", "12 active · 1 in merge review", ""],
      ["Curricula on file", "13", "avg 49 courses / program", ""],
      ["Administrative units", "5", "", ""],
    ]);
    let selected = 0;
    const renderList = () => {
      $("facList").innerHTML = STRUCTURE.map((f, i) => `
        <li style="cursor:pointer${i === selected ? ";background:var(--primary-soft);border-radius:7px;padding-left:8px;padding-right:8px" : ""}" data-i="${i}">
          <b>${f.code}</b><span>${f.name}</span>
          <span class="push" style="color:var(--muted);font-size:.75rem">${f.students} students ›</span>
        </li>`).join("");
      $("facList").querySelectorAll("li").forEach(li => li.onclick = () => {
        selected = +li.dataset.i;
        renderList();
        renderDetail();
      });
    };
    const renderDetail = () => {
      const f = STRUCTURE[selected];
      $("facDetail").innerHTML = `
        <h3>${f.name}</h3>
        <div class="note">Dean: <b>${f.dean}</b> · founded ${f.founded} · ${f.staff} · ${f.students} students</div>
        <h4>Departments</h4>
        <div class="table-wrap"><table>
          <thead><tr><th>Department</th><th>Chair</th><th>Faculty members</th><th>Students</th></tr></thead>
          <tbody>${f.departments.map(d => `<tr><td>${d[0]}</td><td style="text-align:left">${d[1]}</td><td>${d[2]}</td><td>${d[3]}</td></tr>`).join("")}</tbody>
        </table></div>
        <h4>Academic programs &amp; curricula</h4>
        <div class="table-wrap"><table>
          <thead><tr><th>Code</th><th>Program</th><th>Degree</th><th>YÖK quota</th><th>Occupancy</th><th>Courses</th><th>Status</th></tr></thead>
          <tbody>${f.programs.map(p => `<tr><td>${p[0]}</td><td style="text-align:left">${p[1]}</td><td>${p[2]}</td><td>${p[3]}</td><td>${p[4]}</td><td>${p[5]}</td>
            <td style="text-align:left">${chip(p[6][0], p[6][1])}</td></tr>`).join("")}</tbody>
        </table></div>
        <div class="frow" style="margin-top:12px">
          <button class="primary" style="flex:none">+ Add department</button>
          <button style="flex:none">+ Add program</button>
          <button class="ghost" style="flex:none">Edit curriculum…</button>
        </div>`;
    };
    renderList();
    renderDetail();
  },
};

/* ==================== Data Import ==================== */
VIEWS["data-import"] = {
  title: "Data Integration",
  subtitle: "CSV · XLSX · JSON bulk import with validation, preview mode and job tracking",
  html: () => `
    <div class="grid cols-2-3">
      <div class="card">
        <h3>New import</h3>
        <label class="f">Resource type
          <select>
            <option>faculties</option><option>departments</option><option>programs</option>
            <option>students</option><option>student_academic_records</option>
            <option>program_enrollments</option><option>administrative_units</option>
            <option>institutional_metrics</option><option>benchmark_institutions</option>
            <option>benchmark_metric_values</option><option>comparable_university_programs</option>
          </select>
        </label>
        <div class="dropzone" style="margin:12px 0">
          Drop a <b>.csv</b>, <b>.xlsx</b> or <b>.json</b> file here<br>or <b>browse files</b>
        </div>
        <div class="frow">
          <label class="f" style="flex:none;flex-direction:row;align-items:center;gap:8px">
            <input type="checkbox" checked style="width:auto"> Preview mode (validate only)
          </label>
          <button class="primary" style="flex:none">Start import</button>
          <button class="ghost" style="flex:none">Download template</button>
        </div>
        <div class="callout" style="margin-top:12px">
          Import order matters: <b>faculties → departments → programs</b> — child rows reference parent codes.
        </div>
      </div>
      <div class="card">
        <h3>Validation preview — faculties_with_errors.csv</h3>
        <div class="note">Preview mode result: 2 of 4 rows rejected, nothing written.</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Row</th><th>Code</th><th>Name</th><th>Result</th><th>Detail</th></tr></thead>
          <tbody>
            <tr><td>1</td><td>ENG</td><td>Engineering &amp; Architecture</td><td style="text-align:left"><span class="chip good">✓ Valid</span></td><td style="text-align:left">—</td></tr>
            <tr><td>2</td><td>LAW</td><td>Law</td><td style="text-align:left"><span class="chip good">✓ Valid</span></td><td style="text-align:left">—</td></tr>
            <tr><td>3</td><td></td><td>Fine Arts</td><td style="text-align:left"><span class="chip critical">✗ Rejected</span></td><td style="text-align:left">code is required</td></tr>
            <tr><td>4</td><td>ENG</td><td>Engineering (dup)</td><td style="text-align:left"><span class="chip critical">✗ Rejected</span></td><td style="text-align:left">duplicate code in file</td></tr>
          </tbody>
        </table></div>
      </div>
    </div>
    <div class="card">
      <h3>Import jobs</h3>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Job</th><th>Resource</th><th>File</th><th>Rows OK</th><th>Rows rejected</th><th>Mode</th><th>Status</th><th>When</th>
        </tr></thead>
        <tbody id="jobs"></tbody>
      </table></div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the data-integration endpoints (import, templates, jobs) once integrated. Excel integration is a core requirement of the ABU brief.</footer>`,
  init() {
    $("jobs").innerHTML = [
      ["#128", "students", "students_2025.xlsx", 3980, 12, "Import", ["good", "Completed"], "Today 09:14"],
      ["#127", "program_enrollments", "enrollments_fall.csv", 812, 0, "Import", ["good", "Completed"], "Today 08:52"],
      ["#126", "benchmark_metric_values", "yok_atlas_2025.json", 240, 6, "Import", ["good", "Completed"], "Yesterday"],
      ["#125", "faculties", "faculties_with_errors.csv", 2, 2, "Preview", ["warning", "Validation errors"], "Yesterday"],
      ["#124", "institutional_metrics", "metrics_q3.xlsx", 0, 58, "Import", ["critical", "Failed — wrong template"], "2 days ago"],
    ].map(r => `<tr>
      <td>${r[0]}</td><td>${r[1]}</td><td style="text-align:left">${r[2]}</td><td>${r[3].toLocaleString("en-US")}</td>
      <td>${r[4]}</td><td>${r[5]}</td><td style="text-align:left">${chip(r[6][0], r[6][1])}</td><td>${r[7]}</td></tr>`).join("");
  },
};

/* ==================== Users & Roles ==================== */
VIEWS["users"] = {
  title: "Users &amp; Authorization",
  subtitle: "Role-based access — every screen is scoped to the signed-in role",
  html: () => `
    <div class="tiles" id="headline"></div>
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Users</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>User</th><th>Role</th><th>Scope</th><th>Last sign-in</th><th>Status</th></tr></thead>
          <tbody id="userRows"></tbody>
        </table></div>
      </div>
      <div class="card">
        <h3>Add user</h3>
        <label class="f">Full name <input placeholder="e.g. A. Yılmaz"></label>
        <div class="frow" style="margin-top:10px">
          <label class="f">Role
            <select><option>Rector</option><option>Vice-Rector</option><option>Dean</option><option>Department Chair</option><option>Analyst</option></select>
          </label>
          <label class="f">Scope
            <select><option>University-wide</option><option>Engineering &amp; Architecture</option><option>Law</option><option>Econ. &amp; Admin. Sci.</option><option>Fine Arts &amp; Arch.</option></select>
          </label>
        </div>
        <button class="primary" style="margin-top:12px">Create user</button>
        <div class="note" style="margin-top:10px">Passwords are stored hashed; sessions expire after 8 hours (backend policy).</div>
      </div>
    </div>
    <div class="card">
      <h3>Role permissions</h3>
      <div class="note">What each role can see and do — the sidebar and actions adapt to the signed-in role.</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Capability</th><th>Rector</th><th>Dean</th><th>Dept. Chair</th><th>Analyst</th></tr></thead>
        <tbody id="perm"></tbody>
      </table></div>
    </div>
    <footer class="demo">Design prototype — mock data. Backed by the auth endpoints (login, users, roles) once integrated.</footer>`,
  init() {
    tiles("headline", [
      ["Users", "14", "", ""],
      ["Roles", "5", "", ""],
      ["Active sessions", "3", "", ""],
      ["Failed sign-ins (7d)", "2", "", ""],
    ]);
    $("userRows").innerHTML = [
      ["test", "Rector", "University-wide", "Today 08:41", ["good", "Active"]],
      ["M. Kaplan", "Vice-Rector", "University-wide", "Today 09:02", ["good", "Active"]],
      ["F. Erdoğan", "Dean", "Engineering & Architecture", "Yesterday", ["good", "Active"]],
      ["Z. Çelik", "Dean", "Econ. & Admin. Sciences", "2 days ago", ["good", "Active"]],
      ["A. Doğan", "Department Chair", "Computer Engineering", "Today 07:55", ["good", "Active"]],
      ["S. Ateş", "Analyst", "University-wide (read-only)", "Today 09:20", ["good", "Active"]],
      ["k.demir", "Analyst", "—", "Never", ["warning", "Invited"]],
    ].map(r => `<tr>
      <td>${r[0]}</td><td>${r[1]}</td><td style="text-align:left">${r[2]}</td><td>${r[3]}</td>
      <td style="text-align:left">${chip(r[4][0], r[4][1])}</td></tr>`).join("");
    const Y = `<span style="color:var(--good)">✓</span>`, N = `<span style="color:var(--muted)">—</span>`, P = `<span style="color:var(--warning)">scope</span>`;
    $("perm").innerHTML = [
      ["View executive dashboard", Y, P, P, Y],
      ["Run scenarios", Y, P, N, N],
      ["Use AI assistant", Y, Y, Y, Y],
      ["Edit KPI targets & thresholds", Y, N, N, N],
      ["Import data", Y, N, N, Y],
      ["Manage users", Y, N, N, N],
      ["View financials", Y, P, N, Y],
    ].map(r => `<tr><td style="text-align:left">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td></tr>`).join("");
  },
};
