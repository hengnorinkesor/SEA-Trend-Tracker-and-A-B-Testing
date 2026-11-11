"""
meta_ab_test.py — A/B testing for organic Meta (Instagram / Facebook) posts
===========================================================================

Built to sit next to the YouTube SEA trend tracker: same stack (Python + SQLite),
same idea of a small scoring engine, just pointed at your own posts instead of
trending videos.

THE BIG IDEA (plain English)
----------------------------
Meta's built-in A/B test tool only works for *ads*. For organic posts there's no
button, so we run the experiment ourselves:

  1. PLAN    – Decide what you're testing (e.g. "Reel vs Carousel", "question
               hook vs statement hook"). The script randomly assigns A or B to
               each upcoming posting slot. Randomising is what stops "B won
               because we happened to post it on Fridays".
  2. POST    – Post as planned. After each post goes live, record its post ID
               against its slot (or just its variant) in the plan CSV.
  3. IMPORT  – Pull the numbers in, either from a Meta Business Suite CSV export
               or straight from the Instagram Graph API. Stored in SQLite.
  4. ANALYSE – Compare engagement rate (interactions ÷ reach) between A and B
               and tell you whether the difference is real or likely just noise.

Engagement rate per post = (likes + comments + shares + saves) / reach
We use REACH, not followers, because reach is how many people actually saw it.

USAGE
-----
  python meta_ab_test.py sample-size --baseline 0.04 --lift 0.20
  python meta_ab_test.py plan --test hook_style --a "Question hook" --b "Statement hook" \
                              --start 2026-11-16 --posts 16 --per-week 4
  python meta_ab_test.py import-csv --file export.csv --plan plan_hook_style.csv
  python meta_ab_test.py import-api --plan plan_hook_style.csv      # needs .env, see below
  python meta_ab_test.py analyse --test hook_style

API SETUP (optional — CSV import works without it)
--------------------------------------------------
Create a file called .env next to this script (and add .env to .gitignore —
never paste tokens into code, same lesson as the SerpApi key):

  META_ACCESS_TOKEN=your_long_lived_token
  IG_USER_ID=your_instagram_business_account_id

Requirements: pip install pandas numpy scipy requests python-dotenv
"""

from __future__ import annotations

import argparse
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = Path(__file__).with_name("meta_ab_tests.db")
GRAPH_API_VERSION = "v23.0"  # bump if Meta deprecates it
ALPHA = 0.05                 # 5% significance level — the usual convention


# ---------------------------------------------------------------------------
# 1. DATABASE
# ---------------------------------------------------------------------------
# One table, one row per post. post_id is the PRIMARY KEY, so re-importing
# the same post later (e.g. a week on, when numbers have grown) just updates it.

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id      TEXT PRIMARY KEY,
    test_name    TEXT NOT NULL,
    variant      TEXT NOT NULL CHECK (variant IN ('A','B')),
    posted_at    TEXT,
    media_type   TEXT,
    reach        INTEGER,
    likes        INTEGER,
    comments     INTEGER,
    shares       INTEGER,
    saves        INTEGER,
    imported_at  TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def upsert_posts(df: pd.DataFrame) -> int:
    cols = ["post_id", "test_name", "variant", "posted_at", "media_type",
            "reach", "likes", "comments", "shares", "saves"]
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df["imported_at"] = datetime.now().isoformat(timespec="seconds")
    rows = df[cols + ["imported_at"]].astype(object).where(df.notna(), None).values.tolist()
    with get_conn() as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO posts ({','.join(cols)},imported_at) "
            f"VALUES ({','.join('?' * (len(cols) + 1))})",
            rows,
        )
    return len(rows)


# ---------------------------------------------------------------------------
# 2. SAMPLE SIZE — "how many posts do I need?"
# ---------------------------------------------------------------------------
# Social posts are noisy: one post can flop for reasons that have nothing to
# do with your variant. So the unit we count is POSTS, not impressions, and
# we estimate the spread between posts with a coefficient of variation (CV).
# CV ≈ 0.5 means a typical post's engagement rate is ±50% of the average —
# a realistic default for a small account. Measure your own from past posts
# for a better answer.

