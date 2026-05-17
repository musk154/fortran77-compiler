"""
Análise semântica para Fortran 77.

  A AST é percorrida por um SemanticVisitor que despacha cada nó para o
  método visit_<NomeDoNó>. Isto mantém a lógica de análise completamente
  separada das dataclasses da AST, que ficam inalteradas.

  Os métodos visit_* devolvem o nó (eventualmente reescrito). Assim, a
  chamada visit(node) substitui o nó original pelo nó corrigido na AST,
  sem precisar de uma estrutura separada.
"""

from dataclasses import dataclass, field
from typing import Optional
from .ast_nodes import (
    Node, Program, VarDecl, Assign, DoLoop, IfThen, GotoStmt,
    PrintStmt, ReadStmt, LabeledStmt, Continue, StopStmt, ReturnStmt,
    CallStmt, BinOp, UnaryOp, ID, IntLit, RealLit, StrLit, BoolLit,
    ArrayRef, FuncCall, FunctionDef, SubroutineDef,
)


# ─── Tabela de símbolos ───────────────────────────────────────────────────────

@dataclass
class Symbol:
    """
    Entrada na tabela de símbolos.

    Campos:
      name      — nome normalizado (uppercase)
      type_name — 'INTEGER', 'REAL', 'LOGICAL', 'CHARACTER'
      kind      — 'variable' | 'array' | 'function' | 'subroutine'
      shape     — lista de dimensões para arrays, ex: [5] para NUMS(5);
                  None para escalares e subprogramas
    """
    name:      str
    type_name: str
    kind:      str                    # 'variable' | 'array' | 'function' | 'subroutine'
    shape:     Optional[list] = None  # só para arrays


class SymbolTable:
    """
    Tabela de símbolos para uma unidade de programa (PROGRAM, FUNCTION ou
    SUBROUTINE). Em Fortran 77 o escopo é plano — não há blocos aninhados
    dentro de uma unidade, pelo que uma única tabela por unidade é suficiente.
    """

    def __init__(self, unit_name: str):
        self.unit_name = unit_name
        self._table: dict[str, Symbol] = {}
        self.errors:  list[str] = []
        self.warnings: list[str] = []

    # ── Inserção ──────────────────────────────────────────────────────────────

    def declare(self, symbol: Symbol) -> None:
        """
        Regista um símbolo. Se o nome já existe, emite um erro de declaração
        duplicada (Fortran 77 não permite redeclaração).
        """
        if symbol.name in self._table:
            self.errors.append(
                f"Erro semântico em '{self.unit_name}': "
                f"'{symbol.name}' declarado mais de uma vez."
            )
            return
        self._table[symbol.name] = symbol

    # ── Consulta ──────────────────────────────────────────────────────────────

    def lookup(self, name: str) -> Optional[Symbol]:
        """Devolve o Symbol ou None se não existir."""
        return self._table.get(name)

    def is_array(self, name: str) -> bool:
        sym = self._table.get(name)
        return sym is not None and sym.kind == 'array'

    def is_declared(self, name: str) -> bool:
        return name in self._table

    # ── Relatório ─────────────────────────────────────────────────────────────

    def report(self) -> str:
        lines = [f"Tabela de símbolos — {self.unit_name}"]
        lines.append("-" * 50)
        if not self._table:
            lines.append("  (vazia)")
        for sym in self._table.values():
            shape_str = f"  shape={sym.shape}" if sym.shape else ""
            lines.append(f"  {sym.name:20s} {sym.type_name:12s} {sym.kind}{shape_str}")
        if self.errors:
            lines.append("")
            lines.append("Erros:")
            for e in self.errors:
                lines.append(f"  {e}")
        if self.warnings:
            lines.append("")
            lines.append("Avisos:")
            for w in self.warnings:
                lines.append(f"  {w}")
        return "\n".join(lines)

    def __repr__(self):
        return self.report()


# ─── Visitor base ─────────────────────────────────────────────────────────────

