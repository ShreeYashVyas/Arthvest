# Arthvest — Macro Intelligence

Arthvest is a macroeconomic intelligence dashboard designed to present transparent, source-attributed indicators and explainable market-regime assessments.

## Phase 1 scope

- Establish a clean frontend/backend foundation.
- Provide a FastAPI health endpoint.
- Build an institutional-style dashboard shell.
- Add macroeconomic data sources and transparent scoring incrementally.
- Clearly distinguish measured data from proposed, unvalidated scores.

## Architecture

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** Python, FastAPI
- **Data layer (later phase):** source adapters, validation, timestamps, and caching
- **Database (later phase):** PostgreSQL

## Project structure

```text
Arthvest/
├── frontend/             # Next.js dashboard
├── backend/              # FastAPI service
│   ├── app/
│   │   ├── main.py
│   │   └── api/routes/
│   └── requirements.txt
├── .gitignore
└── README.md
```

## Run locally

### Backend

Requires Python 3.11 or newer.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health check: http://127.0.0.1:8000/health  
API docs: http://127.0.0.1:8000/docs

### Frontend

Requires a current Node.js LTS release.

```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

Set `NEXT_PUBLIC_API_BASE_URL` if the backend is not running at `http://127.0.0.1:8000`.

## Data integrity principles

- Do not fabricate current readings.
- Include source and observation dates for data-backed indicators.
- Show unavailable data as unavailable, not as zero.
- Keep score weights and thresholds explicit; treat initial scoring rules as provisional until validated.
- Do not present the dashboard as personalized financial advice.

## Status

Initial foundation. Live indicators, persistence, and scoring logic have not yet been implemented.
