"""
tests/test_parser.py — Testes unitarios do parser

	O parser recebe tokens do lexer e constroi a AST (nodos em ast_nodes.py).
	Estes testes verificam que cada construcao sintatica gera o no correto e
	que a estrutura (campos e hierarquia) esta certa.

"""

import ast
import code
import os
import sys
import pytest

# Adiciona a pasta pai (PL_grupo18) ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.lexer import build_lexer
from src.parser import build_parser
from src.semantic import SemanticAnalyser
from src.ast_nodes import (
		Program, VarDecl, Assign, DoLoop, IfThen, GotoStmt, PrintStmt, ReadStmt,
		LabeledStmt, Continue, StopStmt, ReturnStmt, CallStmt,
		BinOp, UnaryOp, ID, IntLit, RealLit, StrLit, BoolLit, ArrayRef, FuncCall,
)


# ─── Utilitario auxiliar ─────────────────────────────────────────────────────

def parse(source: str):
		"""
		Faz parse de 'source' e devolve a AST.

		Usamos build_lexer() e build_parser() para evitar estado partilhado entre
		testes e garantir que lineno e buffers internos estao limpos.
		"""
		parser = build_parser()
		lexer = build_lexer()
		return parser.parse(source, lexer=lexer)

def parse_with_semantic(source: str):
		"""
		Faz parse e aplica análise semântica (incluindo preenchimento de DO bodies).
		"""
		ast = parse(source)
		analyser = SemanticAnalyser()
		return analyser.analyse(ast)


# ─── 1. Programa base ───────────────────────────────────────────────────────

class TestProgramRoot:
		"""
		o parser devolve um Program com name/decls/body.

		Program e a raiz da AST. Se este no estiver errado, todo o resto
		fica inconsistente.
		"""

		def test_minimal_program(self):
				ast = parse("PROGRAM P\nEND")
				assert isinstance(ast, Program)
				assert ast.name == "P"
				assert ast.decls == []
				assert ast.body == []


# ─── 2. Declaracoes ─────────────────────────────────────────────────────────

class TestDeclarations:
		""" VarDecl e a lista de nomes declarados.

		as declaracoes alimentam a tabela de simbolos. Um erro aqui quebra
		a analise semantica.
		"""

		def test_single_decl(self):
				code = """\
PROGRAM P
	INTEGER N, I
END
"""
				ast = parse(code)
				assert len(ast.decls) == 1
				decl = ast.decls[0]
				assert isinstance(decl, VarDecl)
				assert decl.type_name == "INTEGER"
				assert decl.names == [("N", None), ("I", None)]


# ─── 3. Atribuicao ──────────────────────────────────────────────────────────

class TestAssignments:
		"""
		 Assign com target e value.

		atribuicao e a instrucao mais comum; garante que IDs e literais
		geram os nos certos.
		"""

		def test_simple_assign(self):
				code = """\
PROGRAM P
	N = 1
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, Assign)
				assert isinstance(stmt.target, ID)
				assert stmt.target.name == "N"
				assert isinstance(stmt.value, IntLit)
				assert stmt.value.value == 1

		def test_array_ref_assign(self):
				code = """\
PROGRAM P
	A(1) = 2
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, Assign)
				assert isinstance(stmt.target, ArrayRef)
				assert stmt.target.name == "A"
				assert len(stmt.target.indices) == 1
				assert isinstance(stmt.target.indices[0], IntLit)
    
		def test_array_decl(self):
			code = """\
PROGRAM P
    INTEGER NUMS(5)
END
"""
			ast = parse(code)
			decl = ast.decls[0]
			assert isinstance(decl, VarDecl)
			assert decl.type_name == "INTEGER"
			assert decl.names == [("NUMS", [5])]


# ─── 4. Expressoes ──────────────────────────────────────────────────────────

