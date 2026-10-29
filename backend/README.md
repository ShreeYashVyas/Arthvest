# Arthvest Core API

The Core backend serves the macro dashboard, historical analytics, optional
archive, health checks, and provider-independent market quotes.

## Requirements and startup

Use Python 3.11 or newer. From the repository root in Windows PowerShell:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env  # only when .env does not already exist
uvicorn app.main:app --reload --env-file .env
```

The health check is `GET /health`; interactive API documentation is at
`/docs`. Do not commit `.env` or put credentials in the frontend.

## Upstox market quotes

Core requests read-only index quotes from Upstox. Generate an Analytics Token
under the Analytics tab in [Upstox Developer Apps](https://account.upstox.com/developer/apps)
and set `UPSTOX_ANALYTICS_TOKEN` in the private `backend/.env` file. The token
is sent only as a backend Bearer credential and is never returned by Core.
This Analytics Token is sufficient for the market-data quote API; an API key
and client secret alone do not authenticate quote requests. The alternative
OAuth flow requires an interactive authorization code exchange for an access
token. See the [Analytics Token guide](https://upstox.com/developer/api-documentation/analytics-token/),
[authentication guide](https://upstox.com/developer/api-documentation/authentication/),
and [Full Market Quotes API](https://upstox.com/developer/api-documentation/get-full-market-quote/).

## Provider selection

`MARKET_DATA_PROVIDER` accepts `auto`, `upstox`, or `yahoo`. `auto` selects
Upstox when `UPSTOX_ANALYTICS_TOKEN` is set, otherwise it selects the
best-effort public Yahoo Finance chart feed. An Upstox authentication failure
is returned as an error and is never silently hidden by switching providers.
Yahoo Finance data may be delayed or stale, and its chart endpoint is
undocumented, subject to availability, and subject to Yahoo's terms. Set
`MARKET_DATA_CACHE_SECONDS` (default 30; bounded to 0–300 seconds) to adjust
the backend cache. The frontend refresh interval can be configured with
`NEXT_PUBLIC_MARKET_REFRESH_SECONDS` (default 60; bounded to 30–300 seconds).

`GET /api/market/status` reports provider selection and configuration.
`GET /api/market/quotes` returns normalized NIFTY 50, NIFTY BANK, and India VIX
quotes; optional `symbols` values may be configured keys, display symbols, or
instrument identifiers. Upstox legacy endpoints remain available under
`/api/market/upstox`. A quote snapshot is not a historical series and does not
place orders; Core shows an empty state until a real historical-data endpoint
is configured.

The stock discovery page searches the current Upstox NSE/BSE equity universe.
It uses the Upstox instrument search API and falls back to Upstox's official
compressed complete instrument master when search is unavailable. Search
results exclude debt and fund instrument series. Selected stocks use the
instrument key returned by Upstox for quotes and V3 historical candles. The
Markets page offers 1-month, 3-month, 1-year, and 5-year daily-close ranges.
The V3 feed manager decodes Upstox's published Protobuf schema and shares one
upstream connection across currently subscribed instruments and browser clients.
Core tries `UPSTOX_ANALYTICS_TOKEN` first; a bounded live authorization check
returned HTTP 200 with the current Analytics Token. If it is not configured,
Core can use the optional `UPSTOX_ACCESS_TOKEN` OAuth fallback. The V3 API
returns a camelCase `authorizedRedirectUri`; Core keeps that one-use URL in
memory only and never returns it to browsers or logs. Core does not refresh or
modify tokens. Feed status reports connection and receive timestamps separately
from REST quote timestamps. When no token is configured or the feed is down,
the UI uses clearly labelled REST snapshot fallback.

## Optional archive

Set `DATABASE_URL` to the intended PostgreSQL connection URL to enable durable
macro archives, the Upstox instrument catalogue, and historical candles. Apply
the versioned, additive Alembic baseline from this directory with
`python -m scripts.migrate`; the application also runs pending safe migrations
on first storage use. It does not drop or reset existing tables. The storage
status endpoint reports database connectivity and market-history sync
separately. With no URL configured, live provider responses can still be shown,
but history is explicitly marked as not persisted. Core never falls back to a
temporary database. SQLite URLs are supported for isolated automated tests.

Server-managed watchlists are currently restricted to `APP_ENV=development`
and use one server-side local identity because this repository has no user
authentication yet. Do not expose that development server to multiple users;
multi-user access requires authentication and ownership enforcement first.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check --select E4,E7,E9,F app tests
```
