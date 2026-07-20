$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path .venv\Scripts\Activate.ps1)) {
    throw "Ambiente .venv não encontrado. Execute setup_windows.ps1."
}
& .\.venv\Scripts\Activate.ps1

if (-not $env:OMR_ROOT) { $env:OMR_ROOT = Join-Path $Root "external\OMRChecker" }
if (-not $env:HOST) { $env:HOST = "127.0.0.1" }
if (-not $env:PORT) { $env:PORT = "8003" }

python -m avaliacao_web.database_cli init
python -m avaliacao_web.database_cli import-json
python -m uvicorn avaliacao_web.app:app --host $env:HOST --port $env:PORT
