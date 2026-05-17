"""
tests/test_lexer.py — Testes unitários do analisador léxico

Estrutura dos testes:
    1. Palavras-chave         — são identificadas e separadas de IDs normais
    2. Case-insensitivity     — Fortran não distingue maiúsculas de minúsculas
    3. Identificadores        — normalizados para uppercase
    4. Literais inteiros      — conversão para int Python
    5. Literais reais         — notação decimal e científica, conversão para float
    6. Literais string        — aspas removidas
    7. Literais booleanos     — convertidos para bool Python
    8. Operadores aritméticos — +, -, *, /, **  (POWER antes de STAR)
    9. Operadores relacionais — .GT., .LT., .GE., .LE., .EQ., .NE.
   10. Operadores lógicos     — .AND., .OR., .NOT.
   11. Pontuação              — (, ), ,, =, :
   12. Comentários            — descartados, não geram token
   13. Contagem de linhas     — lineno actualizado em newlines
   14. Programas completos    — os exemplos do enunciado tokenizam sem erros
"""

import sys
import os
import pytest

# Adiciona a pasta pai (PL_grupo18) ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.lexer import build_lexer


# ─── Utilitário auxiliar ──────────────────────────────────────────────────────

def tokenize(source: str) -> list[tuple[str, object]]:
    """
    Tokeniza 'source' e devolve lista de (tipo, valor).

    Usamos build_lexer() para obter um lexer com estado limpo em cada teste,
    evitando que o lineno ou o input de um teste "vaze" para o seguinte.
    """
    lexer = build_lexer()
    lexer.input(source)
    return [(tok.type, tok.value) for tok in lexer]


def token_types(source: str) -> list[str]:
    """Devolve apenas os tipos de token — útil para testes de estrutura."""
    return [t for t, _ in tokenize(source)]


# ─── 1. Palavras-chave ────────────────────────────────────────────────────────

class TestKeywords:
    """
    O que testamos: que cada palavra reservada do Fortran 77 gera o tipo de
    token correto e não é tratada como um identificador genérico (ID).

    se uma palavra-chave fosse tokenizada como ID, o parser não
    conseguiria reconhecer estruturas como 'PROGRAM' ou 'IF'.
    """

    def test_program(self):
        assert tokenize('PROGRAM') == [('PROGRAM', 'PROGRAM')]

    def test_end(self):
        assert tokenize('END') == [('END', 'END')]

    def test_integer(self):
        assert tokenize('INTEGER') == [('INTEGER', 'INTEGER')]

    def test_real(self):
        assert tokenize('REAL') == [('REAL', 'REAL')]

    def test_logical(self):
        assert tokenize('LOGICAL') == [('LOGICAL', 'LOGICAL')]

    def test_if_then_else_endif(self):
        types = token_types('IF THEN ELSE ENDIF')
        assert types == ['IF', 'THEN', 'ELSE', 'ENDIF']

    def test_do_continue_goto(self):
        types = token_types('DO CONTINUE GOTO')
        assert types == ['DO', 'CONTINUE', 'GOTO']

    def test_print_read(self):
        types = token_types('PRINT READ')
        assert types == ['PRINT', 'READ']

    def test_function_subroutine_call_return(self):
        types = token_types('FUNCTION SUBROUTINE CALL RETURN')
        assert types == ['FUNCTION', 'SUBROUTINE', 'CALL', 'RETURN']

    def test_stop(self):
        assert tokenize('STOP') == [('STOP', 'STOP')]


# ─── 2. Case-insensitivity ────────────────────────────────────────────────────

class TestCaseInsensitivity:
    """
    a especificação ANSI do Fortran 77 define a linguagem como
    case-insensitive. Normalizar para uppercase no lexer significa que o parser
    e o resto do compilador nunca precisam de se preocupar com capitalização.
    """

    def test_keyword_lowercase(self):
        assert tokenize('program') == [('PROGRAM', 'PROGRAM')]

    def test_keyword_mixed_case(self):
        assert tokenize('PrOgRaM') == [('PROGRAM', 'PROGRAM')]

    def test_identifier_normalized(self):
        # 'myVar' deve tornar-se o ID 'MYVAR'
        assert tokenize('myVar') == [('ID', 'MYVAR')]

    def test_real_keyword_lowercase(self):
        assert tokenize('real') == [('REAL', 'REAL')]


# ─── 3. Identificadores ───────────────────────────────────────────────────────

