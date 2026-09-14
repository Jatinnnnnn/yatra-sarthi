"""Itinerary planner and weather-aware replanner.

The planner is a scoring engine over the POI database:
  score = interest match + seasonal fit + rating + budget fit + group fit
POIs are grouped by geographic cluster so a day never mixes far-apart regions,
then packed day-by-day (2-3 POIs per day depending on min_days weights).

The replanner takes an existing plan plus the 7-day forecast: on days graded
'alert' or 'caution' it swaps outdoor POIs with indoor/mixed alternatives from
the same cluster, and annotates each day with the weather call.
"""

from datetime import date, timedelta

from ..database import get_conn, rows_to_dicts
from . import weather as weather_svc

CLUSTER_HUBS = {
    "rishikesh_corridor": "Rishikesh",
    "kumaon_lakes": "Nainital",
    "chardham_garhwal": "Joshimath",
    "high_kumaon": "Munsiyari",
}

# typical time spent at a spot, in minutes, by category
DWELL_MIN = {
    "pilgrimage": 90, "sightseeing": 90, "nature": 120, "heritage": 120,
    "lake": 120, "hill_station": 150, "adventure": 180, "wildlife": 210,
    "trek": 240, "camping": 180,
}

VISIT_TIP = {
    "pilgrimage": "Darshan + aarti time; keep footwear counter token safely.",
    "nature": "Carry water and wear grip shoes near wet rocks.",
    "heritage": "Guided walk recommended; photography usually allowed.",
    "lake": "Boating queue is shortest right after opening.",
    "hill_station": "Cafes and viewpoints; keep a light jacket.",
    "adventure": "Report 15 min early for safety briefing and gear.",
    "wildlife": "Safari slots are fixed — reach the gate 30 min early.",
    "trek": "Start early; carry 2L water and a rain layer.",
    "camping": "Check-in by late afternoon for bonfire slots.",
    "sightseeing": "Best light for photos before noon.",
}


