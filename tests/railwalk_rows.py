"""railwalk over a rail of hand-made rows: the walk's choice of row, with nothing worded and nothing recorded - for the tests that pin
WHICH row comes up (the walk has one owner, 2026-10-30). The rows are the rail as given; `rows` may be changed between moves."""
from contextlib import ExitStack
from unittest import mock


class RowWalk:
    def __init__(self, store, rows):
        from taskuary import concierge, funnel, railwalk
        self.s, self.rows, self.rw, self.st = store, rows, railwalk, ExitStack()
        self.st.enter_context(mock.patch.object(railwalk, '_rows', lambda store: list(self.rows)))
        self.st.enter_context(mock.patch.object(railwalk, '_present', lambda store, item, actor, **k: {'item': item, 'say': '', 'options': [], 'chips': []}))
        self.st.enter_context(mock.patch.object(railwalk, '_end', lambda store, st, rows, actor, record=True: {'item': None, 'say': '', 'chips': [], 'over': True}))
        self.st.enter_context(mock.patch.object(railwalk, '_dock', lambda store, actor: 1))
        self.st.enter_context(mock.patch.object(funnel, '_present_one', lambda store, item: item))
        self.st.enter_context(mock.patch.object(concierge, '_stamp_next', lambda *a, **k: False))
        self.read = []
        self.st.enter_context(mock.patch.object(funnel, 'settle', lambda store, key, verb, *a, **k: self.read.append((key, verb, k.get('read')))))

    def close(self): self.st.close()

    def key(self, out): return (out.get('item') or {}).get('key')
    def start(self): return self.key(self.rw.start(self.s))
    def next(self, frm=None): return self.key(self.rw.next(self.s, frm))
    def back(self, frm=None): return self.key(self.rw.back(self.s, frm))
    def open(self, key): return self.key(self.rw.open(self.s, key))
