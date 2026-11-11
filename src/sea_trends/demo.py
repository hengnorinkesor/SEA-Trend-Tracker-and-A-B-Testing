"""Synthetic data so anyone can try the pipeline without an API key."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .youtube_client import TrendingVideo

CATEGORIES = {"10": "Music", "24": "Entertainment", "20": "Gaming",
              "22": "People & Blogs", "17": "Sports", "25": "News & Politics"}
TITLES = ["Official MV", "Reaction", "Live Stream Highlights", "Vlog Day",
          "Challenge", "Full Match", "Behind the Scenes", "Cover Song", "Short Film"]


def generate(regions: list[str], snapshots: int = 2, per_region: int = 25,
             seed: int = 7) -> tuple[list[TrendingVideo], dict[str, str]]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    shared = [f"shared{i:03d}" for i in range(8)]  # some videos trend in many regions
    pool = {}
    out: list[TrendingVideo] = []

    for region in regions:
        ids = rng.sample(shared, 4) + [f"{region}{i:03d}" for i in range(per_region - 4)]
        for vid in ids:
            if vid not in pool:
                pool[vid] = {
                    "title": f"{rng.choice(TITLES)} #{rng.randint(1, 999)}",
                    "channel": f"Channel {rng.randint(1, 60)}",
                    "cat": rng.choice(list(CATEGORIES)),
                    "published": now - timedelta(hours=rng.randint(6, 120)),
                    "base": int(10 ** rng.uniform(4, 7)),
                    "growth": rng.uniform(0.01, 0.4),
                }
        for s in range(snapshots):
            t = now - timedelta(hours=6 * (snapshots - 1 - s))
            ranked = sorted(ids, key=lambda v: -pool[v]["base"])
            for rank, vid in enumerate(ranked, start=1):
                p = pool[vid]
                views = int(p["base"] * (1 + p["growth"]) ** s)
                out.append(TrendingVideo(
                    video_id=vid, region=region, rank=rank, title=p["title"],
                    channel_title=p["channel"], category_id=p["cat"],
                    published_at=p["published"].isoformat(),
                    views=views, likes=int(views * rng.uniform(0.01, 0.06)),
                    comments=int(views * rng.uniform(0.001, 0.005)),
                    fetched_at=t.isoformat(),
                ))
    return out, CATEGORIES
