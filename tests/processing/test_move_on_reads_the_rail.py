"""Next puts the row it leaves down from the build the rail already holds (2026-10-20): a keyed build only to read
back that row's sig was 0.2-1 s of every press on a big home. The rail's build is used only while nothing has been
written since it began, and what is written is exactly what the keyed lookup wrote."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from taskuary import concierge, funnel, funnel_presentation as fp, terminal
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)


def seeded(path):
    s = SQLiteStore(str(path))
    s.set_setting('calendar_enabled', '0', 'test')
    tid = s.create_task({'Title': 'Quarter close', 'Status': 'open'}, 'fixture')
    for n in range(1, 6):
        s.add_message({'ExternalId': f'left:{n}', 'ConversationId': f'left-thread:{n}', 'TaskId': tid if n == 1 else None,
                       'Channel': 'email', 'SourceName': 'fixture@example.test', 'FromName': f'Person {n}',
                       'FromEmail': f'p{n}@example.test', 'Subject': f'Left {n}', 'BodyText': f'Body {n}',
                       'Status': 'routed' if n % 2 else 'filed', 'SentAt': (NOW - timedelta(minutes=n)).strftime('%Y-%m-%d %H:%M:%S')})
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=NOW.isoformat(), live_state=[])
    return s


def copy(s, path):
    s.cx.commit(); dst = sqlite3.connect(str(path)); s.cx.backup(dst); dst.close()
    return SQLiteStore(str(path))


@pytest.fixture
def two(tmp_path, monkeypatch):
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kw: [])
    monkeypatch.setattr(funnel, 'announce', lambda store, *a, **k: [])
    class Frozen(datetime):                              # the two stores write the same clock
        @classmethod
        def now(cls, tz=None): return NOW
    from taskuary import store as store_module, processing_unread
    for m in (funnel, concierge, store_module, processing_unread): monkeypatch.setattr(m, 'datetime', Frozen)
    a = seeded(tmp_path / 'a.db'); b = copy(a, tmp_path / 'b.db')
    fp.forget_stamps(); funnel.invalidate()
    yield a, b
    fp.forget_stamps(); funnel.invalidate()
    a.cx.close(); b.cx.close()


def states(s): return [dict(r) for r in s.cx.execute('SELECT Key, Status, Note, Until FROM funnel_state ORDER BY Key')]


def keyed_builds(monkeypatch):
    calls, real = [], funnel.build
    def spy(store, *a, **k):
        if k.get('keys'): calls.append(k['keys'])
        return real(store, *a, **k)
    monkeypatch.setattr(funnel, 'build', spy)
    return calls


def test_the_row_left_is_put_down_from_the_rail_as_the_lookup_put_it_down(two, monkeypatch):
    a, b = two
    keys = [i['key'] for i in funnel.pile(b, quiet=True, observed=[])['items']]
    assert len(keys) >= 3
    for key in keys:                                   # the lookup it always was: a fresh rail read is never used for it
        funnel.invalidate(); concierge.move_on(b, key)
    calls = keyed_builds(monkeypatch)
    for key in keys:
        funnel.pile(a, quiet=True, observed=[]); concierge.move_on(a, key)
    assert calls == [], 'the row left was found in the rail it was chosen from'
    assert states(a) == states(b)


def test_a_write_since_the_rail_was_built_is_the_lookup_again(two, monkeypatch):
    a, _ = two
    key = funnel.pile(a, quiet=True, observed=[])['items'][0]['key']
    a.add_comment(a.list_tasks()[0]['TaskId'], 'owner', 'user', 'written after the rail was built')
    assert funnel.unwritten_full_items(a) is None
    calls = keyed_builds(monkeypatch)
    concierge.move_on(a, key)
    assert calls, 'a rail built before a write is not the store as of now'


def test_mark_done_asks_whether_its_task_is_on_the_table_from_the_rail_as_the_lookup_answered(two, monkeypatch):
    """concierge.on_table, read before every Mark done: is the act about the item on the Assistant's table? It built the
    table's row by key only to compare one task id (0.06-4.4 s on a big home, 2026-10-20) - now from the rail's own build."""
    a, _ = two
    a.set_setting('assistant_dock_task_id', '1', 'test')
    keys = [i['key'] for i in funnel.pile(a, quiet=True, observed=[])['items']]
    ops = [{'kind': 'task.complete', 'target': t} for t in [t['TaskId'] for t in a.list_tasks()] + [999]]

    def answers(cached):
        out = []
        for key in keys:
            monkeypatch.setattr(concierge, 'current_key', lambda store, dock, key=key: key)
            for op in ops:
                if cached: funnel.pile(a, quiet=True, observed=[])
                else: funnel.invalidate()
                out.append(concierge.on_table(a, op))
        return out
    looked_up = answers(False)
    calls = keyed_builds(monkeypatch)
    assert answers(True) == looked_up and any(looked_up)
    assert calls == [], 'answered from the rail it already holds'
