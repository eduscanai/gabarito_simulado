# Guia de uso

## Criar um simulado

1. abra a página inicial;
2. clique em **Criar simulado**;
3. informe título, quantidade de questões, alternativas e gabarito;
4. escolha peso uniforme ou peso por questão;
5. informe o valor total da prova;
6. salve o simulado.

## Imprimir a folha

Na página do simulado, clique em **Folha**. Todas as folhas possuem:

- quatro marcadores de alinhamento;
- campo de nome;
- dez blocos para matrícula;
- alternativas de cada questão.

O aluno deve escrever um dígito grande e centralizado em cada bloco.

## Correção individual

1. selecione um aluno;
2. clique em **Anexar folha do aluno**;
3. envie PDF, PNG, JPG ou JPEG;
4. aguarde a leitura e confira a nota.

## Correção em lote

1. digitalize uma folha por imagem ou uma página por aluno no PDF;
2. clique em **Corrigir lote**;
3. selecione os arquivos;
4. o sistema separa as páginas, lê a matrícula, corrige e associa o resultado;
5. confira o relatório do lote.

O sistema não deve lançar automaticamente quando:

- a matrícula não for reconhecida;
- a matrícula não existir;
- houver duas folhas do mesmo aluno no mesmo lote;
- o aluno já tiver uma correção que não deva ser sobrescrita;
- o processamento OMR falhar.

## Boas práticas de digitalização

- inclua a folha inteira e os quatro marcadores;
- evite sombras e dobras;
- use 300 dpi no scanner quando possível;
- mantenha a câmera paralela à folha;
- escreva os algarismos sem tocar nas bordas;
- teste primeiro com duas ou três folhas.

## Backup

```bash
bash scripts/backup_data.sh
```

Os backups são gravados em `backups/`, pasta ignorada pelo Git.
