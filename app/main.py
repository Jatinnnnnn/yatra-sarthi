"""Yatra Sarthi — Smart Tourism Assistant for Uttarakhand.

FastAPI backend:
  * /api/auth/*        — signup / login / logout / me (session cookie)
  * /api/assistant     — NL query -> ML intent parser -> smart reply
  * /api/plan          — itinerary planner (+ weather replanning)
  * /api/weather       — 7-day forecast with safety grading
  * /api/transport     — how-to-reach adviser
  * /api/crowd/*       — crowd advisor + decongestion alternatives
  * /api/businesses    — local business directory (restaurants, guides, taxis…)
  * /api/bookings      — book a local business / list my bookings
  * /api/pois|hotels|events|feedback — data services
  * /api/admin/*       — analytics (admin role only)
  * pages              — login + multi-page site (auth-gated server side)
"""

import json
import os
import secrets
from datetime import date

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from .database import (get_conn, hash_password, init_db, rows_to_dicts,
                       verify_password)
from .services import crowd, intent_parser, planner, transport, weather

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI(title="Yatra Sarthi", version="2.0",
              description="Smart Tourism Assistant for Uttarakhand — SIH 2026 PS 26204")

COOKIE = "ys_session"


@app.on_event("startup")
def startup():
    init_db()
    intent_parser.load_model()


# ------------------------------------------------------------------ auth

class SignupIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _user_from_token(token: str | None):
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT u.id, u.full_name, u.email, u.role FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def current_user(ys_session: str | None = Cookie(default=None)):
    user = _user_from_token(ys_session)
    if not user:
        raise HTTPException(401, "Login required")
    return user


def admin_user(user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access only")
    return user


def _start_session(response: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    conn = get_conn()
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?,?)", (token, user_id))
    conn.commit()
    conn.close()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)


@app.post("/api/auth/signup")
def signup(body: SignupIn, response: Response):
    conn = get_conn()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (body.email.lower(),)).fetchone():
        conn.close()
        raise HTTPException(409, "An account with this email already exists")
    cur = conn.execute(
        "INSERT INTO users (full_name, email, password_hash) VALUES (?,?,?)",
        (body.full_name.strip(), body.email.lower(), hash_password(body.password)))
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    _start_session(response, user_id)
    return {"ok": True, "full_name": body.full_name, "role": "traveller"}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email.lower(),)).fetchone()
    conn.close()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    _start_session(response, row["id"])
    return {"ok": True, "full_name": row["full_name"], "role": row["role"]}


@app.post("/api/auth/logout")
def logout(response: Response, ys_session: str | None = Cookie(default=None)):
    if ys_session:
        conn = get_conn()
        conn.execute("DELETE FROM sessions WHERE token = ?", (ys_session,))
        conn.commit()
        conn.close()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return user


# --------------------------------------------------------------- assistant

