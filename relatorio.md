# Construção de um Compilador para Fortran 77

**Projeto de Processamento de Linguagens 2026**  
Universidade do Minho — Licenciatura em Engenharia Informática  
Grupo 18

---

## 1. Introdução

Este relatório descreve o desenvolvimento de um compilador para a linguagem Fortran 77 (norma ANSI X3.9-1978), implementado em Python com recurso à biblioteca PLY (*Python Lex-Yacc*). O compilador traduz código fonte Fortran em instruções para a máquina virtual EWVM, passando pelas fases clássicas de análise léxica, análise sintática, análise semântica e geração de código.

O subconjunto da linguagem suportado inclui declarações de variáveis escalares e arrays unidimensionais, expressões aritméticas, relacionais e lógicas com precedência conforme a norma, estruturas de controlo de fluxo (`IF-THEN-ELSE`, ciclos `DO` com labels e `GOTO`), operações de entrada e saída básicas (`READ *`, `PRINT *`) e chamadas a subrotinas externas (`CALL`).

Relativamente ao formato do código fonte, optou-se pelo formato *free-form*: o compilador não impõe as restrições de colunas fixas do Fortran 77 original (código nas colunas 7–72, comentários na coluna 1 com o caractere `C`). Esta decisão simplifica o analisador léxico e é compatível com todos os exemplos fornecidos no enunciado. Comentários são suportados com o delimitador `!`.

---

## 2. Arquitectura do Compilador

O compilador está organizado como um *package* Python no directório `src/`, com os seguintes módulos:

```
src/
├── __init__.py
├── lexer.py        — análise léxica (PLY lex)
├── parser.py       — análise sintática (PLY yacc)
├── ast_nodes.py    — definição dos nós da AST
├── semantic.py     — análise semântica e tabela de símbolos
└── codegen.py      — geração de código EWVM

tests/
├── test_lexer.py   — testes unitários do lexer
├── test_parser.py  — testes unitários do parser
└── test_semantic.py — testes unitários da análise semântica

examples/
├── hello.f77       — exemplos Fortran de entrada
└── hello.vm        — código EWVM gerado correspondente
```

O processamento segue um *pipeline* linear entre módulos independentes:

```
código Fortran → lexer.py → parser.py → semantic.py → codegen.py → código EWVM
                 tokens      AST          AST corrigida
```

A separação em módulos autónomos tem como consequência directa a testabilidade independente de cada fase: os testes do lexer não dependem do parser, e os testes do parser não dependem da análise semântica. Isto facilita a localização de erros e permite evoluir cada fase sem risco de regressão nas restantes.

---

## 3. Análise Léxica

### 3.1 Implementação

O analisador léxico está implementado em `src/lexer.py` com `ply.lex`. A função pública `build_lexer()` constrói e devolve sempre uma instância com estado limpo (contador de linhas a 1, sem input residual). Usar esta função em cada invocação — em vez de partilhar uma instância global — evita que o estado de um teste ou de uma chamada anterior contamine os resultados seguintes.

### 3.2 Tokens reconhecidos

Os tokens estão organizados nas seguintes categorias:

**Palavras-chave** (25): `PROGRAM`, `END`, `STOP`, `INTEGER`, `REAL`, `LOGICAL`, `CHARACTER`, `DIMENSION`, `IF`, `THEN`, `ELSE`, `ENDIF`, `DO`, `CONTINUE`, `GOTO`, `PRINT`, `READ`, `WRITE`, `FUNCTION`, `SUBROUTINE`, `CALL`, `RETURN`, `COMMON`, `PARAMETER`.

**Literais**: identificadores (`ID`), inteiros (`INT_LIT`), reais (`REAL_LIT`), strings (`STRING_LIT`) e booleanos (`BOOL_LIT`).

**Operadores aritméticos**: `PLUS`, `MINUS`, `STAR`, `SLASH`, `POWER`.

**Operadores relacionais e lógicos**: `EQ`, `NE`, `LT`, `LE`, `GT`, `GE`, `AND`, `OR`, `NOT`.

**Pontuação**: `LPAREN`, `RPAREN`, `COMMA`, `EQUALS`, `COLON`.

### 3.3 Decisões de design

