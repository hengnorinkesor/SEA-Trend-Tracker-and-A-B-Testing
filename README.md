# SEA YouTube Trends

Tracks what's trending on YouTube across **Cambodia, Southeast Asia and wider Asia**, stores every snapshot in SQLite, and ranks videos with a custom **trend score** that blends how big a video is with how fast it's growing.

Built as a self-directed project to learn APIs, databases and data pipelines in Python, and to get a clearer view of the Southeast Asian content market, which global trend tools tend to cover poorly.

![tests](https://github.com/hengnorinkesorSEA-Trend-Tracker-and-A-B-Testing/actions/workflows/tests.yml/badge.svg)

---

## What it does

- **Fetches** the official YouTube trending chart for 12 markets (KH, TH, VN, ID, MY, PH, SG, JP, KR, TW, HK, IN) via the YouTube Data API v3
- **Stores** each run as a timestamped snapshot in SQLite, building a history over time
- **Scores** every video on popularity and velocity, normalised within each country
- **Reports** each country's top trends, videos trending in several countries at once, and the category mix
- **Exports** scored data to CSV for Excel and Power BI (learning Tableau)

## How the trend score works

```
trend_score = 0.6 × popularity + 0.4 × velocity
```

| Component | What it measures | How it's calculated |
|---|---|---|
| **Popularity** | How big the video is right now | log(views), scaled 0–1 within the region |
| **Velocity** | How fast it's growing | Views gained per hour since the previous snapshot (or since publish on first sighting), log-scaled, then scaled 0–1 within the region |

**Why log-scale?** View counts are heavily skewed. A single 50M-view music video would otherwise flatten every other video to near zero.

**Why score within each region?** 200k views is a hit in Cambodia and a rounding error in India. Scaling within each country keeps comparisons fair, so the #1 trend in Phnom Penh and the #1 trend in Tokyo both score near 1.0.

**Why 60/40?** Popularity is the steadier signal. Velocity catches breakout videos early, but it's noisier, especially on the first snapshot. The weights are set in `config.py` so you can change them.

## Quick start

```bash
git clone https://github.com/hengnorinkesor/SEA-Trend-Tracker-and-A-B-Testing.git
cd SEA-Trend-Tracker-and-A-B-Testing
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Try it without an API key (synthetic data)
python -m sea_trends demo
```

### Using real data

1. Create a key in [Google Cloud Console](https://console.cloud.google.com/): APIs & Services → enable **YouTube Data API v3** → Credentials → Create API key
2. `cp .env.example .env` and paste your key in. `.env` is git-ignored, so the key never reaches GitHub.
3. Run:

```bash
python -m sea_trends fetch --regions sea        # pull current charts
python -m sea_trends report --regions sea --top 10
python -m sea_trends export --regions all --out data/trends.csv
```

`--regions` accepts `cambodia`, `sea`, `asia`, `all`, or a comma list like `KH,TH,VN`.

Velocity gets more accurate as you collect more snapshots. Run `fetch` a few times a day, for example with cron:

```bash
0 */6 * * * cd /path/to/SEA-Trend-Tracker-and-A-B-Testing && .venv/bin/python -m sea_trends fetch --regions all
```

**Quota:** one full run uses about 13 of the 10,000 free daily API units.

## Project structure

```
SEA-Trend-Tracker-and-A-B-Testing/
├── src/sea_trends/
│   ├── config.py           # regions, weights, paths
│   ├── youtube_client.py   # YouTube Data API wrapper
│   ├── db.py               # SQLite schema + read/write
│   ├── scoring.py          # trend scoring engine
│   ├── demo.py             # synthetic data generator
│   └── cli.py              # fetch / report / export / demo
├── tests/                  # pytest suite (no network needed)
├── data/                   # local database + exports (git-ignored)
└── .github/workflows/      # CI: runs tests on every push
```

## Database schema

```
videos      (video_id PK, title, channel_title, category_id, published_at)
snapshots   (video_id, region, fetched_at, rank, views, likes, comments)   PK = all three ids
categories  (category_id PK, name)
```

Static details (title, channel) are stored once in `videos`. Numbers that change (views, rank) go into `snapshots`, one row per fetch, so growth over time can be calculated.

## Example output

```
=== Cambodia (KH) — top 3 by trend score ===
 rank                 title channel_title        category     views views_per_hour trend_score
    2 Behind the Scenes #61    Channel 53          Sports 8,736,136        296,717       1.000
    1      Official MV #591    Channel 38  People & Blogs 8,726,278         39,844       0.897
    3       Short Film #974    Channel 40 News & Politics 1,968,810         51,948       0.768
```

*(from `demo` mode: titles and numbers are synthetic)*

Note that the #2 video on YouTube's own chart ranks first here. It has a similar number of views but is growing about 7× faster. Catching that kind of breakout is what the velocity component is for.

## Development notes

- **Started on Google Trends, switched to YouTube.** The original version used `pytrends`, which stopped working reliably after Google changed its endpoints. The YouTube Data API is official, free within quota, and supports country-level trending charts across SEA.
- **Secrets stay out of code.** API keys are read from `.env`, and `.gitignore` is set up before the first commit.
- **Missing data is handled.** Creators can hide like counts and some regions aren't supported by the API. Both are handled without crashing the run.

## Roadmap

- [ ] TikTok trends via a third-party data provider
- [ ] Keyword and topic extraction from titles (including Khmer and Thai text)
- [ ] Simple dashboard (Streamlit) with trend history charts
- [ ] Alerting when a video starts trending in 3+ SEA countries

## License

MIT
