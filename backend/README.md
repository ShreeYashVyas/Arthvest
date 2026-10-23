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

Run the smoke tests after installing test dependencies with `python -m pip install pytest httpx`:

```powershell
pytest
```
