# Testes

## Testes automatizados

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

Os testes atuais verificam funções puras de normalização e cálculo. Eles não
substituem o teste físico do scanner e do OCR.

## Teste físico mínimo

1. crie uma avaliação com cinco questões;
2. imprima três folhas;
3. use três matrículas fictícias;
4. preencha respostas conhecidas;
5. digitalize uma folha por imagem e duas páginas em PDF;
6. envie em lote;
7. compare matrícula, respostas e nota esperada;
8. teste uma matrícula ilegível e confirme que não foi atribuída.

## Critérios antes de uso real

- nenhuma atribuição incorreta de aluno;
- revisão obrigatória em casos ambíguos;
- respostas OMR iguais ao preenchimento visual;
- backup restaurável;
- logs sem exposição desnecessária de dados.
