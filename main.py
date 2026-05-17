#!/usr/bin/env python3
"""
Compilador Fortran 77 → EWVM
Projeto de Processamento de Linguagens 2026 — Grupo 18

Uso:
    python main.py <ficheiro.f>                  # imprime código VM no stdout
    python main.py <ficheiro.f> -o <saida.vm>    # escreve código VM num ficheiro
    python main.py <ficheiro.f> --ast            # mostra a AST após análise semântica
    python main.py <ficheiro.f> --tokens         # mostra a lista de tokens
    python main.py <ficheiro.f> --symbols       # mostra a tabela de símbolos
"""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.codegen import generate_code
from src.lexer import build_lexer
from src.parser import build_parser
from src.semantic import SemanticAnalyser


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compilador Fortran 77 → EWVM (Grupo 18)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input",
        metavar="ficheiro.f",
        help="Ficheiro fonte Fortran 77",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="saida.vm",
        help="Ficheiro de saída para o código VM (por omissão: stdout)",
        default=None,
    )
    parser.add_argument(
        "--ast",
        action="store_true",
        help="Mostrar a AST após análise semântica e terminar",
    )
    parser.add_argument(
        "--tokens",
        action="store_true",
        help="Mostrar a lista de tokens e terminar",
    )
    parser.add_argument(
        "--symbols",
        action="store_true",
        help="Mostrar a tabela de símbolos após análise semântica",
    )
    return parser.parse_args()


def read_source(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Erro: ficheiro '{path}' não encontrado.", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Erro ao ler '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def run_lexer(source: str) -> None:
    lexer = build_lexer()
    lexer.input(source)
    for tok in lexer:
        print(tok)


def compile_source(source: str, args) -> str:
    lexer = build_lexer()
    parser = build_parser()
    ast = parser.parse(source, lexer=lexer)

    if ast is None:
        print("Erro: o parser não conseguiu construir a AST.", file=sys.stderr)
        sys.exit(1)

    analyser = SemanticAnalyser()
    ast = analyser.analyse(ast)

    if analyser.symbol_table and analyser.symbol_table.errors:
        print("Erros semânticos encontrados:", file=sys.stderr)
        for err in analyser.symbol_table.errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    if analyser.symbol_table and analyser.symbol_table.warnings:
        for warn in analyser.symbol_table.warnings:
            print(f"Aviso: {warn}", file=sys.stderr)

    if args.symbols and analyser.symbol_table:
        print(analyser.symbol_table.report(), file=sys.stderr)

    if args.ast:
        print(ast)
        sys.exit(0)

    try:
        return generate_code(ast)
    except NotImplementedError as e:
        print(f"Erro: funcionalidade não suportada — {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Erro na geração de código: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()
    source = read_source(args.input)

    if args.tokens:
        run_lexer(source)
        sys.exit(0)

    vm_code = compile_source(source, args)

    if args.output:
        try:
            Path(args.output).write_text(vm_code + "\n", encoding="utf-8")
            print(f"Código VM escrito em '{args.output}'", file=sys.stderr)
        except OSError as e:
            print(f"Erro ao escrever '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(vm_code)


if __name__ == "__main__":
    main()