**Case-insensitivity.** O Fortran 77 não distingue maiúsculas de minúsculas. A normalização para maiúsculas é feita em `t_ID`, que converte `t.value` para uppercase antes de consultar o dicionário `reserved`. Todas as fases posteriores recebem assim tokens em uppercase, sem necessidade de comparações case-insensitive em nenhum outro módulo.

**Prioridade de regras.** O PLY atribui prioridade às funções face às strings, e dentro das funções ordena por posição no ficheiro. Duas consequências práticas decorrem deste comportamento: a regra `t_POWER` (padrão `\*\*`) está definida antes de `t_STAR` (padrão `\*`) para que a sequência `**` não seja consumida como dois tokens `STAR` separados; a regra `t_REAL_LIT` está definida antes de `t_INT_LIT` para que `3.14` não seja tokenizado como `INT_LIT(3)` seguido de outros tokens.

**Operadores relacionais e lógicos.** A sintaxe Fortran `.GT.`, `.LT.`, `.AND.`, etc. é tratada por uma única função `t_RELOP` com a expressão regular `\.(GT|LT|GE|LE|EQ|NE|AND|OR|NOT)\.`, que despacha para o tipo de token correcto via dicionário. Esta abordagem unificada elimina duplicação de código e garante que a correspondência é sempre determinística.

**Booleanos.** Os literais `.TRUE.` e `.FALSE.` são convertidos para `bool` Python directamente no lexer. Esta decisão antecipa a conversão que seria necessária na análise semântica ou na geração de código, mantendo essas fases mais simples.

**Comentários.** A função `t_COMMENT` tem padrão `![^\n]*` e não devolve `t`, pelo que os comentários são descartados silenciosamente sem gerar tokens. O parser nunca recebe tokens de comentário e não precisa de os tratar na gramática.

### 3.4 Testes

O módulo `tests/test_lexer.py` contém 14 classes de teste cobrindo todas as categorias de tokens, case-insensitivity, contagem de linhas, e os três programas de exemplo do enunciado (`HELLO`, `FATORIAL`, `PRIMO`). Todos os testes passam.

---

## 4. Análise Sintática

### 4.1 Implementação

O analisador sintático está implementado em `src/parser.py` com `ply.yacc`, método LALR(1). A função pública `build_parser()` gera as tabelas LALR e devolve uma instância do parser. A AST produzida é composta pelos nós definidos em `src/ast_nodes.py`.

### 4.2 Gramática

As produções principais da gramática são as seguintes:

```
program      → PROGRAM ID decl_list stmt_list END

decl_list    → decl_list decl | ε
decl         → type_kw id_list
type_kw      → INTEGER | REAL | LOGICAL | CHARACTER
id_list      → id_list COMMA id_item | id_item
id_item      → ID                            (escalar)
             | ID LPAREN INT_LIT RPAREN      (array unidimensional)

stmt_list    → stmt_list stmt | ε
stmt         → labeled_stmt | assign_stmt | if_stmt | do_stmt
             | goto_stmt | print_stmt | read_stmt | continue_stmt
             | stop_stmt | return_stmt | call_stmt

labeled_stmt → INT_LIT stmt
assign_stmt  → ID EQUALS expr
             | ID LPAREN expr_list RPAREN EQUALS expr

if_stmt      → IF LPAREN expr RPAREN THEN stmt_list ENDIF
             | IF LPAREN expr RPAREN THEN stmt_list ELSE stmt_list ENDIF

do_stmt      → DO INT_LIT ID EQUALS expr COMMA expr
             | DO INT_LIT ID EQUALS expr COMMA expr COMMA expr

goto_stmt    → GOTO INT_LIT
print_stmt   → PRINT STAR COMMA expr_list
read_stmt    → READ STAR COMMA expr_list
call_stmt    → CALL ID LPAREN expr_list RPAREN | CALL ID

expr         → expr op expr | MINUS expr | NOT expr
             | LPAREN expr RPAREN
             | ID | INT_LIT | REAL_LIT | STRING_LIT | BOOL_LIT
             | ID LPAREN expr_list RPAREN    (FuncCall unificado)
```

### 4.3 Precedência de operadores

A tabela de precedência do PLY resolve as ambiguidades nas expressões, respeitando a hierarquia definida pela norma ANSI X3.9-1978:

