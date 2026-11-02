"""The help pages the Assistant reads about the app itself go in the Windows build (TQ-1251: "Taskuary doesnt know about itself")."""
from pathlib import Path
from taskuary import lookups

ROOT = Path(__file__).resolve().parent.parent


def test_the_exe_carries_the_help_pages_where_docs_search_looks():
    spec = (ROOT / 'taskuary.spec').read_text(encoding='utf-8')
    assert "('docs/site/*.md', 'docs/site')" in spec
    assert lookups.SITE_DOCS.relative_to(ROOT).as_posix() == 'docs/site' and any(lookups.SITE_DOCS.glob('*.md'))


def test_the_wheel_and_the_container_carry_them_where_an_install_looks():
    """A `pip install taskuary` has no docs/site beside the package: its Assistant searched no help and no What's new (2026-11-02).
    publish.yml and the Dockerfile copy the pages into taskuary/help, the wheel's package data names them, and lookups falls back there."""
    import tempfile
    pub, dock = (ROOT / '.github' / 'workflows' / 'publish.yml').read_text(encoding='utf-8'), (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    assert 'cp docs/site/*.md taskuary/help/' in pub and pub.index('cp docs/site/*.md') < pub.index('pipx run build') and "'help pages'" in pub
    assert 'COPY docs/site/*.md ./taskuary/help/' in dock and '!docs/site/*.md' in (ROOT / '.dockerignore').read_text(encoding='utf-8')
    assert '"help/*.md"' in (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    site_packages = Path(tempfile.mkdtemp())          # an install: the package, and no docs/site beside it
    assert lookups.help_dir(site_packages / 'taskuary') == site_packages / 'taskuary' / 'help'
    assert lookups.help_dir(ROOT / 'taskuary') == ROOT / 'docs' / 'site'


def test_the_assistant_finds_what_a_release_changed():
    import importlib.util
    from taskuary.store import MemoryStore
    out = lookups.docs_search(MemoryStore(), {'query': 'what changed in the last update'})
    assert '[help/whats-new' in out, out[:300]
    spec = importlib.util.spec_from_file_location('whatsnew', ROOT / 'tools' / 'whatsnew.py'); w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
    assert all(w.CHORE.match(s) for s in ('Release 0.3.10.11', "Refresh the README's PyPI pill for 0.3.10.11", 'Rebuild the UI and demo for X'))
    assert not w.CHORE.match('A mail account goes to the mailbox card')
    assert w.has(w.section('9.9.9', '2026-11-01', ['x']), '9.9.9') and not w.has(w.section('9.9.9', '2026-11-01', []), '9.9.90')


def test_a_search_no_passage_carries_hands_the_model_the_contents_to_pick_from():
    """With no embedder only the whole phrase is found - "latest release what changed" found nothing, and the model read no help at all."""
    from taskuary.store import MemoryStore
    out = lookups.docs_search(MemoryStore(), {'query': 'latest release what changed'})
    assert 'help/whats-new:' in out and '`section`' in out
    page = lookups.docs_search(MemoryStore(), {'section': 'help/whats-new'})
    assert page.startswith('[help/whats-new]') and '## 0.' in page
    assert lookups.docs_search(MemoryStore(), {'section': 'help/nope'}).startswith('No section')
