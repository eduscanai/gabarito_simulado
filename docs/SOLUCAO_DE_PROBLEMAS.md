# Solução de problemas

## `Address already in use`

Use outra porta:

```bash
PORT=8004 bash scripts/run_macos.sh
```

Ou encerre o processo antigo:

```bash
lsof -tiTCP:8003 -sTCP:LISTEN | xargs kill
```

## `main.py do OMRChecker não foi encontrado`

Execute o setup ou defina `OMR_ROOT`:

```bash
bash scripts/setup_macos.sh
export OMR_ROOT="$PWD/external/OMRChecker"
```

## `Tesseract OCR não está instalado`

macOS:

```bash
brew install tesseract
```

Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr
```

## A matrícula não é reconhecida

- escreva números maiores e centralizados;
- não encoste nas bordas;
- confirme que os quatro marcadores estão visíveis;
- digitalize em 300 dpi;
- confira se a matrícula existe na lista e no banco.

## `ModuleNotFoundError`

Ative o ambiente correto e reinstale:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Banco com estrutura incompatível durante o desenvolvimento

Faça backup de `avaliacao_web/data` antes de qualquer ação. Em uma instalação de
teste, pode-se recriar o banco e importar os JSON novamente:

```bash
rm avaliacao_web/data/corretor.db
python -m avaliacao_web.database_cli import-json
```

Não execute essa remoção sem backup em um ambiente com dados importantes.
