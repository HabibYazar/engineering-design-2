"""Data layer (model) for Part 6 - Strategic Financial Analysis.

A JSON file acts as the database: the seed dataset is copied to data.json on
first run, every mutation is validated here and written back to disk.
All mutators raise ValueError with a readable message on invalid input.
"""
import json
import shutil
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
SEED_FILE = BASE / "seed_data.json"
DATA_FILE = BASE / "data.json"

_lock = threading.Lock()


def _load():
    if not DATA_FILE.exists():
        shutil.copyfile(SEED_FILE, DATA_FILE)
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


db = _load()


def _save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _require_year(year):
    data = db["years"].get(year)
    if data is None:
        raise ValueError("unknown academic year")
    return data


def _number(raw, field, minimum=None):
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum:g}")
    return value


# ---------- queries ----------
def years():
    return list(db["years"])


def year_data(year):
    return _require_year(year)


# ---------- mutations ----------
def book_entry(year, kind, category, amount):
    """Book an amount onto a revenue/expenditure category (creates the
    category if it is new; negative amounts act as corrections)."""
    with _lock:
        data = _require_year(year)
        if kind not in ("revenue", "expenditure"):
            raise ValueError("type must be revenue or expenditure")
        category = (category or "").strip()
        if not category:
            raise ValueError("category is required")
        amount = _number(amount, "amount")
        if amount == 0:
            raise ValueError("amount must not be zero")
        cats = data[kind]
        cats[category] = max(0, round(cats.get(category, 0) + amount, 2))
        _save()
        return cats[category]


def upsert_department(year, name, students, revenue, expenditure, budget):
    """Add a department, or update it if the name already exists."""
    with _lock:
        data = _require_year(year)
        name = (name or "").strip()
        if not name:
            raise ValueError("department name is required")
        record = {
            "name": name,
            "students": int(_number(students, "students", minimum=0)),
            "revenue": _number(revenue, "revenue", minimum=0),
            "expenditure": _number(expenditure, "expenditure", minimum=0),
            "budget": _number(budget, "budget", minimum=0),
        }
        for i, dep in enumerate(data["departments"]):
            if dep["name"].lower() == name.lower():
                data["departments"][i] = record
                _save()
                return "updated"
        data["departments"].append(record)
        _save()
        return "added"


def update_stats(year, students, graduates):
    """Set the student / graduate headcounts used by the per-student ratios.
    Either field may be left blank to keep its current value."""
    with _lock:
        data = _require_year(year)
        changed = False
        if str(students).strip():
            data["students"] = int(_number(students, "students", minimum=0))
            changed = True
        if str(graduates).strip():
            data["graduates"] = int(_number(graduates, "graduates", minimum=0))
            changed = True
        if not changed:
            raise ValueError("enter students and/or graduates to update")
        _save()


def add_year(label):
    """Open a new academic year with the same category structure, zeroed."""
    with _lock:
        label = (label or "").strip()
        if not label:
            raise ValueError("year label is required (e.g. 2026-27)")
        if label in db["years"]:
            raise ValueError("that year already exists")
        template = list(db["years"].values())[-1]
        db["years"][label] = {
            "students": 0,
            "graduates": 0,
            "revenue": {cat: 0 for cat in template["revenue"]},
            "expenditure": {cat: 0 for cat in template["expenditure"]},
            "departments": [],
        }
        _save()


def reset():
    """Restore the seed dataset (handy before a live demo)."""
    with _lock:
        shutil.copyfile(SEED_FILE, DATA_FILE)
        db.clear()
        db.update(_load())
