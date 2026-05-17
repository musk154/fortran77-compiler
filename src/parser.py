"""
Este módulo define o parser para Fortran 77 usando ply.yacc.

O parser recebe a sequência de tokens do lexer e constrói uma AST
(Abstract Syntax Tree) composta pelos nós definidos em ast_nodes.py.

Decisões de design:
  - Gramática baseada no subset do Fortran 77 exigido no enunciado.
  - Labels numéricos (DO 10 ..., GOTO 10, 10 CONTINUE) são tratados
    como INT_LIT pelo lexer; o parser associa-os às instruções corretas.
  - Chamadas de função vs referências a arrays: ambas têm a forma NAME(args).
    O parser gera FuncCall para tudo — a análise semântica vai distingui-las
    consultando a tabela de símbolos.
  - PRINT *, ... usa '*' como formato wildcard; o parser consome o STAR
    como token especial neste contexto.
"""

import ply.yacc as yacc
from .lexer import tokens, build_lexer   # reutiliza tokens do lexer
from .ast_nodes import *

# ─── Precedência de operadores ────────────────────────────────────────────────
# PLY resolve ambiguidades usando esta tabela (menor índice = menor precedência).
# 'left'/'right'/'nonassoc' define a associatividade.
precedence = (
    ('left',  'OR'),
    ('left',  'AND'),
    ('right', 'NOT'),
    ('nonassoc', 'EQ', 'NE', 'LT', 'LE', 'GT', 'GE'),
    ('left',  'PLUS', 'MINUS'),
    ('left',  'STAR', 'SLASH'),
    ('right', 'UMINUS'),         # menos unário (pseudo-token)
    ('right', 'POWER'),
)

# ─── Programa principal ───────────────────────────────────────────────────────

def p_program(p):
    """program : PROGRAM ID decl_list stmt_list END"""
    p[0] = Program(name=p[2], decls=p[3], body=p[4])

# ─── Declarações ──────────────────────────────────────────────────────────────

def p_decl_list(p):
    """decl_list : decl_list decl
                 | empty"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []

def p_decl(p):
    """decl : type_kw id_list"""
    p[0] = VarDecl(type_name=p[1], names=p[2])

def p_type_kw(p):
    """type_kw : INTEGER
               | REAL
               | LOGICAL
               | CHARACTER"""
    p[0] = p[1]

def p_id_list(p):
    """id_list : id_list COMMA id_item
               | id_item"""
    if len(p) == 4:
        p[0] = p[1] + [p[3]]
    else:
        p[0] = [p[1]]

def p_id_item_scalar(p):
    """id_item : ID"""
    # Escalar — shape None
    p[0] = (p[1], None)

def p_id_item_array(p):
    """id_item : ID LPAREN INT_LIT RPAREN"""
    # Array com uma dimensão — shape é lista com o tamanho, ex: [5]
    # Fortran 77 suporta até 7 dimensões mas o subset do enunciado usa uma.
    p[0] = (p[1], [p[3]])

# ─── Lista de instruções ──────────────────────────────────────────────────────

def p_stmt_list(p):
    """stmt_list : stmt_list stmt
                 | empty"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []

def p_stmt(p):
    """stmt : labeled_stmt
            | assign_stmt
            | if_stmt
            | do_stmt
            | goto_stmt
            | print_stmt
            | read_stmt
            | continue_stmt
            | stop_stmt
            | return_stmt
            | call_stmt"""
    p[0] = p[1]

# ─── Instrução com label (ex: 10 CONTINUE) ───────────────────────────────────

def p_labeled_stmt(p):
    """labeled_stmt : INT_LIT stmt"""
    p[0] = LabeledStmt(label=p[1], stmt=p[2])

# ─── Atribuição ───────────────────────────────────────────────────────────────

def p_assign_stmt(p):
    """assign_stmt : ID EQUALS expr
                   | ID LPAREN expr_list RPAREN EQUALS expr"""
    if len(p) == 4:
        # Atribuição simples: N = expr
        p[0] = Assign(target=ID(name=p[1]), value=p[3])
    else:
        # Atribuição a elemento de array: NUMS(I) = expr
        # O contexto (lado esquerdo de =) garante que é array, não função.
        p[0] = Assign(
            target=ArrayRef(name=p[1], indices=p[3]),
            value=p[6]
        )

# ─── IF-THEN-ELSE ─────────────────────────────────────────────────────────────

def p_if_stmt(p):
    """if_stmt : IF LPAREN expr RPAREN THEN stmt_list ENDIF
               | IF LPAREN expr RPAREN THEN stmt_list ELSE stmt_list ENDIF"""
    if len(p) == 8:
        p[0] = IfThen(condition=p[3], then_body=p[6], else_body=[])
    else:
        p[0] = IfThen(condition=p[3], then_body=p[6], else_body=p[8])

# ─── Ciclo DO ─────────────────────────────────────────────────────────────────
# Fortran 77: DO label var = start, stop [, step]