def sample_size(baseline: float, lift: float, cv: float = 0.5,
                alpha: float = ALPHA, power: float = 0.8) -> int:
    sd = baseline * cv
    delta = baseline * lift
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    n = 2 * ((z_a + z_b) * sd / delta) ** 2
    return int(np.ceil(n))


def cmd_sample_size(args):
    n = sample_size(args.baseline, args.lift, args.cv, power=args.power)
    print(f"\nBaseline engagement rate : {args.baseline:.2%}")
    print(f"Lift you want to detect  : {args.lift:+.0%}  "
          f"(→ {args.baseline * (1 + args.lift):.2%})")
    print(f"Post-to-post spread (CV) : {args.cv}")
    print(f"\n➡  You need about {n} posts PER VARIANT ({2 * n} total).")
    if n > 30:
        print("   That's a lot for organic content. Options: test a bigger change "
              "(bigger lift), run it over more weeks, or "
              "treat the result as directional rather than proof.")


# ---------------------------------------------------------------------------
# 3. PLAN — randomised posting schedule
# ---------------------------------------------------------------------------
# "Blocked" randomisation: within every pair of slots, one is A and one is B,
# in random order. That keeps A and B balanced across weeks, so a busy exam
# week or a viral trend hits both variants roughly equally.

def cmd_plan(args):
    rng = random.Random(args.seed)
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    gap = 7 / args.per_week
    slots = [start + timedelta(days=round(i * gap)) for i in range(args.posts)]

    variants = []
    for _ in range(0, args.posts, 2):
        pair = ["A", "B"]
        rng.shuffle(pair)
        variants.extend(pair)
    variants = variants[: args.posts]

    plan = pd.DataFrame({
        "slot": range(1, args.posts + 1),
        "date": [d.isoformat() for d in slots],
        "weekday": [d.strftime("%a") for d in slots],
        "test_name": args.test,
        "variant": variants,
        "description": [args.a if v == "A" else args.b for v in variants],
        "post_id": "",  # ← fill this in after each post goes live
    })
    out = Path(f"plan_{args.test}.csv")
    plan.to_csv(out, index=False)
    print(plan.to_string(index=False))
    print(f"\nSaved → {out}. After each post goes live, paste its post ID into the "
          "post_id column. Keep everything else (time of day, topic mix, "
          "hashtags) as similar as you can — only the thing being tested should differ.")


def load_plan(path: str) -> pd.DataFrame:
    plan = pd.read_csv(path, dtype={"post_id": str})
    plan = plan[plan["post_id"].notna() & (plan["post_id"].str.strip() != "")]
    plan["post_id"] = plan["post_id"].str.strip()
    if plan.empty:
        sys.exit("No post IDs filled in the plan yet — nothing to import.")
    return plan[["post_id", "test_name", "variant"]]


# ---------------------------------------------------------------------------
# 4a. IMPORT from a Meta Business Suite CSV export
# ---------------------------------------------------------------------------
# Export column names vary by platform and change over time, so we match
# loosely on keywords rather than exact headers.

COLUMN_KEYWORDS = {
    "post_id":    ["post id", "media id"],
    "posted_at":  ["publish time", "date", "timestamp"],
    "media_type": ["post type", "media type"],
    "reach":      ["reach"],
    "likes":      ["likes", "reactions"],
    "comments":   ["comments"],
    "shares":     ["shares"],
    "saves":      ["saves", "saved"],
}


def _match_columns(df: pd.DataFrame) -> dict:
    mapping = {}
    for field, keys in COLUMN_KEYWORDS.items():
        for col in df.columns:
            if any(k in col.lower() for k in keys) and col not in mapping:
                mapping[col] = field
                break
    return mapping


