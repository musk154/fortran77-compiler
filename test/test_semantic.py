"""
tests/test_semantic.py — Testes unitários da análise semântica

    - Construção da tabela de símbolos
    - Resolução de ambiguidade FuncCall vs ArrayRef
    - Validação de labels em GOTO e DO
    - Verificação de tipos
    - Warnings e erros semânticos
"""

import os
import sys
import pytest

# Adiciona a pasta pai (PL_grupo18) ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.lexer import build_lexer
from src.parser import build_parser
from src.semantic import SemanticAnalyser, SymbolTable, Symbol
from src.ast_nodes import (
    Program, VarDecl, Assign, DoLoop, IfThen, GotoStmt, PrintStmt, ReadStmt,
    LabeledStmt, Continue, StopStmt, ReturnStmt, CallStmt,
    BinOp, UnaryOp, ID, IntLit, RealLit, StrLit, BoolLit, ArrayRef, FuncCall,
)


# ─── Utilitários ──────────────────────────────────────────────────────────────

def parse_and_analyze(source: str):
    """Faz parse e análise semântica."""
    lexer = build_lexer()
    parser = build_parser()
    ast = parser.parse(source, lexer=lexer)
    analyser = SemanticAnalyser()
    ast = analyser.analyse(ast)
    return ast, analyser.symbol_table


# ─── 1. Tabela de Símbolos ────────────────────────────────────────────────────

class TestSymbolTable:
    """Testa a construção e consulta da tabela de símbolos."""

    def test_declare_scalar_variable(self):
        """Deve registar um escalar como 'variable'."""
        symtab = SymbolTable("TEST")
        sym = Symbol(name="X", type_name="INTEGER", kind="variable")
        symtab.declare(sym)
        assert symtab.is_declared("X")
        assert not symtab.is_array("X")

    def test_declare_array(self):
        """Deve registar um array com shape."""
        symtab = SymbolTable("TEST")
        sym = Symbol(name="NUMS", type_name="INTEGER", kind="array", shape=[5])
        symtab.declare(sym)
        assert symtab.is_declared("NUMS")
        assert symtab.is_array("NUMS")

    def test_duplicate_declaration_error(self):
        """Deve gerar erro para declaração duplicada."""
        symtab = SymbolTable("TEST")
        sym1 = Symbol(name="X", type_name="INTEGER", kind="variable")
        sym2 = Symbol(name="X", type_name="REAL", kind="variable")
        symtab.declare(sym1)
        symtab.declare(sym2)
        assert len(symtab.errors) == 1
        assert "uma vez" in symtab.errors[0].lower()

    def test_lookup_nonexistent(self):
        """Deve devolver None para símbolo não existente."""
        symtab = SymbolTable("TEST")
        assert symtab.lookup("NONEXISTENT") is None


# ─── 2. Análise Semântica — Declarações ───────────────────────────────────────

class TestSemanticDeclarations:
    """Testa o processamento de declarações."""

    def test_simple_declaration(self):
        """Deve processar declarações simples."""
        code = """\
PROGRAM P
    INTEGER X, Y
    REAL Z
END
"""
        ast, symtab = parse_and_analyze(code)
        assert symtab.is_declared("X")
        assert symtab.is_declared("Y")
        assert symtab.is_declared("Z")
        assert symtab.lookup("X").type_name == "INTEGER"
        assert symtab.lookup("Z").type_name == "REAL"

    def test_array_declaration(self):
        """Deve processar declaração de arrays."""
        code = """\
PROGRAM P
    INTEGER NUMS(5)
    REAL MATRIX(10)
END
"""
        ast, symtab = parse_and_analyze(code)
        assert symtab.is_array("NUMS")
        assert symtab.is_array("MATRIX")
        assert symtab.lookup("NUMS").shape == [5]
        assert symtab.lookup("MATRIX").shape == [10]


# ─── 3. Resolução de Ambiguidade FuncCall vs ArrayRef ──────────────────────────

class TestFuncCallArrayRefResolution:
    """Testa a resolução de FuncCall vs ArrayRef."""

    def test_func_call_stays_func_call(self):
        """FuncCall para nome não declarado deve permanecer FuncCall."""
        code = """\
PROGRAM P
    INTEGER N
    N = MOD(10, 3)
END
"""
        ast, symtab = parse_and_analyze(code)
        assign = ast.body[0]
        assert isinstance(assign, Assign)
        assert isinstance(assign.value, FuncCall)
        assert assign.value.name == "MOD"

    def test_func_call_becomes_array_ref(self):
        """FuncCall para array declarado deve virar ArrayRef."""
        code = """\
PROGRAM P
    INTEGER NUMS(5)
    INTEGER X
    X = NUMS(1)
END
"""
        ast, symtab = parse_and_analyze(code)
        assign = ast.body[0]
        assert isinstance(assign, Assign)
        assert isinstance(assign.value, ArrayRef)
        assert assign.value.name == "NUMS"

    def test_array_assignment(self):
        """Atribuição a elemento de array deve gerar ArrayRef."""
        code = """\
PROGRAM P
    INTEGER NUMS(5)
    NUMS(1) = 42
END
"""
        ast, symtab = parse_and_analyze(code)
        assign = ast.body[0]
        assert isinstance(assign, Assign)
        assert isinstance(assign.target, ArrayRef)
        assert assign.target.name == "NUMS"