def p_do_stmt(p):
    """do_stmt : DO INT_LIT ID EQUALS expr COMMA expr
               | DO INT_LIT ID EQUALS expr COMMA expr COMMA expr"""
    step = p[9] if len(p) == 10 else None
    # O body será preenchido ao encontrar o CONTINUE com o label correto.
    # Abordagem simples: recolhemos tudo até ao labeled CONTINUE.
    p[0] = DoLoop(label=p[2], var=p[3], start=p[5], stop=p[7], step=step, body=[])

# ─── GOTO ─────────────────────────────────────────────────────────────────────

def p_goto_stmt(p):
    """goto_stmt : GOTO INT_LIT"""
    p[0] = GotoStmt(label=p[2])

# ─── PRINT ────────────────────────────────────────────────────────────────────
# PRINT *, expr, expr, ...   — o '*' é o formato wildcard

def p_print_stmt(p):
    """print_stmt : PRINT STAR COMMA expr_list"""
    p[0] = PrintStmt(items=p[4])

# ─── READ ─────────────────────────────────────────────────────────────────────

def p_read_stmt(p):
    """read_stmt : READ STAR COMMA expr_list"""
    p[0] = ReadStmt(items=p[4])

# ─── CONTINUE / STOP / RETURN ─────────────────────────────────────────────────

def p_continue_stmt(p):
    """continue_stmt : CONTINUE"""
    p[0] = Continue()

def p_stop_stmt(p):
    """stop_stmt : STOP"""
    p[0] = StopStmt()

def p_return_stmt(p):
    """return_stmt : RETURN"""
    p[0] = ReturnStmt()

# ─── CALL (valorização) ───────────────────────────────────────────────────────

def p_call_stmt(p):
    """call_stmt : CALL ID LPAREN expr_list RPAREN
                 | CALL ID"""
    args = p[4] if len(p) == 6 else []
    p[0] = CallStmt(name=p[2], args=args)

# ─── Lista de expressões ──────────────────────────────────────────────────────

def p_expr_list(p):
    """expr_list : expr_list COMMA expr
                 | expr"""
    if len(p) == 4:
        p[0] = p[1] + [p[3]]
    else:
        p[0] = [p[1]]

# ─── Expressões ───────────────────────────────────────────────────────────────

def p_expr_binop(p):
    """expr : expr PLUS  expr
            | expr MINUS expr
            | expr STAR  expr
            | expr SLASH expr
            | expr POWER expr
            | expr GT expr
            | expr LT expr
            | expr GE expr
            | expr LE expr
            | expr EQ expr
            | expr NE expr
            | expr AND expr
            | expr OR  expr"""
    p[0] = BinOp(left=p[1], op=p[2], right=p[3])

def p_expr_unary(p):
    """expr : MINUS expr %prec UMINUS
            | NOT   expr"""
    p[0] = UnaryOp(op=p[1], operand=p[2])

def p_expr_paren(p):
    """expr : LPAREN expr RPAREN"""
    p[0] = p[2]

def p_expr_id(p):
    """expr : ID"""
    p[0] = ID(name=p[1])

def p_expr_int(p):
    """expr : INT_LIT"""
    p[0] = IntLit(value=p[1])

def p_expr_real(p):
    """expr : REAL_LIT"""
    p[0] = RealLit(value=p[1])

def p_expr_string(p):
    """expr : STRING_LIT"""
    p[0] = StrLit(value=p[1])

def p_expr_bool(p):
    """expr : BOOL_LIT"""
    p[0] = BoolLit(value=p[1])

def p_expr_call_or_array(p):
    """expr : ID LPAREN expr_list RPAREN"""
    # Gera sempre FuncCall. A análise semântica reescreve para ArrayRef
    # quando o nome constar da tabela de símbolos como array declarado.
    # Isto elimina o conflito reduce/reduce que existia entre p_expr_func_call
    # e p_array_ref na versão anterior.
    p[0] = FuncCall(name=p[1], args=p[3])
# ─── Produção vazia ───────────────────────────────────────────────────────────

def p_empty(p):
    """empty :"""
    p[0] = []

# ─── Erros sintáticos ─────────────────────────────────────────────────────────

def p_error(p):
    if p:
        print(f"Erro sintático — linha {p.lineno}: token inesperado '{p.value}' (tipo {p.type})")
    else:
        print("Erro sintático — fim de ficheiro inesperado")

# ─── Fábrica pública ──────────────────────────────────────────────────────────

def build_parser(debug=False):
    """
    Constrói e devolve uma instância fresca do parser PLY.
    O lexer é criado internamente; não é necessário passá-lo.
    """
    return yacc.yacc(debug=debug)


# ─── Ponto de entrada para teste rápido ──────────────────────────────────────

if __name__ == '__main__':
    from lexer import build_lexer
    _code = """\
PROGRAM FATORIAL
  INTEGER N, I, FAT
  FAT = 1
  DO 10 I = 1, N
    FAT = FAT * I
10 CONTINUE
  PRINT *, 'Fatorial:', FAT
END
"""
    _lexer  = build_lexer()
    _parser = build_parser()
    ast = _parser.parse(_code, lexer=_lexer)
    print(ast)