"""A module never defines the same top-level name twice: the second silently replaces the first, and every caller of the first
gets the second. 2026-10-28 twice in one day: assistant.raised (the digest broke) and concierge.NO_THREAD (the item prompt's line)."""
import ast, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'taskuary'
ALLOWED = {'digest.py:PROMPT'}     # the brief's prompt is rebuilt from its own earlier wording on purpose (digest.py)


def _top_names(tree):
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): yield n.name, n.lineno
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name): yield t.id, n.lineno


def test_no_module_redefines_a_top_level_name():
    seen = []
    for f in sorted(ROOT.rglob('*.py')):
        lines = collections.defaultdict(list)
        for name, ln in _top_names(ast.parse(f.read_text(encoding='utf-8'))): lines[name].append(ln)
        seen += [f'{f.relative_to(ROOT)}:{n} at lines {ls}' for n, ls in lines.items() if len(ls) > 1 and f'{f.name}:{n}' not in ALLOWED]
    assert not seen, 'a name defined twice - the later one replaces the earlier for every caller:\n' + '\n'.join(seen)
