# SousChef Backend (Stage 1 MVP)

FastAPI backend scaffold with in-memory storage for recipes and sessions.

## Requirements
- Python 3.11+

## Setup
```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

## Run API
```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Run Tests
```bash
cd backend
pytest -q
```

## Seed Data
On startup, the app seeds one recipe (`Basic Pancakes`) when the store is empty.
