# Arthvest Frontend

## Requirements
- Node.js LTS with npm

## Setup (Windows PowerShell)

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The dashboard checks the FastAPI `/health` endpoint.

Start the backend in a separate terminal using the instructions in `../backend/README.md`.

The page is a foundation dashboard: macro factors and the composite score are intentionally marked as pending until validated data providers and scoring logic are implemented.
