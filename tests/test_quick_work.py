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

def arrived(s, difficulty='quick', mail_kw=None, **verdict):
    "A general task as triage lands it, with _spawn caught: (task id, the names spawned)."
    said = lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w', 'difficulty': difficulty, **verdict})
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest.ingest_message(s, mail(**(mail_kw or {})), llm=said)
    return out['task_id'], [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]

def test_quick_work_is_a_job_on_the_general_agents_brain():
    s = home(); tid, _ = arrived(s)
    r, g = brainroute.choose(s, 'quick_work', tid), brainroute.choose(s, 'general', tid)
    assert 'quick_work' in brainroute.JOBS and (r.pick, r.model, r.gear) == (g.pick, g.model, 'main')
    assert r.difficulty == 'quick'                        # the depth reaches the router

def test_only_hard_work_takes_the_agent_by_difficulty():
    for d in ('quick', 'standard', None):                # the depth ruling: quick, standard and unrecorded all start quick
        s = home(); t, _ = arrived(s, d); assert quickwork.why_deep(s, t) == '' and quickwork.takes(s, t), d
    s = home(); t, _ = arrived(s, 'hard'); assert quickwork.why_deep(s, t) == 'hard'

def test_a_routine_stays_deep():
    s = home(); tid, _ = arrived(s); s.update_task(tid, {'Source': 'workflow'}, 't')
    assert quickwork.why_deep(s, tid) == 'routine'
    with mock.patch.object(quickwork, 'start') as quick, mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid, 'the routine definition')       # workflows.py and flow.py hand a routine run here
    quick.assert_not_called(); deep.assert_called_once()

def test_several_emails_owed_is_deep():
    s = home(); tid, _ = arrived(s)
    from taskuary import slots
    with mock.patch.object(slots, 'all_', return_value=[{'slot': 1}, {'slot': 2}]): assert quickwork.why_deep(s, tid) == 'emails'

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

def test_a_conversation_from_before_run_events_is_deep():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(general, 'history', return_value=[{'role': 'user', 'content': [{'type': 'text', 'text': 'look into it'}]}]):
        assert quickwork.why_deep(s, tid) == 'ran deep'
    assert quickwork.why_deep(s, tid) == ''

def test_only_ignored_events_are_not_only_quick():
    s = home(); tid, _ = arrived(s)
    ws.record(s, tid, 'o1', 'working', source='owner')                  # an owner's event is not a run
    assert not quickwork.only_quick(s, tid) and quickwork.why_deep(s, tid) == ''
    ws.record(s, tid, 'q1', 'working', source='quick'); assert quickwork.only_quick(s, tid)


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

def test_a_pending_question_is_never_done():
    a = quickwork.read({**ANSWER, 'question': 'Friday or Saturday?', 'done': True})
    assert a.question and not a.done
    assert quickwork.read({**ANSWER, 'done': True}).done

def test_the_quick_line_says_what_it_cannot_reach():
    assert all(w in quickwork.QUICK_LINE for w in ('no mail search', 'no connectors', 'no files', 'cannot verify', 'Never set done while a question is pending'))

def test_lookups_are_claimed_from_the_brain_that_was_built():
    s = home(); tid, _ = arrived(s)
    for looks, line in ((False, True), (True, False)):
        b = Brain(ANSWER); b.looks_up = looks                             # a CLI brain: no provider web, the flags decide
        with mock.patch.object(llm, 'build_llm', return_value=b): quickwork.ask(s, tid, ASK)
        assert (quickwork.NO_LOOKUP_LINE in b.calls[0][0]) is line

def test_only_claudes_quick_flags_reach_the_web():
    from taskuary import clis
    s = MemoryStore()
    for n in ('claude', 'codex'): s.upsert_agent(n, 'general', 'cli', json.dumps({'cmd': n, 'args': ['-p']}))
    assert clis.quick_web('claude') and not clis.quick_web('codex')
    assert llm.make_cli_llm(s, 'claude', research='web').looks_up and not llm.make_cli_llm(s, 'codex', research='web').looks_up
    assert not llm.make_cli_llm(s, 'claude').looks_up and not llm.make_cli_llm(s, 'claude', research=True).looks_up
    assert not llm._build_llm(s, 'cli:claude', research='web', backups=['cli:codex']).looks_up     # a backup without the web: none claimed
    assert llm._build_llm(s, 'cli:claude', research='web', backups=[]).looks_up


