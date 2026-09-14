"""SQLite database layer for Yatra Sarthi.

Reference datasets (POIs, hotels, transport, events, local businesses,
crowd alternatives) live as auditable CSV files in data/ and are loaded into
SQLite tables at startup. Runtime tables (users, sessions, bookings,
query log, generated plans, feedback) are stored in the same database file.
"""

import csv
import hashlib
import os
import secrets
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "yatrasarthi.db")

_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def _migrate(conn):
    """Upgrade an existing database created by an older version in place.
    Adds columns that newer code expects, without touching stored data."""
    needed = {
        "plans": [("user_id", "INTEGER")],
        "query_log": [("user_id", "INTEGER")],
        "feedback": [("user_id", "INTEGER")],
    }
    for table, cols in needed.items():
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            continue
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ctype in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")


def _load_csv(conn, table, csv_name, columns):
    count = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    if count:
        return
    path = os.path.join(DATA_DIR, csv_name)
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    placeholders = ",".join(["?"] * len(columns))
    conn.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        [tuple(r[c] for c in columns) for r in rows],
    )


def init_db():
    with _lock:
        conn = get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pois (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                district TEXT NOT NULL,
                cluster TEXT NOT NULL,
                category TEXT NOT NULL,
                setting TEXT NOT NULL,
                best_months TEXT NOT NULL,
                cost_per_day INTEGER NOT NULL,
                entry_fee INTEGER NOT NULL,
                min_days INTEGER NOT NULL,
                rating REAL NOT NULL,
                crowd TEXT NOT NULL,
                nearest_hub TEXT NOT NULL,
                tags TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hotels (
                name TEXT NOT NULL, place TEXT NOT NULL, type TEXT NOT NULL,
                band TEXT NOT NULL, price_per_night INTEGER NOT NULL,
                rating REAL NOT NULL, notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transport (
                destination TEXT PRIMARY KEY, nearest_railhead TEXT NOT NULL,
                rail_km INTEGER NOT NULL, nearest_airport TEXT NOT NULL,
                air_km INTEGER NOT NULL, bus_route TEXT NOT NULL,
                road_note TEXT NOT NULL, local_transport TEXT NOT NULL,
                taxi_fare_est INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                name TEXT NOT NULL, place TEXT NOT NULL, month INTEGER NOT NULL,
                duration_days INTEGER NOT NULL, note TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, place TEXT NOT NULL, type TEXT NOT NULL,
                speciality TEXT NOT NULL, price INTEGER NOT NULL,
                price_unit TEXT NOT NULL, rating REAL NOT NULL,
                contact TEXT NOT NULL, note TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alternatives (
                famous TEXT NOT NULL, alternative TEXT NOT NULL,
                district TEXT NOT NULL, distance_km INTEGER NOT NULL,
                travel_time TEXT NOT NULL, reason TEXT NOT NULL,
                best_for TEXT NOT NULL, typical_crowd TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'traveller'
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                business_id INTEGER NOT NULL REFERENCES businesses(id),
                visit_date TEXT NOT NULL,
                people INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'confirmed'
            );
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                user_id INTEGER,
                message TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                entities TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                user_id INTEGER,
                destination TEXT NOT NULL,
                days INTEGER NOT NULL,
                month INTEGER NOT NULL,
                budget INTEGER NOT NULL,
                group_type TEXT NOT NULL,
                interests TEXT NOT NULL,
                est_cost INTEGER NOT NULL,
                replanned INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                user_id INTEGER,
                rating INTEGER NOT NULL,
                comment TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _migrate(conn)
        _load_csv(conn, "pois", "pois.csv", [
            "id", "name", "district", "cluster", "category", "setting",
            "best_months", "cost_per_day", "entry_fee", "min_days", "rating",
            "crowd", "nearest_hub", "tags", "description", "image",
        ])
        _load_csv(conn, "hotels", "hotels.csv", [
            "name", "place", "type", "band", "price_per_night", "rating", "notes",
        ])
        _load_csv(conn, "transport", "transport.csv", [
            "destination", "nearest_railhead", "rail_km", "nearest_airport",
            "air_km", "bus_route", "road_note", "local_transport", "taxi_fare_est",
        ])
        _load_csv(conn, "events", "events.csv", [
            "name", "place", "month", "duration_days", "note",
        ])
        _load_csv(conn, "businesses", "businesses.csv", [
            "name", "place", "type", "speciality", "price", "price_unit",
            "rating", "contact", "note",
        ])
        _load_csv(conn, "alternatives", "alternatives.csv", [
            "famous", "alternative", "district", "distance_km", "travel_time",
            "reason", "best_for", "typical_crowd",
        ])
        # seed demo accounts (password shown in README for the demo)
        if not conn.execute("SELECT 1 FROM users WHERE email='admin@yatrasarthi.in'").fetchone():
            conn.execute(
                "INSERT INTO users (full_name, email, password_hash, role) VALUES (?,?,?,?)",
                ("Tourism Admin", "admin@yatrasarthi.in", hash_password("admin@123"), "admin"),
            )
        conn.commit()
        conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
