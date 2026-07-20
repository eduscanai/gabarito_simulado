# Arquitetura

## Componentes

```text
avaliacao_web/
├── app.py              # rotas FastAPI, PDF, OMR, OCR e regras de negócio
├── config.py           # caminhos e variáveis de ambiente
├── database.py         # engine e sessão SQLAlchemy
├── models.py           # tabelas relacionais
├── repository.py       # sincronização JSON ↔ SQLite
├── database_cli.py     # init, import-json e status
├── static/             # HTML, CSS e JavaScript
└── data/               # dados privados de execução
```

## Fluxo de criação

```text
Interface → FastAPI → validação → PDF/template/configuração OMR
                           └────→ JSON + sincronização SQLite
```

## Fluxo da correção em lote

```text
Arquivos/PDF
    │
    ├── expansão de páginas
    ├── detecção dos quatro marcadores
    ├── transformação de perspectiva
    ├── recorte dos blocos da matrícula
    ├── Tesseract OCR
    ├── busca do aluno
    ├── OMRChecker
    ├── cálculo ponderado
    └── JSON + arquivos + SQLite
```

## Armazenamento híbrido

A versão atual está em transição:

- JSON e arquivos continuam sendo usados por partes da interface;
- SQLite recebe os dados sincronizados;
- o objetivo futuro é tornar o banco a fonte principal e manter JSON apenas
  para exportação e compatibilidade.

## Execução do OMRChecker

O `app.py` chama o `main.py` do OMRChecker em um subprocesso. O caminho é
resolvido pela variável `OMR_ROOT` ou automaticamente por uma destas formas:

1. `main.py` na pasta pai de `avaliacao_web`;
2. `external/OMRChecker/main.py` em um clone independente.