| Nível | Operadores | Associatividade |
|-------|-----------|-----------------|
| 1 (menor) | `.OR.` | esquerda |
| 2 | `.AND.` | esquerda |
| 3 | `.NOT.` | direita |
| 4 | `.EQ.` `.NE.` `.LT.` `.LE.` `.GT.` `.GE.` | não-associativo |
| 5 | `+` `-` | esquerda |
| 6 | `*` `/` | esquerda |
| 7 | `-` (unário) | direita |
| 8 (maior) | `**` | direita |

### 4.4 Ambiguidade entre chamada de função e referência a array

O Fortran 77 apresenta uma ambiguidade inerente: a expressão `F(X)` pode representar uma chamada de função ou uma referência a um elemento de array, e a sintaxe é gramaticalmente indistinguível. A distinção requer consultar a tabela de símbolos, que só existe na fase semântica.

A versão inicial do parser continha duas produções com padrão idêntico, o que gerava um conflito *reduce/reduce* nas tabelas LALR: ao reduzir `ID LPAREN expr_list RPAREN`, o parser não conseguia determinar qual das duas regras aplicar. O PLY resolve este conflito silenciosamente pela ordem de definição no ficheiro, comportamento que depende de artefactos de implementação e não de semântica da linguagem.

A solução adoptada consiste em colapsar as duas produções numa única (`p_expr_call_or_array`) que gera sempre um nó `FuncCall`. A análise semântica, com acesso à tabela de símbolos, reescreve `FuncCall → ArrayRef` quando o nome está declarado como array. Esta estratégia é a abordagem standard em compiladores reais para linguagens com esta ambiguidade.

Para o caso particular do lado esquerdo de uma atribuição (`NUMS(I) = expr`), o contexto gramatical garante que se trata sempre de um array, pelo que a regra `assign_stmt` gera `ArrayRef` directamente, sem ambiguidade.

### 4.5 Declaração de arrays

O Fortran 77 permite declarar arrays com dimensão na própria declaração de tipo (por exemplo, `INTEGER NUMS(5)`). A gramática foi estendida com as produções `id_item` para suportar esta sintaxe. Cada elemento da lista `VarDecl.names` é um tuplo `(nome, shape)`, onde `shape=None` indica um escalar e `shape=[n]` indica um array de dimensão `n`. Esta representação uniforme simplifica o processamento na análise semântica e no gerador de código.

### 4.6 Corpo do ciclo DO

O Fortran 77 delimita o corpo de um ciclo `DO` por um label numérico associado a um `CONTINUE`:

```fortran
DO 10 I = 1, N
  FAT = FAT * I
10 CONTINUE
```

Um parser LALR(1) não consegue agrupar dinamicamente as instruções entre `DO` e o `CONTINUE` correspondente durante a análise sintática, porque o label que delimita o corpo só é conhecido após consumir todas as instruções interiores. Codificar este comportamento directamente na gramática exigiria produções *context-sensitive*, incompatíveis com o método LALR(1).

A solução adoptada delega este agrupamento para a análise semântica: o parser gera `DoLoop` com `body=[]`, e uma passagem de pré-processamento linear (`_fill_do_bodies`) sobre a lista plana de instruções utiliza uma pilha para associar cada `CONTINUE` ao `DoLoop` com o label correspondente e preencher `DoLoop.body`. Esta limitação do parser está documentada como `xfail` na suite de testes, assinalando o comportamento esperado.

### 4.7 Testes

O módulo `tests/test_parser.py` contém 14 classes de teste. O estado actual da suite é o seguinte:

| Estado | Contagem |
|--------|----------|
| Passou | 104 |
| xfail esperado | 1 (corpo do DO, resolvido na análise semântica) |
| Falhou | 0 |

---

## 5. Nós da AST

Os nós da AST estão definidos como `dataclass` Python em `src/ast_nodes.py`. A escolha de `dataclass` justifica-se pela geração automática de `__repr__` (essencial durante o debug) e pela ausência de código repetitivo em comparação com classes definidas manualmente. Todos os nós herdam de uma classe base `Node` vazia, o que permite verificações de tipo uniformes nas fases seguintes.

Os principais nós e os seus campos relevantes são:

| Nó | Campos | Descrição |
|----|--------|-----------|
| `Program` | `name`, `decls`, `body` | Raiz da AST |
| `VarDecl` | `type_name`, `names: list[(str, list\|None)]` | Declaração de tipo |
| `Assign` | `target`, `value` | Atribuição; `target` é `ID` ou `ArrayRef` |
| `DoLoop` | `label`, `var`, `start`, `stop`, `step`, `body` | Ciclo DO |
| `IfThen` | `condition`, `then_body`, `else_body` | Condicional |
| `LabeledStmt` | `label`, `stmt` | Instrução com label numérico |
| `BinOp` | `left`, `op`, `right` | Expressão binária |
| `FuncCall` | `name`, `args` | Chamada de função ou referência a array (antes da fase semântica) |
| `ArrayRef` | `name`, `indices` | Referência a array (após resolução semântica) |

---

## 6. Análise Semântica

### 6.1 Estrutura

A análise semântica está implementada em `src/semantic.py` e segue o padrão *Visitor*: a classe `SemanticAnalyser` herda de `Visitor` e implementa um método `visit_<NomeDoNó>` para cada tipo de nó relevante. O despacho é feito por reflexão (`getattr`), seguindo o mesmo padrão do `ast.NodeVisitor` da biblioteca standard do Python. Os métodos `visit_*` devolvem o nó, possivelmente reescrito, o que permite que a substituição `FuncCall → ArrayRef` aconteça de forma transparente durante a travessia da AST.

### 6.2 Tabela de símbolos

A classe `SymbolTable` mapeia nomes normalizados para instâncias de `Symbol`:

```python
@dataclass
class Symbol:
    name:      str
    type_name: str            # 'INTEGER', 'REAL', 'LOGICAL', 'CHARACTER'
    kind:      str            # 'variable' | 'array' | 'function' | 'subroutine'
    shape:     Optional[list] # None para escalares; [5] para arrays de dimensão 5
```

Em Fortran 77 o escopo é plano por unidade de programa — não existem blocos aninhados dentro de um `PROGRAM`. Uma única instância de `SymbolTable` por unidade é suficiente. Erros e avisos são acumulados em listas em vez de lançar excepções imediatamente, o que permite reportar todos os problemas de uma só vez no final da análise.

### 6.3 Duas passagens sobre o programa

A análise semântica opera em duas passagens sobre o nó `Program`.

Na primeira passagem, `_process_decl` percorre todas as declarações (`VarDecl`) e preenche a tabela de símbolos. Esta passagem ocorre antes de visitar o corpo do programa, garantindo que qualquer referência a um array no corpo encontra o símbolo já registado na tabela.

Na segunda passagem, `visit_list(node.body)` percorre o corpo, aplica as verificações descritas na secção 6.5 e reescreve os nós onde necessário.

Entre as duas passagens, o método `_fill_do_bodies` executa o pré-processamento linear descrito na secção 4.6, agrupando as instruções nos corpos dos ciclos `DO`.

### 6.4 Resolução da ambiguidade FuncCall vs ArrayRef

O método `visit_FuncCall` é o ponto central da resolução da ambiguidade entre chamada de função e referência a array:

```python
def visit_FuncCall(self, node: FuncCall) -> Node:
    node.args = self.visit_list(node.args)

    if self.symbol_table.is_array(node.name):
        return ArrayRef(name=node.name, indices=node.args)

    return node  # mantém FuncCall (função real ou intrínseca)
```

Se o nome está registado com `kind='array'` na tabela de símbolos, o nó `FuncCall` é substituído por `ArrayRef`. Caso contrário, o nó mantém-se como `FuncCall`. Um conjunto de funções intrínsecas conhecidas (`MOD`, `ABS`, `SQRT`, `SIN`, `COS`, `MAX`, `MIN`, entre outras) está definido estaticamente para suprimir avisos desnecessários sobre nomes que não constam na tabela de símbolos mas são válidos em Fortran 77.

### 6.5 Verificações implementadas

| Verificação | Severidade | Descrição |
|-------------|------------|-----------|
| Declaração duplicada | Erro | Mesmo nome declarado mais do que uma vez na mesma unidade |
| GOTO sem label correspondente | Erro | Label referenciado por `GOTO` não existe no programa |
| Variável de controlo do DO não INTEGER | Erro | A norma ANSI exige que a variável de controlo seja inteira |
| Variável usada mas não declarada | Aviso | Nome presente no corpo mas ausente da tabela de símbolos |
| Array usado mas não declarado | Aviso | Referência a array não presente na tabela de símbolos |
| FuncCall de nome desconhecido | Aviso | Chamada a função não declarada e não intrínseca |

