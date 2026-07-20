#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="backups/corretor-omr-data-$STAMP.tar.gz"
tar -czf "$ARCHIVE" avaliacao_web/data
echo "Backup criado em: $ARCHIVE"