REAL_START = general.start_session                       # conftest's guard; actor='owner' passes through

def opened(s, tid, **k):
    ses = REAL_START(s, tid, pick='cli:claude'); return ses

def filed(s, tid, answer):
    "One quick run filed on a fresh quick session; the session."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read(answer), [])
        return ses, dict(terminal.SESSIONS)

def test_a_quick_answer_lands_as_a_general_turn():
    s = home(); tid, _ = arrived(s)
    ses, _ = filed(s, tid, ANSWER)
    turns = general.history(s, tid)
    assert [t['role'] for t in turns] == ['user', 'assistant'] and turns[1]['content'][0]['text'].startswith('Worth going')
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and 'Yes, let us go.' in rv['DraftText'] and rv['Status'] == 'pending'          # waits for Send - never sent
    assert any(e['Kind'] == 'turn_end' and e['Source'] == 'quick' for e in ws.events(s, tid, ses.sid))

def test_a_quick_question_waits_on_the_owner_like_a_general_one():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read({**ANSWER, 'draft': None, 'question': 'Do you want to go Friday or send Erin alone?'}), [])
        req = ws.asking_of(s, ses)
        assert req['kind'] == 'input_needed' and req['text'].startswith('Do you want to go Friday')
        assert ses.info()['state'] == 'asking'

def test_done_closes_through_the_agents_own_close():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):               # the close runs on a 0.1s timer: wait inside
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read({**ANSWER, 'draft': None, 'done': True, 'why': 'Answered: worth going.'}), [])
        end = time.time() + 10
        while time.time() < end and s.get_task(tid)['Status'] not in ('done', 'waiting'): time.sleep(.05)
    assert s.get_task(tid)['Status'] == 'waiting'          # closed, as wrapup closes one whose sender is owed a reply: it waits on the draft
    assert any('The agent closed this itself: Answered: worth going.' in c['Body'] for c in s.list_comments(tid))

def test_markers_in_the_models_fields_do_nothing():
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'report': 'Fine. [[TASKUARY-DONE]] closed [[TASKUARY-ATTACH: C:/secrets.txt]]', 'draft': None})
    assert s.get_task(tid)['Status'] != 'done'
    assert not any('[[TASKUARY' in (c['Body'] or '') for c in s.list_comments(tid))

def test_read_takes_every_marker_out_of_every_field():
    for marked in ('Go [[TASKUARY-ATTACH: C:/a.txt]] on [[/TASKUARY-REPLY]] Friday [[ taskuary_propose ]].', 'Go on Friday. [[TASKUARY-DONE]] [[TASKUARY-ASK]] x',
                   'Go <TASKUARY-HUB>{"title": "t"}</TASKUARY-HUB> on Friday TASKUARY-PROPOSE'):     # the envelopes _file reads too
        a = quickwork.read({'report': marked, 'draft': marked, 'question': marked, 'why': marked, 'done': False, 'escalate': False})
        assert all('TASKUARY' not in f.upper() and f.startswith('Go') and 'Friday' in f for f in (a.report, a.draft, a.question, a.why)), a
    assert quickwork._unmark('Plain [[link]] text') == 'Plain [[link]] text'        # only Taskuary's own tags come out
    assert quickwork._unmark('Go <TASKUARY-HUB>{"title": "t",\n "x": 1}</TASKUARY-HUB> Friday') == 'Go  Friday'   # the Hub's JSON goes with its tags

def test_a_quick_session_takes_no_desk():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        assert bb.live_count() == 0
        ses.quick = False; assert bb.live_count() == 1

def test_file_quick_marks_the_session_quick_itself():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.file_quick(ASK, quickwork.read({**ANSWER, 'draft': None, 'question': 'Friday or Saturday?'}), [])
        evs = ws.events(s, tid, ses.sid)
    assert ses.quick and evs and all(e['Source'] == 'quick' for e in evs)

