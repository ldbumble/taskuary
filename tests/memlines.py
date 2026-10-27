"""Test helpers for the one memory (memorylines): LEARNED.md lines where the notes table's rows were, a stand-in model that says what a
verdict teaches, and an older install's notes table for the migration. Invented Northwind world."""
import json
from contextlib import contextmanager
from unittest import mock
from taskuary import memorylines

LEGACY = ('CREATE TABLE IF NOT EXISTS memory (MemoryId INTEGER PRIMARY KEY, Scope TEXT, ScopeKey TEXT, Note TEXT, Source TEXT, '
          'Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT)')


def note(s, f: dict) -> str:
    """What a notes-table row of this shape is now: its LEARNED.md line ('' for one switched off - the owner said "not this")."""
    if not f.get('Active', 1): return ''
    if f.get('Source') == 'writing':                    # an instruction on how to write is the drafter's: STYLE.md's Owner notes
        from taskuary.responder import style_feedback
        style_feedback(s, ' '.join(str(f.get('Note') or '').split()), 'memory'); return ''
    return memorylines.keep(s, f.get('Note') or '', f.get('Scope') or 'global', f.get('ScopeKey'), verdict=(f.get('Source') or 'verdict') == 'verdict')


def legacy_row(s, note, scope='global', key=None, source='manual', active=1) -> int:
    """A row as an install from before 2026-10-27 holds it: in the old notes table, not yet in LEARNED.md."""
    s.cx.execute(LEGACY)
    cur = s.cx.execute("INSERT INTO memory (Scope, ScopeKey, Note, Source, Active, CreatedBy, CreatedAt) VALUES (?,?,?,?,?,?,datetime('now'))",
                       (scope, key, note, source, active, 'owner'))
    s.cx.commit()
    return cur.lastrowid


def teacher(line='', replaces='', only_this=True, seen=None):
    """A model that answers every lesson with `line` (and the existing line it `replaces`)."""
    def llm(system, user, **k):
        if seen is not None: seen.append(user)
        return json.dumps({'line': line, 'replaces': replaces, 'only_this': only_this})
    return llm


@contextmanager
def teaching(line='', **kw):
    """Every verdict in the block is taught by `teacher(line, ...)` - the brain memorylines.teach asks."""
    with mock.patch.object(memorylines, '_llm', lambda store: teacher(line, **kw)): yield


def lines(s) -> list:
    """Every line of LEARNED.md, stripped."""
    return [l.strip() for l in (s.get_doc('learned') or '').splitlines()]
