# Publicar no GitHub

## 1. Verificar dados privados

Antes do primeiro commit:

```bash
python scripts/check_environment.py
python scripts/check_repository.py
git status --ignored
```

Confirme que `avaliacao_web/data`, `.env`, `external/OMRChecker` e `backups` não
serão versionados.

## 2. Inicializar o repositório

```bash
git init
git branch -M main
git add .
git status
git commit -m "chore: organiza versão inicial do gerador de simulados"
```

## 3. Criar o repositório remoto

Pelo site do GitHub, crie um repositório vazio, preferencialmente privado na
primeira publicação. Não peça ao GitHub para gerar README ou `.gitignore`, pois
estes arquivos já existem.

Depois:

```bash
git remote add origin <URL-DO-REPOSITORIO>
git push -u origin main
```

Com GitHub CLI:

```bash
gh repo create gerador-de-simulados --private --source=. --remote=origin --push
```

## 4. Antes de tornar público

- escolha uma licença;
- remova chaves e caminhos pessoais;
- confirme que não existem provas ou matrículas reais no histórico;
- revise a licença do OMRChecker;
- faça um clone limpo e teste a instalação.

## 5. Remover um arquivo privado já commitado

Apagar o arquivo em um commit novo não remove o conteúdo do histórico. Nesse
caso, interrompa a publicação e use uma ferramenta própria para reescrever o
histórico, além de trocar qualquer segredo exposto.
