"""Test helpers for the owner's memory (memory.py): a line of it where the notes table's rows were, a stand-in model that says what a
verdict teaches, and an older install's notes table for the migration. Invented Northwind world."""
import json
from contextlib import contextmanager
from unittest import mock
from taskuary import learning, memory

LEGACY = ('CREATE TABLE IF NOT EXISTS memory (MemoryId INTEGER PRIMARY KEY, Scope TEXT, ScopeKey TEXT, Note TEXT, Source TEXT, '
          'Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT)')


def note(s, f: dict) -> str:
    """What a notes-table row of this shape is now: a verdict's line, learned and confirmed (his press said "from now on"), else a line he
    said - its words ('' for one switched off: the owner said "not this")."""
    if not f.get('Active', 1): return ''
    if f.get('Source') == 'writing':                    # an instruction on how to write is the drafter's: STYLE.md's Owner notes
        from taskuary.responder import style_feedback
        style_feedback(s, ' '.join(str(f.get('Note') or '').split()), 'memory'); return ''
    text, scope, key = str(f.get('Note') or ''), f.get('Scope') or 'global', f.get('ScopeKey') or ''
    if (f.get('Source') or 'verdict') == 'verdict':
        return memory.infer(s, text, f'{text} {key}', scope=scope, key=key, source='verdict:not_ours', confirmed=True).get('Text') or ''
    return memory.remember(s, text, f'{text} {key}', key if scope == 'sender' else '')['text']


def legacy_row(s, note, scope='global', key=None, source='manual', active=1) -> int:
    """A row as an install from before 2026-10-27 holds it: in the old notes table, not yet in the memory."""
    s.cx.execute(LEGACY)
    cur = s.cx.execute("INSERT INTO memory (Scope, ScopeKey, Note, Source, Active, CreatedBy, CreatedAt) VALUES (?,?,?,?,?,?,datetime('now'))",
                       (scope, key, note, source, active, 'owner'))
    s.cx.commit()
    return cur.lastrowid


def teacher(line='', subject='', only_this=True, seen=None, against=''):
    """A model that answers every lesson with `line`, kept under `subject` - and reads it as going `against` a line's subject."""
    def llm(system, user, **k):
        if seen is not None: seen.append(user)
        return json.dumps({'line': line, 'subject': subject or line, 'only_this': only_this, 'against': against})
    return llm


@contextmanager
def teaching(line='', **kw):
    """Every verdict in the block is taught by `teacher(line, ...)` - the brain learning.teach asks."""
    with mock.patch.object(learning, '_llm', lambda store, llm=None: llm or teacher(line, **kw)): yield


def lines(s) -> list:
    """Every line of the memory's face, LEARNED.md, stripped."""
    return [l.strip() for l in (s.get_doc('learned') or '').splitlines()]
