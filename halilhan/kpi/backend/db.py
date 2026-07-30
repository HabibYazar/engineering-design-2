"""Data layer (model) for Part 8 - University Performance Management & Monitoring.

A JSON file acts as the database: the seed dataset is copied to kpis.json on
first run, every mutation is validated here and written back to disk.

The risk status of every KPI is computed HERE, from its achievement rate and
per-KPI configurable thresholds (as the project description requires
thresholds to be configurable by management):

    achievement >= thresholds.on    ->  On Track   (default 90%)
    achievement <  thresholds.risk  ->  At Risk    (default 70%)
    otherwise                       ->  Delayed
"""
import json
import shutil
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
SEED_FILE = BASE / "seed_kpis.json"
DATA_FILE = BASE / "kpis.json"

DEFAULT_THRESHOLDS = {"on": 90, "risk": 70}

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


def _number(raw, field, minimum=None):
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum:g}")
    return value


def evaluate(kpi):
    """Return the KPI plus its computed achievement rate and risk status."""
    achievement = kpi["cur"] / kpi["target"] * 100 if kpi["target"] else 0
    thresholds = kpi.get("thresholds") or DEFAULT_THRESHOLDS
    if achievement >= thresholds["on"]:
        status = "On Track"
    elif achievement < thresholds["risk"]:
        status = "At Risk"
    else:
        status = "Delayed"
    return {**kpi, "ach": round(achievement, 1), "status": status}


# ---------- queries ----------
def faculties():
    return db["faculties"]


def kpis():
    return [evaluate(k) for k in db["kpis"]]


def dimensions():
    return sorted({k["dim"] for k in db["kpis"]})


# ---------- mutations ----------
def add_kpi(name, dim, unit, cur, target, prev, avg, action):
    """Register a new KPI to monitor (prev/avg may be blank)."""
    with _lock:
        name = (name or "").strip()
        dim = (dim or "").strip()
        if not name or not dim:
            raise ValueError("KPI name and strategic dimension are required")
        if any(k["name"].lower() == name.lower() for k in db["kpis"]):
            raise ValueError("a KPI with that name already exists")
        kpi = {
            "id": max((k["id"] for k in db["kpis"]), default=0) + 1,
            "dim": dim,
            "name": name,
            "unit": (unit or "").strip(),
            "cur": _number(cur, "current value", minimum=0),
            "target": _number(target, "target", minimum=0),
            "prev": _number(prev, "previous year", minimum=0) if str(prev).strip() else None,
            "avg": _number(avg, "university average", minimum=0) if str(avg).strip() else None,
            "faculties": None,  # no per-faculty breakdown recorded yet
            "action": (action or "").strip() or "No corrective action defined yet.",
        }
        if kpi["target"] <= 0:
            raise ValueError("target must be greater than zero")
        db["kpis"].append(kpi)
        _save()
        return evaluate(kpi)


def record_measurement(kpi_id, value):
    """Record a new current value for a KPI; its status is re-derived."""
    with _lock:
        try:
            kpi = next(k for k in db["kpis"] if k["id"] == int(kpi_id))
        except (StopIteration, TypeError, ValueError):
            raise ValueError("unknown KPI")
        kpi["cur"] = _number(value, "value", minimum=0)
        _save()
        return evaluate(kpi)


def reset():
    """Restore the seed dataset (handy before a live demo)."""
    with _lock:
        shutil.copyfile(SEED_FILE, DATA_FILE)
        db.clear()
        db.update(_load())
