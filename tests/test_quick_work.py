"""Quick general work (spec 2026-10-29): a general task triage judged quick is answered in one call, not an agent session."""
import json, threading, time, unittest
from unittest import mock
from taskuary import brainroute, browserview, general, ingest, llm, origin, quickwork, senders, terminal, workerstate as ws
from taskuary.store import MemoryStore

ASK = 'Erin Blake asks: does it make sense for us to go to the Northwind partner day on Friday?'

def home(**settings):
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s

def mail(**kw):
    return {'external_id': 'q1', 'channel': 'email', 'subject': 'partner day', 'body': ASK, 'from_email': 'erin@northwind.example',
            'from_name': 'Erin Blake', 'conversation_id': 'conv-partner', 'sent_at': '2026-10-29 09:00', 'source_name': 'alex@northwind.example', **kw}

def arrived(s, difficulty='quick', **verdict):
    "A general task as triage lands it, with _spawn caught: (task id, the names spawned)."
    said = lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w', 'difficulty': difficulty, **verdict})
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True),          mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest.ingest_message(s, mail(), llm=said)
    return out['task_id'], [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]

def test_quick_work_is_a_job_on_the_general_agents_brain():
    s = home(); tid, _ = arrived(s)
    r, g = brainroute.choose(s, 'quick_work', tid), brainroute.choose(s, 'general', tid)
    assert 'quick_work' in brainroute.JOBS and (r.pick, r.model, r.gear) == (g.pick, g.model, 'main')
    assert r.difficulty == 'quick'                        # the depth reaches the router

def test_triage_difficulty_decides_the_depth():
    s = home(); q, _ = arrived(s)
    assert quickwork.why_deep(s, q) == '' and quickwork.takes(s, q)
    for d in ('standard', 'hard', None):                 # an unjudged task reads as deep
        s2 = home(); t2, _ = arrived(s2, d); assert quickwork.why_deep(s2, t2) == 'difficulty'

def test_a_browser_task_is_always_deep():
    s = home(); tid, _ = arrived(s); s.tag_task(tid, browserview.WANTS, actor='triage')
    assert quickwork.why_deep(s, tid) == 'browser'

def test_a_strangers_quick_task_takes_the_deep_path():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(origin, 'of_task', return_value=('stranger', 'a first message')):
        assert quickwork.why_deep(s, tid) == 'stranger'

def test_a_task_that_ran_deep_stays_deep():
    s = home(); tid, _ = arrived(s)
    ws.record(s, tid, 'deep1', 'working', source='api')
    assert quickwork.why_deep(s, tid) == 'ran deep' and not quickwork.only_quick(s, tid)
