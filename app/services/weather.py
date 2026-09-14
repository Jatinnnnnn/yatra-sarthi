"""Weather service — LIVE + fallback.

Primary source: Open-Meteo public forecast API (free, no API key).
Every destination has real coordinates; the 7-day daily forecast is fetched
live, converted from WMO weather codes to readable conditions, graded into
travel-safety levels, and cached for 30 minutes per place.

If the machine is offline or the API is unreachable, the service silently
falls back to the built-in climate-normals simulation so the app never
breaks during a demo. Each forecast is tagged with its `source`:
"live" (Open-Meteo) or "model" (simulated).
"""

import hashlib
import json
import random
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

# ------------------------------------------------------------------ places

# name -> (lat, lon, altitude band)
PLACES = {
    "haridwar":            (29.9457, 78.1642, "plains"),
    "rishikesh":           (30.0869, 78.2676, "plains"),
    "dehradun":            (30.3165, 78.0322, "plains"),
    "ramnagar":            (29.3947, 79.1314, "plains"),
    "jim corbett":         (29.5300, 78.7747, "plains"),
    "mussoorie":           (30.4598, 78.0644, "mid"),
    "dhanaulti":           (30.4278, 78.2397, "mid"),
    "new tehri":           (30.3782, 78.4806, "mid"),
    "nainital":            (29.3919, 79.4542, "mid"),
    "bhimtal":             (29.3444, 79.5631, "mid"),
    "mukteshwar":          (29.4722, 79.6479, "mid"),
    "ranikhet":            (29.6434, 79.4322, "mid"),
    "almora":              (29.5971, 79.6591, "mid"),
    "kausani":             (29.8432, 79.6033, "mid"),
    "chakrata":            (30.7044, 77.8690, "mid"),
    "uttarkashi":          (30.7268, 78.4354, "mid"),
    "chaukori":            (29.8543, 80.0937, "mid"),
    "kasar devi":          (29.6415, 79.6540, "mid"),
    "jageshwar":           (29.6367, 79.8525, "mid"),
    "gangolihat":          (29.6539, 80.0450, "mid"),
    "berinag":             (29.7736, 80.0524, "mid"),
    "chopta":              (30.4880, 79.1934, "high"),
    "auli":                (30.5262, 79.5672, "high"),
    "joshimath":           (30.5553, 79.5644, "high"),
    "munsiyari":           (30.0672, 80.2384, "high"),
    "harsil":              (31.0384, 78.7402, "high"),
    "barkot":              (30.8088, 78.2050, "high"),
    "sonprayag":           (30.6317, 78.9932, "high"),
    "govindghat":          (30.6216, 79.5563, "high"),
    "valley of flowers":   (30.7280, 79.6053, "high"),
    "kedarnath":           (30.7346, 79.0669, "alpine"),
    "badrinath":           (30.7433, 79.4938, "alpine"),
    "gangotri":            (30.9946, 78.9398, "alpine"),
    "yamunotri":           (31.0142, 78.4600, "alpine"),
    "hemkund":             (30.7008, 79.6153, "alpine"),
    "tungnath":            (30.4890, 79.2158, "alpine"),
    "chandrashila":        (30.4924, 79.2205, "alpine"),
}

DEFAULT_COORDS = PLACES["nainital"]