class TestIdentifiers:
    """
    em Fortran, 'n', 'N' e 'N' são a mesma variável. Normalizar no
    lexer simplifica todas as fases seguintes.
    """

    def test_simple_id(self):
        assert tokenize('N') == [('ID', 'N')]

    def test_id_with_digits(self):
        assert tokenize('FAT1') == [('ID', 'FAT1')]

    def test_id_normalized_to_upper(self):
        assert tokenize('numeros') == [('ID', 'NUMEROS')]

    def test_id_not_confused_with_keyword(self):
        # 'ENDO' começa com 'END' mas não é a palavra-chave END
        assert tokenize('ENDO') == [('ID', 'ENDO')]

    def test_id_starts_with_letter(self):
        # Identificadores em Fortran têm de começar por letra
        # '1N' deve gerar INT_LIT(1) e depois ID(N)
        types = token_types('1N')
        assert types == ['INT_LIT', 'ID']


# ─── 4. Literais inteiros ─────────────────────────────────────────────────────

class TestIntLiterals:
    """
    o parser e o gerador de código vão usar estes valores diretamente
    em cálculos; ter strings obrigaria a conversões manuais em todo o lado.
    """

    def test_zero(self):
        assert tokenize('0') == [('INT_LIT', 0)]

    def test_positive(self):
        assert tokenize('42') == [('INT_LIT', 42)]

    def test_large(self):
        assert tokenize('999999') == [('INT_LIT', 999999)]

    def test_value_is_int(self):
        tokens = tokenize('10')
        assert isinstance(tokens[0][1], int)

    def test_multiple_ints(self):
        tokens = tokenize('1 2 3')
        assert tokens == [('INT_LIT', 1), ('INT_LIT', 2), ('INT_LIT', 3)]


# ─── 5. Literais reais ────────────────────────────────────────────────────────

class TestRealLiterals:
    """
    Fortran distingue INTEGER de REAL na declaração de variáveis;
    a análise semântica precisa de saber o tipo de cada literal.
    Notação científica (1E3, 3.14E-2) é comum em programas científicos.
    """

    def test_simple_decimal(self):
        t, v = tokenize('3.14')[0]
        assert t == 'REAL_LIT'
        assert abs(v - 3.14) < 1e-9

    def test_trailing_dot(self):
        # '1.' é um REAL válido em Fortran (equivale a 1.0)
        t, v = tokenize('1.')[0]
        assert t == 'REAL_LIT'
        assert v == 1.0

    def test_scientific_no_decimal(self):
        t, v = tokenize('1E3')[0]
        assert t == 'REAL_LIT'
        assert v == 1000.0

    def test_scientific_with_decimal(self):
        t, v = tokenize('3.14E2')[0]
        assert t == 'REAL_LIT'
        assert abs(v - 314.0) < 1e-9

    def test_scientific_negative_exponent(self):
        t, v = tokenize('1.0E-3')[0]
        assert t == 'REAL_LIT'
        assert abs(v - 0.001) < 1e-12

    def test_value_is_float(self):
        tokens = tokenize('2.5')
        assert isinstance(tokens[0][1], float)

    def test_real_before_int(self):
        # '3.14' não deve ser tokenizado como INT_LIT(3) + ID(.) + INT_LIT(14)
        tokens = tokenize('3.14')
        assert len(tokens) == 1
        assert tokens[0][0] == 'REAL_LIT'


# ─── 6. Literais string ───────────────────────────────────────────────────────

class TestStringLiterals:
    """
    ao remover os delimitadores no lexer, o parser e o gerador de
    código recebem sempre o conteúdo puro — consistente com a semântica do
    Fortran onde as aspas são apenas delimitadores, não parte do valor.
    """

    def test_simple_string(self):
        assert tokenize("'hello'") == [('STRING_LIT', 'hello')]

    def test_string_with_spaces(self):
        assert tokenize("'Ola, Mundo!'") == [('STRING_LIT', 'Ola, Mundo!')]

    def test_empty_string(self):
        assert tokenize("''") == [('STRING_LIT', '')]

    def test_string_with_numbers(self):
        assert tokenize("'abc123'") == [('STRING_LIT', 'abc123')]

    def test_quotes_removed(self):
        tokens = tokenize("'test'")
        assert "'" not in tokens[0][1]


# ─── 7. Literais booleanos ────────────────────────────────────────────────────

class TestBoolLiterals:
    """
   converter para bool Python no lexer simplifica a análise semântica
    e a geração de código — não é necessário comparar strings ".TRUE." em
    nenhum outro sítio do compilador.
    """

    def test_true(self):
        assert tokenize('.TRUE.') == [('BOOL_LIT', True)]

    def test_false(self):
        assert tokenize('.FALSE.') == [('BOOL_LIT', False)]

    def test_true_lowercase(self):
        assert tokenize('.true.') == [('BOOL_LIT', True)]

    def test_false_mixed_case(self):
        assert tokenize('.False.') == [('BOOL_LIT', False)]

    def test_value_is_bool(self):
        tokens = tokenize('.TRUE.')
        assert isinstance(tokens[0][1], bool)
        assert tokens[0][1] is True


