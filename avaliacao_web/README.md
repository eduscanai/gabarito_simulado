# Criador e corretor de avaliações OMR - versão 23

## Correção em lote por matrícula escrita em blocos

A versão 23 ativa o envio em lote e combina duas leituras locais:

- **Tesseract OCR** para reconhecer os algarismos escritos nos blocos da matrícula;
- **OMRChecker** para reconhecer as alternativas e calcular a nota.

Depois da leitura, a aplicação procura a matrícula na lista da avaliação ou no
SQLite, associa a folha ao aluno, salva o resultado e atualiza a nota.

## Formatos aceitos

- vários arquivos PNG, JPG, JPEG ou PDF;
- um PDF com várias páginas, sendo uma folha por página;
- máximo de 30 arquivos e 60 páginas por lote.

## Segurança

A aplicação só lança automaticamente quando a matrícula reconhecida coincide
com um aluno cadastrado. Matrículas ilegíveis, inexistentes, duplicadas ou de
alunos já corrigidos são encaminhadas para revisão e não sobrescrevem notas.

## Dependência do sistema

No macOS, instale o Tesseract uma única vez:

```bash
brew install tesseract
```

Depois instale as dependências Python:

```bash
python -m pip install -r avaliacao_web/requirements-web.txt
```

## Observação sobre escrita manual

O OCR depende de os algarismos serem grandes, centralizados e sem encostar nas
bordas dos blocos. A primeira validação deve ser feita com algumas folhas
físicas antes de usar uma turma completa.