Optou-se por emitir avisos, e não erros fatais, para variáveis não declaradas porque o Fortran 77 define tipagem implícita por omissão (variáveis cujo nome começa por I–N são `INTEGER`, as restantes `REAL`). A implementação exige declaração explícita, mas não bloqueia programas que usem a convenção implícita da norma.

### 6.6 Testes

O módulo `tests/test_semantic.py` contém 21 testes em 8 classes, cobrindo a construção da tabela de símbolos, declarações escalares e de arrays, resolução `FuncCall → ArrayRef`, validação de labels de `GOTO`, verificação da variável de controlo do `DO`, avisos para variáveis não declaradas e preenchimento dos corpos de ciclos `DO`. Todos os 21 testes passam.

---

## 7. Geração de Código

### 7.1 Modelo de memória

O gerador de código está implementado em `src/codegen.py` e produz instruções para a EWVM. A máquina virtual usa um modelo de pilha com uma zona de operandos (*operand stack*), uma zona de chamadas (*call stack*) e um *heap* partilhado para strings e arrays.

As variáveis locais são armazenadas com offset relativo ao *frame pointer* (FP). O offset 0 está reservado para o endereço de retorno; as variáveis ocupam os offsets a partir de 1, pela ordem em que são declaradas. Para arrays, os elementos são armazenados de forma contígua a partir do offset base, e o endereço de um elemento `A(i)` é calculado como `FP + offset_base + (i - 1)`, respeitando o indexing 1-based do Fortran.

### 7.2 Mapeamento de instruções

O mapeamento entre operadores Fortran e instruções EWVM é o seguinte:

| Operador Fortran | Instrução EWVM |
|-----------------|----------------|
| `+` | `ADD` |
| `-` | `SUB` |
| `*` | `MUL` |
| `/` | `DIV` |
| `.GT.` | `SUP` |
| `.LT.` | `INF` |
| `.GE.` | `SUPEQ` |
| `.LE.` | `INFEQ` |
| `.EQ.` | `EQUAL` |
| `.NE.` | `EQUAL` + `NOT` |
| `.AND.` | `AND` |
| `.OR.` | `OR` |
| `.NOT.` | `NOT` |
| `-` (unário) | `PUSHI 0` + `SWAP` + `SUB` |

O operador `.NE.` não existe como instrução atómica na EWVM; é implementado como `EQUAL` seguido de `NOT`, equivalente lógico de `NOT (a == b)`. O operador `**` (potência) não tem instrução nativa na EWVM e lança `NotImplementedError` com uma mensagem informativa.

### 7.3 Geração para cada construção

Para `PRINT *`, cada item da lista de expressões é avaliado e empilhado, seguido da instrução de escrita adequada ao tipo (`WRITEI` para `INTEGER` e `LOGICAL`, `WRITEF` para `REAL`, `WRITES` para `CHARACTER`). Um `WRITELN` é emitido no final para o avanço de linha. O tipo de cada item é inferido pelo método `_type_of`, que percorre a AST de forma conservadora.

Para `READ *`, cada variável de destino recebe a instrução `READ` (que lê uma string da entrada) seguida de `ATOI` ou `ATOF` conforme o tipo declarado, e depois `STOREL` para armazenar o valor.

Para `IF-THEN-ELSE`, a condição é avaliada e seguida de `JZ else_label`. O corpo *then* é gerado a seguir, terminado com `JUMP end_label`. O corpo *else* começa com `else_label:` e termina com `end_label:`.

Para o ciclo `DO`, a variável de controlo é inicializada com `STOREL`, o label de início do ciclo é emitido, a condição de paragem é avaliada com `INFEQ` e seguida de `JZ end_label`, o corpo é gerado, o incremento (por omissão 1) é aplicado com `ADD` + `STOREL`, e um `JUMP` volta ao início.

Para `GOTO`, é emitido `JUMP L{label}`, onde `{label}` é o número de label Fortran. As instruções com label emitem `L{label}:` antes do código da instrução interior.

### 7.4 Limitações conhecidas

A geração de código para chamadas a subrotinas e funções externas (`CALL`, `FUNCTION`, `SUBROUTINE`) não está implementada nesta fase. A sua implementação exige um modelo de *frames* com passagem de parâmetros e convenção de chamada, que o enunciado classifica como valorização. O método `_generate_call` lança `NotImplementedError` com uma mensagem explicativa.

---

