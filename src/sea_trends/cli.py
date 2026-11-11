"""Command-line entry point.

    python -m sea_trends fetch  --regions sea
    python -m sea_trends report --regions sea --top 10
    python -m sea_trends export --regions all --out data/trends.csv
    python -m sea_trends demo
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from . import config, db, demo, scoring
from .youtube_client import YouTubeAPIError, YouTubeClient

log = logging.getLogger("sea_trends")
REPORT_COLS = ["rank", "title", "channel_title", "category", "views",
               "views_per_hour", "trend_score"]


def _regions(group: str) -> dict[str, str]:
    if group in config.REGION_GROUPS:
        return config.REGION_GROUPS[group]
    codes = [c.strip().upper() for c in group.split(",")]  # allow "KH,TH"
    return {c: config.REGION_GROUPS["all"].get(c, c) for c in codes}


def cmd_fetch(args) -> None:
    regions = _regions(args.regions)
    client = YouTubeClient(config.YOUTUBE_API_KEY)
    conn = db.connect(config.DB_PATH)
    db.save_categories(conn, client.categories())

    total = 0
    for code, name in regions.items():
        try:
            n = db.save_videos(conn, client.trending(code, config.MAX_RESULTS_PER_REGION))
            log.info("%-12s %3d videos", name, n)
            total += n
        except YouTubeAPIError as e:
            log.warning("%-12s skipped – %s", name, e)
    log.info("Saved %d snapshots → %s", total, config.DB_PATH)


def _scored(regions: dict[str, str]) -> pd.DataFrame:
    conn = db.connect(config.DB_PATH)
    snaps = db.load_snapshots(conn, list(regions))
    if snaps.empty:
        sys.exit("No data yet — run `fetch` (or `demo`) first.")
    return scoring.score(snaps)


def print_report(scored: pd.DataFrame, regions: dict[str, str], top: int) -> None:
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.width", 160)
    for code, name in regions.items():
        sub = scored[scored["region"] == code].head(top)
        if sub.empty:
            continue
        print(f"\n=== {name} ({code}) — top {len(sub)} by trend score ===")
        print(sub[REPORT_COLS].to_string(
            index=False,
            formatters={"views": "{:,.0f}".format,
                        "views_per_hour": "{:,.0f}".format,
                        "trend_score": "{:.3f}".format}))

    multi = scoring.cross_region(scored)
    if not multi.empty:
        print("\n=== Trending in multiple regions ===")
        print(multi.head(top)[["title", "category", "n_regions", "regions", "avg_score"]]
              .to_string(index=False, formatters={"avg_score": "{:.3f}".format}))

    cats = (scored.groupby("category")["video_id"].count()
            .sort_values(ascending=False).head(8))
    print("\n=== Category mix across selected regions ===")
    print(cats.to_string())


def cmd_report(args) -> None:
    regions = _regions(args.regions)
    print_report(_scored(regions), regions, args.top)


def cmd_export(args) -> None:
    regions = _regions(args.regions)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _scored(regions).to_csv(out, index=False)
    log.info("Exported → %s", out)


def cmd_demo(args) -> None:
    config.DB_PATH = config.PROJECT_ROOT / "data" / "demo.db"
    config.DB_PATH.unlink(missing_ok=True)
    regions = config.REGION_GROUPS["sea"]
    videos, cats = demo.generate(list(regions))
    conn = db.connect(config.DB_PATH)
    db.save_categories(conn, cats)
    db.save_videos(conn, videos)
    log.info("Generated %d synthetic snapshots → %s", len(videos), config.DB_PATH)
    print_report(_scored(regions), regions, args.top)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(prog="sea_trends",
                                description="Track YouTube trending videos across Southeast Asia.")
    sub = p.add_subparsers(dest="cmd", required=True)
    region_help = "cambodia | sea | asia | all | comma list e.g. KH,TH"

    s = sub.add_parser("fetch", help="Pull the current trending charts")
    s.add_argument("--regions", default="sea", help=region_help)
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("report", help="Print scored trends")
    s.add_argument("--regions", default="sea", help=region_help)
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("export", help="Write scored trends to CSV")
    s.add_argument("--regions", default="all", help=region_help)
    s.add_argument("--out", default="data/trends_scored.csv")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("demo", help="Run end-to-end on synthetic data (no API key)")
    s.add_argument("--top", type=int, default=5)
    s.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except YouTubeAPIError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
