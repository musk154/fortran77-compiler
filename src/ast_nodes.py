"""
Cada classe representa um tipo de construção da linguagem.
Usamos dataclasses para simplicidade e __repr__ automático (útil no debug).
"""
from dataclasses import dataclass, field
from typing import Any, Optional

# ─── Nó base ──────────────────────────────────────────────────────────────────
@dataclass
class Node:
    pass

# ─── Programa ─────────────────────────────────────────────────────────────────
@dataclass
class Program(Node):
    name: str           # nome do PROGRAM
    decls: list         # declarações de variáveis
    body: list          # instruções

# ─── Declarações ──────────────────────────────────────────────────────────────
@dataclass
class VarDecl(Node):
    type_name: str      # 'INTEGER', 'REAL', 'LOGICAL', etc.
    names: list         # lista de (nome, shape) onde shape é None para
                        # escalares e [dim] para arrays, ex: ('NUMS', [5])

# ─── Instruções ───────────────────────────────────────────────────────────────
@dataclass
class Assign(Node):
    target: Node        # ID ou ArrayRef
    value: Node         # expressão

@dataclass
class DoLoop(Node):
    label: int          # label do CONTINUE final (ex: 10)
    var: str            # variável de controlo (ex: 'I')
    start: Node
    stop: Node
    step: Optional[Node]
    body: list

@dataclass
class IfThen(Node):
    condition: Node
    then_body: list
    else_body: list     # pode ser vazio

@dataclass
class GotoStmt(Node):
    label: int

@dataclass
class PrintStmt(Node):
    items: list         # lista de expressões a imprimir

@dataclass
class ReadStmt(Node):
    items: list

@dataclass
class LabeledStmt(Node):
    label: int
    stmt: Node          # instrução que tem label (ex: CONTINUE)

@dataclass
class Continue(Node):
    pass

@dataclass
class ReturnStmt(Node):
    pass

@dataclass
class StopStmt(Node):
    pass

# ─── Subprogramas (valorização) ───────────────────────────────────────────────
@dataclass
class FunctionDef(Node):
    return_type: str
    name: str
    params: list
    decls: list
    body: list

@dataclass
class SubroutineDef(Node):
    name: str
    params: list
    decls: list
    body: list

@dataclass
class CallStmt(Node):
    name: str
    args: list

# ─── Expressões ───────────────────────────────────────────────────────────────
@dataclass
class BinOp(Node):
    left: Node
    op: str             # '+', '-', '*', '/', '**', '.GT.', etc.
    right: Node

@dataclass
class UnaryOp(Node):
    op: str             # '-', '.NOT.'
    operand: Node

@dataclass
class ID(Node):
    name: str

@dataclass
class IntLit(Node):
    value: int

@dataclass
class RealLit(Node):
    value: float

@dataclass
class StrLit(Node):
    value: str

@dataclass
class BoolLit(Node):
    value: bool

@dataclass
class ArrayRef(Node):   # ex: NUMS(I)
    name: str
    indices: list

@dataclass
class FuncCall(Node):   # ex: MOD(NUM, I)
    name: str
    args: list