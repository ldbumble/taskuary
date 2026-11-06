"""The route log: one row per brain CALLED (or refused) - which job, which brain, why - and never what it was asked or said."""
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
    assert (r['Job'], r['TaskId'], r['Pick'], r['Tier'], r['Rule'], r['Outcome']) == ('draft', t, f'connector:{a}', 'standard', 'work', 'ok')
    flat = ' '.join(str(v) for v in r.values())
    assert 'CONFIDENTIAL' not in flat and 'SECRET' not in flat and 'Erin' not in flat


def test_a_brain_built_and_never_called_writes_nothing_and_a_call_writes_one_row_with_its_time():
    """THE CHAT POLL'S JUNK (the owner's live install, 2026-11-06): triage's brain was built once a second and never called, and every
    build wrote an 'ok' row with no task, time or tokens. The row is written on the first call now - once, however many calls follow."""
    s, a, o, made = _two_connectors(False)
    with made:
        for _ in range(5): llm.build_llm(s, job='triage')
        assert s.brain_routes() == []
        b = llm.build_llm(s, job='triage')
        b('sys', 'one'); b('sys', 'two')
    rows = s.brain_routes()
    assert len(rows) == 1 and rows[0]['Ms'] is not None and rows[0]['Calls'] == 2 and rows[0]['Outcome'] == 'ok'


def test_a_step_up_still_names_the_row_it_stepped_up_from(monkeypatch):
    "The lazy row resolves for what reads it after the first call: the step up's EscalatedFrom and the first row's 'escalated'."
    s = MemoryStore()
    r = brainroute.Route('triage', 'light', 'cli:claude', '', 'light', [], 'auto', 'quick', 'easy', None)
    rid = brainroute.Lazy(s, r)
    assert s.brain_routes() == []
    first = rid()
    up = brainroute.log(s, r._replace(tier='strong'), escalated_from=rid); brainroute.outcome(s, rid, 'escalated')
    rows = {x['Id']: x for x in s.brain_routes()}
    assert rid() == first and rows[up]['EscalatedFrom'] == first and rows[first]['Outcome'] == 'escalated'


def test_the_chat_polls_deferred_read_builds_no_brain():
    "The doorway's once-a-second read is deferred (server._poll_quick): what it reads is the drain's to judge, with its own brain."
    from taskuary import channels, ingest
    s = MemoryStore()
    with mock.patch('taskuary.llm.build_llm') as build:
        with ingest.deferred(): channels.poll_channels(s, only=['slack'])
        build.assert_not_called()
        channels.poll_channels(s, only=['slack'])
        build.assert_called_once()


def test_the_migration_sweeps_rows_of_brains_never_called_once():
    "Each 'ok' row with no time and no tokens from before the sweep goes; a call's row, a refusal and the newer rows stay; never twice."
    import sqlite3, tempfile, os
    from taskuary.store import SQLiteStore
    d = tempfile.mkdtemp(); p = os.path.join(d, 'tq.db')
    s = SQLiteStore(p)
    old = '2026-11-01 09:00:00'
    for rec in ({'Job': 'triage', 'Outcome': 'ok'}, {'Job': 'triage', 'Outcome': 'ok', 'Ms': 120}, {'Job': 'triage', 'Outcome': 'refused:no AI'},
                {'Job': 'coding', 'Outcome': 'ok', 'TokensIn': 900}):
        s.add_brain_route({'At': old, **rec})
    s.cx.execute("DELETE FROM setting WHERE Name='brainroute_uncalled_swept'"); s.cx.commit(); s.cx.close()
    s = SQLiteStore(p)
    assert sorted((r['Outcome'], r['Ms'] or 0, r['TokensIn'] or 0) for r in s.brain_routes()) == [('ok', 0, 900), ('ok', 120, 0), ('refused:no AI', 0, 0)]
    assert s.get_setting('brainroute_uncalled_swept') == '1'
    s.add_brain_route({'At': old, 'Job': 'triage', 'Outcome': 'ok'}); s.cx.close()
    assert len(SQLiteStore(p).brain_routes()) == 4                                                      # once, never again


def test_a_failover_is_written_on_the_row_it_happened_to():
    s, a, o, made = _two_connectors(True)
    t = s.create_task({'Title': 'Vendor renewal', 'Status': 'open'}, 'owner')
    with made: assert llm.build_llm(s, job='triage', task_id=t)('sys', 'user') == 'openai answered'
    assert s.brain_routes()[0]['Outcome'] == f'fallback:connector:{o}'
    why = brainroute.why_for_task(s, t)
    assert why.startswith('Triage -> light on Anthropic') and 'answered instead, as its backup.' in why


def test_no_ai_is_written_as_refused_and_says_so():
    s = MemoryStore()
    assert llm.build_llm(s, job='summary') is None
    r = s.brain_routes()[0]
    assert (r['Pick'], r['Outcome']) == ('', 'refused:no AI') and 'No AI is connected' in r['Why']


def test_the_demo_logs_its_route_as_the_demo(monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    s = MemoryStore()
    b = llm.build_llm(s, job='draft')
    assert b is not None and s.brain_routes() == []
    b('sys', 'user')
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


def test_retention_keeps_the_row_90_days_and_its_reason_a_month():
    "The AI-use dashboard reads 90 days of what each call used (aiusage); the reason line is still dropped after a month."
    s = MemoryStore(); now = datetime(2026, 10, 25, 9, 0)
    for days in (100, 91, 40, 29, 1):
        s.add_brain_route({'At': (now - timedelta(days=days)).isoformat(sep=' ', timespec='seconds'), 'Job': 'triage', 'Why': f'{days}'})
    assert retention.tick(s, now)['routes_trimmed'] == 2
    rows = s.brain_routes()
    assert len(rows) == 3 and sorted(r['Why'] or '' for r in rows) == ['', '1', '29']


def test_why_for_a_task_with_no_ai_call_is_blank():
    s = MemoryStore()
    assert brainroute.why_for_task(s, s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')) == ''