def _fmt(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {suffix}"


def _travel_minutes(prev_hub, prev_district, stop) -> int:
    if prev_hub and prev_hub == stop.get("nearest_hub"):
        return 30
    if prev_district and prev_district == stop.get("district"):
        return 60
    return 90


def _schedule_day(stops, hub):
    """Build an hour-by-hour schedule: breakfast, travel legs, visits with
    dwell times, a lunch break, and the evening return to the stay.
    If the raw plan would run past ~7 PM, visit dwell times are compressed
    proportionally so the traveller is back before dinner."""
    # -- pre-compute fixed time (breakfast, travel legs, lunch, return) and
    #    raw dwell wishes, then compress only the dwells to fit 08:00-19:00
    fixed, prev_hub_c, prev_district_c = 30 + 45 + 40, hub, None  # breakfast+lunch+return
    dwells = []
    for s in stops:
        fixed += _travel_minutes(prev_hub_c, prev_district_c, s)
        dwells.append(300 if s.get("note") == "continued" else DWELL_MIN.get(s["category"], 120))
        prev_hub_c, prev_district_c = s.get("nearest_hub"), s.get("district")
    budget_minutes = (19 * 60) - (8 * 60)  # 08:00 -> 19:00
    dwell_budget = max(45 * max(1, len(stops)), budget_minutes - fixed)
    total_dwell = sum(dwells) or 1
    scale = min(1.0, dwell_budget / total_dwell)
    dwell_final = {i: max(45, int(dw * scale / 15) * 15) for i, dw in enumerate(dwells)}

    items = []
    t = 8 * 60  # 08:00
    items.append({"kind": "meal", "icon": "🍳", "start": _fmt(t), "end": _fmt(t + 30),
                  "title": f"Breakfast at your stay in {hub}",
                  "note": "Pack water, cap and power bank before leaving."})
    t += 30
    lunch_done = False
    prev_hub, prev_district = hub, None

    for i, s in enumerate(stops):
        leg = _travel_minutes(prev_hub, prev_district, s)
        items.append({"kind": "travel", "icon": "🚕", "start": _fmt(t), "end": _fmt(t + leg),
                      "title": f"Drive to {s['name']}",
                      "note": f"≈ {leg} min from {prev_hub or 'your last stop'}."})
        t += leg

        dwell = dwell_final[i]
        if s.get("note") == "continued":
            tip = "Continue at your own pace — this activity spans multiple days."
        else:
            tip = VISIT_TIP.get(s["category"], "")
        items.append({"kind": "visit", "icon": "📍", "start": _fmt(t), "end": _fmt(t + dwell),
                      "title": s["name"],
                      "note": f"Spend ≈ {dwell // 60} hr {dwell % 60 or ''}".rstrip() +
                              (f" min. {tip}" if dwell % 60 else f". {tip}"),
                      "stop": s})
        t += dwell

        if not lunch_done and t >= 12 * 60 + 30 and i < len(stops) - 1:
            items.append({"kind": "meal", "icon": "🍛", "start": _fmt(t), "end": _fmt(t + 45),
                          "title": "Lunch break — try a nearby local dhaba",
                          "note": "Pahadi thali or rajma-chawal; book via Local Bazaar."})
            t += 45
            lunch_done = True

        prev_hub, prev_district = s.get("nearest_hub"), s.get("district")

    back = 40
    items.append({"kind": "travel", "icon": "🚕", "start": _fmt(t), "end": _fmt(t + back),
                  "title": f"Return to your stay in {hub}",
                  "note": "Keep buffer for hill traffic near sunset."})
    t += back
    items.append({"kind": "meal", "icon": "🌙", "start": _fmt(t), "end": "",
                  "title": "Evening free — dinner and local market walk",
                  "note": "Ganga aarti / mall road stroll if nearby."})
    return items

GROUP_PREF = {
    "family": {"pilgrimage": 2, "lake": 2, "hill_station": 2, "nature": 1, "heritage": 1, "wildlife": 1},
    "friends": {"adventure": 3, "camping": 2, "trek": 2, "wildlife": 1, "lake": 1},
    "couple": {"hill_station": 2, "lake": 2, "nature": 2, "camping": 1, "heritage": 1},
    "solo": {"trek": 2, "adventure": 2, "heritage": 1, "pilgrimage": 1, "nature": 1},
}

INTEREST_CATEGORY = {
    "adventure": {"adventure", "trek", "camping"},
    "pilgrimage": {"pilgrimage"},
    "nature": {"nature", "lake", "hill_station", "trek"},
    "wildlife": {"wildlife"},
    "heritage": {"heritage"},
    "hill_station": {"hill_station", "lake"},
}


def _load_pois():
    conn = get_conn()
    pois = rows_to_dicts(conn.execute("SELECT * FROM pois").fetchall())
    conn.close()
    for p in pois:
        p["best_months"] = {int(x) for x in str(p["best_months"]).split(",") if x.strip()}
        p["tags"] = p["tags"].split(";")
    return pois


def _score(poi, month, interests, group_type, budget_per_day):
    s = poi["rating"] * 2.0
    if month in poi["best_months"]:
        s += 3.0
    else:
        s -= 2.5
    for interest in interests:
        if poi["category"] in INTEREST_CATEGORY.get(interest, set()):
            s += 3.0
    if group_type:
        s += GROUP_PREF.get(group_type, {}).get(poi["category"], 0)
    if budget_per_day:
        if poi["cost_per_day"] + poi["entry_fee"] * 0.5 > budget_per_day:
            s -= 3.0
        else:
            s += 1.0
    if poi["crowd"] == "low":
        s += 0.5
    return s


def _pick_cluster(pois, month, interests, group_type, budget_per_day, destination):
    if destination:
        dest = destination.lower()
        for p in pois:
            if dest in p["name"].lower() or dest in p["nearest_hub"].lower() or dest in p["district"].lower():
                return p["cluster"]
        alias = {
            "mussoorie": "rishikesh_corridor", "dehradun": "rishikesh_corridor",
            "haridwar": "rishikesh_corridor", "rishikesh": "rishikesh_corridor",
            "nainital": "kumaon_lakes", "jim corbett": "kumaon_lakes",
            "auli": "chardham_garhwal", "kedarnath": "chardham_garhwal",
            "badrinath": "chardham_garhwal", "chopta": "chardham_garhwal",
            "munsiyari": "high_kumaon",
        }
        if dest in alias:
            return alias[dest]
    totals = {}
    for p in pois:
        totals.setdefault(p["cluster"], 0.0)
        totals[p["cluster"]] += max(0.0, _score(p, month, interests, group_type, budget_per_day))
    return max(totals, key=totals.get)


def build_plan(days=4, month=None, budget=None, group_type=None,
               interests=None, destination=None, start=None):
    interests = interests or []
    today = date.today()
    month = month or today.month
    if start is None:
        if month == today.month:
            start = today + timedelta(days=1)
        else:
            year = today.year if month > today.month else today.year + 1
            start = date(year, month, 10)
    days = max(1, min(9, int(days)))
    budget_per_day = (budget / days) if budget else None

    pois = _load_pois()
    cluster = _pick_cluster(pois, month, interests, group_type, budget_per_day, destination)
    pool = [p for p in pois if p["cluster"] == cluster]
    ranked = sorted(pool, key=lambda p: _score(p, month, interests, group_type, budget_per_day), reverse=True)

    per_day = 2 if cluster in ("chardham_garhwal", "high_kumaon") else 3
    chosen, used_days = [], 0.0
    for p in ranked:
        weight = max(0.34, (p["min_days"] if p["min_days"] > 1 else 1) / per_day)
        if used_days + weight > days + 0.2:
            continue
        chosen.append(p)
        used_days += weight
        if used_days >= days:
            break

    # pack into day buckets
    day_plans = [[] for _ in range(days)]
    load = [0.0] * days
    for p in sorted(chosen, key=lambda x: -x["min_days"]):
        weight = max(0.34, (p["min_days"] if p["min_days"] > 1 else 1) / per_day)
        idx = min(range(days), key=lambda i: load[i])
        if p["min_days"] > 1:
            # multi-day POI occupies consecutive days
            idx = min(range(days - p["min_days"] + 1), key=lambda i: sum(load[i:i + p["min_days"]])) if days >= p["min_days"] else 0
            for j in range(idx, min(days, idx + p["min_days"])):
                day_plans[j].append(p)
                load[j] += 1.0
        else:
            day_plans[idx].append(p)
            load[idx] += weight

    for dp in day_plans:
        dp.sort(key=lambda x: -x["rating"])

    hub = CLUSTER_HUBS[cluster]
    est_cost = 0
    itinerary = []
    seen_multi = set()
    for i, dp in enumerate(day_plans):
        d = start + timedelta(days=i)
        stops = []
        day_cost = 900  # stay + food base
        for p in dp:
            key = p["id"]
            note = ""
            if p["min_days"] > 1:
                if key in seen_multi:
                    note = "continued"
                seen_multi.add(key)
            stops.append({
                "id": p["id"], "name": p["name"], "category": p["category"],
                "setting": p["setting"], "description": p["description"],
                "district": p["district"], "rating": p["rating"],
                "entry_fee": p["entry_fee"], "image": p["image"],
                "tags": p["tags"], "note": note, "nearest_hub": p["nearest_hub"],
            })
            if note != "continued":
                day_cost += p["entry_fee"]
            day_cost += max(0, p["cost_per_day"] - 900) // max(1, len(dp))
        est_cost += day_cost
        itinerary.append({
            "day": i + 1,
            "date": d.isoformat(),
            "label": d.strftime("%a, %d %b"),
            "stops": stops,
            "schedule": _schedule_day(stops, hub),
            "day_cost": int(day_cost),
        })

    # events in the travel month near this cluster
    conn = get_conn()
    events = rows_to_dicts(conn.execute(
        "SELECT * FROM events WHERE month = ? LIMIT 4", (month,)).fetchall())

    # local-business places that actually fall on this trip:
    # the hub + the nearest hubs of every stop that have businesses listed
    trip_towns = {hub}
    for dp in day_plans:
        for p in dp:
            trip_towns.add(p["nearest_hub"])
    biz_places = [r["place"] for r in conn.execute(
        "SELECT DISTINCT place FROM businesses").fetchall()]
    bazaar_places = sorted(t for t in trip_towns if t in biz_places)
    conn.close()

    return {
        "cluster": cluster,
        "hub": hub,
        "days": days,
        "month": month,
        "group_type": group_type or "general",
        "interests": interests,
        "budget": budget,
        "est_cost": int(est_cost),
        "start_date": start.isoformat(),
        "itinerary": itinerary,
        "events": events,
        "bazaar_places": bazaar_places,
    }


# ------------------------------------------------------------- replanning

def apply_weather(plan: dict) -> dict:
    """Annotate each plan day with weather and swap risky outdoor stops."""
    pois = _load_pois()
    by_id = {p["id"]: p for p in pois}
    cluster_pool = [p for p in pois if p["cluster"] == plan["cluster"]]
    indoor_pool = [p for p in cluster_pool if p["setting"] in ("indoor", "mixed")]
    used_ids = {s["id"] for d in plan["itinerary"] for s in d["stops"]}

    changes = []
    for day in plan["itinerary"]:
        d = date.fromisoformat(day["date"])
        wx = weather_svc.day_weather(plan["hub"], d)
        day["weather"] = wx
        if wx["safety"] in ("alert", "caution"):
            new_stops = []
            for stop in day["stops"]:
                is_multi_day = by_id.get(stop["id"], {}).get("min_days", 1) > 1
                if stop["setting"] == "outdoor" and stop["note"] != "continued" and not is_multi_day:
                    replacement = next(
                        (p for p in sorted(indoor_pool, key=lambda x: -x["rating"])
                         if p["id"] not in used_ids), None)
                    if replacement:
                        used_ids.add(replacement["id"])
                        changes.append({
                            "day": day["day"],
                            "removed": stop["name"],
                            "added": replacement["name"],
                            "reason": f"{wx['condition']} expected ({wx['safety']})",
                        })
                        new_stops.append({
                            "id": replacement["id"], "name": replacement["name"],
                            "category": replacement["category"],
                            "setting": replacement["setting"],
                            "description": replacement["description"],
                            "district": replacement["district"],
                            "rating": replacement["rating"],
                            "entry_fee": replacement["entry_fee"],
                            "image": replacement["image"],
                            "tags": replacement["tags"],
                            "note": "weather swap",
                            "nearest_hub": replacement["nearest_hub"],
                        })
                        continue
                if stop["setting"] == "outdoor" and is_multi_day and wx["safety"] == "alert" and not stop["note"]:
                    stop["note"] = "check advisory"
                new_stops.append(stop)
            day["stops"] = new_stops
            # stops changed -> rebuild the hour-by-hour schedule for this day
            day["schedule"] = _schedule_day(new_stops, plan["hub"])
    plan["weather_changes"] = changes
    plan["replanned"] = bool(changes)
    return plan