# ─── 4. Validação de Labels ───────────────────────────────────────────────────

class TestLabelValidation:
    """Testa a validação de labels em GOTO e DO."""

    def test_goto_valid_label(self):
        """GOTO para label definido não deve gerar erro."""
        code = """\
PROGRAM P
    GOTO 10
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        # Não deve haver erros
        assert len(symtab.errors) == 0

    def test_goto_undefined_label(self):
        """GOTO para label indefinido deve gerar erro."""
        code = """\
PROGRAM P
    GOTO 10
    20 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        assert len(symtab.errors) > 0
        assert "label não definido" in symtab.errors[0].lower()

    def test_do_loop_label_collection(self):
        """DO loop com label deve ser registado."""
        code = """\
PROGRAM P
    INTEGER I, N
    DO 10 I = 1, N
        N = N + 1
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        # Não deve haver erros de label
        assert len(symtab.errors) == 0


# ─── 5. Validação de Tipos — DO Loop ──────────────────────────────────────────

class TestDoLoopValidation:
    """Testa a validação da variável de controlo do DO."""

    def test_do_with_integer_var(self):
        """DO com variável INTEGER deve ser válido."""
        code = """\
PROGRAM P
    INTEGER I, N
    DO 10 I = 1, N
        N = N + 1
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        assert len(symtab.errors) == 0

    def test_do_with_real_var_error(self):
        """DO com variável REAL deve gerar erro."""
        code = """\
PROGRAM P
    REAL X, N
    DO 10 X = 1, N
        N = N + 1
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        assert len(symtab.errors) > 0
        assert "INTEGER" in symtab.errors[0]

    def test_do_with_undeclared_var_warning(self):
        """DO com variável não declarada deve gerar aviso."""
        code = """\
PROGRAM P
    DO 10 I = 1, 5
        I = I + 1
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        # Fortran tem implicit typing; aqui geramos aviso
        assert len(symtab.warnings) > 0 or len(symtab.errors) > 0


# ─── 6. Avisos para Variáveis Não Declaradas ──────────────────────────────────

class TestUndeclaredVariableWarnings:
    """Testa o rastreio de variáveis não declaradas."""

    def test_unused_declared_variable(self):
        """Variável declarada mas não usada é válida."""
        code = """\
PROGRAM P
    INTEGER X
    INTEGER Y
    Y = 1
END
"""
        ast, symtab = parse_and_analyze(code)
        # Nenhum aviso por variável declarada mas não usada
        assert not any("X" in w for w in symtab.warnings)

    def test_variable_used_in_expression(self):
        """Variável declarada e usada não deve gerar aviso."""
        code = """\
PROGRAM P
    INTEGER X, Y
    Y = X + 1
END
"""
        ast, symtab = parse_and_analyze(code)
        assert len(symtab.errors) == 0
        assert not any("X" in w or "Y" in w for w in symtab.warnings)


# ─── 7. DO Loop Body Preenchimento ────────────────────────────────────────────

class TestDoLoopBodyFilling:
    """Testa o preenchimento de corpos de DO loops."""

    def test_do_body_single_stmt(self):
        """DO loop com uma instrução deve ter body preenchido."""
        code = """\
PROGRAM P
    INTEGER I, N
    DO 10 I = 1, N
        N = N + 1
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        loop = ast.body[0]
        assert isinstance(loop, DoLoop)
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], Assign)

    def test_do_body_multiple_stmts(self):
        """DO loop com múltiplas instruções deve preservá-las."""
        code = """\
PROGRAM P
    INTEGER I, N, X
    DO 10 I = 1, N
        N = N + 1
        X = X + 2
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        loop = ast.body[0]
        assert len(loop.body) == 2
        assert all(isinstance(s, Assign) for s in loop.body)

    def test_nested_do_loops(self):
        """DO loops aninhados devem ter bodies preenchidos corretamente."""
        code = """\
PROGRAM P
    INTEGER I, J, N
    DO 10 I = 1, N
        DO 20 J = 1, N
            N = N + 1
        20 CONTINUE
    10 CONTINUE
END
"""
        ast, symtab = parse_and_analyze(code)
        outer_loop = ast.body[0]
        assert isinstance(outer_loop, DoLoop)
        assert len(outer_loop.body) == 1
        inner_loop = outer_loop.body[0]
        assert isinstance(inner_loop, DoLoop)
        assert len(inner_loop.body) == 1


# ─── 8. Symbol Tabela — Relatório ─────────────────────────────────────────────

class TestSymbolTableReport:
    """Testa o relatório da tabela de símbolos."""

    def test_report_format(self):
        """Relatório deve ser formatado corretamente."""
        code = """\
PROGRAM P
    INTEGER X
    REAL Y(5)
END
"""
        ast, symtab = parse_and_analyze(code)
        report = symtab.report()
        assert "P" in report
        assert "X" in report
        assert "Y" in report
        assert "INTEGER" in report
        assert "REAL" in report
        assert "array" in report.lower()
