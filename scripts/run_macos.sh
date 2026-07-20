#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

[ -f .venv/bin/activate ] || { echo "Ambiente .venv não encontrado. Execute o setup."; exit 1; }
source .venv/bin/activate
export OMR_ROOT="${OMR_ROOT:-$ROOT_DIR/external/OMRChecker}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8003}"

python -m avaliacao_web.database_cli init
python -m avaliacao_web.database_cli import-json
python -m uvicorn avaliacao_web.app:app --reload --host "$HOST" --port "$PORT"
