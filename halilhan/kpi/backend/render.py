"""View layer for Part 8 - University Performance Management & Monitoring.

All HTML is rendered here, in Python: the page shell lives in
frontend/templates/page.html and this module fills in the dynamic fragments
(summary tiles, the KPI list, form options) before the server sends it out.
KPI rows use <details>/<summary>, so expanding a row needs no JavaScript.
"""
import html
from pathlib import Path
from string import Template

import db

TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "frontend" / "templates" / "page.html"
SHELL = Template(TEMPLATE_FILE.read_text(encoding="utf-8"))

STATUS_STYLE = {
    "On Track": ("var(--good)", "✓"),
    "Delayed": ("var(--warning)", "!"),
    "At Risk": ("var(--critical)", "▲"),
}


def esc(text):
    return html.escape(str(text), quote=True)


def fmt(value, unit):
    if value is None:
        return "—"
    text = f"{value:g}"
    return f"₺{text}M" if unit == "₺M" else f"{text}{unit}"


def chip(status):
    color, icon = STATUS_STYLE[status]
    return (f'<span class="chip"><span class="dot" style="background:{color}"></span>'
            f'{icon} {status}</span>')


# ---------- fragments ----------
def summary_tiles(kpi_list):
    def count(status):
        return sum(1 for k in kpi_list if k["status"] == status)

    def tile(label, value, color=""):
        dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
        return (f'<div class="tile"><div class="label">{label}</div>'
                f'<div class="value">{dot}{value}</div></div>')

    return "".join([
        tile("KPIs tracked", len(kpi_list)),
        tile("On track", count("On Track"), "var(--good)"),
        tile("Delayed", count("Delayed"), "var(--warning)"),
        tile("At risk", count("At Risk"), "var(--critical)"),
    ])


def faculty_bars(kpi):
    if not kpi["faculties"]:
        return '<span class="hint">No faculty breakdown recorded for this KPI yet.</span>'
    maximum = max(kpi["faculties"] + [1])
    rows = []
    for name, value in zip(db.faculties(), kpi["faculties"]):
        width = value / maximum * 100
        rows.append(f'''
        <div class="mini-row" title="{esc(name)}: {fmt(value, kpi["unit"])}">
          <span class="dim">{esc(name)}</span>
          <div class="track"><div class="fill" style="width:{width:.1f}%"></div></div>
          <span class="v">{value:g}</span>
        </div>''')
    return "".join(rows)


def detail(kpi):
    if kpi["prev"] is not None:
        arrow = "▲" if kpi["cur"] >= kpi["prev"] else "▼"
        difference = f"{abs(kpi['cur'] - kpi['prev']):g}"
        change = f"{arrow} {difference}{'M' if kpi['unit'] == '₺M' else kpi['unit']}"
    else:
        change = "—"
    return f'''
    <div class="detail-grid">
      <div>
        <h4>Trend &amp; benchmarks</h4>
        Previous year: <b>{fmt(kpi["prev"], kpi["unit"])}</b><br>
        University-wide average: <b>{fmt(kpi["avg"], kpi["unit"])}</b><br>
        Change vs previous year: <b>{change}</b>
      </div>
      <div>
        <h4>Faculty comparison</h4>
        {faculty_bars(kpi)}
      </div>
      <div>
        <h4>Recommended corrective action</h4>
        {esc(kpi["action"])}
      </div>
    </div>'''


def kpi_rows(kpi_list):
    rows = []
    for kpi in kpi_list:
        color, _ = STATUS_STYLE[kpi["status"]]
        width = min(kpi["ach"], 100)
        rows.append(f'''
        <details class="kpi">
          <summary>
            <span><span class="kname">{esc(kpi["name"])}</span><span class="dim">{esc(kpi["dim"])}</span></span>
            <span class="num">{fmt(kpi["cur"], kpi["unit"])}</span>
            <span class="num">{fmt(kpi["target"], kpi["unit"])}</span>
            <span class="ach">
              <span class="track"><span class="fill" style="width:{width:.1f}%;background:{color}"></span></span>
              <span class="pct">{kpi["ach"]:.0f}%</span>
            </span>
            <span>{chip(kpi["status"])} <span class="expander"></span></span>
          </summary>
          <div class="detail">{detail(kpi)}</div>
        </details>''')
    if not rows:
        rows.append('<div class="empty">No KPIs match the current filters.</div>')
    return "".join(rows)


def options(values, selected=""):
    return "".join(
        f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(v)}</option>'
        for v in values)


def flash(message):
    if not message:
        return ""
    css_class = "flash error" if message.startswith("Error") else "flash"
    return f'<div class="{css_class}">{esc(message)}</div>'


# ---------- the page ----------
def page(dim_filter="", status_filter="", message=""):
    kpi_list = [k for k in db.kpis()
                if (not dim_filter or k["dim"] == dim_filter)
                and (not status_filter or k["status"] == status_filter)]
    measure_options = "".join(
        f'<option value="{k["id"]}">{esc(k["name"])}</option>' for k in db.kpis())
    return SHELL.substitute(
        flash=flash(message),
        summary_tiles=summary_tiles(kpi_list),
        dim_options=options(db.dimensions(), dim_filter),
        status_options=options(["On Track", "Delayed", "At Risk"], status_filter),
        kpi_rows=kpi_rows(kpi_list),
        measure_options=measure_options,
        dim_datalist="".join(f'<option value="{esc(d)}">' for d in db.dimensions()),
    )