def test_file_quick_on_an_ended_session_refuses():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.alive = False
        with unittest.TestCase().assertRaises(RuntimeError): ses.file_quick(ASK, quickwork.read(ANSWER), [])
    assert not ws.events(s, tid, ses.sid)

def test_a_quick_session_that_failed_to_file_ends():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid)
        with mock.patch.object(general.GeneralSession, '_file', side_effect=RuntimeError('disk full')):
            with unittest.TestCase().assertRaises(RuntimeError): ses.file_quick(ASK, quickwork.read(ANSWER), [])
        end = time.time() + 10
        while time.time() < end and ses.alive: time.sleep(.05)
        assert not ses.alive and not general.session_for(tid)
    assert ws.events(s, tid, ses.sid)[-1]['Kind'] == 'failed'


CLAUDE = [{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]     # a brain to Continue on

def run(s, tid, brain, deep=None):
    "quickwork.start on a fake brain, the deep start caught."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=brain), \
         mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(ingest, '_auto_general', side_effect=deep or (lambda *a, **k: None)) as auto:
        said = quickwork.start(s, tid)
        return said, auto, dict(terminal.SESSIONS)

def test_escalate_starts_the_general_agent_with_the_notes():
    s = home(); tid, _ = arrived(s)
    said, auto, live = run(s, tid, Brain({**ANSWER, 'escalate': True, 'why': 'it means booking travel across three sites', 'report': 'Two dates fit.'}))
    assert said == 'escalated' and not live                                   # no quick session was opened
    (store_, t, brief), k = auto.call_args
    assert t == tid and k == {'deep': True} and 'booking travel across three sites' in brief and 'Two dates fit.' in brief
    assert any(c['Body'] == quickwork.ESCALATED + 'it means booking travel across three sites' for c in s.list_comments(tid))

def test_a_failed_quick_call_escalates_and_frees_its_slot():
    s = home(); tid, _ = arrived(s)
    def boom(*a, **k): raise TimeoutError('timed out after 180s')
    boom.takes_web = False
    said, auto, _ = run(s, tid, boom)
    assert said == 'escalated' and auto.call_args.kwargs == {'deep': True}
    assert any('the quick answer could not be made (timed out after 180s)' in c['Body'] for c in s.list_comments(tid))
    assert quickwork.POOL._value == quickwork.QUICK_POOL                    # the slot came back

def test_unreadable_json_escalates():
    s = home(); tid, _ = arrived(s)
    garbled = lambda *a, **k: 'not json at all'; garbled.takes_web = False; garbled.takes_want = True
    assert run(s, tid, garbled)[0] == 'escalated'

def test_continue_on_a_quick_task_runs_the_general_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        ses = general.session_for(tid); assert ses.quick
        deep = mock.Mock(return_value='Booked nothing; here is the plan.')
        with mock.patch.object(llm, 'build_llm', return_value=deep) as build: ses.send_prompt('go on', pick='cli:claude')
        assert build.call_args.kwargs['job'] == 'general' and not ses.quick
        system, user = deep.call_args[0][:2]
        assert 'Worth going: Erin is presenting.' in user                     # the quick turn is in its conversation

def test_an_answer_to_a_quick_question_runs_the_general_agent():
    s = home(); tid, _ = arrived(s)
    q = {**ANSWER, 'draft': None, 'question': 'Friday or Saturday?'}
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(q)): quickwork.start(s, tid)
        with mock.patch.object(llm, 'build_llm', return_value=mock.Mock(return_value='Friday it is.')) as build:
            out = ws.answer_open(s, tid, 'Friday', 'owner')
        assert out['delivered'] and build.call_args.kwargs['job'] == 'general' and not general.session_for(tid).quick

def test_an_escalated_reply_task_is_told_its_job_once():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(ingest, 'reply_job', return_value='Work it out, then draft the reply to Erin.'):
        said, auto, _ = run(s, tid, Brain({**ANSWER, 'escalate': True, 'why': 'three sites to check'}))
        brief = auto.call_args[0][2]
        assert ingest.first_ask(s, tid, brief).count('Work it out, then draft the reply to Erin.') == 1   # what _start_general asks

