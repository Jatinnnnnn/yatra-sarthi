# Yatra Sarthi — Smart Tourism Assistant for Uttarakhand

**Smart India Hackathon 2026 · Problem Statement ID 26204 (AICTE, MIC-Student Innovation · Theme: Travel & Tourism · Category: Software)**

> *"Student Innovation — A solution/idea that can boost the current situation of the tourism industries including hotels, travel and others."*

Yatra Sarthi is a one-stop smart tourism platform piloted for **Uttarakhand**. Travellers **sign up / log in**, then type plain-language queries (English or Hinglish); the system parses the **intent** with a machine-learning classifier, extracts trip details, and responds with the right service — a **day-wise itinerary**, a **7-day weather and safety outlook**, **transport routing**, or the **festival calendar**. Risky weather days are **replanned automatically**. The **Crowd Advisor** flags overcrowded famous spots and recommends nearby lesser-known alternatives *with the reason they work* — the decongestion feature. The **Local Bazaar** lets travellers book verified local restaurants, guides, taxis, artisans and experiences directly, putting money into hill families' hands. A **role-protected analytics dashboard** gives the tourism department live demand and local-economy signals.

## Login accounts

| Role | How |
|---|---|
| Traveller | Create an account on the login page (any email + password) |
| Tourism-department admin | `admin@yatrasarthi.in` / `admin@123` → opens `/admin` dashboard |

---

## Feature overview

| Module | What it does |
|---|---|
| **Travel Assistant** | Natural-language chat. TF-IDF + Logistic Regression intent classifier (11 intents, 120+ labelled utterances) + rule-based entity extractor (destination, days, month, budget, group type, interests). |
| **Trip Planner** | Scores 50 POIs on interest match, seasonal fit, rating, budget fit and group fit; groups by geographic circuit (Rishikesh corridor, Kumaon lakes, Char Dham Garhwal, High Kumaon); packs a day-wise itinerary with per-day cost and total estimate. |
| **Weather & Safety Watch** | 7-day forecast per destination from district climate normals with deterministic variation, graded into `good / watch / caution / alert` travel-safety levels with advisories. Single integration point — swappable with the IMD/live API. |
| **Auto Replanning** | For `alert`/`caution` days the planner swaps outdoor stops with indoor/mixed POIs of the same circuit and shows exactly what changed and why. |
| **Transport Adviser** | Rail / air / bus / road / local guidance for 23 gateway towns, plus a recommended mode based on railhead distance and estimated taxi fare. |
| **Explore** | Filterable, searchable database of 50 verified POIs across 13 districts with real destination photos. |
| **Hotels** | 30 stays across bands (dharamshala → heritage) surfaced by the assistant. |
| **Events** | 16 fairs & festivals month-wise (Kanwar Yatra, Uttarayani Mela, kapat opening/closing…). |
| **Crowd Advisor** | Live crowd score (0-100) per famous spot from footfall class + seasonality + weekend/yatra uplift. Overcrowded/busy spots show curated nearby alternatives with distance, travel time and reason (24-row dataset), with an automatic same-circuit fallback so no crowded spot is ever left without an alternative. |
| **Local Bazaar** | 30 verified local businesses (restaurants, cafes, taxis, rentals, guides, adventure co-ops, artisans, experiences) with in-app **booking** (reference number, my-bookings list, cancellation). |
| **Accounts** | Signup/login with PBKDF2-hashed passwords and session cookies; all pages and APIs are auth-gated server-side; `/admin` requires the admin role. |
| **Feedback** | 5-star rating + comment stored in the database. |
| **Admin Analytics** | `/admin` — registered users, query volume, intent mix, most-planned hubs, **bookings by business type, top booked businesses**, group split, seasonality, weather-replan count, average feedback, recent parsed queries. |

## Tech stack

- **Backend:** Python **FastAPI** + Uvicorn
- **Intent parser (ML):** scikit-learn — TF-IDF (1–2 grams) + Logistic Regression, trained from `data/intents.csv` at startup and cached (`intent_model.joblib`)
- **Database:** **SQLite** (`data/yatrasarthi.db`) — reference tables loaded from auditable CSV datasets + runtime tables (`query_log`, `plans`, `feedback`)
- **Frontend:** hand-written **HTML + CSS + JavaScript** (no framework), responsive, real tourist photography

## Datasets (show these to the judges)

| File | Contents |
|---|---|
| `data/pois.csv` | 50 points of interest: district, circuit, category, best months, costs, rating, crowd level, nearest hub, tags, description, photo |
| `data/transport.csv` | 23 gateways: nearest railhead/airport with distances, bus routes, road condition notes, local transport, taxi fare estimates |
| `data/hotels.csv` | 30 stays with type, band, tariff, rating |
| `data/events.csv` | 16 fairs & festivals with month and duration |
| `data/intents.csv` | 120+ labelled utterances across 11 intents used to train the classifier |
| `data/businesses.csv` | 30 local businesses with speciality, price, contact and community note |
| `data/alternatives.csv` | 24 curated overcrowding alternatives: famous spot → nearby quieter option with distance, travel time and reason |

## Run it

```bash
cd YatraSarthi
python -m venv .venv
.venv\Scripts\activate        # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** — you land on the **login page** first.
Sign up as a traveller, or use the admin account for **/admin**.
Interactive API docs: **http://localhost:8000/docs**.

## Project structure

```
YatraSarthi/
├── app/
│   ├── main.py                  # FastAPI app: auth, all API routes, page guards
│   ├── database.py              # SQLite schema, CSV loading, password hashing
│   └── services/
│       ├── intent_parser.py     # ML intent classifier + entity extractor
│       ├── planner.py           # itinerary scoring engine + weather replanner
│       ├── weather.py           # 7-day forecast + safety grading
│       ├── crowd.py             # crowd scoring + decongestion alternatives
│       └── transport.py         # route adviser
├── data/                        # datasets (CSV) + SQLite db + trained model
├── frontend/
│   ├── login.html               # signup / sign-in (entry point)
│   ├── index.html               # home + assistant
│   ├── planner.html             # trip planner
│   ├── explore.html             # destination explorer with crowd badges
│   ├── crowd.html               # crowd advisor board + place check
│   ├── bazaar.html              # local business directory + bookings
│   ├── info.html                # transport, weather, events, feedback
│   ├── admin.html               # analytics dashboard (admin only)
│   ├── css/style.css
│   ├── js/                      # common.js + one file per page
│   └── img/                     # destination photos
└── requirements.txt
```

## How it boosts the tourism industry (pitch points)

1. **Converts interest into bookings** — a complete plan with costs removes the biggest drop-off point for first-time hill travellers.
2. **Safety-first travel** — weather-graded days and automatic replanning reduce monsoon/snow-season incidents and cancellations.
3. **Crowd distribution** — the Crowd Advisor actively redirects travellers from overcrowded icons to nearby offbeat spots with a concrete reason, spreading tourist income beyond Nainital/Mussoorie and reducing pressure on fragile sites.
4. **Direct local-economy support** — the Local Bazaar books local restaurants, guides, taxi unions, artisan collectives and village experiences with zero commission in the prototype; the admin dashboard shows which business types earn the most bookings.
5. **Data for the department** — the admin dashboard shows real demand: what travellers ask, where they plan, which months — enabling targeted campaigns and capacity planning.
6. **Scales beyond the pilot** — every dataset is a CSV/DB table; adding another state is a data task, not a code rewrite.
