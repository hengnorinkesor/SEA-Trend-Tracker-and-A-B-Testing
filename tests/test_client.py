import pytest

from sea_trends.youtube_client import YouTubeAPIError, YouTubeClient


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        return self.response


def test_trending_parses_items_and_handles_hidden_likes():
    payload = {"items": [{
        "id": "vid1",
        "snippet": {"title": "T", "channelTitle": "C", "categoryId": "10",
                    "publishedAt": "2026-11-01T00:00:00Z"},
        "statistics": {"viewCount": "1234"},  # likes/comments hidden
    }]}
    session = FakeSession(FakeResponse(200, payload))
    videos = YouTubeClient("k", session).trending("KH")
    assert videos[0].views == 1234 and videos[0].likes == 0 and videos[0].rank == 1
    assert session.calls[0][1]["regionCode"] == "KH"


def test_api_error_surfaces_message():
    session = FakeSession(FakeResponse(400, {"error": {"message": "bad region"}}))
    with pytest.raises(YouTubeAPIError, match="bad region"):
        YouTubeClient("k", session).trending("ZZ")


def test_missing_key_is_a_clear_error():
    with pytest.raises(YouTubeAPIError, match=".env"):
        YouTubeClient("")