## 8. Testes e Validação

### 8.1 Testes automatizados

A estratégia de testes segue uma abordagem *bottom-up*: cada fase é testada de forma independente antes de avançar para a seguinte. A suite é executada com `pytest` a partir da raiz do projecto.

| Módulo | Classes de teste | Testes | Estado |
|--------|-----------------|--------|--------|
| `test_lexer.py` | 14 | 40 | 40 passaram |
| `test_parser.py` | 14 | 105 | 104 passaram, 1 xfail esperado |
| `test_semantic.py` | 8 | 21 | 21 passaram |
| **Total** | **36** | **166** | **165 passaram, 1 xfail, 0 falhas** |

O único `xfail` corresponde ao teste `test_do_loop_body_collected` no parser, que documenta explicitamente que o corpo do `DO` é preenchido na análise semântica e não no parser. Este comportamento é intencional e esperado.

### 8.2 Validação na EWVM

Para além dos testes automatizados, os ficheiros de código EWVM gerados foram executados manualmente na máquina virtual para validação de integração fim-a-fim:

| Programa | Ficheiro EWVM | Resultado esperado | Estado |
|----------|--------------|-------------------|--------|
| HELLO | `examples/hello.vm` | `Ola, Mundo!` | OK |
| FATORIAL (N=5) | `examples/fatorial.vm` | `120` | OK |
| SOMAARR | `examples/somaarr.vm` | `15` | OK |
| PRIMO (N=7) | `examples/primo.vm` | `7 e um numero primo` | OK |

---

## 9. Instruções de Execução

### Pré-requisitos

```
Python >= 3.10
PLY >= 3.11
pytest >= 7.0
```

Instalação das dependências:

```bash
pip install ply pytest
```

### Compilar um programa Fortran

```bash
python -m src.main exemplos/fatorial.f77
```

O ficheiro de saída `fatorial.vm` é gerado no directório corrente e pode ser executado na EWVM em https://ewvm.epl.di.uminho.pt.

### Executar os testes

```bash
pytest tests/
```

---

## 10. Limitações documentadas

As seguintes limitações são conhecidas e estão documentadas explicitamente no código. Estão aqui como aspetos a melhorar.

**Subprogramas no gerador de código.** As chamadas a subrotinas e funções externas (`CALL`, `FUNCTION`, `SUBROUTINE`) são suportadas sintática e semanticamente, mas o gerador de código lança `NotImplementedError` para `CALL`. A implementação requer um modelo de *frames* e uma convenção de chamada.

**Arrays unidimensionais apenas.** A gramática suporta declarações de arrays com uma única dimensão. O Fortran 77 suporta até sete dimensões; contudo, todos os exemplos do enunciado utilizam apenas arrays 1D.

**Verificação de tipos em expressões binárias.** A análise semântica valida declarações e tipos de variáveis de controlo, mas não efectua verificação de compatibilidade de tipos em todas as expressões binárias (por exemplo, atribuição de `REAL` a variável `INTEGER`). Esta verificação foi preterida em favor da cobertura sintática e da geração de código funcional; a extensão para erros explícitos é trabalho futuro.

**Operador de potência.** O operador `**` é reconhecido pelo lexer e pelo parser, mas o gerador de código não o traduz para instruções EWVM por ausência de uma instrução nativa equivalente. O compilador lança um erro informativo quando este operador é encontrado no corpo de um programa.

---

## 11. Conclusão

Foram implementadas com sucesso as quatro fases do compilador exigidas pelo enunciado. O analisador léxico reconhece o conjunto completo de tokens do subconjunto Fortran 77 especificado, com normalização para maiúsculas e descarte silencioso de comentários. O analisador sintático LALR(1) cobre todas as construções exigidas e gera uma AST bem estruturada, resolvendo a ambiguidade entre chamadas de função e referências a arrays por unificação no parser e resolução diferida na fase semântica. A análise semântica constrói a tabela de símbolos, valida labels de `GOTO`, verifica tipos das variáveis de controlo dos ciclos `DO` e preenche os corpos desses ciclos por pós-processamento linear. O gerador de código produz instruções EWVM correctas para as construções essenciais da linguagem, validadas por execução manual na máquina virtual.

A arquitectura em *pipeline* com módulos independentes e uma suite de 166 testes automatizados permitiu um desenvolvimento incremental com garantias de não-regressão em cada fase.