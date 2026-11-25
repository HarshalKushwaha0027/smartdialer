#!/usr/bin/env bash
# One-command startup for a fresh host (Replit, Render, etc.):
# build the frontend once, install backend deps, then run the single
# FastAPI process that serves both the UI and the API on $PORT.
set -e

echo "== Installing backend dependencies =="
pip install -q -r backend/requirements.txt || pip install -q --break-system-packages -r backend/requirements.txt

if [ ! -d "frontend/dist" ]; then
  echo "== Building frontend =="
  cd frontend
  npm install --silent
  npm run build
  cd ..
fi

echo "== Starting SmartDialer on port ${PORT:-8000} =="
python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
