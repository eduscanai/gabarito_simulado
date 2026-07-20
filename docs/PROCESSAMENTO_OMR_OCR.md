# Processamento OMR e OCR

## OMR

O OMRChecker identifica as alternativas preenchidas depois que a folha é
recortada e alinhada pelos quatro marcadores. A aplicação gera, para cada
avaliação:

- `template.json`;
- `config.json`;
- `evaluation.json`;
- marcador de referência;
- PDF da folha de respostas.

## OCR da matrícula

A matrícula possui dez blocos. O processamento:

1. carrega a imagem ou a primeira página do arquivo;
2. encontra os quatro marcadores;
3. corrige perspectiva e escala;
4. recorta cada bloco;
5. prepara contraste e binarização;
6. chama o Tesseract para reconhecer um único dígito;
7. combina os dez resultados;
8. compara com as matrículas cadastradas.

## Critério de segurança

Uma folha só deve ser associada automaticamente quando o resultado corresponde
a um aluno existente. Casos ambíguos devem ser revisados, nunca atribuídos por
aproximação silenciosa.

## Fatores que reduzem a precisão

- algarismos pequenos;
- escrita encostando nas bordas;
- caneta muito clara;
- scan cortado;
- marcador oculto;
- folha inclinada ou amassada;
- fotografia com sombra;
- dígitos visualmente semelhantes, como 1/7 e 3/8.

## Validação recomendada

Monte um conjunto de teste com diferentes pessoas e materiais:

- caneta preta e azul;
- scanner e câmera de celular;
- escrita forte e leve;
- diferentes algarismos repetidos;
- folhas perfeitamente alinhadas e levemente inclinadas.

Registre taxa de acerto por dígito, por matrícula e por tipo de captura antes de
uso institucional.