def test_a_quick_session_that_cannot_start_says_so_and_never_raises():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)), \
         mock.patch.object(general, 'start_session', side_effect=RuntimeError('claude is not signed in')), mock.patch.object(bb, 'drain_later'):
        assert quickwork.start(s, tid) == 'failed'
    assert any("The assistant couldn't start" in c['Body'] and 'not signed in' in c['Body'] for c in s.list_comments(tid))
    assert s.get_dispatch(tid)                                                   # on the retry budget, as a failed deep start is

def test_fifty_arrivals_run_eight_at_a_time_and_take_no_desk():
    from taskuary import blackboard as bb
    s = home(); tids = [arrived(s, mail_kw={'external_id': f'q{i}', 'conversation_id': f'conv-{i}'})[0] for i in range(50)]
    assert len(set(tids)) == 50
    gate, now, most, lock = threading.Event(), [0], [0], threading.Lock()
    def slow(system, user, **k):
        with lock: now[0] += 1; most[0] = max(most[0], now[0])
        gate.wait(5)
        with lock: now[0] -= 1
        return json.dumps(ANSWER)
    slow.takes_web, slow.takes_want = False, True
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow),          mock.patch.object(general, 'start_session', side_effect=opened):
        ts = [threading.Thread(target=quickwork.start, args=(s, t)) for t in tids]
        for t in ts: t.start()
        time.sleep(.5); gate.set()
        for t in ts: t.join(10)
        assert most[0] == quickwork.QUICK_POOL == 8
        assert bb.live_count() == 0 and not s.queued_dispatches()             # no desk taken, nothing "Waiting its turn"


def test_a_quick_arrival_gets_one_call_and_no_agent_session():
    s = home(); tid, spawned = arrived(s)
    assert spawned == ['_auto_general']                                       # arrival is unchanged: auto_start_ok decided
    with mock.patch.object(quickwork, 'start', return_value='filed') as quick, mock.patch.object(ingest, '_start_general') as deep:
        ingest._auto_general(s, tid)
    quick.assert_called_once(); deep.assert_not_called()

def test_a_hard_arrival_starts_the_agent_as_today():
    s = home(); tid, _ = arrived(s, 'hard')
    with mock.patch.object(quickwork, 'start') as quick, mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()

def test_a_held_start_stays_held():
    s = home(general_auto_enabled='0'); tid, spawned = arrived(s)
    assert spawned == []                                                      # the owner's switch holds quick work too

def test_more_mail_on_a_live_quick_task_is_answered_quick_again():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        quickwork.start(s, tid)
        ingest._pass_general(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None})
        assert [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'] == ['quick_work', 'quick_work']

def test_more_mail_judged_hard_carries_on_as_the_general_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened),          mock.patch.object(general, 'provider_options', return_value=CLAUDE):                     # a brain for the general turn to run on
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        s.judge_task(tid, {'difficulty': 'hard'}, 'triage')
        with mock.patch.object(llm, 'build_llm', return_value=mock.Mock(return_value='On it.')) as build:
            ingest._pass_general(s, tid, {**mail(body='Erin Blake: please book it for three of us'), 'message_id': None})
        assert build.call_args.kwargs['job'] == 'general'

def test_more_mail_a_quick_call_cannot_answer_puts_the_ask_to_the_agent_on_the_same_session():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        ses = general.session_for(tid)
        with mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'escalate': True, 'why': 'it means booking for three'})), \
             mock.patch.object(general.GeneralSession, 'send_prompt') as deep:
            ingest._pass_general(s, tid, {**mail(body='Erin Blake: please book it for three of us'), 'message_id': None})
        assert general.session_for(tid) is ses                              # the quick session carries on as the agent's
        ask = deep.call_args[0][0]                                           # a turn put to it although its history is not empty
        assert 'please book it for three of us' in ask and 'it means booking for three' in ask