# WMO weather interpretation codes -> readable condition
WMO = {
    0: "Clear", 1: "Sunny", 2: "Partly cloudy", 3: "Cloudy",
    45: "Cloudy", 48: "Cloudy",
    51: "Light rain", 53: "Light rain", 55: "Rain",
    56: "Light rain", 57: "Rain",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Rain", 67: "Heavy rain",
    71: "Snowfall", 73: "Snowfall", 75: "Snowfall", 77: "Snowfall",
    80: "Light rain", 81: "Rain", 82: "Heavy rain",
    85: "Snowfall", 86: "Snowfall",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL = 30 * 60  # 30 minutes
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _place_key(place: str) -> str:
    p = place.strip().lower()
    if p in PLACES:
        return p
    for name in PLACES:                      # fuzzy: "kedarnath temple" -> kedarnath
        if name in p or p in name:
            return name
    return "nainital"


def _band(place: str) -> str:
    return PLACES[_place_key(place)][2]


# ------------------------------------------------------------- safety grade

def _grade(condition: str, band: str, wind: int) -> tuple[str, str]:
    if condition in ("Heavy rain", "Thunderstorm") and band in ("high", "alpine"):
        return "alert", "Landslide-prone stretch: avoid hill travel, follow district advisories."
    if condition in ("Heavy rain", "Thunderstorm"):
        return "caution", "Carry rain gear; expect slow traffic and slippery ghats."
    if condition == "Snowfall":
        return "caution", "Snow chains may be needed; roads can close briefly."
    if condition in ("Light rain", "Rain"):
        return "watch", "Light showers likely; keep indoor options handy."
    if wind >= 40:
        return "watch", "Strong winds expected on ridges and ropeways."
    return "good", "Great day for outdoor sightseeing."


# ------------------------------------------------------------------- live

def _fetch_live(place: str, days: int = 7) -> dict | None:
    """Fetch the daily forecast from Open-Meteo. Returns {iso_date: day_dict}
    or None on any failure (offline, timeout, bad response)."""
    key = _place_key(place)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]

    lat, lon, band = PLACES[key]
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
        "timezone": "Asia/Kolkata",
        "forecast_days": min(16, max(days, 7)),
    })
    try:
        req = urllib.request.Request(f"{API_URL}?{params}",
                                     headers={"User-Agent": "YatraSarthi/2.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
        daily = data["daily"]
        result = {}
        for i, iso in enumerate(daily["time"]):
            condition = WMO.get(int(daily["weather_code"][i]), "Partly cloudy")
            wind = int(round(daily["wind_speed_10m_max"][i] or 0))
            safety, advice = _grade(condition, band, wind)
            d = date.fromisoformat(iso)
            result[iso] = {
                "date": iso,
                "day": d.strftime("%a"),
                "temp_max": int(round(daily["temperature_2m_max"][i])),
                "temp_min": int(round(daily["temperature_2m_min"][i])),
                "condition": condition,
                "rain_mm": int(round(daily["precipitation_sum"][i] or 0)),
                "rain_chance": int(daily["precipitation_probability_max"][i] or 0),
                "wind_kmh": wind,
                "safety": safety,
                "advice": advice,
                "source": "live",
            }
        with _cache_lock:
            _cache[key] = (now, result)
        return result
    except Exception:
        return None


# --------------------------------------------------------- simulated model
# (fallback for offline demos and for dates beyond the live forecast window)

BANDS = {
    "plains":  {"temps": [14, 17, 22, 28, 32, 33, 30, 29, 28, 25, 20, 15], "monsoon": 0.75},
    "mid":     {"temps": [8, 10, 14, 18, 22, 23, 20, 19, 18, 16, 12, 9],   "monsoon": 0.85},
    "high":    {"temps": [1, 2, 6, 10, 13, 15, 14, 13, 12, 9, 5, 2],       "monsoon": 0.9},
    "alpine":  {"temps": [-6, -4, 0, 4, 8, 11, 10, 10, 8, 4, -1, -4],      "monsoon": 0.95},
}

CONDITIONS_DRY = ["Clear", "Sunny", "Partly cloudy", "Cloudy"]
CONDITIONS_WET = ["Light rain", "Rain", "Heavy rain", "Thunderstorm"]


def _seed(place: str, d: date) -> int:
    key = f"{place.lower()}|{d.isoformat()}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _model_day(place: str, d: date) -> dict:
    band_name = _band(place)
    band = BANDS[band_name]
    rng = random.Random(_seed(place, d))
    month = d.month
    base = band["temps"][month - 1]
    tmax = base + rng.randint(2, 6)
    tmin = base - rng.randint(3, 7)

    monsoon = month in (7, 8) or (month == 6 and rng.random() < 0.4) or (month == 9 and rng.random() < 0.35)
    rain_chance = band["monsoon"] if monsoon else {1: 0.15, 2: 0.2, 3: 0.2, 4: 0.15,
                                                   5: 0.2, 6: 0.35, 9: 0.3, 10: 0.1,
                                                   11: 0.08, 12: 0.12}.get(month, 0.15)
    raining = rng.random() < rain_chance
    if raining:
        condition = rng.choice(CONDITIONS_WET if monsoon else CONDITIONS_WET[:2])
        rain_mm = rng.randint(18, 80) if monsoon else rng.randint(2, 20)
    else:
        condition = rng.choice(CONDITIONS_DRY)
        rain_mm = 0
    if tmax <= 2 and raining:
        condition = "Snowfall"

    wind = rng.randint(4, 14) + (8 if condition == "Thunderstorm" else 0)
    safety, advice = _grade(condition, band_name, wind)
    return {
        "date": d.isoformat(),
        "day": d.strftime("%a"),
        "temp_max": tmax,
        "temp_min": tmin,
        "condition": condition,
        "rain_mm": rain_mm,
        "rain_chance": int(rain_chance * 100),
        "wind_kmh": wind,
        "safety": safety,
        "advice": advice,
        "source": "model",
    }


# ------------------------------------------------------------------ public

def day_weather(place: str, d: date | None = None) -> dict:
    """Weather for one day. Live data when the date falls inside the
    Open-Meteo window; simulated model otherwise (or when offline)."""
    d = d or date.today()
    live = _fetch_live(place)
    if live and d.isoformat() in live:
        return live[d.isoformat()]
    return _model_day(place, d)


def get_forecast(place: str, start: date | None = None, days: int = 7) -> dict:
    start = start or date.today()
    live = _fetch_live(place, days)
    forecast = []
    for i in range(days):
        d = start + timedelta(days=i)
        iso = d.isoformat()
        forecast.append(live[iso] if live and iso in live else _model_day(place, d))
    return {
        "place": place.title(),
        "band": _band(place),
        "source": "live" if forecast and forecast[0].get("source") == "live" else "model",
        "forecast": forecast,
    }
