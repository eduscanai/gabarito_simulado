# Avisos e atribuições

## OMRChecker

A aplicação utiliza o projeto externo OMRChecker para detectar as alternativas
marcadas nas folhas de respostas.

- Projeto: OMRChecker
- Repositório: https://github.com/Udayraj123/OMRChecker

O OMRChecker não está incluído neste pacote. Os scripts de instalação clonam o
repositório separadamente em `external/OMRChecker`, diretório ignorado pelo Git.
Ao redistribuir uma cópia do OMRChecker, verifique e respeite a licença e os
avisos do projeto original.

## Tesseract OCR

A leitura de matrícula em blocos utiliza o executável local Tesseract OCR. O
Tesseract também é instalado separadamente e não faz parte deste repositório.
