"""
Database layer for AutoJob AI.
Supports dual-mode storage:
- Cloud PostgreSQL (Neon / Supabase / AWS RDS) when DATABASE_URL is set in environment.
- Local SQLite fallback (config/data/autojob.db) when running offline/locally.
"""

import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Path for local SQLite storage
DATA_DIR = Path("config/data")
SQLITE_DB_PATH = DATA_DIR / "autojob.db"

# Check if PostgreSQL connection string is provided
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def get_connection():
    """
    Returns a database connection.
    If DATABASE_URL is defined, attempts PostgreSQL (Neon).
    Otherwise, returns local SQLite connection.
    """
    if DATABASE_URL:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            return conn, "postgres"
        except Exception as e:
            print(f"[Database Warning] Failed to connect to PostgreSQL ({e}). Falling back to SQLite.")

    # SQLite local fallback
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def init_db():
    """
    Initializes database tables if they do not exist.
    Compatible with both PostgreSQL and SQLite dialects.
    """
    conn, dialect = get_connection()
    try:
        cur = conn.cursor()
        if dialect == "postgres":
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_applications (
                    app_id VARCHAR(100) PRIMARY KEY,
                    date_applied VARCHAR(50),
                    company VARCHAR(255),
                    job_title VARCHAR(255),
                    category VARCHAR(100),
                    location VARCHAR(255),
                    job_url TEXT,
                    platform VARCHAR(100),
                    status VARCHAR(100),
                    apply_mode VARCHAR(100),
                    match_pct NUMERIC(5, 2),
                    chance VARCHAR(100),
                    last_updated VARCHAR(50),
                    follow_up_date VARCHAR(50),
                    gmail_thread_id VARCHAR(255),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key VARCHAR(100) PRIMARY KEY,
                    value JSONB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_applications (
                    app_id TEXT PRIMARY KEY,
                    date_applied TEXT,
                    company TEXT,
                    job_title TEXT,
                    category TEXT,
                    location TEXT,
                    job_url TEXT,
                    platform TEXT,
                    status TEXT,
                    apply_mode TEXT,
                    match_pct REAL,
                    chance TEXT,
                    last_updated TEXT,
                    follow_up_date TEXT,
                    gmail_thread_id TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
    finally:
        conn.close()


def save_application(app_data: Dict[str, Any]) -> bool:
    """
    Inserts or updates a job application in the database.
    """
    conn, dialect = get_connection()
    try:
        cur = conn.cursor()
        fields = [
            "app_id", "date_applied", "company", "job_title", "category",
            "location", "job_url", "platform", "status", "apply_mode",
            "match_pct", "chance", "last_updated", "follow_up_date",
            "gmail_thread_id", "notes"
        ]
        values = [app_data.get(f, "") for f in fields]

        if dialect == "postgres":
            placeholders = ", ".join(["%s"] * len(fields))
            cols = ", ".join(fields)
            update_clause = ", ".join([f"{f} = EXCLUDED.{f}" for f in fields if f != "app_id"])
            query = f"""
                INSERT INTO job_applications ({cols})
                VALUES ({placeholders})
                ON CONFLICT (app_id) DO UPDATE SET {update_clause};
            """
        else:
            placeholders = ", ".join(["?"] * len(fields))
            cols = ", ".join(fields)
            query = f"""
                INSERT OR REPLACE INTO job_applications ({cols})
                VALUES ({placeholders});
            """
        cur.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        print(f"[Database Error] Failed to save application {app_data.get('app_id')}: {e}")
        return False
    finally:
        conn.close()


def get_all_applications(limit: int = 500) -> List[Dict[str, Any]]:
    """
    Retrieves latest job applications from the active database.
    """
    conn, dialect = get_connection()
    try:
        cur = conn.cursor()
        query = f"SELECT * FROM job_applications ORDER BY date_applied DESC LIMIT {limit};"
        cur.execute(query)
        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append(dict(r))
        return results
    except Exception as e:
        print(f"[Database Error] Failed to fetch applications: {e}")
        return []
    finally:
        conn.close()


# Initialize tables when module is imported
try:
    init_db()
except Exception as _e:
    pass
