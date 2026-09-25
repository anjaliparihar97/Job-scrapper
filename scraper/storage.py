"""
SQLite-backed storage for deduplication.

Every job we've ever seen gets written here. On each run we diff freshly
scraped jobs against this table so the email only ever contains jobs we
haven't already sent - i.e. "give me the latest job postings" without
repeating yesterday's email every day.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from scraper.models import JobPosting

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "seen_jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    job_id       TEXT PRIMARY KEY,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    location     TEXT,
    first_seen   TEXT NOT NULL
);
"""


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def filter_new_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    """Return only the jobs that are not already in the database."""
    if not jobs:
        return []
    with get_connection() as conn:
        existing_ids = {
            row[0]
            for row in conn.execute("SELECT job_id FROM seen_jobs").fetchall()
        }
    return [job for job in jobs if job.job_id not in existing_ids]


def mark_jobs_as_seen(jobs: list[JobPosting]) -> None:
    """Persist jobs so future runs know not to re-send them."""
    if not jobs:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO seen_jobs
                (job_id, company, title, url, location, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (j.job_id, j.company, j.title, j.url, j.location, j.scraped_at)
                for j in jobs
            ],
        )


def stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
        by_company = conn.execute(
            "SELECT company, COUNT(*) FROM seen_jobs GROUP BY company"
        ).fetchall()
    return {"total_jobs_tracked": total, "by_company": dict(by_company)}
