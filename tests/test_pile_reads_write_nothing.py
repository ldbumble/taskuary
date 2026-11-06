"""Building the rail writes nothing, so the pile's cache holds until something else does (perf 2026-11-06).

The cache (funnel.pile) is served only while the store's dirty-row top has not moved since the build. One write made BY the
build - a follow-up line already done, re-marked done on every card - moved it each time: no read was ever served from the
cache, and the walk's peek built the rail a second time in the same request. A home with many rows of every kind pins that
two builds agree byte for byte and that the second read of an unchanged store is the cached one."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import funnel, terminal
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
PEOPLE = [('Erin Blake', 'erin'), ('Gail Moreno', 'gail'), ('Paula Vance', 'paula'), ('Ray Colton', 'ray'), ('Marcus Reed', 'marcus')]

@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    for k in range(60):
        name, user = PEOPLE[k % len(PEOPLE)]
        t = s.create_task({'Title': f'Budget line {k}', 'Status': ('open', 'waiting', 'done')[k % 3]}, 'owner')
        for j in range(3):
            s.add_message({'ConversationId': f'c{k}', 'Channel': 'email', 'Subject': f'Budget line {k}', 'FromEmail': f'{user}@northwind.example',
                           'FromName': name, 'SentAt': ago(days=k % 9, hours=j), 'BodyText': f'note {j}', 'Status': 'filed', 'TaskId': t})
    for k in range(40):                                     # loose mail: FYI and report rows
        s.add_message({'ConversationId': f'f{k}', 'Channel': 'email', 'Subject': f'Weekly digest {k}', 'FromEmail': 'news@vendor.example',
                       'FromName': 'Payworth', 'SentAt': ago(days=k % 6, hours=k % 5), 'BodyText': 'numbers', 'Status': 'filed'})
    for k in range(8):                                      # follow-up lines; half of them answered since the ask
        mid = s.add_message({'ConversationId': f'q{k}', 'Channel': 'email', 'Subject': f'Schema {k}', 'FromEmail': 'ray@northwind.example',
                             'FromName': 'Ray Colton', 'SentAt': ago(days=8), 'BodyText': 'q', 'Status': 'filed'})
        s.upsert_idea({'key': f'followup:q{k}', 'kind': 'followup', 'text': f'No answer from Ray on "Schema {k}" - follow up?', 'sig': f's{k}',
                       'action': {'type': 'followup', 'mid': mid, 'who_email': 'ray@northwind.example', 'asked_at': ago(days=7)}}, ago(hours=1))
        if k % 2: s.add_message({'ConversationId': f'q{k}', 'Channel': 'email', 'Subject': f'Re: Schema {k}', 'FromEmail': 'ray@northwind.example',
                                 'FromName': 'Ray Colton', 'SentAt': ago(days=1), 'BodyText': 'done', 'Status': 'filed'})
    s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.close()

def same(p): return json.dumps({k: v for k, v in p.items() if k not in ('rev', 'live_seq')}, sort_keys=True, default=str)

def test_a_build_writes_nothing_and_the_next_read_is_the_cached_one(s, monkeypatch):
    funnel.pile(s, force=True)                              # the first build may settle what it finds (an answered line is marked done)
    first = funnel.pile(s, force=True); top = s.rail_top(); again = funnel.pile(s, force=True)
    assert s.rail_top() == top, 'a rebuild of an unchanged store wrote'
    assert same(again) == same(first) and len(again['items']) > 20
    builds = []; monkeypatch.setattr(funnel, 'build', lambda *a, **k: builds.append(1) or {})
    assert funnel.pile(s) is again and not builds, 'nothing moved: the read is served from the cache'
