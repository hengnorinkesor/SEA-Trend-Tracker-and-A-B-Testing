from sea_trends import db
from sea_trends.youtube_client import TrendingVideo


def _video(views, fetched_at):
    return TrendingVideo("abc", "KH", 1, "Title", "Chan", "10",
                         "2026-11-01T00:00:00+00:00", views, 10, 1, fetched_at)


def test_snapshots_accumulate_and_videos_dedupe(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_videos(conn, [_video(100, "2026-11-10T00:00:00+00:00")])
    db.save_videos(conn, [_video(200, "2026-11-10T06:00:00+00:00")])
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2


def test_load_snapshots_joins_category_name(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_categories(conn, {"10": "Music"})
    db.save_videos(conn, [_video(100, "2026-11-10T00:00:00+00:00")])
    df = db.load_snapshots(conn, ["KH"])
    assert df.iloc[0]["category"] == "Music"