class AssistantQuery(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def _log_query(message, parsed, user_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO query_log (user_id, message, intent, confidence, entities) VALUES (?,?,?,?,?)",
        (user_id, message, parsed["intent"], parsed["confidence"], json.dumps(parsed["entities"])))
    conn.commit()
    conn.close()


@app.post("/api/assistant")
def assistant(q: AssistantQuery, user: dict = Depends(current_user)):
    parsed = intent_parser.parse(q.message)
    _log_query(q.message, parsed, user["id"])
    intent = parsed["intent"]
    ent = parsed["entities"]
    payload = {"parsed": parsed, "type": intent}

    if intent == "greeting":
        payload["reply"] = (f"Namaste {user['full_name'].split()[0]}! I am Yatra Sarthi. Ask me to plan a trip, "
                            "check crowd levels, find local food and guides, or check weather and routes.")

    elif intent == "plan_trip":
        plan = planner.build_plan(
            days=ent["days"] or 4, month=ent["month"], budget=ent["budget"],
            group_type=ent["group_type"], interests=ent["interests"],
            destination=ent["destination"])
        plan = planner.apply_weather(plan)
        _save_plan(plan, user["id"])
        payload["plan"] = plan
        payload["reply"] = (f"Here is a {plan['days']}-day plan around {plan['hub']} — "
                            f"estimated ₹{plan['est_cost']:,} per person. Open the Planner page for the full view.")

    elif intent == "ask_weather":
        place = ent["destination"] or "Nainital"
        payload["weather"] = weather.get_forecast(place)
        payload["reply"] = f"7-day outlook for {place.title()} with travel-safety grading:"

    elif intent == "ask_transport":
        place = ent["destination"] or "Nainital"
        advice = transport.advise(place)
        if advice:
            payload["transport"] = advice
            payload["reply"] = f"How to reach {advice['destination']}: {advice['recommended']}"
        else:
            payload["reply"] = ("I have route data for major gateways — try Nainital, Mussoorie, "
                                "Kedarnath, Auli, Chopta, Munsiyari and more.")

    elif intent == "find_hotel":
        place = ent["destination"] or ""
        conn = get_conn()
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM hotels WHERE place LIKE ? ORDER BY rating DESC LIMIT 6",
            (f"%{place}%",)).fetchall())
        if not rows:
            rows = rows_to_dicts(conn.execute(
                "SELECT * FROM hotels ORDER BY rating DESC LIMIT 6").fetchall())
        conn.close()
        payload["hotels"] = rows
        payload["reply"] = (f"Stay options in {place.title()}:" if place else "Top-rated stays:")

    elif intent == "ask_budget":
        days = ent["days"] or 4
        base = 1400 * days + 1200
        comfort = 2600 * days + 2500
        payload["reply"] = (f"A {days}-day trip typically costs ₹{base:,} per person on a budget and "
                            f"₹{comfort:,} with comfort stays. The Planner gives an exact day-wise estimate.")

    elif intent == "events":
        month = ent["month"] or date.today().month
        conn = get_conn()
        rows = rows_to_dicts(conn.execute("SELECT * FROM events WHERE month = ?", (month,)).fetchall())
        if not rows:
            rows = rows_to_dicts(conn.execute("SELECT * FROM events ORDER BY month LIMIT 5").fetchall())
        conn.close()
        payload["events"] = rows
        payload["reply"] = "Fairs and festivals you can catch:"

    elif intent == "emergency":
        payload["reply"] = ("Emergency contacts — Disaster Helpline 1070, Tourist Helpline 1364, "
                            "Police 112, Ambulance 108, Char Dham Control Room 0135-2559898.")

    else:
        # sightseeing / adventure / pilgrimage -> POIs, with crowd status attached
        conn = get_conn()
        clauses, params = [], []
        if ent["destination"]:
            clauses.append("(name LIKE ? OR district LIKE ? OR nearest_hub LIKE ?)")
            d = f"%{ent['destination']}%"
            params += [d, d, d]
        if intent == "adventure":
            clauses.append("category IN ('adventure','trek','camping')")
        if intent == "pilgrimage":
            clauses.append("category = 'pilgrimage'")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = rows_to_dicts(conn.execute(
            f"SELECT * FROM pois {where} ORDER BY rating DESC LIMIT 6", params).fetchall())
        if not rows:
            rows = rows_to_dicts(conn.execute(
                "SELECT * FROM pois ORDER BY rating DESC LIMIT 6").fetchall())
        conn.close()
        for r in rows:
            r["crowd_now"] = crowd.crowd_score(r)
        payload["pois"] = rows
        payload["reply"] = "Here is what I found (with live crowd status):"

    return payload


# ------------------------------------------------------------------- plan

class PlanRequest(BaseModel):
    destination: str | None = None
    days: int = Field(default=4, ge=1, le=9)
    month: int | None = Field(default=None, ge=1, le=12)
    budget: int | None = Field(default=None, ge=1000, le=500000)
    group_type: str | None = None
    interests: list[str] = []


def _save_plan(plan, user_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO plans (user_id, destination, days, month, budget, group_type, interests, est_cost, replanned) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, plan["hub"], plan["days"], plan["month"], plan["budget"] or 0,
         plan["group_type"], ",".join(plan["interests"]), plan["est_cost"],
         1 if plan.get("replanned") else 0))
    conn.commit()
    conn.close()


@app.post("/api/plan")
def make_plan(req: PlanRequest, user: dict = Depends(current_user)):
    plan = planner.build_plan(
        days=req.days, month=req.month, budget=req.budget,
        group_type=req.group_type, interests=req.interests,
        destination=req.destination)
    plan = planner.apply_weather(plan)
    _save_plan(plan, user["id"])
    return plan


# ------------------------------------------------------------ crowd advisor

@app.get("/api/crowd/board")
def crowd_board(user: dict = Depends(current_user)):
    return {"date": date.today().isoformat(), "board": crowd.advisor_board()}


@app.get("/api/crowd/check")
def crowd_check(place: str = Query(min_length=2), user: dict = Depends(current_user)):
    result = crowd.check_place(place)
    if not result:
        raise HTTPException(404, "Place not found in the destination database")
    return result


# --------------------------------------------------------- local businesses

class BookingIn(BaseModel):
    business_id: int
    visit_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    people: int = Field(ge=1, le=30)
    note: str = Field(default="", max_length=300)


