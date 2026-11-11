"""SQLite storage.

Two core tables:
  videos     – one row per video (things that don't change: title, channel…)
  snapshots  – one row per video × region × fetch time (things that do: views…)

Keeping snapshots over time is what makes velocity possible: compare a
video's views now with its views at the previous fetch.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .youtube_client import TrendingVideo

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id      TEXT PRIMARY KEY,
    title         TEXT,
    channel_title TEXT,
    category_id   TEXT,
    published_at  TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    video_id   TEXT NOT NULL REFERENCES videos(video_id),
    region     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    rank       INTEGER,
    views      INTEGER,
    likes      INTEGER,
    comments   INTEGER,
    PRIMARY KEY (video_id, region, fetched_at)
);

CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name        TEXT
);

CREATE INDEX IF NOT EXISTS idx_snap_region_time ON snapshots(region, fetched_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_videos(conn: sqlite3.Connection, videos: Iterable[TrendingVideo]) -> int:
    videos = list(videos)
    with conn:
        conn.executemany(
            """INSERT INTO videos (video_id, title, channel_title, category_id, published_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET title = excluded.title""",
            [(v.video_id, v.title, v.channel_title, v.category_id, v.published_at) for v in videos],
        )
        conn.executemany(
            """INSERT OR IGNORE INTO snapshots
               (video_id, region, fetched_at, rank, views, likes, comments)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(v.video_id, v.region, v.fetched_at, v.rank, v.views, v.likes, v.comments)
             for v in videos],
        )
    return len(videos)


def save_categories(conn: sqlite3.Connection, cats: dict[str, str]) -> None:
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO categories (category_id, name) VALUES (?, ?)",
            cats.items(),
        )


def load_snapshots(conn: sqlite3.Connection, regions: list[str] | None = None) -> pd.DataFrame:
    sql = """
        SELECT s.*, v.title, v.channel_title, v.published_at,
               COALESCE(c.name, v.category_id) AS category
        FROM snapshots s
        JOIN videos v USING (video_id)
        LEFT JOIN categories c ON c.category_id = v.category_id
    """
    params: list[str] = []
    if regions:
        sql += f" WHERE s.region IN ({','.join('?' * len(regions))})"
        params = regions
    return pd.read_sql(sql, conn, params=params)
