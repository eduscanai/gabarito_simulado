# Contribuindo

## Preparação

1. crie uma branch a partir de `main`;
2. configure o ambiente conforme `docs/INSTALACAO.md`;
3. não use dados reais de alunos em testes ou commits;
4. execute `pytest`, `ruff check tests scripts` e `python scripts/check_repository.py` antes de abrir o pull request.

## Padrão de commits

Use mensagens curtas e descritivas, por exemplo:

```text
feat: adiciona importação de alunos por CSV
fix: corrige recorte da matrícula em scans inclinados
docs: atualiza guia de instalação no Windows
```

## Dados de teste

Use apenas dados fictícios. Não inclua:

- nomes reais de alunos;
- matrículas reais;
- provas digitalizadas;
- notas;
- banco `corretor.db`;
- arquivos dentro de `avaliacao_web/data/`.
