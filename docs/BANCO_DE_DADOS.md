# Banco de dados

## Tecnologia

O sistema usa SQLite por meio do SQLAlchemy. Por padrão, o arquivo é:

```text
avaliacao_web/data/corretor.db
```

## Tabelas

- `students`: alunos;
- `classes`: turmas;
- `class_students`: vínculo entre turma e aluno;
- `assessments`: simulados;
- `questions`: questões e gabarito;
- `assessment_students`: vínculo entre simulado e aluno;
- `submissions`: folhas enviadas;
- `results`: resultado geral;
- `detected_answers`: respostas detectadas por questão.

## Comandos

```bash
python -m avaliacao_web.database_cli init
python -m avaliacao_web.database_cli import-json
python -m avaliacao_web.database_cli status
```

A importação é idempotente: repetir o comando não deve duplicar registros
protegidos pelas restrições de unicidade.

## Estado atual

O banco ainda não é a única fonte de verdade. Parte da interface lê os arquivos
JSON dos simulados e sincroniza o SQLite. Isso preserva compatibilidade com as
versões anteriores enquanto a migração é concluída.

## Backup

Para uma cópia completa, salve toda a pasta `avaliacao_web/data`, não apenas o
arquivo `.db`, pois as imagens e PDFs permanecem no sistema de arquivos.
