"""ONE FYI ROW PER EMAIL THREAD (trust audit P2, 2026-10-28): three FYI mails on one thread with no task were three rows on the rail. They
are one row - the newest mail speaking, "+2" for the rest - and a press on it settles every mail it speaks for. A chat's lines are combined
by triage already, and a mail on a task is the task's row. Invented Northwind people only."""
from unittest import mock
from taskuary import funnel, processing_unread


def fyi(key, cid, when, channel='email', **kw):
    return {'key': key, 'kind': 'fyi', 'lane': 'fyi', 'cid': cid, 'when': when, 'channel': channel, 'unread': True, 'aliases': [], **kw}


def test_fyi_mails_on_one_thread_are_one_row_the_newest_speaking():
    cards = [fyi('processing:a', 'email:newsletter', '2026-10-28 07:00:00', unread=False),
             fyi('processing:b', 'email:newsletter', '2026-10-28 09:00:00'),
             fyi('processing:c', 'email:newsletter', '2026-10-28 08:00:00'),
             fyi('processing:d', 'email:other', '2026-10-28 08:30:00'),
             fyi('processing:e', 'teams:standup', '2026-10-28 08:00:00', channel='teams'),
             fyi('processing:f', 'teams:standup', '2026-10-28 09:00:00', channel='teams'),
             fyi('processing:g', 'email:newsletter', '2026-10-28 09:30:00', tid=7, kind='task', lane='asked')]
    got = {c['key']: c for c in processing_unread.fold_fyi_threads(cards)}
    assert set(got) == {'processing:b', 'processing:d', 'processing:e', 'processing:f', 'processing:g'}
    head = got['processing:b']
    assert (head['thread_n'], sorted(head['thread']), head['unread']) == (2, ['processing:a', 'processing:c'], True)
    assert 'thread' not in got['processing:d'] and 'thread' not in got['processing:e'], 'a lone mail and a chat stay as they were'


def test_a_press_on_the_row_settles_every_mail_it_speaks_for():
    from taskuary.store import MemoryStore
    s, said = MemoryStore(), []
    head = fyi('processing:b', 'email:newsletter', '2026-10-28 09:00:00', thread=['processing:a', 'processing:c'])
    real = funnel.settle
    def spy(store, key, verb, *a, **kw):
        said.append(key)
        return real(store, key, verb, *a, **kw) if key == 'processing:b' else {}
    with mock.patch.dict(funnel._CACHE, {'store': s, 'pile': {'items': [head]}, 'full': None}), \
         mock.patch.object(funnel, 'settle', side_effect=spy), mock.patch.object(funnel, 'invalidate'), \
         mock.patch.object(s, 'set_funnel_state'):
        assert funnel.thread_of(s, 'processing:b') == ['processing:a', 'processing:c']
        funnel.settle(s, 'processing:b', 'surfaced', read=True)
    assert said == ['processing:b', 'processing:a', 'processing:c']
