$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git não encontrado." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python não encontrado." }
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Warning "Tesseract não encontrado no PATH. Instale-o antes do teste em lote."
}

python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel

New-Item -ItemType Directory -Force -Path external | Out-Null
if (-not (Test-Path external\OMRChecker\main.py)) {
    git clone https://github.com/Udayraj123/OMRChecker.git external\OMRChecker
}
if (Test-Path external\OMRChecker\requirements.txt) {
    python -m pip install -r external\OMRChecker\requirements.txt
}
python -m pip install -r requirements.txt
python -m avaliacao_web.database_cli init
Write-Host "Instalação concluída. Execute .\scripts\run_windows.ps1"
