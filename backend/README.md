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
