# Privacidade e dados acadêmicos

O sistema pode armazenar dados pessoais e acadêmicos. O repositório de código
não deve conter dados de produção.

## Nunca versionar

- nomes e matrículas reais;
- notas;
- imagens de provas;
- PDFs preenchidos;
- `corretor.db`;
- relatórios de processamento;
- arquivos `.env`;
- backups.

## Separação recomendada

Mantenha o código no Git e os dados em um diretório local ou volume separado,
configurado por `OMR_DATA_DIR`.

## Compartilhamento de erros

Ao abrir uma issue, substitua nomes, matrículas e respostas por dados fictícios.
Recorte a imagem apenas na área necessária e remova metadados quando possível.
