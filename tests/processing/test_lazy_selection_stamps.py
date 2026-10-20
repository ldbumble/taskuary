"""A selection captured from the rail's cached pile stamps only what it rests on (2026-10-20): the selected row and
its batch. Stamping the whole rail there was the first of three whole-pile fingerprints every press paid. Nothing
another row's stamp fed is allowed to move: the revision Next echoes, the selected card, its batch members, and
every row the pile payload sends are byte-for-byte what a whole-pile present() gives."""
from datetime import datetime, timedelta

import pytest

from taskuary import funnel, funnel_presentation as fp, funnel_selection as fs, terminal
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)


@pytest.fixture
def db(tmp_path, monkeypatch):
    s = SQLiteStore(str(tmp_path / 'lazy.db'))
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kw: [])
    monkeypatch.setattr(funnel, 'announce', lambda store, *a, **k: [])
    tid = s.create_task({'Title': 'Quarter close', 'Status': 'open'}, 'fixture')
    for n in range(1, 9):
        s.add_message({'ExternalId': f'lazy:{n}', 'ConversationId': f'lazy-thread:{n}', 'TaskId': tid if n == 1 else None,
                       'Channel': 'email', 'SourceName': 'fixture@example.test', 'FromName': f'Person {n}',
                       'FromEmail': f'p{n}@example.test', 'Subject': f'Lazy {n}', 'BodyText': f'Body {n}',
                       'Status': 'routed' if n % 3 == 0 else 'filed', 'Category': 'info' if n % 3 else 'action',
                       'SentAt': (NOW - timedelta(minutes=n)).strftime('%Y-%m-%d %H:%M:%S')})
    s.add_comment(tid, 'owner', 'user', 'a note the card backs onto')
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=NOW.isoformat(), live_state=[])
    fp.forget_stamps(); funnel.invalidate()
    yield s
    fp.forget_stamps(); funnel.invalidate()
    s.cx.close()


def whole(store, cached, monkeypatch, **scope):
    """The capture as it was: the whole cached pile presented before selecting from it."""
    real = fs.detach
    with monkeypatch.context() as m:
        m.setattr(fs, 'detach', lambda v, memo=None: funnel.present(store, v) if v is cached else real(v, memo))
        return fs.capture_selection(store, pile=cached, now=NOW, **scope)


def scopes(cached):
    keys = [i['key'] for i in cached['items']]
    return [{}, *({'exclude': k} for k in keys), {'include_surfaced': True}]


def test_the_lazy_capture_is_the_whole_capture(db, monkeypatch):
    cached = funnel.pile(db, quiet=True, observed=[])
    assert len(cached['items']) >= 4
    picked = set()
    for scope in scopes(cached):
        fp.forget_stamps(); lazy = fs.capture_selection(db, pile=cached, now=NOW, **scope)
        fp.forget_stamps(); full = whole(db, cached, monkeypatch, **scope)
        assert (lazy.revision, lazy.member_keys, lazy.selected, lazy.pending) == (full.revision, full.member_keys, full.selected, full.pending)
        picked.add((lazy.selected or {}).get('kind'))
        # every row the selection rests on carries the whole present's stamp, nested cards included
        rows = {r['key']: r for r in full.pile['items']}
        for r in lazy.pile['items']:
            if r['key'] in lazy.member_keys: assert r == rows[r['key']]
            else: assert {k: v for k, v in r.items() if k != 'presentation_revision'} == {k: v for k, v in rows[r['key']].items() if k != 'presentation_revision'}
    assert 'fyis' in picked and len(picked) > 1, picked


def test_every_row_the_payload_sends_is_stamped_as_a_whole_present_stamps_it(db, monkeypatch):
    """The payload's final present() is what stamps the rows sent - the lazy capture must leave it nothing different to do."""
    cached = funnel.pile(db, quiet=True, observed=[])
    for scope in scopes(cached):
        fp.forget_stamps(); lazy = fs.capture_selection(db, pile=cached, now=NOW, **scope)
        fp.forget_stamps(); full = whole(db, cached, monkeypatch, **scope)
        fp.forget_stamps(); sent = funnel.present(db, {**lazy.pile, 'display_revision': None})
        fp.forget_stamps(); was = funnel.present(db, full.pile)
        assert list(sent) == list(was) and sent == was
        fp.forget_stamps(); assert sent['items'] == fp.present(db, cached)['items']
