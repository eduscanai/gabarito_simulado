# Instalação

## 1. Pré-requisitos

- Python 3.11 ou superior;
- Git;
- Tesseract OCR;
- acesso ao terminal;
- scanner ou celular para digitalizar as folhas.

## 2. macOS

Instale o Tesseract:

```bash
brew install tesseract
```

Clone o repositório e execute o instalador:

```bash
git clone <URL-DO-SEU-REPOSITORIO>
cd corretor-omr-local
bash scripts/setup_macos.sh
```

O script:

1. cria `.venv`;
2. clona o OMRChecker em `external/OMRChecker`;
3. instala as dependências do OMRChecker;
4. instala as dependências da interface web;
5. inicializa o SQLite.

Execute:

```bash
bash scripts/run_macos.sh
```

## 3. Linux

Instale o Tesseract conforme a distribuição. Em Debian/Ubuntu:

```bash
sudo apt update
sudo apt install tesseract-ocr
```

Depois:

```bash
git clone <URL-DO-SEU-REPOSITORIO>
cd corretor-omr-local
bash scripts/setup_linux.sh
bash scripts/run_linux.sh
```

## 4. Windows

1. instale Python e Git;
2. instale o Tesseract e adicione o executável ao `PATH`;
3. abra o PowerShell na pasta do projeto;
4. execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
.\scriptsun_windows.ps1
```

## 5. Instalação sobre uma cópia existente do OMRChecker

A configuração mantém compatibilidade com o formato antigo. Quando a pasta
`avaliacao_web` está diretamente dentro da raiz do OMRChecker, o sistema detecta
`main.py` automaticamente.

Também é possível definir explicitamente:

```bash
export OMR_ROOT=/caminho/para/OMRChecker
```

## 6. Verificação

```bash
source .venv/bin/activate
python scripts/check_environment.py
python -m avaliacao_web.database_cli status
```

## 7. Variáveis de ambiente

Copie o exemplo:

```bash
cp .env.example .env
```

Os scripts carregam `.env` automaticamente. As variáveis principais são:

- `HOST`;
- `PORT`;
- `OMR_ROOT`;
- `OMR_DATA_DIR`;
- `OMR_DATABASE_PATH`;
- `DATABASE_URL`.