class TestExpressions:
		"""
		BinOp, UnaryOp, precedencia e literais.

		a AST precisa refletir a precedencia correta para gerar codigo
		correto (ex: 1 + 2 * 3 nao pode virar (1 + 2) * 3).
		"""

		def test_binop_precedence(self):
				code = """\
PROGRAM P
	N = 1 + 2 * 3
END
"""
				ast = parse(code)
				value = ast.body[0].value
				assert isinstance(value, BinOp)
				assert value.op == "+"
				assert isinstance(value.left, IntLit)
				assert isinstance(value.right, BinOp)
				assert value.right.op == "*"

		def test_binop_parentheses(self):
				code = """\
PROGRAM P
	N = (1 + 2) * 3
END
"""
				ast = parse(code)
				value = ast.body[0].value
				assert isinstance(value, BinOp)
				assert value.op == "*"
				assert isinstance(value.left, BinOp)
				assert value.left.op == "+"

		def test_unary_minus(self):
				code = """\
PROGRAM P
	N = -1
END
"""
				ast = parse(code)
				value = ast.body[0].value
				assert isinstance(value, UnaryOp)
				assert value.op == "-"
				assert isinstance(value.operand, IntLit)

		def test_real_literal(self):
				code = """\
PROGRAM P
	X = 1.5
END
"""
				ast = parse(code)
				value = ast.body[0].value
				assert isinstance(value, RealLit)
				assert abs(value.value - 1.5) < 1e-9

		def test_bool_literal(self):
				code = """\
PROGRAM P
	IF (.TRUE.) THEN
		N = 1
	ENDIF
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, IfThen)
				assert isinstance(stmt.condition, BoolLit)
				assert stmt.condition.value is True


# ─── 5. IF / THEN / ELSE ─────────────────────────────────────────────────────

class TestIfThenElse:
		"""
		IfThen com e sem ELSE.

		estruturas de controlo precisam manter os blocos then/else
		separados para a geracao de codigo.
		"""

		def test_if_without_else(self):
				code = """\
PROGRAM P
	IF (N .GT. 0) THEN
		N = 1
	ENDIF
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, IfThen)
				assert isinstance(stmt.condition, BinOp)
				assert stmt.condition.op == ".GT."
				assert len(stmt.then_body) == 1
				assert stmt.else_body == []

		def test_if_with_else(self):
				code = """\
PROGRAM P
	IF (N .GT. 0) THEN
		N = 1
	ELSE
		N = 2
	ENDIF
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, IfThen)
				assert len(stmt.then_body) == 1
				assert len(stmt.else_body) == 1


# ─── 6. PRINT / READ ─────────────────────────────────────────────────────────

class TestIOStatements:
		"""
		PrintStmt e ReadStmt com o formato '*'.

		PRINT/READ sao comuns nos exemplos e exercicios. O parser precisa
		tratar o '*' como formato e nao como operador aritmetico.
		"""

		def test_print(self):
				code = """\
PROGRAM P
	PRINT *, 'HI', N
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, PrintStmt)
				assert isinstance(stmt.items[0], StrLit)
				assert isinstance(stmt.items[1], ID)

		def test_read(self):
				code = """\
PROGRAM P
	READ *, N
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, ReadStmt)
				assert isinstance(stmt.items[0], ID)


# ─── 7. Labels, GOTO e CONTINUE ──────────────────────────────────────────────

class TestLabelsAndGoto:
		"""
		labels sao essenciais no Fortran 77 (DO e GOTO). O parser precisa
		manter o numero do label ligado a instrucao correta.
		"""

		def test_labeled_continue(self):
				code = """\
PROGRAM P
	10 CONTINUE
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, LabeledStmt)
				assert stmt.label == 10
				assert isinstance(stmt.stmt, Continue)

		def test_goto(self):
				code = """\
PROGRAM P
	GOTO 10
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, GotoStmt)
				assert stmt.label == 10


# ─── 8. DO loop (comportamento atual) ───────────────────────────────────────

class TestDoLoop:
		"""
		DoLoop e os campos base (label, var, start, stop, step).

		o parser atual cria DoLoop sem corpo. Este teste valida a parte
		que ja existe hoje e deixa o problema do corpo em xfail separado.
		"""

		def test_do_loop_basic(self):
				code = """\
