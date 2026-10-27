"""Unit tests for the best-effort GDELT headline adapter."""

from app.services import geopolitical_news


def test_normalise_articles_deduplicates_and_rejects_non_https() -> None:
    payload = {"articles": [
        {"title": "  Energy shipping update  ", "url": "https://news.example.com/a",
         "seendate": "20261027T120000Z", "domain": "news.example.com"},
        {"title": "Duplicate", "url": "https://news.example.com/a"},
        {"title": "Insecure", "url": "http://news.example.com/b"},
        {"title": "Bad scheme", "url": "javascript:alert(1)"},
    ]}

    articles = geopolitical_news._normalise_articles(payload)

    assert len(articles) == 1
    assert articles[0]["title"] == "Energy shipping update"
    assert articles[0]["seen_at"] == "2026-10-27T12:00:00+00:00"


def test_news_feed_caches_successful_metadata(monkeypatch) -> None:
    geopolitical_news.clear_news_cache()
    calls = {"count": 0}

    def fake_request():
        calls["count"] += 1
        return {"articles": [{"title": "Headline", "url": "https://example.com/story"}]}

    monkeypatch.setattr(geopolitical_news, "_request_gdelt_payload", fake_request)
    first = geopolitical_news.fetch_geopolitical_news()
    second = geopolitical_news.fetch_geopolitical_news()

    assert first["status"] == "available"
    assert first["count"] == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["count"] == 1
    geopolitical_news.clear_news_cache()


def test_news_failure_is_explicit_and_contains_no_invented_headlines(monkeypatch) -> None:
    geopolitical_news.clear_news_cache()
    monkeypatch.setattr(
        geopolitical_news, "_request_gdelt_payload",
        lambda: (_ for _ in ()).throw(TimeoutError("test timeout")),
    )

    result = geopolitical_news.fetch_geopolitical_news()

    assert result["status"] == "unavailable"
    assert result["articles"] == []
    assert result["count"] == 0
    assert "no current-event conclusions" in result["reason"]
    geopolitical_news.clear_news_cache()
