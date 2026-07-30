"""View layer for Part 6 - Strategic Financial Analysis.

All HTML is rendered here, in Python: the page shell lives in
frontend/templates/page.html and this module fills in the dynamic fragments
(tiles, bar charts, tables, form options) before the server sends it out.
"""
import html
from pathlib import Path
from string import Template

import db

TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "frontend" / "templates" / "page.html"
SHELL = Template(TEMPLATE_FILE.read_text(encoding="utf-8"))


# ---------- formatting helpers ----------
def esc(text):
    return html.escape(str(text), quote=True)


def fmt_m(value):
    """486 -> '₺486M', 21.5 -> '₺21.5M' (millions of TRY)."""
    text = f"{round(value, 1):,.1f}".rstrip("0").rstrip(".")
    return f"₺{text}M"


def fmt_k(value):
    return f"₺{round(value):,}K"


def pct(part, whole):
    return f"{part / whole * 100:.1f}%" if whole > 0 else "—"


# ---------- fragments ----------
def tile(label, value, delta=""):
    return (f'<div class="tile"><div class="label">{label}</div>'
            f'<div class="value">{value}</div>{delta}</div>')


def tiles(data):
    revenue = sum(data["revenue"].values())
    expenditure = sum(data["expenditure"].values())
    balance = revenue - expenditure
    personnel = (data["expenditure"].get("Academic staff salaries", 0)
                 + data["expenditure"].get("Administrative staff salaries", 0))
    research = data["revenue"].get("Research project revenues", 0)
    scholarships = data["expenditure"].get("Scholarship expenditures", 0)
    students, graduates = data["students"], data["graduates"]
    balance_delta = (f'<div class="delta {"up" if balance >= 0 else "down"}">'
                     f'{"▲ surplus" if balance >= 0 else "▼ deficit"}</div>')
    return "".join([
        tile("Total revenue", fmt_m(revenue)),
        tile("Total expenditure", fmt_m(expenditure)),
        tile("Revenue–expenditure balance", fmt_m(balance), balance_delta),
        tile("Revenue / student", fmt_k(revenue * 1000 / students) if students else "—"),
        tile("Cost / student", fmt_k(expenditure * 1000 / students) if students else "—"),
        tile("Cost / graduate", f"₺{expenditure / graduates:.2f}M" if graduates else "—"),
        tile("Personnel / total expenditure", pct(personnel, expenditure)),
        tile("Research income share", pct(research, revenue)),
        tile("Scholarship impact on revenue", pct(scholarships, revenue)),
    ])


def bar_chart(categories):
    maximum = max(list(categories.values()) + [1])
    rows = []
    for name, value in categories.items():
        width = value / maximum * 100
        rows.append(f'''
        <div class="bar-row" title="{esc(name)}: {fmt_m(value)}">
          <span class="name">{esc(name)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>
          <span class="val">{fmt_m(value)}</span>
        </div>''')
    return "".join(rows)


def status_chip(realization):
    if realization <= 100:
        color, text = "var(--good)", "✓ Within budget"
    elif realization <= 108:
        color, text = "var(--warning)", "! Slightly over"
    else:
        color, text = "var(--critical)", "✗ Over budget"
    return (f'<span class="chip"><span class="dot" style="background:{color}"></span>'
            f'{text}</span>')


def department_rows(data):
    rows = []
    for dep in data["departments"]:
        balance = dep["revenue"] - dep["expenditure"]
        sign = "+" if balance >= 0 else "−"
        realization = dep["expenditure"] / dep["budget"] * 100 if dep["budget"] else 0
        rows.append(f'''
        <tr>
          <td>{esc(dep["name"])}</td><td>{dep["students"]:,}</td>
          <td>{fmt_m(dep["revenue"])}</td><td>{fmt_m(dep["expenditure"])}</td>
          <td class="{"pos" if balance >= 0 else "neg"}">{sign}{fmt_m(abs(balance))[1:]}</td>
          <td>{fmt_k(dep["expenditure"] * 1000 / dep["students"]) if dep["students"] else "—"}</td>
          <td>{f"{realization:.1f}%" if dep["budget"] else "—"}</td>
          <td>{status_chip(realization) if dep["budget"] else ""}</td>
        </tr>''')
    if not rows:
        rows.append('<tr><td colspan="8" style="text-align:center;color:var(--muted)">'
                    'No departments yet — add one below.</td></tr>')
    return "".join(rows)


def options(values, selected):
    return "".join(
        f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(v)}</option>'
        for v in values)


def datalist_options(values):
    return "".join(f'<option value="{esc(v)}">' for v in values)


def flash(message):
    if not message:
        return ""
    css_class = "flash error" if message.startswith("Error") else "flash"
    return f'<div class="{css_class}">{esc(message)}</div>'


# ---------- the page ----------
def page(year, message=""):
    data = db.year_data(year)
    year_options = options(db.years(), year)
    categories = list(data["revenue"]) + [c for c in data["expenditure"] if c not in data["revenue"]]
    return SHELL.substitute(
        flash=flash(message),
        year_options=year_options,
        tiles=tiles(data),
        rev_total=f"Total: {fmt_m(sum(data['revenue'].values()))}",
        exp_total=f"Total: {fmt_m(sum(data['expenditure'].values()))}",
        rev_bars=bar_chart(data["revenue"]),
        exp_bars=bar_chart(data["expenditure"]),
        dept_rows=department_rows(data),
        cat_options=datalist_options(categories),
        dept_options=datalist_options(dep["name"] for dep in data["departments"]),
    )
