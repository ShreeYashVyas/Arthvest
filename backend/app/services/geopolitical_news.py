"""Best-effort public geopolitical news headline feed via GDELT DOC 2.0."""

import copy
import json
import logging
import time
from datetime import datetime, timezone
from threading import Lock
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_PROJECT_URL = "https://www.gdeltproject.org/"
REQUEST_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 2_000_000
MAX_ARTICLES = 12
CACHE_TTL_SECONDS = 600
QUERY = (
    '(India OR Pakistan OR China OR Taiwan OR Iran OR Israel OR Ukraine OR Russia '
    'OR "Red Sea" OR "Strait of Hormuz") '
    '(sanctions OR conflict OR tariff OR oil OR shipping OR border OR attack OR trade)'
)
_cache_lock = Lock()
_cache: tuple[float, dict[str, object]] | None = None


def _request_gdelt_payload() -> dict[str, object]:
    """Query recent article metadata only; never download article bodies."""
    params = urlencode({
        "query": QUERY, "mode": "ArtList", "format": "json",
        "maxrecords": MAX_ARTICLES, "timespan": "24h", "sort": "DateDesc",
    })
    request = Request(
        f"{GDELT_DOC_URL}?{params}",
        headers={"User-Agent": "Arthvest/0.1 (research dashboard)"},
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("GDELT response exceeded the configured size limit.")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GDELT returned an unexpected response shape.")
    return payload


def _normalise_articles(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, list):
        return []
    articles: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        title, url = item.get("title"), item.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            continue
        title, url = title.strip()[:300], url.strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or url in seen_urls:
            continue
        seen_urls.add(url)
        seen_at = None
        raw_seen = item.get("seendate")
        if isinstance(raw_seen, str):
            try:
                seen_at = datetime.strptime(raw_seen, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                ).isoformat()
            except ValueError:
                seen_at = None
        domain, country, language = item.get("domain"), item.get("sourcecountry"), item.get("language")
        articles.append({
            "key": f"news-{len(articles) + 1}",
            "title": title,
            "url": url,
            "domain": domain.strip()[:200] if isinstance(domain, str) and domain.strip() else parsed.hostname,
            "seen_at": seen_at,
            "source_country": country.strip()[:80] if isinstance(country, str) and country.strip() else None,
            "language": language.strip()[:40] if isinstance(language, str) and language.strip() else None,
        })
        if len(articles) >= MAX_ARTICLES:
            break
    return articles


def fetch_geopolitical_news() -> dict[str, object]:
    """Return cached, validated recent headlines or an explicit unavailable state."""
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
            cached = copy.deepcopy(_cache[1])
            cached["cached"] = True
            return cached
    try:
        articles = _normalise_articles(_request_gdelt_payload())
        fetched_at = datetime.now(timezone.utc).isoformat()
        result: dict[str, object] = {
            "status": "available" if articles else "empty",
            "provider": "GDELT DOC 2.0",
            "source_url": GDELT_PROJECT_URL,
            "generated_at": fetched_at,
            "fetched_at": fetched_at,
            "timespan_hours": 24,
            "count": len(articles),
            "articles": articles,
            "cached": False,
            "limitations": [
                "Headline metadata is a news-index signal, not independently verified article facts.",
                "Only article titles and metadata are analyzed; full article text is not fetched.",
                "Coverage and ranking can be incomplete or duplicated across publishers.",
            ],
        }
        with _cache_lock:
            _cache = (time.monotonic(), copy.deepcopy(result))
        return result
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("GDELT news feed unavailable (%s)", type(exc).__name__)
    except Exception as exc:
        logger.warning("Unexpected GDELT response failure (%s)", type(exc).__name__)
    return {
        "status": "unavailable",
        "provider": "GDELT DOC 2.0",
        "source_url": GDELT_PROJECT_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at": None,
        "timespan_hours": 24,
        "count": 0,
        "articles": [],
        "cached": False,
        "reason": "Recent geopolitical headlines are temporarily unavailable; no current-event conclusions should be inferred.",
        "limitations": [
            "The public news feed was unavailable for this run.",
            "Do not infer the absence of an event from an empty or failed news query.",
        ],
    }


def clear_news_cache() -> None:
    """Clear in-process cache; intended for tests."""
    global _cache
    with _cache_lock:
        _cache = None