# ─── 8. Operadores aritméticos ───────────────────────────────────────────────

class TestArithmeticOperators:
    """
    a distinção POWER vs STAR é crítica para a precedência de
    operadores no parser. Se '**' gerasse dois STAR, a gramática da
    expressão 'A**B' seria analisada incorretamente.
    """

    def test_plus(self):
        assert tokenize('+') == [('PLUS', '+')]

    def test_minus(self):
        assert tokenize('-') == [('MINUS', '-')]

    def test_star(self):
        assert tokenize('*') == [('STAR', '*')]

    def test_slash(self):
        assert tokenize('/') == [('SLASH', '/')]

    def test_power(self):
        assert tokenize('**') == [('POWER', '**')]

    def test_power_not_two_stars(self):
        # '**' deve gerar UM token POWER, não dois STAR
        tokens = tokenize('**')
        assert len(tokens) == 1
        assert tokens[0][0] == 'POWER'

    def test_expression(self):
        types = token_types('A + B * C')
        assert types == ['ID', 'PLUS', 'ID', 'STAR', 'ID']

    def test_power_expression(self):
        types = token_types('X**2')
        assert types == ['ID', 'POWER', 'INT_LIT']


# ─── 9. Operadores relacionais ────────────────────────────────────────────────

class TestRelationalOperators:
    """
    os operadores relacionais em Fortran têm sintaxe única (ponto-
    operador-ponto) e precisam de ser distinguidos entre si para que o parser
    possa construir expressões booleanas corretamente.
    """

    def test_gt(self):
        assert tokenize('.GT.') == [('GT', '.GT.')]

    def test_lt(self):
        assert tokenize('.LT.') == [('LT', '.LT.')]

    def test_ge(self):
        assert tokenize('.GE.') == [('GE', '.GE.')]

    def test_le(self):
        assert tokenize('.LE.') == [('LE', '.LE.')]

    def test_eq(self):
        assert tokenize('.EQ.') == [('EQ', '.EQ.')]

    def test_ne(self):
        assert tokenize('.NE.') == [('NE', '.NE.')]

    def test_lowercase(self):
        # '.lt.' deve ser tratado igual a '.LT.'
        assert tokenize('.lt.') == [('LT', '.lt.')]

    def test_in_expression(self):
        types = token_types('I .LE. N')
        assert types == ['ID', 'LE', 'ID']


# ─── 10. Operadores lógicos ───────────────────────────────────────────────────

class TestLogicalOperators:
    """
    estes operadores são usados em condições compostas (ex: IF com
    múltiplas condições) e precisam de tipos próprios para a gramática do parser.
    """

    def test_and(self):
        assert tokenize('.AND.') == [('AND', '.AND.')]

    def test_or(self):
        assert tokenize('.OR.') == [('OR', '.OR.')]

    def test_not(self):
        assert tokenize('.NOT.') == [('NOT', '.NOT.')]

    def test_compound_condition(self):
        types = token_types('A .AND. B .OR. .NOT. C')
        assert types == ['ID', 'AND', 'ID', 'OR', 'NOT', 'ID']


# ─── 11. Pontuação ────────────────────────────────────────────────────────────

class TestPunctuation:
    """
    estes tokens são usados em chamadas de função, declarações,
    atribuições e slices de arrays — aparecem em quase todas as construções.
    """

    def test_lparen(self):
        assert tokenize('(') == [('LPAREN', '(')]

    def test_rparen(self):
        assert tokenize(')') == [('RPAREN', ')')]

    def test_comma(self):
        assert tokenize(',') == [('COMMA', ',')]

    def test_equals(self):
        assert tokenize('=') == [('EQUALS', '=')]

    def test_colon(self):
        assert tokenize(':') == [('COLON', ':')]

    def test_declaration_line(self):
        # 'INTEGER N, I, FAT' — padrão típico de declaração
        types = token_types('INTEGER N, I, FAT')
        assert types == ['INTEGER', 'ID', 'COMMA', 'ID', 'COMMA', 'ID']


# ─── 12. Comentários ──────────────────────────────────────────────────────────

