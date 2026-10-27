"""Stamp only what changed (design D, 2026-09-17): a card's presentation_revision is reused while nothing
has been written anywhere and the card's own fields are unchanged; every write - to any backing table, from
any connection - starts a fresh book, and a reused stamp is byte-for-byte the recomputed one."""
import sqlite3
from datetime import datetime

import pytest

from taskuary import funnel, funnel_presentation as fp, terminal
from taskuary.store import SQLiteStore


@pytest.fixture
def db(tmp_path, monkeypatch):
    s = SQLiteStore(str(tmp_path / 'stamps.db'))
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(funnel, 'announce', lambda store: [])
    fp.forget_stamps(); funnel.invalidate()
    tid = s.create_task({'Title': 'Stamped', 'Status': 'open'}, 'fixture')
    mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed', 'Subject': 'Stamped source',
                         'BodyText': 'First body', 'SentAt': datetime.now().isoformat(sep=' ')})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'A draft'})
    yield s, tid, mid, rid
    fp.forget_stamps(); funnel.invalidate()
    s.close()


def pile(s): return funnel.build(s, keep_surfaced=True)


def fetched(monkeypatch):
    """How many cards had their backing fetched by the presents that follow."""
    calls, real = [], fp._backings
    def spy(cur, items):
        calls.append(len(items)); return real(cur, items)
    monkeypatch.setattr(fp, '_backings', spy)
    return calls


def cold(s, payload):
    fp.forget_stamps()
    return fp.present(s, payload)


def stamps(out): return [(i['key'], i['presentation_revision']) for i in out['items']]


def test_a_second_present_with_nothing_written_fetches_no_backing_and_stamps_the_same(db, monkeypatch):
    s, tid, mid, rid = db
    p = pile(s)
    calls = fetched(monkeypatch)
    first = fp.present(s, p)
    again = fp.present(s, p)
    assert calls == [len(p['items']), 0], 'the second read reused every stamp'
    assert stamps(again) == stamps(first) and again['display_revision'] == first['display_revision']


@pytest.mark.parametrize('write', ['body', 'comment', 'run', 'waitroom', 'connector', 'reply_channels', 'funnel_state', 'attachment'])
def test_a_write_to_any_backing_table_recomputes_and_matches_a_cold_stamp(db, monkeypatch, write):
    """Every table the backing reads leaves a dirty row (processing_rail.DIRTY_ROWS + PROCESSING_DIRTY_SETTINGS),
    so a write to it opens a new book. The recomputed stamp is the one a cold present makes."""
    s, tid, mid, rid = db
    p = pile(s)
    before = fp.present(s, p)
    if write == 'body': s.update_message_body(mid, 'A body that grew')
    elif write == 'comment': s.add_comment(tid, 'coding', 'agent', 'Working on it.')
    elif write == 'run': s.cx.execute('INSERT INTO run(TaskId, AgentName, Status, StartedAt) VALUES (?,?,?,?)', (tid, 'codex', 'running', '2026-09-17 12:00:00')); s.cx.commit()
    elif write == 'waitroom': s.cx.execute('INSERT INTO waitroom(TaskId, Note, CreatedBy, CreatedAt) VALUES (?,?,?,?)', (tid, 'parked', 'codex', '2026-09-17 12:00:00')); s.cx.commit()
    elif write == 'connector':
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': '{"reply_comments": true}'}, 'test')
    elif write == 'reply_channels': s.set_setting('reply_channels', 'email', 'test')
    elif write == 'funnel_state': s.set_funnel_state(f'review:{rid}', 'surfaced', 'owner')
    elif write == 'attachment': s.cx.execute('INSERT INTO attachment(MessageId, Name) VALUES (?,?)', (mid, 'a.pdf')); s.cx.commit()
    p2 = pile(s)
    calls = fetched(monkeypatch)
    warm = fp.present(s, p2)
    assert calls == [len(p2['items'])], 'the write opened a new book: every card fetched again'
    assert stamps(warm) == stamps(cold(s, p2))
    assert stamps(warm) != stamps(before) or write in ('run',), 'the card whose backing changed changed its stamp'


def test_a_write_from_another_connection_is_seen(db, monkeypatch, tmp_path):
    """Another process's write reaches the dirty rows through the database triggers, not this connection."""
    s, tid, mid, rid = db
    p = pile(s)
    before = fp.present(s, p)
    other = sqlite3.connect(str(tmp_path / 'stamps.db'))
    other.execute('UPDATE message SET BodyText=? WHERE MessageId=?', ('Changed elsewhere', mid)); other.commit(); other.close()
    calls = fetched(monkeypatch)
    after = fp.present(s, p)
    assert calls == [len(p['items'])]
    assert stamps(after) != stamps(before) and stamps(after) == stamps(cold(s, p))


def test_a_card_whose_own_fields_changed_is_stamped_fresh(db, monkeypatch):
    s, tid, mid, rid = db
    p = pile(s)
    fp.present(s, p)
    changed = {**p, 'items': [{**p['items'][0], 'title': 'Renamed on the card'}, *p['items'][1:]]}
    calls = fetched(monkeypatch)
    out = fp.present(s, changed)
    assert calls == [1], 'only the changed card was fetched'
    assert out['items'][0]['presentation_revision'] == cold(s, changed)['items'][0]['presentation_revision']


