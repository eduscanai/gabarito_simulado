from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "avaliacao_web" / "data"
ALLOWED_DATA_FILES = {DATA / ".gitkeep", DATA / "README.md"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key"}
problems: list[str] = []

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    if ".git" in path.parts or ".venv" in path.parts or "external" in path.parts:
        continue
    if path.name == ".env":
        problems.append(f"configuração local versionável: {path.relative_to(ROOT)}")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        problems.append(f"arquivo sensível: {path.relative_to(ROOT)}")
    if DATA in path.parents and path not in ALLOWED_DATA_FILES:
        problems.append(f"dado de execução: {path.relative_to(ROOT)}")

if problems:
    print("Foram encontrados arquivos que não devem ser publicados:")
    for problem in problems:
        print(f"- {problem}")
    raise SystemExit(1)

print("Repositório limpo: nenhum dado de execução ou segredo óbvio foi encontrado.")
