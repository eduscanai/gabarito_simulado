from __future__ import annotations

import os
from pathlib import Path

# service/app/config.py -> service/app -> service -> omrchecker (repo root)
SERVICE_DIR = Path(__file__).resolve().parent.parent
OMR_ROOT = Path(os.getenv("OMR_ROOT", str(SERVICE_DIR.parent))).expanduser().resolve()

TMP_ROOT = Path(
    os.getenv("OMR_SERVICE_TMP_DIR", "/tmp/omr-service")
).expanduser().resolve()

# Shared secret checked on every request. Left empty only for local dev.
SERVICE_TOKEN = os.getenv("OMR_SERVICE_TOKEN", "")

SUBPROCESS_TIMEOUT_SECONDS = int(os.getenv("OMR_SERVICE_TIMEOUT", "180"))

TMP_ROOT.mkdir(parents=True, exist_ok=True)
