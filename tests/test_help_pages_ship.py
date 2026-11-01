"""The help pages the Assistant reads about the app itself go in the Windows build (TQ-1251: "Taskuary doesnt know about itself")."""
from pathlib import Path
from taskuary import lookups

ROOT = Path(__file__).resolve().parent.parent


def test_the_exe_carries_the_help_pages_where_docs_search_looks():
    spec = (ROOT / 'taskuary.spec').read_text(encoding='utf-8')
    assert "('docs/site/*.md', 'docs/site')" in spec
    assert lookups.SITE_DOCS.relative_to(ROOT).as_posix() == 'docs/site' and any(lookups.SITE_DOCS.glob('*.md'))
