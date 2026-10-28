# Arthvest API

## Requirements
- Python 3.11+

## Setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --env-file .env
```

Use these endpoints:
- `GET /` — service information
- `GET /health` — health status
- `GET /docs` — interactive API documentation

## Free local AI model (recommended for development)

Arthvest defaults to Ollama on your own computer. The six research stages use the local qwen3:4b model by default; no OpenAI API key is required and inference requests stay on the machine running the backend. Downloading the model requires internet once, and inference uses local RAM/GPU.

1. Install [Ollama for Windows](https://ollama.com/download/windows) and start the Ollama app.
2. In PowerShell, download the model:

   ```powershell
   ollama pull qwen3:4b
   ollama list
   ```

3. Copy .env.example to .env if needed, then set:

   ```dotenv
   ARTHVEST_LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   ARTHVEST_AGENT_MODEL=qwen3:4b
   ```

4. Restart the backend and open GET /api/agents/status. It should report configured: true only when Ollama is reachable and the model is installed. Then open the frontend Agents page and run a research request.

Use ARTHVEST_LLM_PROVIDER=openai and configure OPENAI_API_KEY only when you deliberately want paid cloud inference. Local mode disables OpenAI tracing and does not require that key. Macro and market data collection can still use the internet; only model inference is local.


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


## Scheduled archive ingestion

Run `python -m scripts.ingest_macro_archive` from the backend directory to fetch each configured indicator and verify that persisted source-check records were added. It refuses to start without `DATABASE_URL`, checks storage connectivity first, and returns a non-zero exit code for upstream failures or unconfirmed archive writes. The repository's **Archive Macro Observations** workflow runs this daily and can also be started manually; add a repository Actions secret named `DATABASE_URL` separately from deployment secrets.
