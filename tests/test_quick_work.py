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


class Brain:
    "A fake brain: answers `said`, records each call; takes_web/takes_want as an API connector says them."
    def __init__(self, said, web=False, want=True): self.said, self.calls, self.takes_web, self.takes_want = said, [], web, want
    def __call__(self, system, user, **k): self.calls.append((system, user, k)); return json.dumps(self.said)

ANSWER = {'report': 'Worth going: Erin is presenting.', 'draft': 'Yes, let us go.', 'question': None, 'done': False, 'escalate': False, 'why': ''}

def test_the_prompt_carries_what_the_general_agent_reads_plus_the_mail_history():
    s = home(); tid, _ = arrived(s)
    with mock.patch('taskuary.context.for_prompt', return_value='TODAY 14:00 partner day prep'), \
         mock.patch.object(general, 'earlier_mail', return_value='Erin Blake wrote on Monday about the agenda'):
        system, user = quickwork.prompt(s, tid, ASK, lookups=True)
    assert 'RULES (AGENT.md - every worker)' in system and quickwork.QUICK_LINE in system
    assert 'what counts as a task' not in system.lower()   # triage's sorting rules stay with triage; _prompt gives workers the SOUL/JOB background (brief.TRIAGE_ONLY)
    assert 'TODAY 14:00 partner day prep' in user and 'Erin Blake wrote on Monday' in user and ASK in user

def test_an_api_brain_with_web_searches_and_one_without_gets_the_schema():
    s = home(); tid, _ = arrived(s)
    web = Brain(ANSWER, web=True)
    with mock.patch.object(llm, 'build_llm', return_value=web) as build: out = quickwork.ask(s, tid, ASK)
    assert out.draft == 'Yes, let us go.' and web.calls[0][2].get('web') is True and 'want' not in web.calls[0][2]
    assert build.call_args.kwargs['job'] == 'quick_work' and build.call_args.kwargs['research'] == 'web'

def test_an_api_brain_without_web_gets_the_schema_and_the_escalate_line():
    s = home(); tid, _ = arrived(s)
    plain = Brain(ANSWER, web=False)
    with mock.patch.object(llm, 'build_llm', return_value=plain): quickwork.ask(s, tid, ASK)
    system, _, k = plain.calls[0]
    assert k['want'] == quickwork.QUICK_WANT and 'web' not in k and quickwork.NO_LOOKUP_LINE in system

def test_a_cli_quick_call_may_search_the_web_and_nothing_else():
    from taskuary import clis
    assert clis.quick_read_args('claude', ['-p', '--dangerously-skip-permissions']) == \
        ['-p', '--tools', 'WebFetch,WebSearch', '--allowedTools', 'WebFetch,WebSearch', '--disallowedTools', 'mcp__*']
    assert clis.quick_read_args('codex', ['exec', '--full-auto']) == clis.readonly_args('codex', ['exec', '--full-auto'])

def test_unreadable_answers_read_as_none():
    assert quickwork.read(None) is None and quickwork.read({'draft': 'x'}) is None
    assert quickwork.read({'escalate': True, 'why': 'books travel across three sites'}).escalate
