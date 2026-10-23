# Arthvest — Macro Intelligence

Arthvest is a research-first macroeconomic intelligence dashboard. It presents source-attributed observations, data-quality status, historical trends and a transparent **provisional U.S. macro conditions subscore**.

> The current score is experimental, not backtested, and is not the full global/India macro regime model or a market-return forecast.

## Current Phase 1 capabilities

- Next.js dashboard with API connection state, indicator cards and historical sparklines.
- FastAPI endpoints for health, a macro-indicator catalog, a best-effort overview, history, data quality, and a provisional U.S. score.
- U.S. indicators: Federal Funds Effective Rate, CPI inflation (calculated year over year), and unemployment rate.
- India-related indicators: quarterly real GDP growth, annual consumer-price inflation, Economic Policy Uncertainty Index, INR per USD exchange rate, and real effective exchange rate.
- Source observation dates, retrieval timestamps, native units, frequency-aware freshness and period-labelled historical trends.
- In-process 15-minute source-series cache and parser/API/scoring tests.
- GitHub Actions workflow for backend tests and frontend production build.

## Technology

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, Lucide
- **Backend:** Python, FastAPI, Pydantic
- **Source data:** published FRED series with source-attribution links
- **Persistence:** not yet implemented; cache is in-process only
- **Database:** PostgreSQL remains a future phase

## Project structure

```text
Arthvest/
├── .github/workflows/ci.yml
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── docs/MACRO_DATA.md
└── frontend/
    └── src/app/
```

## Run locally (Windows PowerShell)

Use two VS Code terminals.

### 1. Backend

Requires Python 3.11 or newer.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs

### 2. Frontend

Requires a current Node.js LTS release.

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The frontend expects the API at `http://127.0.0.1:8000` by default.

### 3. Backend tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Backend health |
| `GET /api/macro/catalog` | Indicator definitions and metadata |
| `GET /api/macro/overview` | Latest available snapshot for configured indicators |
| `GET /api/macro/quality` | Coverage, staleness and availability summary |
| `GET /api/macro/history/{indicator_key}?limit=12` | Historical observations; limit from 1 to 60 |
| `GET /api/macro/fed-funds` | Federal Funds Rate endpoint |
| `GET /api/macro/score/us-conditions` | Provisional U.S.-only macro conditions subscore |

Indicator keys, formulas, sources and freshness thresholds are documented in [docs/MACRO_DATA.md](docs/MACRO_DATA.md).

## Data integrity principles

- Never fabricate current readings or replace missing data with zero.
- Distinguish source observation date from retrieval timestamp.
- Show stale data explicitly; freshness thresholds are provisional operational checks.
- Treat initial scoring weights and thresholds as illustrative until empirically reviewed and backtested.
- FRED data may be revised; consult the original source links for details.
- Arthvest is research and decision support, not personalized financial advice.

## Current limitations

No persistent database, scheduled ingestion, historical database, Indian inflation series with verified current observations, market-price feeds, geopolitical event model, or calibrated full composite score has been implemented yet. Current historical trends are fetched from upstream series and cached in memory.