@app.get("/api/businesses")
def businesses(place: str | None = None, places: str | None = None,
               type: str | None = None, user: dict = Depends(current_user)):
    clauses, params = [], []
    if places:  # comma-separated list of trip towns from the planner
        towns = [t.strip() for t in places.split(",") if t.strip()][:12]
        if towns:
            clauses.append("(" + " OR ".join(["place = ?"] * len(towns)) + ")")
            params += towns
    elif place:
        clauses.append("place LIKE ?"); params.append(f"%{place}%")
    if type:
        clauses.append("type = ?"); params.append(type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        f"SELECT * FROM businesses {where} ORDER BY rating DESC", params).fetchall())
    types = [r["type"] for r in conn.execute("SELECT DISTINCT type FROM businesses ORDER BY type")]
    places = [r["place"] for r in conn.execute("SELECT DISTINCT place FROM businesses ORDER BY place")]
    conn.close()
    return {"businesses": rows, "types": types, "places": places}


@app.post("/api/bookings")
def create_booking(body: BookingIn, user: dict = Depends(current_user)):
    conn = get_conn()
    biz = conn.execute("SELECT * FROM businesses WHERE id = ?", (body.business_id,)).fetchone()
    if not biz:
        conn.close()
        raise HTTPException(404, "Business not found")
    cur = conn.execute(
        "INSERT INTO bookings (user_id, business_id, visit_date, people, note) VALUES (?,?,?,?,?)",
        (user["id"], body.business_id, body.visit_date, body.people, body.note))
    conn.commit()
    booking_id = cur.lastrowid
    conn.close()
    return {"ok": True, "booking_id": booking_id, "business": biz["name"],
            "reference": f"YS-{booking_id:05d}"}


@app.get("/api/bookings")
def my_bookings(user: dict = Depends(current_user)):
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        "SELECT b.id, b.created_at, b.visit_date, b.people, b.note, b.status, "
        "biz.name, biz.place, biz.type, biz.price, biz.price_unit, biz.contact "
        "FROM bookings b JOIN businesses biz ON biz.id = b.business_id "
        "WHERE b.user_id = ? ORDER BY b.id DESC", (user["id"],)).fetchall())
    conn.close()
    return {"bookings": rows}


