# OMR Correction Service

Microserviço HTTP stateless que expõe a lógica de geração/correção de folhas
OMR do OMRChecker (bolhas, marcadores, matrícula em blocos via OCR). Não
conhece escola, turma, aluno ou qualquer outro conceito de negócio — recebe
arquivos, devolve resultado. Toda a modelagem e persistência ficam do lado de
quem chama (no caso, o EduScanAI).

Faz parte da Fase 1 do plano "Módulo Simulados no EduScanAI".

## Rodando localmente

```bash
cd service
pip install -r requirements.txt
# tesseract precisa estar instalado no sistema, ex: brew install tesseract
uvicorn main:app --reload --port 8000
```

Variáveis de ambiente (todas opcionais para uso local):

- `OMR_ROOT`: caminho da raiz do OMRChecker (onde está `main.py`). Por
  padrão, assume que `service/` está dentro do checkout do `omrchecker`
  (`service/../`), igual ao `avaliacao_web`.
- `OMR_SERVICE_TMP_DIR`: onde os diretórios temporários de processamento são
  criados (`/tmp/omr-service` por padrão).
- `OMR_SERVICE_TOKEN`: segredo compartilhado exigido no header
  `Authorization: Bearer <token>`. Se vazio, nenhuma checagem é feita (só
  para desenvolvimento local — sempre defina em qualquer ambiente exposto).
- `OMR_SERVICE_TIMEOUT`: timeout em segundos do subprocesso do OMRChecker
  (180 por padrão).

## Endpoints

### `POST /v1/gabarito/gerar`

Gera o template de bolhas, config, marcador e os PDFs (folha de respostas e
solução) a partir de uma lista de questões.

```json
{
  "titulo": "Simulado de Matemática",
  "identificador": "turma-9a-simulado-1",
  "matricula_em_blocos": true,
  "questoes": [
    {"numero": 1, "option_count": 4, "resposta": "B", "peso": 1.0}
  ],
  "alunos": [
    {"aluno_id": "uuid-do-aluno", "nome": "Fulano", "matricula": "202600001"}
  ]
}
```

Devolve `gabarito`, `pesos` e os arquivos gerados em base64
(`template_json`/`config_json` já vêm como objeto, os demais como base64).
Se `alunos` for enviado, devolve também `folhas_alunos`: uma folha de
respostas **personalizada por aluno**, cada uma com um QR code
(`SIM:{identificador}|ALU:{aluno_id}`) impresso no canto inferior direito —
usado por `/v1/folha/corrigir` para identificar o aluno sem depender de OCR.
`identificador` deve ser o id do simulado (é o que vai dentro do QR).

### `POST /v1/folha/corrigir`

`multipart/form-data` com:

- `sheet`: arquivo escaneado (PNG/JPG/JPEG/PDF).
- `template`, `config`, `marker`: os mesmos arquivos devolvidos por
  `/v1/gabarito/gerar` para aquele simulado.
- `matricula_em_blocos` (form bool): se `true`, roda o OCR dos 10 blocos de
  matrícula.
- `gabarito_json` (form string, opcional): JSON
  `{"questoes": [...], "valor_maximo": 10}` — se enviado, a nota já vem
  calculada na resposta.

Devolve respostas detectadas por questão, **QR decodificado** (se a folha for
personalizada — `{"simulado_id", "aluno_id"}` ou `null`), matrícula OCR (se
solicitado), nota (se gabarito enviado), a imagem processada em base64 e um
trecho do log do OMRChecker para diagnóstico. O QR é tentado sempre (mesmo
com `matricula_em_blocos=false`); a matrícula manuscrita continua existindo
como método de identificação alternativo/fallback quando não há QR ou ele não
foi lido — quem decide qual usar é o chamador (o QR é bem mais confiável que
OCR de caligrafia).

Processa **uma folha por chamada** (uma imagem, ou só a primeira página de um
PDF). Para lotes (um PDF com várias folhas escaneadas de uma vez), divida
primeiro com `/v1/folha/dividir` e chame este endpoint uma vez por página.

### `POST /v1/folha/dividir`

`multipart/form-data` com um único campo `arquivo` (PNG/JPG/JPEG/PDF). Uma
imagem passa direto (1 página); um PDF de várias páginas é dividido em uma
imagem PNG por página (renderização com PyMuPDF, 3x de escala). Devolve
`{"paginas": [{"nome": "...", "conteudo_base64": "..."}, ...]}`.

## Docker

```bash
# a partir da raiz do repo omrchecker (não de dentro de service/)
docker build -f service/Dockerfile -t omr-service .
docker run --rm -p 8000:8000 -e OMR_SERVICE_TOKEN=changeme omr-service
```
