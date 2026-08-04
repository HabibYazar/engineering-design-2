# Full-System Frontend (Design Prototype)

Unified frontend for the **ABU Strategic University Management & Decision
Support System** — a **single-page application** covering every module of the
group project in one interface: one entry point, client-side routing, a
persistent app shell, and a mock session.

All data is mock and there are no backend calls — this is the **design** work
package; wiring the screens to the team's APIs is a later group task.

## How to run

Serve the folder over HTTP (closest to how it would really run):

```
python -m http.server 8010 --directory full-frontend
```

Then open **http://localhost:8010** — or simply double-click `index.html`,
which works too.

Sign in with any username (authentication is mocked) and pick a role, then
navigate with the sidebar. **Sign out** from the user chip in the top-right.

## What to look at first

| Try this | Where |
|---|---|
| Drill down university → faculty → department | Executive Dashboard, bottom table |
| Ask an executive question and get an explained answer | AI Assistant (or the ✨ bubble on any screen) |
| Drag sliders and watch revenue/capacity recompute live | Scenario Cockpit |
| Filter KPIs by dimension or risk status | Performance & KPIs |
| Switch to night mode | 🌙 in the sidebar corner |
| See the phone layout | narrow the window → the ☰ drawer appears |

## Architecture

```
full-frontend/
├── index.html                 single entry point — loads the scripts, nothing else
└── assets/
    ├── style.css              design tokens, components, light + dark themes
    ├── app.js                 SPA core: hash router (#/dashboard, #/finance, …),
    │                          session, persistent shell, theme + mobile drawer,
    │                          floating AI chat, shared render helpers
    │                          (tiles, bars, meters, ring gauges, line charts, chips)
    ├── views-overview.js      Executive Dashboard · AI Assistant
    ├── views-analytics.js     Students · Staff · Physical · Finance ·
    │                          Sustainability · KPIs · THE/QS/YÖK
    ├── views-planning.js      Scenario Cockpit · Early Warning
    └── views-system.js        University Structure · Data Import · Users & Roles
```

Each view registers itself into a shared `VIEWS` registry with a `title`,
`subtitle`, an `html()` template and an `init()` that fills in the data —
so adding a screen means adding one object, not a new page.

How it behaves like a real product:

- **Routing** — every screen is a `#/route`; URLs are shareable, browser
  back/forward work, and unknown or unauthenticated routes redirect to sign-in.
- **Session** — signing in stores the user and role; every route is guarded;
  sign-out clears it.
- **Persistent shell** — sidebar and topbar are built once; only the content
  area swaps, with a subtle transition.
- **Stateful views** — assistant conversations survive navigation, KPI filters
  really filter, the Scenario Cockpit recomputes projections live.
- **Night mode** — the 🌙 in the sidebar toggles a full dark theme; the choice
  is remembered across reloads.
- **Responsive** — below 880px the sidebar becomes a ☰ slide-in drawer with a
  dimmed backdrop, so the app is usable on a phone.
- **Floating AI chat** — a ✨ bubble in the bottom-right opens a mini assistant
  on any screen (hidden on the full assistant page); it shares the same
  scripted answers and keeps its history while you navigate.

## Screens → modules

| Route | Covers |
|---|---|
| `#/login` | User & Authorization (roles: Rector / Dean / Chair / Analyst) |
| `#/dashboard` | Consolidated overview + drill-down / roll-up |
| `#/assistant` | AI-Powered Strategic Decision Support Assistant (RAG, explainable answers) |
| `#/students` | Enrollment, occupancy, admission-score benchmarks, demand trends |
| `#/staff` | Performance ranking, teaching load, publications, configurable weights |
| `#/physical` | Classroom/lab occupancy, utilization heat map, capacity forecast |
| `#/finance` | Net revenue vs expenditure, per-student economics, tuition optimization |
| `#/sustainability` | Weighted program scoring, ABU 4-category classification |
| `#/kpi` | KPI targets, achievement, risk statuses, corrective actions |
| `#/rankings` | THE / QS / YÖK readiness, Ankara benchmark |
| `#/scenarios` | Live what-if sliders + the 7 executive scenario families |
| `#/alerts` | Early-warning alerts by severity, rule engine view |
| `#/structure` | Core data — faculties, departments, programs, curricula (master-detail) |
| `#/data-import` | CSV / XLSX / JSON import, validation preview, job tracking |
| `#/users` | User list, role permission matrix |

## Design notes

- Mock data follows the **ABU KDS assumptions**: ~4,000 students, 4 faculties,
  $20,000 tuition, 15% full + 50% partial + 3% merit scholarships, 27
  classrooms + 6 labs (1,450 seats), USD salary scale, $1.15M/month overhead.
  Figures are consistent across screens — the dashboard, finance and structure
  views describe the same university.
- The visual language follows the reference dashboards in the project brief:
  dark navigation rail, clean stat cards, **ring gauges** for readiness and
  capacity, and **color-tinted cards** for alert and risk counters.
- Role selection at sign-in sets the displayed role; actual enforcement belongs
  to the backend's authorization module — the permission matrix on
  `#/users` documents the intended rules.
- No frameworks, no CDN, no build step — plain HTML/CSS/JS, fully offline-capable.
  Asset links carry a `?v=` tag so browsers pick up design updates.
