#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit .env and set DEEPSEEK_API_KEY before using AI features."
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/health_check.py
python -m uvicorn src.web:app --host 0.0.0.0 --port 8090 --reload
