from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OMR = ROOT / "external" / "OMRChecker"
OMR_ROOT = Path(os.getenv("OMR_ROOT", DEFAULT_OMR)).expanduser().resolve()

checks = []

def add(name: str, ok: bool, detail: str) -> None:
    checks.append((name, ok, detail))

add("Python", sys.version_info >= (3, 11), sys.version.split()[0])
add("Tesseract", shutil.which("tesseract") is not None, shutil.which("tesseract") or "não encontrado")
add("OMRChecker", (OMR_ROOT / "main.py").exists(), str(OMR_ROOT / "main.py"))

for module in ["fastapi", "uvicorn", "reportlab", "PIL", "sqlalchemy", "fitz", "cv2", "numpy"]:
    add(f"Python: {module}", importlib.util.find_spec(module) is not None, "instalado" if importlib.util.find_spec(module) else "ausente")

failed = False
for name, ok, detail in checks:
    marker = "OK" if ok else "FALHA"
    print(f"[{marker:5}] {name}: {detail}")
    failed = failed or not ok

raise SystemExit(1 if failed else 0)