class Visitor:
    """
    Despacha visit(node) para visit_<NomeClasse>(node).
    Se não existir método específico, chama generic_visit que percorre
    os filhos por omissão.

    Os métodos visit_* devolvem o nó (possivelmente reescrito). Listas
    de nós são percorridas e reconstruídas em visit_list.
    """

    def visit(self, node):
        if node is None:
            return None
        method = 'visit_' + type(node).__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_list(self, lst: list) -> list:
        return [self.visit(item) for item in lst]

    def generic_visit(self, node):
        """Percorre todos os campos que sejam Node ou list."""
        for attr, value in node.__dict__.items():
            if isinstance(value, list):
                setattr(node, attr, self.visit_list(value))
            elif isinstance(value, Node):
                setattr(node, attr, self.visit(value))
        return node


# ─── Analisador semântico ─────────────────────────────────────────────────────

class SemanticAnalyser(Visitor):
    """
    Percorre a AST, constrói a tabela de símbolos e reescreve nós onde
    necessário (FuncCall → ArrayRef).

    Uso:
        analyser = SemanticAnalyser()
        ast = analyser.analyse(ast)
        print(analyser.symbol_table.report())
    """

    def __init__(self):
        self.symbol_table: Optional[SymbolTable] = None
        # Conjunto de labels definidos no programa (para verificar GOTOs)
        self._defined_labels: set[int] = set()
        # Labels referenciados por GOTO (verificados no final)
        self._goto_labels: list[int] = []

    def analyse(self, program: Program) -> Program:
        """Ponto de entrada público. Devolve a AST (possivelmente modificada)."""
        return self.visit(program)

    # ── Program ───────────────────────────────────────────────────────────────

    def visit_Program(self, node: Program) -> Program:
        self.symbol_table = SymbolTable(node.name)

        # Primeira passagem: preencher tabela de símbolos a partir das declarações.
        # Fazemos isto ANTES de visitar o body para que qualquer referência a um
        # array no body já encontre o símbolo na tabela.
        for decl in node.decls:
            self._process_decl(decl)

        # Pré-processamento: preencher corpos vazios dos DO loops
        # O parser não consegue agrupar dinamicamente instruções entre DO e CONTINUE,
        # pelo que esta passagem iterativa encontra cada DoLoop e agrupa as
        # instruções até ao CONTINUE correspondente.
        node.body = self._fill_do_bodies(node.body)

        # Recolher todos os labels definidos no programa (para validar GOTOs)
        self._collect_labels(node.body)

        # Segunda passagem: visitar o body (reescreve FuncCall → ArrayRef onde aplicável)
        node.body = self.visit_list(node.body)

        # Validar GOTOs
        for lbl in self._goto_labels:
            if lbl not in self._defined_labels:
                self.symbol_table.errors.append(
                    f"Erro semântico: GOTO {lbl} — label não definido no programa."
                )

        return node

    # ── Declarações ───────────────────────────────────────────────────────────

    def _fill_do_bodies(self, stmts: list) -> list:
        """
        Pós-processamento para agrupar instruções entre DO e CONTINUE.

        O parser gera DoLoop com body=[], porque LALR(1) não consegue agrupar
        dinamicamente. Esta função percorre a lista plana de instruções e
        para cada DoLoop com label X, encontra o CONTINUE com label X e move
        as instruções entre eles para DoLoop.body.

        Processa recursivamente dentro de IfThen e DoLoop já preenchidos.
        """
        result = []
        i = 0
        while i < len(stmts):
            stmt = stmts[i]

            # Recursivamente processar corpos de IF e DO aninhados
            if isinstance(stmt, IfThen):
                stmt.then_body = self._fill_do_bodies(stmt.then_body)
                stmt.else_body = self._fill_do_bodies(stmt.else_body)
                result.append(stmt)
                i += 1
                continue

            if isinstance(stmt, DoLoop) and stmt.body == []:
                # DoLoop com body vazio — procurar o CONTINUE correspondente
                target_label = stmt.label
                body_stmts = []
                j = i + 1

                # Recolher instruções até encontrar um LabeledStmt com label == target_label
                while j < len(stmts):
                    next_stmt = stmts[j]
                    if isinstance(next_stmt, LabeledStmt) and next_stmt.label == target_label:
                        # Encontrámos o CONTINUE — paramos
                        stmt.body = body_stmts
                        # Recursivamente processar os corpos aninhados dentro do DO
                        stmt.body = self._fill_do_bodies(stmt.body)
                        result.append(stmt)
                        # Saltar até ao CONTINUE
                        i = j + 1
                        break
                    else:
                        body_stmts.append(next_stmt)
                        j += 1
                else:
                    # Não encontrámos CONTINUE correspondente — deixar DoLoop como estava
                    # e registar um aviso (isto pode ser um erro do programa Fortran)
                    self.symbol_table.warnings.append(
                        f"Aviso: DoLoop com label {target_label} não tem CONTINUE correspondente."
                    )
                    result.append(stmt)
                    i += 1
                continue

            # Recursivamente processar corpos de DO já preenchidos
            if isinstance(stmt, DoLoop) and stmt.body != []:
                stmt.body = self._fill_do_bodies(stmt.body)
                result.append(stmt)
                i += 1
                continue

            result.append(stmt)
            i += 1

        return result

    def _process_decl(self, decl: VarDecl) -> None:
        """
        Processa uma VarDecl e insere os símbolos na tabela.

        Cada entrada em decl.names é um tuplo (nome, shape) onde shape é
        None para escalares e [dim] para arrays — ex: ('NUMS', [5]).
        Esta estrutura vem do parser após a extensão de id_list.
        """
        for name, shape in decl.names:
            kind = 'array' if shape is not None else 'variable'
            sym = Symbol(
                name=name,
                type_name=decl.type_name,
                kind=kind,
                shape=shape,
            )
            self.symbol_table.declare(sym)

    def _collect_labels(self, stmts: list) -> None:
        """Recolhe recursivamente todos os labels definidos no programa."""
        for stmt in stmts:
            if isinstance(stmt, LabeledStmt):
                self._defined_labels.add(stmt.label)
                self._collect_labels([stmt.stmt])
            elif isinstance(stmt, IfThen):
                self._collect_labels(stmt.then_body)
                self._collect_labels(stmt.else_body)
            elif isinstance(stmt, DoLoop):
                self._collect_labels(stmt.body)

    # ── Instruções ────────────────────────────────────────────────────────────

    def visit_Assign(self, node: Assign) -> Assign:
        node.target = self.visit(node.target)
        node.value  = self.visit(node.value)
        return node

    def visit_DoLoop(self, node: DoLoop) -> DoLoop:
        # Verifica que a variável de controlo é INTEGER
        sym = self.symbol_table.lookup(node.var)
        if sym is None:
            self.symbol_table.warnings.append(
                f"Aviso: variável de controlo '{node.var}' do DO não declarada."
            )
        elif sym.type_name != 'INTEGER':
            self.symbol_table.errors.append(
                f"Erro semântico: variável de controlo '{node.var}' do DO "
                f"deve ser INTEGER, mas é {sym.type_name}."
            )
        node.start = self.visit(node.start)
        node.stop  = self.visit(node.stop)
        node.step  = self.visit(node.step)
        node.body  = self.visit_list(node.body)
        return node

    def visit_IfThen(self, node: IfThen) -> IfThen:
        node.condition  = self.visit(node.condition)
        node.then_body  = self.visit_list(node.then_body)
        node.else_body  = self.visit_list(node.else_body)
        return node

    def visit_GotoStmt(self, node: GotoStmt) -> GotoStmt:
        self._goto_labels.append(node.label)
        return node

    def visit_PrintStmt(self, node: PrintStmt) -> PrintStmt:
        node.items = self.visit_list(node.items)
        return node

    def visit_ReadStmt(self, node: ReadStmt) -> ReadStmt:
        node.items = self.visit_list(node.items)
        return node

    def visit_LabeledStmt(self, node: LabeledStmt) -> LabeledStmt:
        node.stmt = self.visit(node.stmt)
        return node

    def visit_CallStmt(self, node: CallStmt) -> CallStmt:
        node.args = self.visit_list(node.args)
        return node

    # ── Expressões ────────────────────────────────────────────────────────────

    def visit_BinOp(self, node: BinOp) -> BinOp:
        node.left  = self.visit(node.left)
        node.right = self.visit(node.right)
        return node

    def visit_UnaryOp(self, node: UnaryOp) -> UnaryOp:
        node.operand = self.visit(node.operand)
        return node

    def visit_ID(self, node: ID) -> ID:
        """Verifica que a variável foi declarada."""
        if not self.symbol_table.is_declared(node.name):
            self.symbol_table.warnings.append(
                f"Aviso: '{node.name}' usado mas não declarado."
            )
        return node

    def visit_ArrayRef(self, node: ArrayRef) -> ArrayRef:
        """ArrayRefs explícitos (lado esquerdo de atribuição) — visita os índices."""
        if not self.symbol_table.is_declared(node.name):
            self.symbol_table.warnings.append(
                f"Aviso: array '{node.name}' usado mas não declarado."
            )
        node.indices = self.visit_list(node.indices)
        return node

    def visit_FuncCall(self, node: FuncCall) -> Node:
        """
        Ponto central da resolução da ambiguidade.

        Se o nome está declarado como array na tabela de símbolos, reescreve
        FuncCall → ArrayRef. Caso contrário, mantém FuncCall (é uma chamada
        de função real, possivelmente intrínseca como MOD, ABS, SQRT).

        Funções intrínsecas do Fortran 77 não precisam de ser declaradas —
        não emitimos aviso para nomes conhecidos.
        """
        INTRINSICS = {
            'MOD', 'ABS', 'SQRT', 'INT', 'REAL', 'FLOAT', 'IFIX',
            'MAX', 'MIN', 'MAX0', 'MIN0', 'AMAX1', 'AMIN1',
            'SIN', 'COS', 'TAN', 'EXP', 'LOG', 'LOG10',
            'LEN', 'INDEX', 'CHAR', 'ICHAR',
        }

        node.args = self.visit_list(node.args)

        if self.symbol_table.is_array(node.name):
            # Reescreve para ArrayRef — a distinção estava pendente desde o parser
            return ArrayRef(name=node.name, indices=node.args)

        if not self.symbol_table.is_declared(node.name) and node.name not in INTRINSICS:
            self.symbol_table.warnings.append(
                f"Aviso: '{node.name}' chamado mas não declarado "
                f"(pode ser função externa ou intrínseca não listada)."
            )

        return node

    # Literais não precisam de verificação — devolvem-se a si próprios
    def visit_IntLit(self, node):  return node
    def visit_RealLit(self, node): return node
    def visit_StrLit(self, node):  return node
    def visit_BoolLit(self, node): return node
    def visit_Continue(self, node): return node
    def visit_StopStmt(self, node): return node
    def visit_ReturnStmt(self, node): return node


# ─── Ponto de entrada para teste rápido ──────────────────────────────────────

if __name__ == '__main__':
    from lexer import build_lexer
    from parser import build_parser

    _code = """\
PROGRAM SOMAARR
  INTEGER NUMS(5)
  INTEGER I, SOMA
  SOMA = 0
  DO 30 I = 1, 5
    READ *, NUMS(I)
    SOMA = SOMA + NUMS(I)
  30 CONTINUE
  PRINT *, 'A soma dos numeros e: ', SOMA
END
"""
    _lexer  = build_lexer()
    _parser = build_parser()
    _ast    = _parser.parse(_code, lexer=_lexer)

    analyser = SemanticAnalyser()
    _ast     = analyser.analyse(_ast)

    print(analyser.symbol_table.report())