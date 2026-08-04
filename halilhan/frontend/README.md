# Part 12 — Executive Dashboard (Demo)

Demo for **Section 12 "Executive Dashboard"** of the *Strategic University
Management and Decision Support System* project description.

## What it shows

A consolidated, university-wide overview for senior management:

- **Headline tiles** — total students, total revenue/expenditure, budget
  realization, cost per student, graduation rate, student attrition, and
  physical capacity utilization, each with a year-over-year delta.
- **5-year enrollment trend** — line chart of total students.
- **THE / QS / YÖK data readiness scores** — meter per ranking framework.
- **Revenue vs expenditure by faculty** — paired bar chart with legend.
- **Critical risks & early warnings** — list with critical / serious / warning
  levels (feed from the risk & early warning system).
- **Strong and weak performance indicators** — the university's best and worst
  KPIs at a glance.
- **Drill-down / roll-up navigation** — the signature feature of Section 12:
  a hierarchy table where clicking a row drills down from the university total
  to faculties and then to departments, and clicking again rolls back up.

## How to run

No installation, no server, no dependencies — open `index.html` in any browser
(double-click it). Everything is a single self-contained HTML file.

## Note

This is a **demo**: all figures are mock data. In the full system every tile
would link to its source module (finance, KPI monitoring, risk system, etc.)
for further drill-down.
