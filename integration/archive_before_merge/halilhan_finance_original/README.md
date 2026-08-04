# Part 6 — Strategic Financial Analysis (Demo)

Demo for **Section 6 "Strategic Financial Analysis"** of the *Strategic University
Management and Decision Support System* project description — a **pure-Python
web application** (standard library only, no JavaScript, nothing to install).

```
finance/
├── frontend/
│   ├── templates/page.html   HTML page shell with placeholders
│   └── style.css             styling (light + dark mode)
└── backend/
    ├── server.py             controller — HTTP routing, form handling, redirects
    ├── render.py             view — server-side HTML rendering in Python
    ├── db.py                 model — JSON-file database + validation
    ├── seed_data.json        seed dataset (mock data)
    └── data.json             runtime database — auto-created on first run
```

The backend follows a small MVC split: `db.py` owns the data and validation,
`render.py` fills the template with computed fragments (tiles, bar charts,
tables), `server.py` routes requests. Every form is a plain HTML POST followed
by a redirect (Post/Redirect/Get) with a flash message — no JavaScript anywhere.

## How to run

```
cd finance/backend
python server.py
```

Then open **http://localhost:8006**. Requires Python 3 — no packages, no build
step. (`data.json` is created automatically; delete it or use the Reset button
to go back to the seed data.)

## What it shows

Using the Faculty of Engineering and Architecture as the pilot unit:

- **Key financial indicators** — total revenue/expenditure, balance,
  revenue/cost per student, cost per graduate, personnel share, research income
  share, scholarship impact. All computed in Python from the raw data.
- **Revenue by source** and **expenditure by category** bar charts.
- **Financial status by department** — balance, cost per student, and budget
  realization with a within/over-budget status.
- **Academic year selector** — every view recalculates per year.

## Adding data (updates the charts on submit)

The "Add / update data" forms write to the database and the page re-renders
with the new numbers:

- **Book a financial entry** — add an amount to any revenue/expenditure
  category (or type a new category name — it gets its own bar). Negative
  amounts act as corrections.
- **Add / update a department** — new departments appear in the table with
  their computed indicators; existing names are updated in place.
- **Update headcounts** — students/graduates, which drive the per-student ratios.
- **Open a new academic year** — creates an empty year to book entries into.
- **Reset demo data** — restores the seed dataset (handy before presenting).

Invalid input (bad numbers, unknown year, empty names) is rejected by the data
layer and shown as an error banner.

## Routes

| Method | Route          | Purpose                                        |
|--------|----------------|------------------------------------------------|
| GET    | `/`            | Rendered page (`?year=` selects the year)      |
| POST   | `/entry`       | Book an amount onto a category                 |
| POST   | `/department`  | Add or update a department                     |
| POST   | `/stats`       | Update student/graduate headcounts             |
| POST   | `/year`        | Open a new academic year                       |
| POST   | `/reset`       | Restore the seed dataset                       |
| GET    | `/api/data`    | Full dataset as JSON (integration endpoint)    |

## Note

This is a **demo**: all figures are mock data (₺M = million TRY). In the full
system this data would come from the university's Financial Management System
through the data integration module.
