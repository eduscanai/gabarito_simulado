#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

command -v python3 >/dev/null || { echo "Python 3 não encontrado."; exit 1; }
command -v git >/dev/null || { echo "Git não encontrado."; exit 1; }
command -v tesseract >/dev/null || {
  echo "Tesseract não encontrado. Instale o pacote tesseract-ocr da sua distribuição"
  exit 1
}

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

mkdir -p external
if [ ! -f external/OMRChecker/main.py ]; then
  git clone https://github.com/Udayraj123/OMRChecker.git external/OMRChecker
fi

if [ -f external/OMRChecker/requirements.txt ]; then
  python -m pip install -r external/OMRChecker/requirements.txt
fi
python -m pip install -r requirements.txt
python -m avaliacao_web.database_cli init

echo "Instalação concluída. Execute: bash scripts/run_linux.sh"
