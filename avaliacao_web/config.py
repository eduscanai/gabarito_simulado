from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

default_data_root = BASE_DIR / "data"
DATA_ROOT = Path(
    os.getenv("OMR_DATA_DIR", str(default_data_root))
).expanduser().resolve()

ASSESSMENTS_DIR = DATA_ROOT / "avaliacoes"

default_database_path = DATA_ROOT / "corretor.db"
DATABASE_PATH = Path(
    os.getenv("OMR_DATABASE_PATH", str(default_database_path))
).expanduser().resolve()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATABASE_PATH.as_posix()}",
)

legacy_omr_root = BASE_DIR.parent
repository_omr_root = BASE_DIR.parent / "external" / "OMRChecker"
default_omr_root = (
    legacy_omr_root
    if (legacy_omr_root / "main.py").exists()
    else repository_omr_root
)
OMR_ROOT = Path(
    os.getenv("OMR_ROOT", str(default_omr_root))
).expanduser().resolve()


def ensure_storage_directories() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    ASSESSMENTS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


ensure_storage_directories()
