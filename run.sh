#!/bin/zsh
set -e
cd "$(dirname "$0")/.."
source ../.venv/bin/activate
python -m uvicorn avaliacao_web.app:app --reload --port 8000
