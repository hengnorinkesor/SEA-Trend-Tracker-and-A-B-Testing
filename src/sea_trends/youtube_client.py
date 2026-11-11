"""Thin wrapper around the YouTube Data API v3.

Only two endpoints are used:
  * videos.list?chart=mostPopular   – the trending chart for a region (1 quota unit)
  * videoCategories.list            – maps category IDs to names   (1 quota unit)

A full run over all 12 regions costs ~13 units of the 10,000 daily free quota.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
log = logging.getLogger(__name__)


class YouTubeAPIError(RuntimeError):
    pass


@dataclass
class TrendingVideo:
    video_id: str
    region: str
    rank: int
    title: str
    channel_title: str
    category_id: str
    published_at: str
    views: int
    likes: int
    comments: int
    fetched_at: str


class YouTubeClient:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        if not api_key:
            raise YouTubeAPIError(
                "No API key. Copy .env.example to .env and set YOUTUBE_API_KEY."
            )
        self.api_key = api_key
        self.session = session or requests.Session()

    def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        resp = self.session.get(f"{API_BASE}/{endpoint}", params=params, timeout=30)
        if resp.status_code != 200:
            try:
                msg = resp.json()["error"]["message"]
            except (ValueError, KeyError):
                msg = resp.text[:200]
            raise YouTubeAPIError(f"{endpoint} [{resp.status_code}]: {msg}")
        return resp.json()

    def trending(self, region: str, max_results: int = 50) -> list[TrendingVideo]:
        data = self._get(
            "videos",
            {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region,
                "maxResults": max_results,
            },
        )
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        videos = []
        for rank, item in enumerate(data.get("items", []), start=1):
            sn, st = item["snippet"], item.get("statistics", {})
            videos.append(
                TrendingVideo(
                    video_id=item["id"],
                    region=region,
                    rank=rank,
                    title=sn.get("title", ""),
                    channel_title=sn.get("channelTitle", ""),
                    category_id=sn.get("categoryId", ""),
                    published_at=sn.get("publishedAt", ""),
                    # likes/comments can be hidden by the creator → default 0
                    views=int(st.get("viewCount", 0)),
                    likes=int(st.get("likeCount", 0)),
                    comments=int(st.get("commentCount", 0)),
                    fetched_at=fetched_at,
                )
            )
        return videos

    def categories(self, region: str = "US") -> dict[str, str]:
        data = self._get("videoCategories", {"part": "snippet", "regionCode": region})
        return {c["id"]: c["snippet"]["title"] for c in data.get("items", [])}