class TestComments:
    """
    O parser nunca deve ver tokens de comentário. Se gerassem tokens,
    teríamos de adicionar regras de comentário em toda a gramática.
    """

    def test_comment_alone(self):
        assert tokenize('! isto e um comentario') == []

    def test_comment_after_code(self):
        # Apenas 'N' deve ser tokenizado; o comentário é descartado
        tokens = tokenize('N ! variável contador')
        assert tokens == [('ID', 'N')]

    def test_comment_does_not_affect_next_line(self):
        types = token_types('! linha 1\nINTEGER')
        assert types == ['INTEGER']

    def test_multiple_comments(self):
        code = '! linha a\n! linha b\nEND'
        types = token_types(code)
        assert types == ['END']


# ─── 13. Contagem de linhas ───────────────────────────────────────────────────

class TestLineNumbers:
    """
    mensagens de erro do compilador precisam de indicar a linha do
    problema. Um lineno errado tornaria o compilador difícil de usar.
    """

    def test_first_token_on_line_1(self):
        lexer = build_lexer()
        lexer.input('PROGRAM')
        tok = next(iter(lexer))
        assert tok.lineno == 1

    def test_token_after_newline(self):
        lexer = build_lexer()
        lexer.input('PROGRAM\nEND')
        tokens = list(lexer)
        assert tokens[0].lineno == 1
        assert tokens[1].lineno == 2

    def test_multiple_newlines(self):
        lexer = build_lexer()
        lexer.input('A\n\n\nB')
        tokens = list(lexer)
        assert tokens[0].lineno == 1
        assert tokens[1].lineno == 4


# ─── 14. Programas completos (exemplos do enunciado) ─────────────────────────

class TestFullPrograms:
    """
    estes são os programas que o compilador deve processar
    corretamente para aprovação. Usá-los como testes de integração do
    lexer garante que não há regressões ao modificar as regras.

    Nota: não verificamos aqui a sequência completa de tokens (seria
    frágil e difícil de manter) — verificamos que não há erros e que
    as palavras-chave principais são reconhecidas.
    """

    HELLO = """\
PROGRAM HELLO
  PRINT *, 'Ola, Mundo!'
END
"""

    FATORIAL = """\
PROGRAM FATORIAL
  INTEGER N, I, FAT
  FAT = 1
  DO 10 I = 1, N
    FAT = FAT * I
10 CONTINUE
  PRINT *, 'Fatorial:', FAT
END
"""

    PRIMO = """\
PROGRAM PRIMO
  INTEGER NUM, I
  LOGICAL ISPRIM
  ISPRIM = .TRUE.
  I = 2
20 IF (I .LE. (NUM/2) .AND. ISPRIM) THEN
     IF (MOD(NUM, I) .EQ. 0) THEN
       ISPRIM = .FALSE.
     ENDIF
     I = I + 1
     GOTO 20
   ENDIF
END
"""

    def _keyword_types(self, source):
        """Filtra apenas os tokens que são palavras-chave."""
        kw = set(
            'PROGRAM END INTEGER REAL LOGICAL IF THEN ELSE ENDIF '
            'DO CONTINUE GOTO PRINT READ FUNCTION SUBROUTINE CALL RETURN STOP'.split()
        )
        return [t for t, _ in tokenize(source) if t in kw]

    def test_hello_no_crash(self):
        tokens = tokenize(self.HELLO)
        assert len(tokens) > 0

    def test_hello_keywords(self):
        kws = self._keyword_types(self.HELLO)
        assert 'PROGRAM' in kws
        assert 'PRINT' in kws
        assert 'END' in kws

    def test_fatorial_no_crash(self):
        tokens = tokenize(self.FATORIAL)
        assert len(tokens) > 0

    def test_fatorial_do_continue(self):
        kws = self._keyword_types(self.FATORIAL)
        assert 'DO' in kws
        assert 'CONTINUE' in kws

    def test_fatorial_label_as_int(self):
        # O label '10' antes de CONTINUE deve ser tokenizado como INT_LIT
        tokens = tokenize(self.FATORIAL)
        # Encontra o token imediatamente antes de CONTINUE
        for i, (t, v) in enumerate(tokens):
            if t == 'CONTINUE' and i > 0:
                prev_type, prev_val = tokens[i - 1]
                assert prev_type == 'INT_LIT'
                assert prev_val == 10
                break

    def test_primo_logical_operators(self):
        tokens = tokenize(self.PRIMO)
        types = [t for t, _ in tokens]
        assert 'LE' in types
        assert 'AND' in types
        assert 'EQ' in types

    def test_primo_bool_literal(self):
        tokens = tokenize(self.PRIMO)
        bool_tokens = [(t, v) for t, v in tokens if t == 'BOOL_LIT']
        assert len(bool_tokens) >= 1
        assert bool_tokens[0] == ('BOOL_LIT', True)