from pathlib import Path
import sys

# Garantir que o root do projecto está no sys.path para importar `src`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.lexer import build_lexer
from src.parser import build_parser
from src.semantic import SemanticAnalyser
from src.codegen import generate_code


EXAMPLES = ROOT / 'examples'


def compile_example(path: Path) -> None:
    src = path.read_text()
    lexer = build_lexer()
    parser = build_parser()
    ast = parser.parse(src, lexer=lexer)
    if ast is None:
        print(f"Parsing failed for {path}; skipping")
        return
    analyser = SemanticAnalyser()
    ast = analyser.analyse(ast)
    if ast is None:
        print(f"Semantic analysis failed for {path}; skipping")
        return
    code = generate_code(ast)
    out = path.with_suffix('.vm')
    out.write_text(code)
    print(f"Wrote {out}")


def main():
    for f in sorted(EXAMPLES.glob('*.f')):
        compile_example(f)


if __name__ == '__main__':
    main()
