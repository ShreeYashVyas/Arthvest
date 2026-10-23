# Arthvest API

## Requirements
- Python 3.11+

## Setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Use these endpoints:
- `GET /` — service information
- `GET /health` — health status
- `GET /docs` — interactive API documentation

Install development tooling and run tests/lint checks:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check --select E4,E7,E9,F app tests
```

## Optional persistent archive

Set `DATABASE_URL` to a PostgreSQL URL such as `postgresql+psycopg://USER:PASSWORD@HOST:5432/arthvest` to retain source observations, revisions, and source-fetch checks. Add it to private environment configuration, not Git. Leaving it unset is supported: live FRED requests still work, while archive endpoints return HTTP 503. Initial SQLAlchemy tables are created on the first storage operation.

New endpoints:
- `GET /api/macro/storage` — storage readiness and counts
- `GET /api/macro/archive/{indicator_key}?limit=12` — current archived source values by observation date
- `GET /api/macro/revisions/{indicator_key}?limit=20` — upstream value revisions
- `GET /api/macro/source-checks?limit=24` — recent source fetch outcomes

The archive stores source-native FRED values. For example, `CPIAUCSL` is the CPI index, not the derived year-over-year inflation rate. Persistence errors are logged but do not interrupt live feed delivery; check the storage endpoint to verify the database is available.

- `GET /api/macro/analytics/{indicator_key}?limit=12` — descriptive historical trend and distribution statistics (requires `DATABASE_URL` and archived observations)


## Archived cross-indicator comparison

When `DATABASE_URL` points to a reachable database, use `GET /api/macro/compare?indicators=fed-funds,us-inflation,us-unemployment&years=5` to compare 2–5 supported indicators across a 1, 3, 5, or 10 year window. Relative trends are independently rebased to 100 at each indicator's first in-window archived observation. Different source frequencies are preserved, and series without enough history or a positive baseline are marked explicitly.