def test_a_batch_card_is_hashed_fresh_over_reused_children(db, monkeypatch):
    s, tid, mid, rid = db
    p = pile(s)
    fp.present(s, p)
    batch = {'items': [], 'current': {'key': 'fyis:x', 'kind': 'fyis', 'lane': 'fyi', 'title': '1 fyi', 'items': [dict(p['items'][0])]}}
    calls = fetched(monkeypatch)
    out = fp.present(s, batch)
    assert calls == [1], 'the parent is fetched; its child was already stamped'
    assert out['current']['presentation_revision'] == cold(s, batch)['current']['presentation_revision']


def test_a_store_without_the_rail_table_keeps_no_book(monkeypatch):
    class Bare:
        def _processing_read(self):
            import contextlib
            @contextlib.contextmanager
            def cm():
                cx = sqlite3.connect(':memory:'); cx.row_factory = sqlite3.Row
                for t in ('message', 'task', 'review', 'attachment', 'comment', 'run', 'waitroom', 'idea', 'setting', 'connector', 'funnel_state'):
                    cx.execute(f'CREATE TABLE {t} (MessageId, TaskId, ReviewId, IdeaId, Name, Key, Type, ConversationId, ConfigJson, Active, ConnectorId)')
                yield cx.cursor()
            return cm()
    item = {'key': 'msg:1', 'kind': 'message', 'lane': 'fyi', 'mid': 1}
    calls = fetched(monkeypatch)
    a = fp.present(Bare(), {'items': [item]}); b = fp.present(Bare(), {'items': [item]})
    assert calls == [1, 1] and stamps(a) == stamps(b)


def test_random_writes_carry_only_untouched_stamps_and_every_stamp_is_the_cold_one(tmp_path, monkeypatch):
    """A write keeps every stamp whose backing it cannot have reached (2026-10-20) - so after any mix of writes, through
    this connection or another, every card's stamp is still exactly the one a cold present makes. Rows that JOIN a key a
    card reads by (a message arriving on its task or its conversation, a review on its message) are the hard case."""
    import random
    from datetime import timedelta
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(funnel, 'announce', lambda store: [])
    s = SQLiteStore(str(tmp_path / 'carry.db'))
    fp.forget_stamps(); funnel.invalidate()
    now = datetime.now().replace(microsecond=0)
    tids = [s.create_task({'Title': f'Task {n}', 'Status': 'open'}, 'fixture') for n in range(4)]

    def mail(n, tid=None, conv=None):
        return s.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed' if tid is None else 'routed', 'Subject': f'Mail {n}',
                              'ConversationId': conv or f'conv:{n}', 'BodyText': f'Body {n}', 'FromEmail': f'p{n}@example.test',
                              'SentAt': (now - timedelta(minutes=n)).isoformat(sep=' ')})
    mids = [mail(n, tids[n % 4] if n % 3 else None, f'conv:{n % 5}') for n in range(12)]
    rng, carried, n, kinds = random.Random(20261020), 0, 100, set()
    other = sqlite3.connect(str(tmp_path / 'carry.db'))
    real = fp._backings
    for step in range(60):
        p = funnel.build(s, keep_surfaced=True)
        assert p['items']
        calls = []
        monkeypatch.setattr(fp, '_backings', lambda cur, items: calls.append(len(items)) or real(cur, items))
        warm = fp.present(s, p)                          # the book as the app keeps it, carried across the last write
        monkeypatch.setattr(fp, '_backings', real)
        book = fp._STAMPS[s]; saved = (book['top'], dict(book['by']), dict(book['deps']))
        assert stamps(warm) == stamps(cold(s, p)), f'step {step} after {kinds}: a carried stamp is not the cold one'
        fp._STAMPS[s] = {'top': saved[0], 'by': saved[1], 'deps': saved[2]}      # cold() emptied it: put the app's back
        carried += bool(calls and calls[0] < len(p['items']))
        n += 1; mid, tid = rng.choice(mids), rng.choice(tids)
        w = rng.choice(['body', 'join_task', 'join_conv', 'move', 'comment', 'review', 'state', 'attachment', 'title', 'delete', 'other', 'nothing'])
        kinds.add(w)
        if w == 'body': s.update_message_body(mid, f'Edited {n}')
        elif w == 'join_task': mids.append(mail(n, tid))
        elif w == 'join_conv': mids.append(mail(n, None, f'conv:{rng.randrange(5)}'))
        elif w == 'move': s.cx.execute('UPDATE message SET TaskId=? WHERE MessageId=?', (rng.choice([tid, None]), mid)); s.cx.commit()
        elif w == 'comment': s.add_comment(tid, 'owner', 'user', f'note {n}')
        elif w == 'review': s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': f'draft {n}'})
        elif w == 'state': s.set_funnel_state(rng.choice(p['items'])['key'], 'surfaced', 'owner')
        elif w == 'attachment': s.cx.execute('INSERT INTO attachment(MessageId, Name) VALUES (?,?)', (mid, f'{n}.pdf')); s.cx.commit()
        elif w == 'title': s.update_task(tid, {'Title': f'Retitled {n}'}, 'owner')
        elif w == 'delete' and len(mids) > 6: mids.remove(mid); s.cx.execute('DELETE FROM message WHERE MessageId=?', (mid,)); s.cx.commit()
        elif w == 'other': other.execute('UPDATE message SET BodyText=? WHERE MessageId=?', (f'elsewhere {n}', mid)); other.commit()
    other.close(); s.close(); fp.forget_stamps()
    assert carried, 'some write left some stamps standing'