PROGRAM P
	DO 10 I = 1, N
	10 CONTINUE
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, DoLoop)
				assert stmt.label == 10
				assert stmt.var == "I"
				assert isinstance(stmt.start, IntLit)
				assert isinstance(stmt.stop, ID)
				assert stmt.step is None
				assert stmt.body == []


# ─── 9. CALL ────────────────────────────────────────────────────────────────

class TestCallStmt:
		"""
		CallStmt com e sem argumentos.

		CALL e uma instrucao distinta de FuncCall (expressao). E preciso
		garantir que o parser separa corretamente estes casos.
		"""

		def test_call_with_args(self):
				code = """\
PROGRAM P
	CALL F(N)
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, CallStmt)
				assert stmt.name == "F"
				assert len(stmt.args) == 1
				assert isinstance(stmt.args[0], ID)

		def test_call_without_args(self):
				code = """\
PROGRAM P
	CALL F
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, CallStmt)
				assert stmt.name == "F"
				assert stmt.args == []


# ─── 10. Limites conhecidos (xfail) ─────────────────────────────────────────

class TestKnownLimitations:
		"""
		Estes testes documentam limites atuais do parser. Estao marcados como xfail
		para que a suite passe, mas continuam a evidenciar o problema.
		"""

		@pytest.mark.xfail(reason="Parser LALR(1) não consegue agrupar DO bodies dinamicamente — resolvido na análise semântica.")
		def test_do_loop_body_collected(self):
				"""
				O parser não consegue agrupar instruções entre DO e CONTINUE porque
				é uma construção context-sensitive. Isto é resolvido na fase de
				análise semântica, com a função _fill_do_bodies.
				"""
				code = """\
PROGRAM P
	DO 10 I = 1, N
		N = N + 1
	10 CONTINUE
END
"""
				ast = parse(code)
				stmt = ast.body[0]
				assert isinstance(stmt, DoLoop)
				assert len(stmt.body) == 1
				assert isinstance(stmt.body[0], Assign)

		
		def test_func_call_in_expr(self):
				code = """\
PROGRAM P
	N = F(1)
END
"""
				ast = parse(code)
				value = ast.body[0].value
				assert isinstance(value, FuncCall)


# ─── 11. Testes de Análise Semântica ────────────────────────────────────────

class TestSemanticAnalysis:
		"""
		Testes que verificam a análise semântica, incluindo:
		- Preenchimento dos corpos dos DO loops
		- Resolução de ambiguidade FuncCall vs ArrayRef
		- Validação de símbolos
		"""

		def test_do_loop_body_filled_by_semantic(self):
				"""
				Após análise semântica, o corpo do DO deve estar preenchido com as
				instruções entre DO e CONTINUE.
				"""
				code = """\
PROGRAM P
	INTEGER N
	DO 10 I = 1, N
		N = N + 1
	10 CONTINUE
END
"""
				ast = parse_with_semantic(code)
				stmt = ast.body[0]
				assert isinstance(stmt, DoLoop)
				assert len(stmt.body) == 1
				assert isinstance(stmt.body[0], Assign)

		def test_do_loop_body_multiple_stmts(self):
				"""
				Validar que múltiplas instruções no corpo do DO são preservadas.
				"""
				code = """\
PROGRAM P
	INTEGER I, N
	DO 10 I = 1, N
		N = N + 1
		N = N + 2
	10 CONTINUE
END
"""
				ast = parse_with_semantic(code)
				stmt = ast.body[0]
				assert isinstance(stmt, DoLoop)
				assert len(stmt.body) == 2
				assert all(isinstance(s, Assign) for s in stmt.body)

		def test_func_call_becomes_array_ref(self):
				"""
				Após análise semântica, FuncCall para nomes declarados como arrays
				devem ser reescritos como ArrayRef.
				"""
				code = """\
PROGRAM P
	INTEGER NUMS(5), I
	I = NUMS(1)
END
"""
				ast = parse_with_semantic(code)
				assign = ast.body[0]
				assert isinstance(assign, Assign)
				# O valor deve ser ArrayRef, não FuncCall
				assert isinstance(assign.value, ArrayRef)
				assert assign.value.name == "NUMS"
