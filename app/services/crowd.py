"""Crowd Advisor.

Estimates a live crowd score (0-100) for every famous destination using:
  * the POI's typical footfall class (low / medium / high)
  * seasonality — whether the visit month is in the POI's best months
  * weekend / long-weekend uplift
  * yatra-season uplift for Char Dham shrines (May-Jun, Sep-Oct)
  * a deterministic day-hash jitter (same place + date => same score)

When a place is OVERCROWDED or BUSY, the advisor looks up the curated
alternatives dataset (data/alternatives.csv) and returns nearby lesser-known
substitutes with distance, travel time and the *reason* they work as a
replacement — the core decongestion feature of the platform.
"""

import hashlib
from datetime import date

from ..database import get_conn, rows_to_dicts

BASE = {"low": 28, "medium": 50, "high": 68}

CHARDHAM = {"kedarnath", "badrinath", "gangotri", "yamunotri", "hemkund"}


def _jitter(name: str, d: date) -> int:
    h = int(hashlib.sha256(f"{name.lower()}|{d.isoformat()}".encode()).hexdigest()[:6], 16)
    return (h % 21) - 10  # -10 .. +10


def crowd_score(poi: dict, d: date | None = None) -> dict:
    d = d or date.today()
    score = BASE.get(poi["crowd"], 45)
    best_months = {int(x) for x in str(poi["best_months"]).split(",") if str(x).strip()}
    if d.month in best_months:
        score += 14
    if d.weekday() >= 5:          # Sat/Sun
        score += 12
    elif d.weekday() == 4:        # Friday evening starts
        score += 5
    low_name = poi["name"].lower()
    if any(k in low_name for k in CHARDHAM) and d.month in (5, 6, 9, 10):
        score += 15
    score += _jitter(poi["name"], d)
    score = max(5, min(98, score))

    if score >= 75:
        level, label = "overcrowded", "Overcrowded"
        advice = "Expect long queues, parking trouble and surge pricing. Strongly consider the alternative below."
    elif score >= 55:
        level, label = "busy", "Busy"
        advice = "Manageable but crowded at peak hours — go before 9 AM or after 4 PM, or pick the quieter alternative."
    else:
        level, label = "comfortable", "Comfortable"
        advice = "Footfall is comfortable right now. Good time to visit."

    return {"score": score, "level": level, "label": label, "advice": advice}


def get_alternatives(poi_name: str, place_hint: str = "") -> list[dict]:
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        "SELECT * FROM alternatives WHERE lower(famous) = lower(?)", (poi_name,)).fetchall())
    if not rows and place_hint:
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM alternatives WHERE lower(famous) = lower(?)", (place_hint,)).fetchall())
    if not rows:
        # fuzzy: famous name contained in poi name or vice versa
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM alternatives WHERE instr(lower(?), lower(famous)) > 0 "
            "OR instr(lower(famous), lower(?)) > 0",
            (poi_name, poi_name)).fetchall())
    conn.close()
    return rows


CATEGORY_LABEL = {
    "pilgrimage": "temple/darshan", "adventure": "adventure", "trek": "trekking",
    "nature": "nature", "lake": "lakeside", "hill_station": "hill-station",
    "wildlife": "wildlife", "heritage": "heritage", "camping": "camping",
    "sightseeing": "sightseeing",
}


def _fallback_alternatives(poi: dict) -> list[dict]:
    """If no curated alternative exists, suggest the best low-crowd POI of the
    same category in the same circuit — an automatic decongestion substitute."""
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        "SELECT * FROM pois WHERE cluster = ? AND category = ? AND crowd = 'low' "
        "AND id != ? ORDER BY rating DESC LIMIT 2",
        (poi["cluster"], poi["category"], poi["id"])).fetchall())
    if not rows:
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM pois WHERE cluster = ? AND crowd = 'low' AND id != ? "
            "ORDER BY rating DESC LIMIT 2", (poi["cluster"], poi["id"])).fetchall())
    conn.close()
    return [{
        "famous": poi["name"], "alternative": r["name"], "district": r["district"],
        "distance_km": 0, "travel_time": f"near {r['nearest_hub']}",
        "reason": (f"A quieter {CATEGORY_LABEL.get(r['category'], r['category'])} option "
                   f"in the same circuit — {r['description']} "
                   f"Typical footfall stays low even in season."),
        "best_for": CATEGORY_LABEL.get(r["category"], r["category"]),
        "typical_crowd": "low",
    } for r in rows]


def advisor_board(d: date | None = None) -> list[dict]:
    """Crowd status + alternatives for every 'famous' (medium/high) POI."""
    d = d or date.today()
    conn = get_conn()
    pois = rows_to_dicts(conn.execute(
        "SELECT * FROM pois WHERE crowd IN ('high','medium') ORDER BY rating DESC").fetchall())
    conn.close()
    board = []
    for p in pois:
        status = crowd_score(p, d)
        entry = {
            "id": p["id"], "name": p["name"], "district": p["district"],
            "image": p["image"], "category": p["category"], "rating": p["rating"],
            "nearest_hub": p["nearest_hub"], **status,
            "alternatives": [],
        }
        if status["level"] in ("overcrowded", "busy"):
            alts = get_alternatives(p["name"], p["nearest_hub"])
            entry["alternatives"] = alts or _fallback_alternatives(p)
        board.append(entry)
    order = {"overcrowded": 0, "busy": 1, "comfortable": 2}
    board.sort(key=lambda e: (order[e["level"]], -e["score"]))
    return board


def check_place(query: str, d: date | None = None) -> dict | None:
    """Crowd status for a single place searched by name."""
    d = d or date.today()
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pois WHERE lower(name) LIKE lower(?) OR lower(nearest_hub) = lower(?) "
        "ORDER BY CASE crowd WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, rating DESC LIMIT 1",
        (f"%{query}%", query)).fetchone()
    conn.close()
    if not row:
        return None
    p = dict(row)
    status = crowd_score(p, d)
    return {
        "id": p["id"], "name": p["name"], "district": p["district"],
        "image": p["image"], "category": p["category"], "rating": p["rating"],
        "nearest_hub": p["nearest_hub"], **status,
        "alternatives": ((get_alternatives(p["name"], p["nearest_hub"])
                          or _fallback_alternatives(p))
                         if status["level"] in ("overcrowded", "busy") else []),
    }
