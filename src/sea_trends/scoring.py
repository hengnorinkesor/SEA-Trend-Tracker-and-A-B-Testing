"""Trend scoring engine.

    trend_score = 0.6 × popularity + 0.4 × velocity

popularity – how big the video is right now: log(views), min-max scaled
             to 0–1 within each region.
velocity   – how fast it's growing: views gained per hour since the previous
             snapshot (or since publish, if this is the first time we've seen
             it), log-scaled then min-max scaled to 0–1 within each region.

Why log? View counts are extremely skewed — one 50M-view music video would
otherwise squash every other video to ~0. Why per region? A 200k-view video
is huge in Cambodia and tiny in India; scaling inside each region keeps the
comparison fair.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import POPULARITY_WEIGHT, VELOCITY_WEIGHT


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)  # no spread → everyone is "average"
    return (s - lo) / (hi - lo)


def add_velocity(snaps: pd.DataFrame) -> pd.DataFrame:
    """Return the latest snapshot per (video, region) with views_per_hour."""
    df = snaps.copy()
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True, format="ISO8601")
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, format="ISO8601")
    df = df.sort_values(["region", "video_id", "fetched_at"])

    g = df.groupby(["region", "video_id"])
    df["prev_views"] = g["views"].shift(1)
    df["prev_fetched_at"] = g["fetched_at"].shift(1)

    has_prev = df["prev_views"].notna()
    hours = np.where(
        has_prev,
        (df["fetched_at"] - df["prev_fetched_at"]).dt.total_seconds() / 3600,
        (df["fetched_at"] - df["published_at"]).dt.total_seconds() / 3600,
    )
    gained = np.where(has_prev, df["views"] - df["prev_views"], df["views"])
    df["views_per_hour"] = np.clip(gained, 0, None) / np.clip(hours, 1, None)  # ≥1h avoids /0
    df["velocity_source"] = np.where(has_prev, "snapshot", "since_publish")

    latest = df.groupby(["region", "video_id"]).tail(1)
    # keep only videos that are in each region's most recent chart
    latest_run = latest.groupby("region")["fetched_at"].transform("max")
    return latest[latest["fetched_at"] == latest_run].drop(columns=["prev_fetched_at"])


def score(snaps: pd.DataFrame) -> pd.DataFrame:
    if snaps.empty:
        return snaps
    df = add_velocity(snaps)
    df["popularity"] = df.groupby("region")["views"].transform(lambda s: _minmax(np.log1p(s)))
    df["velocity"] = df.groupby("region")["views_per_hour"].transform(
        lambda s: _minmax(np.log1p(s))
    )
    df["engagement_rate"] = (df["likes"] + df["comments"]) / df["views"].replace(0, np.nan)
    df["trend_score"] = POPULARITY_WEIGHT * df["popularity"] + VELOCITY_WEIGHT * df["velocity"]
    return df.sort_values(["region", "trend_score"], ascending=[True, False]).reset_index(drop=True)


def cross_region(scored: pd.DataFrame, min_regions: int = 2) -> pd.DataFrame:
    """Videos trending in several regions at once — a strong regional signal."""
    agg = (
        scored.groupby(["video_id", "title", "channel_title", "category"])
        .agg(regions=("region", lambda r: ", ".join(sorted(r))),
             n_regions=("region", "nunique"),
             avg_score=("trend_score", "mean"),
             max_views=("views", "max"))
        .reset_index()
    )
    return (agg[agg["n_regions"] >= min_regions]
            .sort_values(["n_regions", "avg_score"], ascending=False)
            .reset_index(drop=True))


def category_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """Which content categories dominate each region's chart."""
    return (
        scored.groupby(["region", "category"])
        .agg(videos=("video_id", "count"), avg_score=("trend_score", "mean"))
        .reset_index()
        .sort_values(["region", "videos", "avg_score"], ascending=[True, False, False])
    )
