"""The route log: one row per brain built - which job, which brain, why - and never what it was asked or said."""
from datetime import datetime, timedelta
from unittest import mock

from taskuary import brainroute, demo, llm, retention
from taskuary.store import MemoryStore


def _keyed(s, typ):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1}, 'owner')
    return cid


def _two_connectors(primary_fails: bool):
    "Triage on one key, backed by a second - the first answering 'rate limit' when it is told to."
    s = MemoryStore()
    a, o = _keyed(s, 'anthropic'), _keyed(s, 'openai')
    s.set_setting('triage_ai', f'connector:{a}', 'owner'); s.set_setting('triage_backup_ai', f'connector:{o}', 'owner')
    def make(typ, conf, secret):
        def brain(system, user, **kw):
            if typ == 'anthropic' and primary_fails: raise RuntimeError('anthropic: rate limit reached, try again later')
            return f'{typ} answered'
        return brain
    return s, a, o, mock.patch.object(llm, 'make_llm', make)


def test_one_row_per_brain_built_and_no_words_of_the_call():
    s, a, o, made = _two_connectors(False)
    t = s.create_task({'Title': 'Quarterly numbers', 'Status': 'open'}, 'owner')
    with made:
        brain = llm.build_llm(s, job='draft', task_id=t)
        assert brain('SYSTEM-SECRET-WORDS', 'Dear Erin, the CONFIDENTIAL-FIGURE is 42') == 'anthropic answered'
    rows = s.brain_routes()
    assert len(rows) == 1
    r = rows[0]
    assert (r['Job'], r['TaskId'], r['Pick'], r['Tier'], r['Rule'], r['Outcome']) == ('draft', t, f'connector:{a}', 'fixed', 'fixed', 'ok')
    flat = ' '.join(str(v) for v in r.values())
    assert 'CONFIDENTIAL' not in flat and 'SECRET' not in flat and 'Erin' not in flat


def test_a_failover_is_written_on_the_row_it_happened_to():
    s, a, o, made = _two_connectors(True)
    t = s.create_task({'Title': 'Vendor renewal', 'Status': 'open'}, 'owner')
    with made: assert llm.build_llm(s, job='triage', task_id=t)('sys', 'user') == 'openai answered'
    assert s.brain_routes()[0]['Outcome'] == f'fallback:connector:{o}'
    why = brainroute.why_for_task(s, t)
    assert why.startswith('Triage on Anthropic') and 'answered instead, as its backup.' in why


def test_no_ai_is_written_as_refused_and_says_so():
    s = MemoryStore()
    assert llm.build_llm(s, job='summary') is None
    r = s.brain_routes()[0]
    assert (r['Pick'], r['Outcome']) == ('', 'refused:no AI') and 'No AI is connected' in r['Why']


def test_the_demo_logs_its_route_as_the_demo(monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    s = MemoryStore()
    assert llm.build_llm(s, job='draft') is not None
    assert s.brain_routes()[0]['Pick'] == 'demo'


def test_a_log_that_cannot_be_written_never_fails_the_call():
    s, a, o, made = _two_connectors(False)
    with made, mock.patch.object(s, 'add_brain_route', side_effect=RuntimeError('disk full')):
        assert llm.build_llm(s, job='rank')('s', 'u') == 'anthropic answered'


def test_route_rows_do_not_move_the_display_caches():
    "Every AI call writes one: counting it as a write would make the rail and the feed rebuild after every triage."
    s = MemoryStore(); before = s._writes
    brainroute.log(s, brainroute.choose(s, 'triage'))
    assert s._writes == before and len(s.brain_routes()) == 1


def test_retention_keeps_a_month():
    s = MemoryStore(); now = datetime(2026, 10, 25, 9, 0)
    for days in (40, 31, 29, 1):
        s.add_brain_route({'At': (now - timedelta(days=days)).isoformat(sep=' ', timespec='seconds'), 'Job': 'triage', 'Why': f'{days}'})
    assert retention.tick(s, now)['routes_trimmed'] == 2
    assert sorted(r['Why'] for r in s.brain_routes()) == ['1', '29']


def test_why_for_a_task_with_no_ai_call_is_blank():
    s = MemoryStore()
    assert brainroute.why_for_task(s, s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')) == ''
