"""THE SURFACES THAT ARE GONE are named in no line the server writes (words.json's gone): the Timeline, the Reports tab and the Assistant
tab outlived their removal in replies, prompts and setting labels, and the model repeated "it is on the Reports tab" to the owner
(2026-10-19 UI walk). Docstrings and comments are the code's own history and are not read; a bare "Timeline" is a destination key the
page's router still resolves (problems.py's `where`), not a line."""
import ast, re, unittest
from pathlib import Path
from taskuary import words

PKG = Path(__file__).parent.parent / 'taskuary'


def _lines(src: str):
    t = ast.parse(src)
    docs = {id(n.body[0].value) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], 'value', None), ast.Constant)}
    return [(n.lineno, n.value) for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


class GoneSurfaces(unittest.TestCase):
    def test_no_server_line_names_a_surface_that_is_gone(self):
        gone = re.compile(r'\b(?:' + '|'.join(map(re.escape, words.GONE)) + r')\b')
        hits = [f'{f.name}:{ln}: {v[:80]!r}' for f in sorted(PKG.glob('*.py')) for ln, v in _lines(f.read_text(encoding='utf-8'))
                if v != 'Timeline' and gone.search(v)]
        self.assertEqual(hits, [])
        cat = (PKG / 'connectorcatalog.json').read_text(encoding='utf-8')
        self.assertIsNone(gone.search(cat), 'a connector card still names a gone surface')

    def test_jargon_in_flags_them_as_written(self):
        self.assertEqual(words.jargon_in('it is on the Reports tab'), ['Reports tab'])
        self.assertEqual(words.jargon_in('the project timeline slipped'), [])
        self.assertEqual(words.noun('cli_agents'), 'AI CLI agents')
        self.assertTrue(words.name('ai_apps').endswith(words.noun('cli_agents')))


if __name__ == '__main__': unittest.main()
