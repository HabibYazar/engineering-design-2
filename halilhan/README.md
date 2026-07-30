# SENG 449 — Strategic University Management & DSS (my parts: 6, 8, 12)

Feature demos for three parts of the *Strategic University Management and
Decision Support System* project, numbered per the section numbering of
`information/Eng-DesignProject.pdf`. The parts are **separate, standalone**
demos — they are not integrated with each other. All data is mock data.

| Part | Section | Folder | Tech |
|------|---------|--------|------|
| 6 | Strategic Financial Analysis | `finance/` | Python web app (frontend + backend) |
| 8 | University Performance Management & Monitoring | `kpi/` | Python web app (frontend + backend) |
| 12 | Executive Dashboard | `frontend/` | frontend-only page |

## Requirements

- **Python 3** (any recent version — standard library only, nothing to `pip install`)
- Any modern browser

## Part 6 — Strategic Financial Analysis (`finance/`)

Financial picture of the pilot faculty (Engineering & Architecture): revenue by
source, expenditure by category, and computed indicators — revenue/cost per
student, cost per graduate, personnel expense ratio, research income share,
scholarship impact — plus a per-department table with budget realization
status. A year selector recalculates everything per academic year.

**Run:**

```
python finance/backend/server.py
```

Then open **http://localhost:8006**.

**How to use:** scroll to *Add / update data*.
- *Book a financial entry* — pick year + type, pick a category (or type a brand
  new one — it gets its own bar), enter an amount in ₺M and submit. Charts and
  indicators update on submit; negative amounts subtract (corrections).
- *Add / update a department* — fills the department table; using an existing
  name updates it instead.
- *Manage dataset* — change student/graduate headcounts (drives the per-student
  ratios), open a new academic year, or **Reset demo data** back to the seed.

## Part 8 — University Performance Management & Monitoring (`kpi/`)

14 KPIs across the strategic dimensions of Section 8, each with current value,
target, achievement bar and an **On Track / Delayed / At Risk** status that the
backend computes from per-KPI configurable thresholds. Click any KPI row to
expand its details: previous year, university-wide average, per-faculty
comparison chart, and the recommended corrective action. Filter the list by
dimension or status; summary tiles count each status.

**Run:**

```
python kpi/backend/server.py
```

Then open **http://localhost:8008**.

**How to use:** scroll to *Add / update data*.
- *Record a new measurement* — pick a KPI and enter its new current value; the
  backend recomputes its achievement rate and risk status (try raising
  "International student ratio" from 6.8 to 9.2 — it flips from At Risk to On
  Track).
- *Add a new KPI* — appears in the table with a computed status.
- **Reset demo data** restores the 14 seed KPIs.

## Part 12 — Executive Dashboard (`frontend/`)

Consolidated senior-management view: headline tiles (students, revenue,
expenditure, budget realization, graduation/attrition, capacity), a 5-year
enrollment trend, THE/QS/YÖK data-readiness scores, revenue vs expenditure by
faculty, critical risks & early warnings, strong/weak indicators, and a
**drill-down / roll-up** table (click a faculty row to open its departments,
click again to close).

**Run:** no server needed — just open `frontend/index.html` in a browser
(double-click it).

## How parts 6 and 8 are built

Pure-Python web apps with a small MVC split, no JavaScript and no dependencies:

- `backend/db.py` — model: JSON-file database, input validation, status logic
- `backend/render.py` — view: server-side HTML rendering into `frontend/templates/page.html`
- `backend/server.py` — controller: HTTP routing, form handling, Post/Redirect/Get with flash messages

Data lives in a seed JSON file (`seed_*.json`) that is copied to a runtime
database file on first start; every form submission is validated and persisted,
and each app also exposes its dataset as JSON (`/api/data`, `/api/kpis`).
See `finance/README.md` and `kpi/README.md` for full details and route tables.
