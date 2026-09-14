"""Transport adviser.

Combines the transport reference table with simple mode recommendation logic:
given a destination (and optionally the traveller's origin style), it returns
rail / air / bus / road guidance, local transport notes and an estimated taxi
fare, plus a recommended mode based on distance bands.
"""

from ..database import get_conn, rows_to_dicts

ALIASES = {
    "kedarnath": "Sonprayag",
    "badrinath": "Joshimath",
    "auli": "Joshimath",
    "valley of flowers": "Govindghat",
    "hemkund": "Govindghat",
    "gangotri": "Uttarkashi",
    "harsil": "Uttarkashi",
    "yamunotri": "Barkot",
    "tungnath": "Chopta",
    "chandrashila": "Chopta",
    "jim corbett": "Ramnagar",
    "corbett": "Ramnagar",
    "patal bhuvaneshwar": "Gangolihat",
    "chaukori": "Berinag",
    "bhimtal": "Bhimtal",
    "naukuchiatal": "Bhimtal",
    "mukteshwar": "Mukteshwar",
    "kasar devi": "Almora",
    "jageshwar": "Almora",
    "tehri": "New Tehri",
    "dhanaulti": "Dhanaulti",
}


def advise(destination: str) -> dict | None:
    dest = destination.strip()
    key = ALIASES.get(dest.lower(), dest.title())
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM transport WHERE lower(destination) = lower(?)", (key,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    info = dict(row)

    if info["rail_km"] <= 40:
        recommended = f"Train to {info['nearest_railhead']}, then a short taxi ({info['rail_km']} km)."
    elif info["rail_km"] <= 120:
        recommended = f"Train to {info['nearest_railhead']} + shared taxi/bus for the {info['rail_km']} km hill leg."
    else:
        recommended = (f"Overnight bus or drive; start early. Nearest railhead "
                       f"{info['nearest_railhead']} is {info['rail_km']} km away.")

    steps = [
        {"mode": "rail", "detail": f"{info['nearest_railhead']} ({info['rail_km']} km away)"},
        {"mode": "air", "detail": f"{info['nearest_airport']} ({info['air_km']} km away)"},
        {"mode": "bus", "detail": info["bus_route"]},
        {"mode": "road", "detail": info["road_note"]},
        {"mode": "local", "detail": info["local_transport"]},
    ]
    return {
        "destination": dest.title(),
        "gateway": info["destination"],
        "recommended": recommended,
        "steps": steps,
        "taxi_fare_est": info["taxi_fare_est"],
    }


def all_destinations():
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        "SELECT destination FROM transport ORDER BY destination").fetchall())
    conn.close()
    return [r["destination"] for r in rows]