def test_two_quick_starts_on_one_task_make_one_call():
    s = home(); tid, _ = arrived(s)
    gate, calls = threading.Event(), []
    def slow(system, user, **k): calls.append(1); gate.wait(5); return json.dumps(ANSWER)
    slow.takes_web, slow.takes_want = False, True
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'start_session', side_effect=opened):
        first = threading.Thread(target=quickwork.start, args=(s, tid)); first.start()
        end = time.time() + 5
        while time.time() < end and not calls: time.sleep(.02)
        assert ingest.live_agent(s, tid) == 'general'                         # a line landing now is passed in, not a second start
        assert quickwork.start(s, tid) == 'running'
        gate.set(); first.join(10)
    assert len(calls) == 1 and tid not in general.OPENING and tid not in quickwork.RUNNING

def test_more_mail_after_a_quick_session_ended_is_answered_quick():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)):
        quickwork.start(s, tid); general.session_for(tid).alive = False
        new = {**mail(body='Erin Blake: also, can Gail Moreno come?', external_id='q2')}
        mid = s.list_messages(tid)[0]['MessageId']
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
             mock.patch.object(general, 'provider_options', return_value=CLAUDE):
            assert ingest._carry_on(s, tid, new, mid, {'intent': 'task', 'kind': 'general'}, 'triage')
        general.OPENING.discard(tid)
    fn, *args = spawn.call_args[0]
    assert fn is quickwork.start and args[:2] == [s, tid] and 'can Gail Moreno come' in args[2] and args[3] is False

def test_a_depth_that_cannot_be_read_starts_the_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(quickwork, 'takes', side_effect=RuntimeError('store gone')), mock.patch.object(quickwork, 'start') as quick, \
         mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()

def test_a_line_landing_mid_call_is_passed_in_however_long_the_call_takes():
    s = home(); tid, _ = arrived(s)
    gate, calls = threading.Event(), []
    def slow(system, user, **k): calls.append(user); gate.wait(5); return json.dumps(ANSWER)
    slow.takes_web, slow.takes_want = False, True
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'start_session', side_effect=opened), mock.patch.object(ingest, 'PASS_WAIT', .2):     # the call outlasts the wait
        first = threading.Thread(target=quickwork.start, args=(s, tid)); first.start()
        end = time.time() + 5
        while time.time() < end and not calls: time.sleep(.02)
        line = threading.Thread(target=ingest._pass_general, args=(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None}))
        line.start(); time.sleep(.6); gate.set()
        first.join(10); line.join(10)
    assert len(calls) == 2 and 'can Gail Moreno come' in calls[1]                 # answered quick again, behind the first
    assert not any('could not be passed in' in c['Body'] for c in s.list_comments(tid))

def test_a_queued_escalation_starts_the_agent_with_its_notes():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'escalate': True, 'why': 'it means booking for three', 'report': 'Two dates fit.'})), \
         mock.patch.object(bb, 'live_count', return_value=99):                   # every agent slot is taken
        assert quickwork.start(s, tid) == 'escalated'
    brief = s.get_dispatch(tid)['Brief']
    assert 'it means booking for three' in brief and 'Two dates fit.' in brief
    with mock.patch.object(bb, 'live_count', return_value=0), mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        bb.drain(s)
    assert deep.call_args[0][1:] == (tid, brief)                                 # the slot freed: the agent starts on the notes, not the bare Summary

def test_a_live_quick_session_does_not_hold_back_a_queued_escalation():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    s.enqueue_dispatch(tid, None, 'assistant', 'full', brief='notes')
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(bb, 'live_count', return_value=0), \
         mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ses = opened(s, tid); ses.quick = True                                  # the quick answer's session, still live
        bb.drain(s)
        assert deep.call_args[0][1:] == (tid, 'notes') and not s.get_dispatch(tid)
        s.enqueue_dispatch(tid, None, 'assistant', 'full', brief='more'); ses.quick = False      # a real agent working it: the row is cleared
        deep.reset_mock(); bb.drain(s)
        deep.assert_not_called(); assert not s.get_dispatch(tid)