def cmd_import_csv(args):
    raw = pd.read_csv(args.file, dtype=str)
    mapping = _match_columns(raw)
    df = raw.rename(columns=mapping)[list(mapping.values())]
    if "post_id" not in df or "reach" not in df:
        sys.exit(f"Couldn't find post ID / reach columns. Columns seen: {list(raw.columns)}")
    for c in ["reach", "likes", "comments", "shares", "saves"]:
        if c in df:
            df[c] = pd.to_numeric(df[c].str.replace(",", ""), errors="coerce").fillna(0).astype(int)
    df["post_id"] = df["post_id"].str.strip()

    merged = load_plan(args.plan).merge(df, on="post_id", how="left")
    missing = merged[merged["reach"].isna()]["post_id"].tolist()
    if missing:
        print(f"⚠  {len(missing)} planned post(s) not found in the export: {missing}")
    n = upsert_posts(merged.dropna(subset=["reach"]))
    print(f"Imported {n} post(s) into {DB_PATH.name}")


# ---------------------------------------------------------------------------
# 4b. IMPORT from the Instagram Graph API
# ---------------------------------------------------------------------------

def _graph_get(path: str, params: dict) -> dict:
    import requests
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{path}"
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Graph API error on {path}: {r.text[:300]}")
    return r.json()


def fetch_ig_post(media_id: str, token: str) -> dict:
    base = _graph_get(media_id, {
        "fields": "id,timestamp,media_type,like_count,comments_count",
        "access_token": token,
    })
    ins = _graph_get(f"{media_id}/insights", {
        "metric": "reach,saved,shares",
        "access_token": token,
    })
    metrics = {m["name"]: m["values"][0]["value"] for m in ins.get("data", [])}
    return {
        "post_id": media_id,
        "posted_at": base.get("timestamp"),
        "media_type": base.get("media_type"),
        "likes": base.get("like_count", 0),
        "comments": base.get("comments_count", 0),
        "reach": metrics.get("reach", 0),
        "saves": metrics.get("saved", 0),
        "shares": metrics.get("shares", 0),
    }


def cmd_import_api(args):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).with_name(".env"))
    except ImportError:
        pass
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        sys.exit("META_ACCESS_TOKEN not set — add it to .env (see top of file).")

    plan = load_plan(args.plan)
    records = []
    for pid in plan["post_id"]:
        try:
            records.append(fetch_ig_post(pid, token))
            print(f"  ✓ {pid}")
        except Exception as e:  # keep going if one post fails
            print(f"  ✗ {pid}: {e}")
    if not records:
        sys.exit("Nothing fetched.")
    merged = plan.merge(pd.DataFrame(records), on="post_id")
    print(f"Imported {upsert_posts(merged)} post(s) into {DB_PATH.name}")


# ---------------------------------------------------------------------------
# 5. ANALYSE
# ---------------------------------------------------------------------------
# Three lenses, from most to least trustworthy for social data:
#
#  • Welch's t-test on per-post engagement rates — the main result. Each post
#    is one data point; doesn't assume A and B have equal spread.
#  • Mann-Whitney U — same question, but doesn't care about outliers. If one
#    post went semi-viral, this keeps it from dominating.
#  • Bootstrap 95% CI on the lift — resamples your posts 10,000 times to show
#    the plausible range of "B is X% better/worse than A". If the range
#    crosses 0%, you can't rule out "no difference".

def bootstrap_lift(a: np.ndarray, b: np.ndarray, n: int = 10_000, seed: int = 42):
    rng = np.random.default_rng(seed)
    a_means = rng.choice(a, (n, len(a)), replace=True).mean(axis=1)
    b_means = rng.choice(b, (n, len(b)), replace=True).mean(axis=1)
    lifts = b_means / a_means - 1
    return np.percentile(lifts, [2.5, 97.5])


