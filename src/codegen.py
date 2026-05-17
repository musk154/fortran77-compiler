"""
Gerador de código para EWVM (Emulated WebAssembly Virtual Machine).
Organização:
  - CodeGen: classe principal que percorre a AST e emite código
  - Tabela de offsets para variáveis locais e globais
  - Stack-based code generation com labels para controlo de fluxo
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from .ast_nodes import (
    Node, Program, VarDecl, Assign, DoLoop, IfThen, GotoStmt,
    PrintStmt, ReadStmt, LabeledStmt, Continue, StopStmt, ReturnStmt,
    CallStmt, BinOp, UnaryOp, ID, IntLit, RealLit, StrLit, BoolLit,
    ArrayRef, FuncCall,
)


@dataclass
class VariableInfo:
    """Informação sobre uma variável (tipo, offset em memória)."""
    name: str
    type_name: str  # 'INTEGER', 'REAL', 'LOGICAL', 'CHARACTER'
    is_array: bool
    shape: Optional[List[int]] = None
    offset: int = 0  # offset relativo a FP (frame pointer)


class CodeGen:
    """
    A máquina virtual usa um modelo de pilha com:
    - Operand stack: para valores e cálculos
    - Call stack: para retornos de funções
    - String Heap: para strings
    - Struct Heap: para arrays

    Variáveis locais são armazenadas com offset relativo a FP.
    Variáveis globais com offset relativo a GP.
    """

    def __init__(self):
        self.code: List[str] = []
        self.label_counter = 0
        self.variables: Dict[str, VariableInfo] = {}
        self.next_offset = 1  # FP[0] é o return address
        self.string_literals: Dict[str, int] = {}  # mapeamento string → label

    def generate(self, program: Program) -> str:
        """Ponto de entrada: gera código completo do programa."""
        self._emit_program_header()

        # Primeira passagem: alocar espaço para variáveis
        self._allocate_variables(program.decls)

        # Gerar código do corpo
        for stmt in program.body:
            self._generate_stmt(stmt)

        # Finalizar programa
        self._emit("STOP")

        return "\n".join(self.code)

    # ── Alocação de variáveis ─────────────────────────────────────────────────

    def _allocate_variables(self, decls: List[VarDecl]) -> None:
        """Aloca espaço para todas as variáveis declaradas."""
        offset = 1  # FP[0] é return address
        for decl in decls:
            for name, shape in decl.names:
                size = 1 if shape is None else shape[0]
                self.variables[name] = VariableInfo(
                    name=name,
                    type_name=decl.type_name,
                    is_array=(shape is not None),
                    shape=shape,
                    offset=offset,
                )
                offset += size
        self.next_offset = offset

    # ── Geração de instruções ─────────────────────────────────────────────────

    def _emit(self, instr: str) -> None:
        """Emite uma instrução."""
        # Labels são emitidos como estão (ex.: IL1: ou L10:)
        if instr.endswith(':'):
            self.code.append(instr)
            return

        # Para instruções, apenas o opcode é normalizado para lowercase.
        # Isto evita alterar operandos (ex.: strings em PUSHS).
        parts = instr.split(' ', 1)
        opcode = parts[0].lower()
        if len(parts) == 1:
            self.code.append(opcode)
        else:
            self.code.append(f"{opcode} {parts[1]}")

    def _new_label(self) -> str:
        """Gera um novo label único."""
        self.label_counter += 1
        # Prefixo começando por letra para evitar colisão com labels Fortran
        # e ser aceite pelo parser da VM (ex.: IL1, IL2, ...)
        return f"IL{self.label_counter}"

    def _emit_label(self, label: str) -> None:
        """Emite um label."""
        self._emit(f"{label}:")

    def _emit_array_address(self, var_info: VariableInfo, index_expr: Node) -> None:
        """Empilha o endereço de um elemento de array local (1D, índice 1-based).

        Endereço = FP + offset_base + (index - 1)
        """
        self._emit("PUSHFP")
        self._emit(f"PUSHI {var_info.offset}")
        self._emit("PADD")
        self._generate_expr(index_expr)
        self._emit("PUSHI 1")
        self._emit("SUB")
        self._emit("PADD")

    def _type_of(self, expr: Node) -> str:
        """Inferir tipo de expressão: 'INTEGER', 'REAL', 'CHARACTER', 'LOGICAL'.

        Regras simples e conservadoras suficientes para o subset atual:
        - Literais: imediato
        - ID/ArrayRef: consultar self.variables
        - BinOp: relacionais/logicos -> LOGICAL; aritméticos -> REAL se qualquer operando for REAL, senão INTEGER
        - FuncCall: heurística para intrínsecos suportados
        """
        if isinstance(expr, IntLit):
            return 'INTEGER'
        if isinstance(expr, RealLit):
            return 'REAL'
        if isinstance(expr, StrLit):
            return 'CHARACTER'
        if isinstance(expr, BoolLit):
            return 'LOGICAL'
        if isinstance(expr, ID):
            var = self.variables.get(expr.name)
            return var.type_name if var is not None else 'INTEGER'
        if isinstance(expr, ArrayRef):
            var = self.variables.get(expr.name)
            return var.type_name if var is not None else 'INTEGER'
        if isinstance(expr, BinOp):
            # operadores relacionais/logicos retornam LOGICAL
            rel_ops = {'.GT.', '.LT.', '.GE.', '.LE.', '.EQ.', '.NE.'}
            logic_ops = {'.AND.', '.OR.'}
            if expr.op in rel_ops or expr.op in logic_ops:
                return 'LOGICAL'
            left_t = self._type_of(expr.left)
            right_t = self._type_of(expr.right)
            if left_t == 'REAL' or right_t == 'REAL':
                return 'REAL'
            return 'INTEGER'
        if isinstance(expr, FuncCall):
            # Heurística: intrínsecos conhecidos
            name = expr.name
            if name == 'MOD':
                return 'INTEGER'
            if name == 'ABS':
                # retorna o tipo do primeiro argumento
                if expr.args:
                    return self._type_of(expr.args[0])
                return 'INTEGER'
            # fallback conservador
            return 'INTEGER'
        return 'INTEGER'

    def _emit_program_header(self) -> None:
        """Emite o cabeçalho do programa (inicialização da VM)."""
        self._emit("START")

    # ── Geração de instruções (statements) ────────────────────────────────────

    def _generate_stmt(self, stmt: Node) -> None:
        """Despacha a geração de código para cada tipo de instrução."""
        if isinstance(stmt, Assign):
            self._generate_assign(stmt)
        elif isinstance(stmt, IfThen):
            self._generate_if_then(stmt)
        elif isinstance(stmt, DoLoop):
            self._generate_do_loop(stmt)
        elif isinstance(stmt, GotoStmt):
            self._generate_goto(stmt)
        elif isinstance(stmt, PrintStmt):
            self._generate_print(stmt)
        elif isinstance(stmt, ReadStmt):
            self._generate_read(stmt)
        elif isinstance(stmt, LabeledStmt):
            self._generate_labeled_stmt(stmt)
        elif isinstance(stmt, CallStmt):
            self._generate_call(stmt)
        elif isinstance(stmt, Continue):
            pass  # CONTINUE não gera código na entrega mínima
        elif isinstance(stmt, StopStmt):
            self._emit("STOP")
        elif isinstance(stmt, ReturnStmt):
            self._emit("RETURN")
        else:
            raise ValueError(f"Instrução desconhecida: {type(stmt)}")

    def _generate_assign(self, assign: Assign) -> None:
        """Gera código para uma atribuição: target = value."""
        # Gerar código do valor (pilha do operando)
        self._generate_expr(assign.value)

        # Armazenar no target
        if isinstance(assign.target, ID):
            var_info = self.variables.get(assign.target.name)
            if var_info is None:
                raise ValueError(f"Variável não declarada: {assign.target.name}")
            self._emit(f"STOREL {var_info.offset}")
        elif isinstance(assign.target, ArrayRef):
            var_info = self.variables.get(assign.target.name)
            if var_info is None:
                raise ValueError(f"Array não declarado: {assign.target.name}")
            # Calcular endereço do elemento alvo
            self._emit_array_address(var_info, assign.target.indices[0])
            # STORE espera [endereço, valor] (topo = valor)
            self._emit("SWAP")
            self._emit("STORE 0")
        else:
            raise ValueError(f"Target inválido: {type(assign.target)}")

    def _generate_expr(self, expr: Node) -> None:
        """Gera código para uma expressão (postfix → pilha)."""
        if isinstance(expr, IntLit):
            self._emit(f"PUSHI {expr.value}")
        elif isinstance(expr, RealLit):
            self._emit(f"PUSHF {expr.value}")
        elif isinstance(expr, StrLit):
            escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"')
            self._emit(f'PUSHS "{escaped}"')
        elif isinstance(expr, BoolLit):
            self._emit(f"PUSHI {1 if expr.value else 0}")
        elif isinstance(expr, ID):
            var_info = self.variables.get(expr.name)
            if var_info is None:
                raise ValueError(f"Variável não declarada: {expr.name}")
            # PUSHL já empilha o valor da variável local
            self._emit(f"PUSHL {var_info.offset}")
        elif isinstance(expr, ArrayRef):
            var_info = self.variables.get(expr.name)
            if var_info is None:
                raise ValueError(f"Array não declarado: {expr.name}")
            self._emit_array_address(var_info, expr.indices[0])
            self._emit("LOAD 0")
        elif isinstance(expr, BinOp):
            self._generate_binop(expr)
        elif isinstance(expr, UnaryOp):
            self._generate_unaryop(expr)
        elif isinstance(expr, FuncCall):
            self._generate_func_call(expr)
        else:
            raise ValueError(f"Expressão desconhecida: {type(expr)}")

    def _generate_binop(self, binop: BinOp) -> None:
        """Gera código para operações binárias."""
        self._generate_expr(binop.left)
        self._generate_expr(binop.right)

        # Mapear operador para instrução EWVM (casos simples)
        op_map = {
            '+': 'ADD',
            '-': 'SUB',
            '*': 'MUL',
            '/': 'DIV',
            '.GT.': 'SUP',
            '.LT.': 'INF',
            '.GE.': 'SUPEQ',
            '.LE.': 'INFEQ',
            '.EQ.': 'EQUAL',
            '.AND.': 'AND',
            '.OR.': 'OR',
        }

        # Tratar operadores que não têm instrução direta na EWVM.
        # '**' (potência) não tem instrução nativa. Lançamos um erro
        # informativo para que o programador saiba que não está suportado
        # aqui (alternativa: implementar potência inteira por multiplicações
        # repetidas ou usar uma rotina de biblioteca externa).
        if binop.op == '**':
            raise NotImplementedError(
                "Operador ** não suportado na geração de código EWVM; "
                "considere implementar potência inteira via multiplicações repetidas"
            )

        # .NE. (not equal) não existe como instrução única na EWVM.
        # Implementamos como EQUAL seguido de NOT.
        # Razão: a EWVM não tem uma instrução direta "NE". Para obter
        # o teste "a != b" primeiro comparamos com EQUAL (a == b) e
        # depois invertimos o resultado com NOT, produzindo (a != b).
        if binop.op == '.NE.':
            self._emit('EQUAL')
            self._emit('NOT')
            return

        instr = op_map.get(binop.op)
        if instr is None:
            raise ValueError(f"Operador desconhecido: {binop.op}")
        self._emit(instr)

    def _generate_unaryop(self, unaryop: UnaryOp) -> None:
        """Gera código para operações unárias."""
        self._generate_expr(unaryop.operand)
        if unaryop.op == '.NOT.':
            self._emit("NOT")
        elif unaryop.op == '-':
            self._emit("PUSHI 0")
            self._emit("SWAP")
            self._emit("SUB")
        else:
            raise ValueError(f"Operador unário desconhecido: {unaryop.op}")

    def _generate_if_then(self, if_stmt: IfThen) -> None:
        """Gera código para IF-THEN-ELSE."""
        else_label = self._new_label()
        end_label = self._new_label()

        # Condição
        self._generate_expr(if_stmt.condition)
        self._emit(f"JZ {else_label}")

        # Then body
        for stmt in if_stmt.then_body:
            self._generate_stmt(stmt)
        self._emit(f"JUMP {end_label}")

        # Else body
        self._emit_label(else_label)
        for stmt in if_stmt.else_body:
            self._generate_stmt(stmt)

        # Fim
        self._emit_label(end_label)

    def _generate_do_loop(self, do_loop: DoLoop) -> None:
        """Gera código para ciclo DO."""
        loop_label = self._new_label()
        end_label = self._new_label()

        # Inicializar variável de controlo: var = start
        var_info = self.variables.get(do_loop.var)
        if var_info is None:
            raise ValueError(f"Variável de controlo não declarada: {do_loop.var}")

        self._generate_expr(do_loop.start)
        self._emit(f"STOREL {var_info.offset}")

        # Rótulo do loop
        self._emit_label(loop_label)

        # Verificar condição: var <= stop (INFEQ)
        self._emit(f"PUSHL {var_info.offset}")
        self._generate_expr(do_loop.stop)
        self._emit("INFEQ")
        self._emit(f"JZ {end_label}")

        # Corpo do loop
        for stmt in do_loop.body:
            self._generate_stmt(stmt)

        # Incrementar variável de controlo: var = var + step (ou 1 se step é None)
        step = do_loop.step if do_loop.step is not None else IntLit(value=1)
        self._emit(f"PUSHL {var_info.offset}")
        self._generate_expr(step)
        self._emit("ADD")
        self._emit(f"STOREL {var_info.offset}")

        # Voltar ao início
        self._emit(f"JUMP {loop_label}")

        # Fim do loop
        self._emit_label(end_label)

    def _generate_goto(self, goto_stmt: GotoStmt) -> None:
        """Gera código para GOTO."""
        # Fortran usa labels numéricos; mapeamos para labels L{número}
        label = f"L{goto_stmt.label}"
        self._emit(f"JUMP {label}")

    def _generate_labeled_stmt(self, labeled: LabeledStmt) -> None:
        """Gera código para instrução com label."""
        label = f"L{labeled.label}"
        self._emit_label(label)
        self._generate_stmt(labeled.stmt)

    def _generate_print(self, print_stmt: PrintStmt) -> None:
        """Gera código para PRINT."""
        for item in print_stmt.items:
            self._generate_expr(item)
            # Determinar o tipo usando heurísticas e emitir a instrução correcta
            t = self._type_of(item)
            if t == 'INTEGER' or t == 'LOGICAL':
                self._emit("WRITEI")
            elif t == 'REAL':
                self._emit("WRITEF")
            else:
                self._emit("WRITES")
        self._emit("WRITELN")

    def _generate_read(self, read_stmt: ReadStmt) -> None:
        """Gera código para READ."""
        for item in read_stmt.items:
            self._emit("READ")
            if isinstance(item, ID):
                var_info = self.variables.get(item.name)
                if var_info is None:
                    raise ValueError(f"Variável não declarada: {item.name}")
                self._emit(f"STOREL {var_info.offset}")
            elif isinstance(item, ArrayRef):
                var_info = self.variables.get(item.name)
                if var_info is None:
                    raise ValueError(f"Array não declarado: {item.name}")
                # Calcular índice e endereço, depois armazenar
                self._emit_array_address(var_info, item.indices[0])
                self._emit("SWAP")
                self._emit("STORE 0")
            else:
                raise ValueError(f"Item de READ não suportado: {type(item)}")

    def _generate_call(self, call_stmt: CallStmt) -> None:
        """Gera código para CALL (chamada de subrotina)."""
        # Esta é uma operação avançada que requer suporte a subprogramas
        # Deixamos como não implementado
        raise NotImplementedError("CALL ainda não está implementado no gerador de código")

    def _generate_func_call(self, func_call: FuncCall) -> None:
        """Gera código para chamadas de função (intrínsecas ou externas)."""
        # Apenas funções intrínsecas simples
        INTRINSICS = {
            'MOD': 'MOD',
            'ABS': 'ABS',
        }

        if func_call.name in INTRINSICS:
            for arg in func_call.args:
                self._generate_expr(arg)
            self._emit(INTRINSICS[func_call.name])
        else:
            raise NotImplementedError(f"Função {func_call.name} não implementada")


# ── Ponto de entrada para uso público ─────────────────────────────────────────

def generate_code(program: Program) -> str:
    """Gera código EWVM para um programa Fortran."""
    codegen = CodeGen()
    return codegen.generate(program)


# ── Teste rápido ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from lexer import build_lexer
    from parser import build_parser
    from semantic import SemanticAnalyser

    _code = """\
PROGRAM HELLO
  PRINT *, 'Hello, World!'
END
"""
    _lexer  = build_lexer()
    _parser = build_parser()
    _ast    = _parser.parse(_code, lexer=_lexer)

    _analyser = SemanticAnalyser()
    _ast      = _analyser.analyse(_ast)

    _generated = generate_code(_ast)
    print(_generated)
