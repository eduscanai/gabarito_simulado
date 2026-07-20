# Roadmap

## Próximas prioridades

1. cadastrar alunos e turmas pela interface;
2. substituir os alunos fictícios por dados reais importados;
3. criar fila persistente de revisão manual;
4. mostrar o recorte da matrícula e a confiança de cada dígito;
5. permitir correção manual da matrícula reconhecida;
6. mover as leituras principais de JSON para SQLite;
7. criar migrações formais de banco com Alembic;
8. criar exportação de notas para CSV/XLSX;
9. adicionar autenticação local opcional;
10. testar diferentes scanners, celulares, canetas e caligrafias.

## Limitações atuais

- a leitura de escrita manual depende da qualidade do scan e da caligrafia;
- a fila de revisão ainda não é um módulo completo e persistente;
- o SQLite recebe dados sincronizados, mas parte da interface ainda usa JSON;
- o sistema foi pensado inicialmente para uso local por um professor;
- ainda não há gestão completa de turmas e usuários.
