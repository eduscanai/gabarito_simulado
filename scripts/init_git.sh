#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
python scripts/check_repository.py
git init
git branch -M main
git add .
git status
echo
echo "Revise a lista acima e depois execute:"
echo 'git commit -m "chore: organiza versão inicial do corretor OMR"'