def cmd_analyse(args):
    with get_conn() as conn:
        df = pd.read_sql("SELECT * FROM posts WHERE test_name = ?", conn, params=(args.test,))
    if df.empty:
        sys.exit(f"No posts found for test '{args.test}'.")

    df["interactions"] = df[["likes", "comments", "shares", "saves"]].sum(axis=1)
    df = df[df["reach"] > 0]
    df["eng_rate"] = df["interactions"] / df["reach"]
    df["share_save_rate"] = (df["shares"] + df["saves"]) / df["reach"]

    a = df[df.variant == "A"]
    b = df[df.variant == "B"]
    if len(a) < 3 or len(b) < 3:
        sys.exit(f"Need at least 3 posts per variant (have A={len(a)}, B={len(b)}).")

    summary = df.groupby("variant").agg(
        posts=("post_id", "count"),
        avg_reach=("reach", "mean"),
        eng_rate_mean=("eng_rate", "mean"),
        eng_rate_median=("eng_rate", "median"),
        share_save_rate=("share_save_rate", "mean"),
    )
    print(f"\n=== Test: {args.test} ===\n")
    print(summary.to_string(float_format=lambda x: f"{x:.4f}"))

    ea, eb = a["eng_rate"].to_numpy(), b["eng_rate"].to_numpy()
    lift = eb.mean() / ea.mean() - 1
    t_p = stats.ttest_ind(eb, ea, equal_var=False).pvalue
    mw_p = stats.mannwhitneyu(eb, ea, alternative="two-sided").pvalue
    lo, hi = bootstrap_lift(ea, eb)

    print(f"\nLift (B vs A)           : {lift:+.1%}")
    print(f"95% bootstrap range     : {lo:+.1%} to {hi:+.1%}")
    print(f"Welch t-test p-value    : {t_p:.3f}")
    print(f"Mann-Whitney p-value    : {mw_p:.3f}")

    # Secondary check: did one variant just get shown to more people?
    reach_p = stats.mannwhitneyu(b["reach"], a["reach"], alternative="two-sided").pvalue
    print(f"Reach difference p-value: {reach_p:.3f}  (low = the algorithm treated them differently)")

    print("\n--- Verdict ---")
    winner = "B" if lift > 0 else "A"
    if t_p < ALPHA and mw_p < ALPHA:
        print(f"✅ {winner} wins. Both tests agree the difference is unlikely to be chance.")
    elif t_p < ALPHA or mw_p < ALPHA:
        print(f"🟡 Leaning {winner}, but the tests disagree — probably one outlier post. "
              "Run a few more posts before deciding.")
    else:
        needed = sample_size(ea.mean(), abs(lift) if lift else 0.2,
                             cv=max(df.groupby('variant')['eng_rate'].std().mean() / ea.mean(), 0.1))
        print("⚪ No clear winner yet — the difference could be noise.")
        print(f"   To confirm a {abs(lift):.0%} lift you'd need ~{needed} posts per variant "
              f"(you have {len(a)} / {len(b)}).")

    if args.export:
        out = Path(f"results_{args.test}.csv")
        df.to_csv(out, index=False)
        print(f"\nPer-post data saved → {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="A/B test organic Meta posts for engagement.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample-size", help="How many posts do I need?")
    s.add_argument("--baseline", type=float, required=True, help="Current avg engagement rate, e.g. 0.04")
    s.add_argument("--lift", type=float, default=0.2, help="Relative lift to detect, e.g. 0.2 = +20%%")
    s.add_argument("--cv", type=float, default=0.5, help="Post-to-post spread (std/mean)")
    s.add_argument("--power", type=float, default=0.8)
    s.set_defaults(func=cmd_sample_size)

    s = sub.add_parser("plan", help="Create a randomised posting schedule")
    s.add_argument("--test", required=True, help="Short test name, e.g. hook_style")
    s.add_argument("--a", required=True, help="Description of variant A")
    s.add_argument("--b", required=True, help="Description of variant B")
    s.add_argument("--start", default=date.today().isoformat())
    s.add_argument("--posts", type=int, default=16)
    s.add_argument("--per-week", type=float, default=3)
    s.add_argument("--seed", type=int, default=None)
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("import-csv", help="Import a Meta Business Suite export")
    s.add_argument("--file", required=True)
    s.add_argument("--plan", required=True)
    s.set_defaults(func=cmd_import_csv)

    s = sub.add_parser("import-api", help="Import via Instagram Graph API")
    s.add_argument("--plan", required=True)
    s.set_defaults(func=cmd_import_api)

    s = sub.add_parser("analyse", help="Compare A vs B")
    s.add_argument("--test", required=True)
    s.add_argument("--export", action="store_true")
    s.set_defaults(func=cmd_analyse)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()