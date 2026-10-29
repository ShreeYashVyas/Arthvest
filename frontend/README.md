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

The Markets page searches Upstox's supported NSE/BSE equity universe, shows real selected-stock quote snapshots and historical candles, and stores watchlist identities in this browser. V3 streaming authorization uses the backend `UPSTOX_ANALYTICS_TOKEN` when configured, or the optional `UPSTOX_ACCESS_TOKEN` OAuth fallback. Without either, the page labels the REST snapshot fallback.

## Frontend checks

```powershell
npm test
npm run lint
npm run build
```

Component tests use Vitest and React Testing Library; their provider responses are deterministic test fixtures and do not represent live market connectivity.
