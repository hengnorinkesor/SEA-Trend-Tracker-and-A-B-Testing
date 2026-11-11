import pandas as pd
import pytest

from sea_trends import scoring


def _snap(video_id, region, fetched_at, views, published="2026-11-01T00:00:00+00:00"):
    return dict(video_id=video_id, region=region, fetched_at=fetched_at, rank=1,
                views=views, likes=views // 50, comments=views // 500,
                title=video_id, channel_title="c", category="Music",
                published_at=published)


def test_velocity_uses_previous_snapshot():
    df = pd.DataFrame([
        _snap("a", "KH", "2026-11-10T00:00:00+00:00", 1_000),
        _snap("a", "KH", "2026-11-10T10:00:00+00:00", 6_000),
    ])
    out = scoring.add_velocity(df)
    assert len(out) == 1
    assert out.iloc[0]["views_per_hour"] == pytest.approx(500)
    assert out.iloc[0]["velocity_source"] == "snapshot"


def test_velocity_falls_back_to_publish_time():
    df = pd.DataFrame([_snap("a", "KH", "2026-11-01T10:00:00+00:00", 1_000)])
    out = scoring.add_velocity(df)
    assert out.iloc[0]["views_per_hour"] == pytest.approx(100)
    assert out.iloc[0]["velocity_source"] == "since_publish"


def test_scores_are_bounded_and_weighted():
    t = "2026-11-10T00:00:00+00:00"
    df = pd.DataFrame([_snap("big", "KH", t, 1_000_000), _snap("small", "KH", t, 1_000)])
    out = scoring.score(df).set_index("video_id")
    assert out["trend_score"].between(0, 1).all()
    assert out.loc["big", "trend_score"] == pytest.approx(1.0)
    assert out.loc["small", "trend_score"] == pytest.approx(0.0)


def test_regions_are_normalised_independently():
    t = "2026-11-10T00:00:00+00:00"
    df = pd.DataFrame([
        _snap("kh1", "KH", t, 100_000), _snap("kh2", "KH", t, 10_000),
        _snap("in1", "IN", t, 50_000_000), _snap("in2", "IN", t, 5_000_000),
    ])
    out = scoring.score(df).set_index("video_id")
    # the top video in each region scores the same despite a 500x view gap
    assert out.loc["kh1", "trend_score"] == pytest.approx(out.loc["in1", "trend_score"])


def test_dropped_videos_are_excluded_from_latest_chart():
    df = pd.DataFrame([
        _snap("old", "KH", "2026-11-09T00:00:00+00:00", 5_000),
        _snap("new", "KH", "2026-11-10T00:00:00+00:00", 5_000),
    ])
    out = scoring.score(df)
    assert list(out["video_id"]) == ["new"]


def test_cross_region_detection():
    t = "2026-11-10T00:00:00+00:00"
    df = pd.DataFrame([
        _snap("x", "KH", t, 10_000), _snap("x", "TH", t, 20_000),
        _snap("y", "KH", t, 5_000),
    ])
    multi = scoring.cross_region(scoring.score(df))
    assert list(multi["video_id"]) == ["x"]
    assert multi.iloc[0]["n_regions"] == 2