@app.delete("/api/bookings/{booking_id}")
def cancel_booking(booking_id: int, user: dict = Depends(current_user)):
    conn = get_conn()
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=? AND user_id=?",
                 (booking_id, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


# ------------------------------------------------------------ data lookups

@app.get("/api/weather")
def api_weather(place: str = Query(min_length=2), user: dict = Depends(current_user)):
    return weather.get_forecast(place)


@app.get("/api/transport")
def api_transport(destination: str = Query(min_length=2), user: dict = Depends(current_user)):
    advice = transport.advise(destination)
    if not advice:
        raise HTTPException(404, "No route data for this destination")
    return advice


@app.get("/api/transport/destinations")
def api_transport_dests(user: dict = Depends(current_user)):
    return {"destinations": transport.all_destinations()}


@app.get("/api/pois")
def api_pois(category: str | None = None, district: str | None = None,
             q: str | None = None, limit: int = Query(default=50, le=100),
             user: dict = Depends(current_user)):
    clauses, params = [], []
    if category:
        clauses.append("category = ?"); params.append(category)
    if district:
        clauses.append("district = ?"); params.append(district)
    if q:
        clauses.append("(name LIKE ? OR tags LIKE ? OR description LIKE ?)")
        params += [f"%{q}%"] * 3
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    rows = rows_to_dicts(conn.execute(
        f"SELECT * FROM pois {where} ORDER BY rating DESC LIMIT ?", params + [limit]).fetchall())
    cats = [r["category"] for r in conn.execute("SELECT DISTINCT category FROM pois ORDER BY category")]
    dists = [r["district"] for r in conn.execute("SELECT DISTINCT district FROM pois ORDER BY district")]
    conn.close()
    for r in rows:
        r["crowd_now"] = crowd.crowd_score(r)
    return {"pois": rows, "categories": cats, "districts": dists}


@app.get("/api/hotels")
def api_hotels(place: str | None = None, user: dict = Depends(current_user)):
    conn = get_conn()
    if place:
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM hotels WHERE place LIKE ? ORDER BY rating DESC", (f"%{place}%",)).fetchall())
    else:
        rows = rows_to_dicts(conn.execute("SELECT * FROM hotels ORDER BY rating DESC").fetchall())
    conn.close()
    return {"hotels": rows}


@app.get("/api/events")
def api_events(month: int | None = Query(default=None, ge=1, le=12),
               user: dict = Depends(current_user)):
    conn = get_conn()
    if month:
        rows = rows_to_dicts(conn.execute("SELECT * FROM events WHERE month = ?", (month,)).fetchall())
    else:
        rows = rows_to_dicts(conn.execute("SELECT * FROM events ORDER BY month").fetchall())
    conn.close()
    return {"events": rows}


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


@app.post("/api/feedback")
def api_feedback(fb: FeedbackIn, user: dict = Depends(current_user)):
    conn = get_conn()
    conn.execute("INSERT INTO feedback (user_id, rating, comment) VALUES (?,?,?)",
                 (user["id"], fb.rating, fb.comment))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------------------------------------------------------- admin

@app.get("/api/admin/analytics")
def admin_analytics(user: dict = Depends(admin_user)):
    conn = get_conn()
    intents = rows_to_dicts(conn.execute(
        "SELECT intent, COUNT(*) count FROM query_log GROUP BY intent ORDER BY count DESC").fetchall())
    recent = rows_to_dicts(conn.execute(
        "SELECT created_at, message, intent, confidence FROM query_log ORDER BY id DESC LIMIT 12").fetchall())
    hubs = rows_to_dicts(conn.execute(
        "SELECT destination, COUNT(*) count, AVG(days) avg_days, AVG(est_cost) avg_cost "
        "FROM plans GROUP BY destination ORDER BY count DESC").fetchall())
    groups = rows_to_dicts(conn.execute(
        "SELECT group_type, COUNT(*) count FROM plans GROUP BY group_type ORDER BY count DESC").fetchall())
    months = rows_to_dicts(conn.execute(
        "SELECT month, COUNT(*) count FROM plans GROUP BY month ORDER BY month").fetchall())
    biz_types = rows_to_dicts(conn.execute(
        "SELECT biz.type, COUNT(*) count FROM bookings b JOIN businesses biz ON biz.id=b.business_id "
        "WHERE b.status='confirmed' GROUP BY biz.type ORDER BY count DESC").fetchall())
    biz_top = rows_to_dicts(conn.execute(
        "SELECT biz.name, biz.place, COUNT(*) count FROM bookings b JOIN businesses biz ON biz.id=b.business_id "
        "WHERE b.status='confirmed' GROUP BY biz.id ORDER BY count DESC LIMIT 8").fetchall())
    totals = conn.execute(
        "SELECT (SELECT COUNT(*) FROM users WHERE role='traveller') users,"
        " (SELECT COUNT(*) FROM query_log) queries,"
        " (SELECT COUNT(*) FROM plans) plans,"
        " (SELECT COUNT(*) FROM plans WHERE replanned=1) replans,"
        " (SELECT COUNT(*) FROM bookings WHERE status='confirmed') bookings,"
        " (SELECT COUNT(*) FROM businesses) businesses,"
        " (SELECT COUNT(*) FROM pois) pois,"
        " (SELECT COALESCE(ROUND(AVG(rating),2),0) FROM feedback) avg_feedback,"
        " (SELECT COUNT(*) FROM feedback) feedback_count").fetchone()
    conn.close()
    return {
        "totals": dict(totals),
        "intents": intents,
        "recent_queries": recent,
        "popular_hubs": hubs,
        "group_split": groups,
        "month_split": months,
        "booking_types": biz_types,
        "top_businesses": biz_top,
    }


# -------------------------------------------------------------- pages

def _page(name):
    return FileResponse(os.path.join(FRONTEND_DIR, name))


def _guarded_page(name, ys_session, admin_only=False):
    user = _user_from_token(ys_session)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if admin_only and user["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    return _page(name)


@app.get("/login")
def login_page(ys_session: str | None = Cookie(default=None)):
    if _user_from_token(ys_session):
        return RedirectResponse("/", status_code=303)
    return _page("login.html")


@app.get("/")
def home_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("index.html", ys_session)


@app.get("/planner")
def planner_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("planner.html", ys_session)


@app.get("/explore")
def explore_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("explore.html", ys_session)


@app.get("/crowd")
def crowd_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("crowd.html", ys_session)


@app.get("/bazaar")
def bazaar_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("bazaar.html", ys_session)


@app.get("/info")
def info_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("info.html", ys_session)


@app.get("/admin")
def admin_page(ys_session: str | None = Cookie(default=None)):
    return _guarded_page("admin.html", ys_session, admin_only=True)


app.mount("/static/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/static/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
app.mount("/static/img", StaticFiles(directory=os.path.join(FRONTEND_DIR, "img")), name="img")
