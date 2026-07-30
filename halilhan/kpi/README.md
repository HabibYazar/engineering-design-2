# Part 8 — University Performance Management & Monitoring (Demo)

Demo for **Section 8 "University Performance Management and Monitoring"** of the
*Strategic University Management and Decision Support System* project
description — a **pure-Python web application** (standard library only, no
JavaScript, nothing to install).

```
kpi/
├── frontend/
│   ├── templates/page.html   HTML page shell with placeholders
│   └── style.css             styling (light + dark mode)
└── backend/
    ├── server.py             controller — HTTP routing, form handling, redirects
    ├── render.py             view — server-side HTML rendering in Python
    ├── db.py                 model — JSON-file database, validation, status logic
    ├── seed_kpis.json        seed dataset (14 mock KPIs)
    └── kpis.json             runtime database — auto-created on first run
```

The backend follows a small MVC split: `db.py` owns the data, validation and
the risk-status logic, `render.py` fills the template with computed fragments,
`server.py` routes requests. Every form is a plain HTML POST followed by a
redirect (Post/Redirect/Get) with a flash message. Expanding a KPI row uses
the HTML `<details>` element — no JavaScript anywhere.

## How to run

```
cd kpi/backend
python server.py
```

Then open **http://localhost:8008**. Requires Python 3 — no packages, no build
step. (`kpis.json` is created automatically; delete it or use the Reset button
to go back to the seed data.)

## What it shows

14 mock KPIs across the strategic dimensions of Section 8. For each KPI:

- **Current value**, **target value**, and **achievement rate** (progress bar)
- **Risk level** — On Track / Delayed / At Risk status chips
- Click a row to expand: **previous year**, **university-wide average**,
  **faculty comparison** chart, and the **recommended corrective action**
- Summary tiles count how many objectives are on track / delayed / at risk
- **Filters** by strategic dimension and by status

## Where the "business logic" lives

Risk statuses are **not** stored — `db.py` derives them on every request from
the achievement rate and per-KPI configurable thresholds (the project
description requires thresholds to be configurable by management):

```
achievement >= thresholds.on    ->  On Track   (default 90%)
achievement <  thresholds.risk  ->  At Risk    (default 70%)
otherwise                       ->  Delayed
```

## Adding data (updates the page on submit)

- **Record a new measurement** — pick a KPI, enter its new current value; the
  backend recomputes its achievement rate and risk status, and the summary
  tiles/bars update.
- **Add a new KPI** — name, dimension (existing or new), unit, current/target,
  benchmarks and corrective action; it appears with a computed status.
- **Reset demo data** — restores the 14 seed KPIs (handy before presenting).

Invalid input (bad numbers, duplicate names, zero targets) is rejected by the
data layer and shown as an error banner.

## Routes

| Method | Route        | Purpose                                              |
|--------|--------------|------------------------------------------------------|
| GET    | `/`          | Rendered page (`?dim=` / `?status=` filter the list) |
| POST   | `/measure`   | Record a new current value for a KPI                 |
| POST   | `/kpis`      | Register a new KPI                                   |
| POST   | `/reset`     | Restore the seed dataset                             |
| GET    | `/api/kpis`  | All KPIs as JSON with computed achievement + status  |

## Note

This is a **demo**: all values are mock data. In the full system, values would
be fed from the operational systems (SIS, HRMS, finance) through the data
integration module.
