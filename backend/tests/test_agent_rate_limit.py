"""Tests for the process-local per-client AI research rate limit."""

from app.api.routes import agents as routes


def test_research_rate_limit_is_per_client_and_expires(monkeypatch) -> None:
    monkeypatch.setenv("ARTHVEST_AGENT_MAX_REQUESTS_PER_HOUR", "2")
    client_id = "rate-limit-test-client"
    routes._REQUEST_TIMESTAMPS.pop(client_id, None)

    assert routes._reserve_research_request(client_id, now=100.0) == (True, 0)
    assert routes._reserve_research_request(client_id, now=101.0) == (True, 0)
    allowed, retry_after = routes._reserve_research_request(client_id, now=102.0)
    assert allowed is False
    assert retry_after > 0
    assert routes._reserve_research_request("different-client", now=102.0) == (True, 0)
    assert routes._reserve_research_request(client_id, now=3702.0) == (True, 0)

    routes._REQUEST_TIMESTAMPS.pop(client_id, None)
    routes._REQUEST_TIMESTAMPS.pop("different-client", None)
