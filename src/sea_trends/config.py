"""Central settings: regions, scoring weights, file paths."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
DB_PATH = Path(os.getenv("SEA_TRENDS_DB", PROJECT_ROOT / "data" / "trends.db"))

# ISO 3166-1 alpha-2 codes accepted by the YouTube Data API `regionCode`.
# Regions YouTube doesn't support (e.g. some smaller markets) are skipped
# at fetch time with a warning instead of crashing the run.
REGION_GROUPS: dict[str, dict[str, str]] = {
    "cambodia": {"KH": "Cambodia"},
    "sea": {
        "KH": "Cambodia",
        "TH": "Thailand",
        "VN": "Vietnam",
        "ID": "Indonesia",
        "MY": "Malaysia",
        "PH": "Philippines",
        "SG": "Singapore",
    },
    "asia": {
        "JP": "Japan",
        "KR": "South Korea",
        "TW": "Taiwan",
        "HK": "Hong Kong",
        "IN": "India",
    },
}
REGION_GROUPS["all"] = {**REGION_GROUPS["sea"], **REGION_GROUPS["asia"]}

MAX_RESULTS_PER_REGION = 50  # API maximum for chart=mostPopular per page

# Trend score = 60% popularity + 40% velocity (both normalised 0–1 within region)
POPULARITY_WEIGHT = 0.6
VELOCITY_WEIGHT = 0.4
