"""Quick general work (spec 2026-10-29; with tools since 2026-11-13): a general task triage judged quick or normal is the warm agent's - a
turn of the task's own session with every tool an agent turn has, at a fraction of a desk - and only complex work starts the full agent."""
import json, threading, time, unittest
from unittest import mock
from taskuary import brainroute, browserview, general, ingest, llm, origin, quickwork, selfclose, senders, terminal, workerstate as ws
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
    for d in ('quick', 'standard', None):                # the depth ruling: quick, standard and unrecorded all take the warm agent
        s = home(); t, _ = arrived(s, d); assert quickwork.why_deep(s, t) == '' and quickwork.takes(s, t), d
    s = home(); t, _ = arrived(s, 'hard'); assert quickwork.why_deep(s, t) == 'hard'

def test_a_routine_stays_deep():
    s = home(); tid, _ = arrived(s); s.update_task(tid, {'Source': 'workflow'}, 't')
    assert quickwork.why_deep(s, tid) == 'routine'
    with mock.patch.object(quickwork, 'start') as quick, mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid, 'the routine definition')       # workflows.py and flow.py hand a routine run here
    quick.assert_not_called(); deep.assert_called_once()

def test_a_coding_task_is_never_the_warm_agents():
    "A coding task on an AI card runs on this module's session (general.ON_CARD), but it is a coding session's work: unchanged."
    s = home(); tid, _ = arrived(s); s.update_task(tid, {'Kind': 'coding'}, 't')
    with mock.patch.object(general, 'ON_CARD', {tid}): assert quickwork.why_deep(s, tid) == 'kind'

def test_several_emails_owed_is_deep():
    s = home(); tid, _ = arrived(s)
    from taskuary import slots
    with mock.patch.object(slots, 'all_', return_value=[{'slot': 1}, {'slot': 2}]): assert quickwork.why_deep(s, tid) == 'emails'

def test_a_browser_task_starts_after_its_verdict_is_on_file():
    "Spawned before the route row, the start read no needs_browser and took the one call; its session then opened a Chrome beside it."
    s = home(); seen = []
    said = lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w', 'difficulty': 'quick', 'needs_browser': True})
    def spawn(fn, *a):
        if fn.__name__ == '_auto_general': seen.append(quickwork.why_deep(a[0], a[1]))
    with mock.patch('taskuary.ingest._spawn', side_effect=spawn), mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        ingest.ingest_message(s, mail(), llm=said)
    assert seen == ['browser']

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


def said(a: dict) -> str:
    "What an agent's turn writes for an answer: its words, the reply it drafts, its one question, its close - and the hand-on."
    return '\n\n'.join(x for x in (a.get('report'), a.get('draft') and f"[[TASKUARY-REPLY]]{a['draft']}[[/TASKUARY-REPLY]]",
                                   a.get('question') and f"{selfclose.ASK_MARKER} {a['question']}", a.get('done') and f"{selfclose.MARKER} {a.get('why')}",
                                   a.get('escalate') and f"{quickwork.HAND_ON} {a.get('why')}") if x)

class Brain:
    "A fake brain: answers `answer` as an agent's turn writes it, records each call."
    def __init__(self, answer): self.answer, self.calls = answer, []
    def __call__(self, system, user, **k): self.calls.append((system, user, k)); return said(self.answer) if isinstance(self.answer, dict) else self.answer

ANSWER = {'report': 'Worth going: Erin is presenting.', 'draft': 'Yes, let us go.', 'question': None, 'done': False, 'escalate': False, 'why': ''}
CLAUDE = [{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]     # a brain for the turn to run on
REAL_START = general.start_session                       # conftest's guard; actor='owner' passes through

def opened(s, tid, quick=False, **k):
    ses = REAL_START(s, tid, pick='cli:claude', quick=quick); return ses

def run(s, tid, brain, deep=None):
    "quickwork.start on a fake brain, the deep start caught."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=brain), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(ingest, '_auto_general', side_effect=deep or (lambda *a, **k: None)) as auto:
        out = quickwork.start(s, tid)
        return out, auto, dict(terminal.SESSIONS)

def filed(s, tid, answer, **kw):
    "One warm turn on a fresh quick session; the session."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=Brain(answer)), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        ses = opened(s, tid, quick=True)
        quickwork.again(s, tid, ses, kw.pop('ask', ASK), **kw)
        return ses, dict(terminal.SESSIONS)

# THE WARM AGENT HAS THE AGENT'S TOOLS (the owner, 2026-11-13: "they should have tools"): 16 of 20 one-shot calls handed on because they
# could not open the screenshot, the attachment, the code or the owner's systems. The warm turn is built as the full agent's turn is - hands,
# Taskuary's tools for this task, its live conversation, the origin gate - and only its job, quick_work, says it is the quick lane
def test_the_warm_turn_is_built_with_the_general_agents_tools():
    s = home(); tid, _ = arrived(s); deep_tid, _ = arrived(s, 'hard', mail_kw={'external_id': 'q9', 'conversation_id': 'conv-9'})
    with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
             mock.patch.object(general, 'start_session', side_effect=opened):
            assert quickwork.start(s, tid) == 'filed'
            opened(s, deep_tid).send_prompt('Plan the partner day.', brief=True)
    quick, deep = (c.kwargs for c in build.call_args_list if c.kwargs.get('job') in ('quick_work', 'general'))
    assert quick['job'] == 'quick_work' and deep['job'] == 'general'
    assert quick.get('cli_tools') is True and not quick.get('research') and quick['task_id'] == tid and quick['keep'] == f'general:{tid}'
    same = lambda k: {x: v for x, v in k.items() if x not in ('job', 'task_id', 'keep', 'trace', 'cancel', 'fallback_user', 'extra_env', 'hold_sid')}
    assert same(quick) == same(deep), (same(quick), same(deep))           # the full agent's own build, tools and all - never the one-shot's flags

def test_a_standard_task_takes_the_warm_road():
    "The owner, 2026-11-13: normal work is the warm agent's too - only complex work starts the full agent."
    s = home(); tid, _ = arrived(s, 'standard')
    with mock.patch.object(quickwork, 'start', return_value='filed') as quick, mock.patch.object(ingest, '_start_general') as deep:
        ingest._auto_general(s, tid)
    quick.assert_called_once(); deep.assert_not_called()
    out, auto, _ = run(s, tid, Brain(ANSWER))
    assert out == 'filed' and not auto.called and quickwork.only_quick(s, tid)

def test_a_line_he_typed_while_it_was_held_rides_the_warm_turn():
    "He typed on a held task, then trusted its sender: the one tool-less call could not take his line, so it went to the agent. The warm turn does."
    s = home(); tid, _ = arrived(s)
    general.wait_line(s, tid, 'Tell her yes, send the form.')
    assert quickwork.takes(s, tid)
    b = Brain(ANSWER); run(s, tid, b)
    assert 'Tell her yes, send the form.' in b.calls[0][1] and not general.waiting_lines(s, tid)

def test_a_quick_answer_lands_as_a_general_turn():
    s = home(); tid, _ = arrived(s)
    ses, _ = filed(s, tid, ANSWER)
    turns = general.history(s, tid)
    assert [t['role'] for t in turns] == ['user', 'assistant'] and turns[1]['content'][0]['text'].startswith('Worth going')
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and 'Yes, let us go.' in rv['DraftText'] and rv['Status'] == 'pending'          # waits for Send - never sent
    assert any(e['Kind'] == 'turn_end' and e['Source'] == 'quick' for e in ws.events(s, tid, ses.sid))

LETTER = "Hi Erin,\n\nYes - let us go on Friday.\n\nBest,\nAlex Doyle"
def test_a_report_that_writes_the_draft_out_keeps_only_its_own_words():
    "The overnight run, 2026-11-03: the report carried the whole letter, ruled off, over the same letter in Close out."
    s = home(); tid, _ = arrived(s)
    words = "I drafted your yes to Erin.\n\n" + LETTER.replace('\n\nYes', '\n\n---\n\nYes').replace('\n\nBest', '\n\n---\n\nBest') + "\n\nAdd the time if you know it."
    filed(s, tid, {**ANSWER, 'report': words, 'draft': LETTER})
    shown = general.history(s, tid)[1]['content'][0]['text']
    assert shown == 'I drafted your yes to Erin.\n\nAdd the time if you know it.'
    assert 'Yes - let us go on Friday.' in s.pending_review(tid, 'draft_reply')['DraftText']       # the letter is Close out's, whole

def test_without_draft_leaves_an_answer_that_never_quotes_it():
    assert selfclose.without_draft('Worth going.\n\n---\n\nSee you.', 'Yes, let us go.') == 'Worth going.\n\n---\n\nSee you.'

def test_a_turn_stored_with_its_letter_reads_without_it():
    "A turn filed before _file took the letter out still had it, in the owner's voice under Taskuary: it reads back without it everywhere."
    s = home(); tid, _ = arrived(s)
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, ASK)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I drafted your yes to Erin.\n\n' + LETTER + '\n\nShould I add the time?')
    s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'DraftText': LETTER, 'Status': 'pending', 'Reason': 'the agent drafted it'})
    got = general.history(s, tid)[-1]['content'][0]['text']
    assert got == 'I drafted your yes to Erin.\n\nShould I add the time?'
    assert general.chat_rows(s, tid)[-1]['Body'] == got                     # ...and the next turn's history, the close-out
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, LETTER)
    assert general.history(s, tid)[-1]['content'][0]['text'] == general.DRAFTED

def test_a_quick_question_waits_on_the_owner_like_a_general_one():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses, _ = filed(s, tid, {**ANSWER, 'draft': None, 'question': 'Do you want to go Friday or send Erin alone?'})
        terminal.SESSIONS[ses.sid] = ses
        req = ws.asking_of(s, ses)
        assert req['kind'] == 'input_needed' and req['text'].startswith('Do you want to go Friday')
        assert ses.info()['state'] == 'asking'

def test_done_never_closes_the_task():
    # the owner, 2026-11-05: "agent should never close once it's open until we hit close" - a quick turn that says done leaves it open
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'draft': None, 'done': True, 'why': 'Answered: worth going.'})
    time.sleep(.5)                                     # past the 0.1s the close used to wait
    assert s.get_task(tid)['Status'] not in ('done', 'waiting', 'dropped')
    assert not any('The agent closed this itself' in (c['Body'] or '') for c in s.list_comments(tid))

def test_unmark_takes_every_taskuary_tag_and_only_those():
    for marked in ('Go [[TASKUARY-ATTACH: C:/a.txt]] on [[/TASKUARY-REPLY]] Friday [[ taskuary_propose ]].', 'Go on Friday. [[TASKUARY-DONE]] [[TASKUARY-ASK]] x',
                   'Go <TASKUARY-HUB>{"title": "t"}</TASKUARY-HUB> on Friday TASKUARY-PROPOSE'):     # the envelopes _file reads too
        got = quickwork._unmark(marked)
        assert 'TASKUARY' not in got.upper() and got.startswith('Go') and 'Friday' in got, got
    assert quickwork._unmark('Plain [[link]] text') == 'Plain [[link]] text'        # only Taskuary's own tags come out
    assert quickwork._unmark('Go <TASKUARY-HUB>{"title": "t",\n "x": 1}</TASKUARY-HUB> Friday') == 'Go  Friday'   # the Hub's JSON goes with its tags

def test_raw_answers_are_told_from_text():
    assert all(quickwork.is_raw(t) for t in ('{"report": "x"}', '```json\n{\n  "report": "Worth', '  { "draft": null, "report": "x"'))
    assert not any(quickwork.is_raw(t) for t in ('Worth going.', '{"title": "t"}', 'The report says {"report": 1}'))

def test_a_quick_session_takes_no_desk():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True; ses.busy = True        # working: only a working session holds a slot (2026-11-08)
        assert bb.live_count() == 0
        ses.quick = False; assert bb.live_count() == 1
        ses.busy = False; assert bb.live_count() == 0                    # ...parked, waiting on the owner, it holds none

def test_a_warm_turn_marks_every_event_quick():
    s = home(); tid, _ = arrived(s)
    ses, _ = filed(s, tid, {**ANSWER, 'draft': None, 'question': 'Friday or Saturday?'})
    evs = ws.events(s, tid, ses.sid)
    assert ses.quick and evs and all(e['Source'] == 'quick' for e in evs)

def test_a_warm_turn_on_an_ended_session_refuses():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid, quick=True); ses.alive = False
        with unittest.TestCase().assertRaises(general.Ended): quickwork.again(s, tid, ses, ASK)
    assert not ws.events(s, tid, ses.sid) and quickwork.in_flight() == 0

def test_a_warm_turn_that_failed_to_file_ends():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)):
        ses = opened(s, tid, quick=True)
        with mock.patch.object(general.GeneralSession, '_file', side_effect=RuntimeError('disk full')):
            with unittest.TestCase().assertRaises(RuntimeError): quickwork.again(s, tid, ses, ASK)
        end = time.time() + 10
        while time.time() < end and ses.alive: time.sleep(.05)
        assert not ses.alive and not general.session_for(tid)
    assert ws.events(s, tid, ses.sid)[-1]['Kind'] == 'failed' and ws.events(s, tid, ses.sid)[-1]['Source'] == 'quick'


def test_the_warm_agent_hands_on_to_the_full_agent_with_its_notes():
    s = home(); tid, _ = arrived(s)
    out, auto, live = run(s, tid, Brain({**ANSWER, 'escalate': True, 'why': 'it means booking travel across three sites', 'report': 'Two dates fit.', 'draft': None}))
    assert out == 'escalated' and list(live.values())[0].handed_on == ''
    (store_, t, brief), k = auto.call_args
    assert t == tid and k == {'deep': True} and 'booking travel across three sites' in brief
    turns = general.history(s, tid)
    assert turns[-1]['content'][0]['text'] == 'Two dates fit.'                 # its notes are the conversation the full agent carries on
    assert not any(quickwork.HAND_ON in (c['Body'] or '') for c in s.list_comments(tid))
    assert any(c['Body'] == quickwork.ESCALATED + 'it means booking travel across three sites' for c in s.list_comments(tid))

def test_a_hand_on_with_nothing_else_says_so_once():
    s = home(); tid, _ = arrived(s)
    out, _, _ = run(s, tid, Brain(f'{quickwork.HAND_ON} it needs the vendor portal'))
    assert out == 'escalated'
    assert [c['Body'] for c in s.list_comments(tid) if quickwork.ESCALATED in (c['Body'] or '')] == [quickwork.ESCALATED + 'it needs the vendor portal.']

def test_a_failed_warm_turn_is_a_failure_kept_with_its_retry():
    "A tooled turn may have done part of its work before it failed: it is never started again as the full agent behind the owner's back."
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    def boom(*a, **k): raise RuntimeError("codex exit 1: the model is not supported")
    with mock.patch.object(bb, 'drain_later'): out, auto, _ = run(s, tid, boom)
    assert out == 'failed' and not auto.called and s.get_dispatch(tid)
    assert quickwork.in_flight() == 0                                       # the slot came back

# TASKUARY'S INSTRUCTIONS ARE NOT THE OWNER'S WORDS (the owner, 2026-10-30): the ask a quick start files is Taskuary's brief, never under YOU
def test_a_quick_starts_ask_is_filed_as_taskuarys_brief():
    s = home(); tid, _ = arrived(s)
    out, _auto, _ = run(s, tid, Brain(ANSWER))
    turns = general.history(s, tid)
    assert out == 'filed' and turns[0]['role'] == 'user' and turns[0].get('brief') is True and not turns[1].get('brief')
    assert not any(c.get('Actor') == 'owner' and c.get('ActorType') == general.USER_TYPE for c in s.list_comments(tid))

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
        out, auto, _ = run(s, tid, Brain({**ANSWER, 'escalate': True, 'why': 'three sites to check'}))
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

def test_fifty_arrivals_run_as_many_as_the_agent_slots_hold_and_take_no_desk():
    from taskuary import blackboard as bb
    s = home(); tids = [arrived(s, mail_kw={'external_id': f'q{i}', 'conversation_id': f'conv-{i}'})[0] for i in range(50)]
    assert len(set(tids)) == 50
    gate, most, lock = threading.Event(), [0], threading.Lock()
    def slow(system, user, **k):
        with lock: most[0] = max(most[0], quickwork.in_flight())      # the slots held, not who reached the brain first
        gate.wait(5)
        return said(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(general, 'start_session', side_effect=opened):
        ts = [threading.Thread(target=quickwork.start, args=(s, t)) for t in tids]
        for t in ts: t.start()
        time.sleep(1); gate.set()
        for t in ts: t.join(20)
        assert most[0] == ingest.AUTO_SESSIONS * ingest.LIGHT_PER_AGENT == 20   # four agents' worth, five quick answers to one
        assert bb.live_count() == 0 and not s.queued_dispatches()             # no desk taken, no agent queued
    assert quickwork.in_flight() == 0


def test_a_quick_arrival_gets_the_warm_agent_and_no_agent_start():
    s = home(); tid, spawned = arrived(s)
    assert spawned == ['_auto_general']                                       # arrival is unchanged: auto_start_ok decided
    with mock.patch.object(quickwork, 'start', return_value='filed') as quick, mock.patch.object(ingest, '_start_general') as deep:
        ingest._auto_general(s, tid)
    quick.assert_called_once(); deep.assert_not_called()

def test_a_hard_arrival_starts_the_full_agent():
    """The owner, 2026-11-13: "only complex things" go to the full agent - a hard ask is not looked at by the warm agent first (it was, when
    that look was one cheap tool-less call: 2026-11-10). A stranger's task starts the full agent too: its words are its reviewer's to read."""
    s = home(); tid, _ = arrived(s, 'hard')
    with mock.patch.object(quickwork, 'start') as quick, mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(origin, 'of_task', return_value=('stranger', 'a first message')), mock.patch.object(quickwork, 'start') as quick, \
         mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()


def test_a_held_start_stays_held():
    s = home(general_auto_enabled='0'); tid, spawned = arrived(s)
    assert spawned == []                                                      # the owner's switch holds quick work too

def test_more_mail_on_a_live_quick_task_is_answered_quick_again():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        quickwork.start(s, tid)
        ingest._pass_general(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None})
        assert [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'] == ['quick_work', 'quick_work']

def test_more_mail_judged_hard_carries_on_as_the_general_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        s.judge_task(tid, {'difficulty': 'hard'}, 'triage')
        with mock.patch.object(llm, 'build_llm', return_value=mock.Mock(return_value='On it.')) as build:
            ingest._pass_general(s, tid, {**mail(body='Erin Blake: please book it for three of us'), 'message_id': None})
        assert build.call_args.kwargs['job'] == 'general'

def test_more_mail_the_warm_agent_hands_on_puts_the_ask_to_the_full_agent_on_the_same_session():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        ses = general.session_for(tid)
        brains = iter([Brain({**ANSWER, 'escalate': True, 'why': 'it means booking for three', 'draft': None}), Brain('Booking it now.')])
        with mock.patch.object(llm, 'build_llm', side_effect=lambda *a, **k: next(brains)) as build, mock.patch.object(ingest, 'has_room', return_value=True):
            ingest._pass_general(s, tid, {**mail(body='Erin Blake: please book it for three of us'), 'message_id': None})
        assert general.session_for(tid) is ses                              # the quick session carries on as the full agent's
        assert [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'] == ['quick_work', 'general'] and not ses.quick
        ask = [m for m in general.history(s, tid) if m['role'] == 'user'][-1]['content'][0]['text']
        assert 'please book it for three of us' in ask and 'it means booking for three' in ask, general.history(s, tid)

def test_two_quick_starts_on_one_task_make_one_turn():
    s = home(); tid, _ = arrived(s)
    gate, calls = threading.Event(), []
    def slow(system, user, **k): calls.append(1); gate.wait(5); return said(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(general, 'start_session', side_effect=opened):
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
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)):
        quickwork.start(s, tid); general.session_for(tid).alive = False
        new = {**mail(body='Erin Blake: also, can Gail Moreno come?', external_id='q2')}
        mid = s.list_messages(tid)[0]['MessageId']
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True):
            assert ingest._carry_on(s, tid, new, mid, {'intent': 'task', 'kind': 'general'}, 'triage')
        general.OPENING.discard(tid)
    fn, *args = spawn.call_args[0]
    assert fn is quickwork.start and args[:2] == [s, tid] and 'can Gail Moreno come' in args[2] and args[3:] == []    # filed as Taskuary's brief: the chat shows it

def test_a_depth_that_cannot_be_read_starts_the_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(quickwork, 'why_deep', side_effect=RuntimeError('store gone')), mock.patch.object(quickwork, 'start') as quick, \
         mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()

def test_a_line_landing_mid_turn_is_passed_in_however_long_the_turn_takes():
    s = home(); tid, _ = arrived(s)
    gate, calls = threading.Event(), []
    def slow(system, user, **k): calls.append(user); gate.wait(5); return said(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(general, 'start_session', side_effect=opened), mock.patch.object(ingest, 'PASS_WAIT', .2):     # the turn outlasts the wait
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
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'escalate': True, 'why': 'it means booking for three', 'report': 'Two dates fit.'})), \
         mock.patch.object(quickwork, '_fits', return_value=True), mock.patch.object(bb, 'live_count', return_value=99):
        assert quickwork.start(s, tid) == 'escalated'                           # it had its quick slot; by the hand-on every agent slot is taken
    brief = s.get_dispatch(tid)['Brief']
    assert 'it means booking for three' in brief and 'Two dates fit.' in general.history(s, tid)[-1]['content'][0]['text']
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

DRAFT = 'great, tell Gail the first month is free while we set her up - send me her email'

def test_a_quick_draft_is_not_said_inside_the_agents_turn():
    """The draft is a reply in the owner's voice; left in the turn it read as the owner's own words in Taskuary's column. It waits in
    Close out, and the pane's notice says it was drafted (agentDraftAsk.noticeLine)."""
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'report': 'Gail Moreno asks what it costs.', 'draft': DRAFT, 'question': 'First month free, or a price now?'})
    got = general.history(s, tid)[-1]['content'][0]['text']
    assert got.startswith('Gail Moreno asks') and DRAFT not in got
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and DRAFT in rv['DraftText']

def test_a_raw_answer_stored_as_a_turn_reads_back_as_its_report():
    "A turn whose body is the object itself - whole, fenced or cut short - is shown, and carried on, as the report it holds."
    s = home(); tid, _ = arrived(s)
    raw = json.dumps({**ANSWER, 'report': 'Gail Moreno asks what it costs.\n\nShe wants it.', 'draft': DRAFT})
    for body in (raw, f'```json\n{raw}\n```', raw[:60]):
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, body)
        got = general.history(s, tid)[-1]['content'][0]['text']
        assert '"report"' not in got and got.startswith('Gail Moreno asks what it costs'), got
    assert '"report"' not in general.conversation_text(s, tid)

def test_a_quick_session_opens_no_browser_at_its_start():
    "A Chrome on about:blank beside a quick session was the empty tab the task never used (2026-11-03): its turn launches one if it needs it."
    s = home(); tid, _ = arrived(s); s.tag_task(tid, browserview.WANTS, actor='t')
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.general.threading.Thread') as th:
        opened(s, tid, quick=True)
        assert not any(c.kwargs.get('target') is browserview.start for c in th.call_args_list)


def test_a_quick_turn_writes_its_hand_over_down_so_a_draft_the_owner_answered_past_is_set_aside_before_it_is_told():
    """Recorded on the real CLI, 2026-11-13 (invented people): a quick answer drafted the reply; the owner answered in the chat himself; the
    quick turn that heard that left no mark in the ledger - the draft stayed pending (greyed in the chat by where it stood, "ready to
    send" on the pill), and the agent, told a draft still waited and with no tool to put it down, said "it still shows under your Send"."""
    from taskuary import conversation, proposals
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        quickwork.start(s, tid)
        assert len(s._rows("SELECT 1 FROM heard WHERE TaskId=? AND Kind='turn'", (tid,))) == 1          # the first turn's hand-over: the mail, heard
        assert conversation.heard(s, tid, 'mail', [m['MessageId'] for m in s.list_messages(tid)])
        rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
        assert rv and rv['Status'] == 'pending'
        t = time.time()
        while time.time() < t + 1.1: time.sleep(0.05)                                                 # (a stamp is a whole second)
        own = s.add_message({'TaskId': tid, 'ExternalId': 'own1', 'ConversationId': 'conv-partner', 'Channel': 'email', 'FromName': 'You',
                             'BodyText': 'Erin - yes, we will be there.', 'Status': 'context', 'Direction': 'out'})
        seen = []
        class Seeing(Brain):
            "...and says, as its call is made, how the draft's row reads"
            def __call__(self, sy, u, **k): seen.append((s.get_review(rv['ReviewId'])['Status'], general.working(s, tid))); return super().__call__(sy, u, **k)
        build.return_value = Seeing({**ANSWER, 'report': 'I see you answered Erin there - nothing is left.', 'draft': None})
        quickwork.again(s, tid, general.session_for(tid), 'THE THREAD CHANGED: you already answered - the words of the owner:\nErin - yes, we will be there.')
    assert seen == [('superseded', True)], seen                                                       # set aside BEFORE the call read its prompt - and at work while it runs
    assert not general.working(s, tid)
    assert proposals.passed(s.get_review(rv['ReviewId'])) and conversation.heard(s, tid, 'mail', [own]) and not s.waiting_on_owner(tid)


def test_a_turn_that_ends_with_the_reply_owed_and_unwritten_leaves_on_its_card_what_the_agent_needs():
    """The owner, 2026-11-13: an empty reply box is drawn only where its record says why it is empty - so a turn that ended with the reply
    still owed, no draft and nothing on its record left no reply card at all: something owed, nothing lit. The end of the turn keeps, from
    what the turn itself recorded (its question; never its prose), what the agent needs - and the card stands in that turn."""
    from taskuary import conversation
    def owed(s, tid):
        mid = s.list_messages(tid)[0]['MessageId']
        return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
    q = 'Do you want to go Friday or send Erin alone?'
    for answer, want in (({**ANSWER, 'draft': None, 'question': q}, q),                                  # it asked: its question
                         ({**ANSWER, 'draft': None, 'question': None, 'report': 'I looked.'}, general.COULD_NOT)):   # it asked nothing: the one question left
        s = home(); tid, _ = arrived(s); rid = owed(s, tid)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            filed(s, tid, answer)
            assert s.get_review(rid)['DraftNeeds'] == want and not s.get_review(rid)['DraftText'], s.get_review(rid)
            got = conversation.items(s, tid); turn = [x for x in got['items'] if x['kind'] == 'turn'][-1]
            assert [(c['review'], c['status']) for c in turn['cards']] == [(rid, 'pending')] and got['letters'] == turn['id'], turn
    # ...and where he answers and the next turn still cannot write it, the card is THAT turn's, with what it needs now - never left above his
    # line, lit and empty, nor nowhere (the turn before's question is that turn's words)
    s = home(); tid, _ = arrived(s); rid = owed(s, tid)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        ses = opened(s, tid, quick=True); terminal.SESSIONS[ses.sid] = ses
        with mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'draft': None, 'question': q})): quickwork.again(s, tid, ses, ASK)
        t = time.time()
        while time.time() < t + 1.1: time.sleep(0.05)
        with mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'draft': None, 'question': 'Morning or afternoon?'})):
            quickwork.again(s, tid, ses, 'Friday, I think.', brief=False)
        got = conversation.items(s, tid); turns = [x for x in got['items'] if x['kind'] == 'turn']
        assert s.get_review(rid)['DraftNeeds'] == 'Morning or afternoon?'
        assert [[c['review'] for c in x['cards']] for x in turns] == [[], [rid]] and got['letters'] == turns[-1]['id'], [(x['id'], x['cards']) for x in turns]
    # ...a turn that wrote the reply needs nothing: the draft is the card
    s = home(); tid, _ = arrived(s); rid = owed(s, tid)
    filed(s, tid, ANSWER)
    assert not any(r.get('DraftNeeds') for r in s._rows('SELECT DraftNeeds FROM review WHERE TaskId=?', (tid,)))
    assert 'asks the owner the one thing it needs' in ingest.REPLY_JOB                                 # ...and its job says so, for the agent to do it itself


# THE OWNER'S OWN START TAKES THE SAME ROAD (the owner, 2026-11-13): New, the Board and Send to agent reach POST /dispatch, which always
# opened the full agent - a quick or normal task he started himself never met the warm agent
def _dispatch(s, tid, **body):
    from fastapi.testclient import TestClient
    from taskuary import capabilities, server
    with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(capabilities, 'has_ai', return_value=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build, mock.patch.object(ingest, '_auto_general') as auto:
        r = TestClient(server.app).post(f'/api/tasks/{tid}/dispatch', json={'kind': 'general', 'pick': 'cli:claude', **body})
        assert r.status_code == 200, r.text
        return [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') in ('quick_work', 'general')], auto

def test_an_owner_started_quick_job_goes_the_warm_road():
    s = home(); tid, _ = arrived(s, 'standard')
    jobs, auto = _dispatch(s, tid)
    assert jobs == ['quick_work'] and not auto.called and quickwork.only_quick(s, tid)
    assert general.history(s, tid)[0].get('brief') is True                     # pressed with nothing typed: the Summary is Taskuary's brief

def test_an_owner_started_hard_or_strangers_job_goes_to_the_full_agent():
    s = home(); tid, _ = arrived(s, 'hard')
    assert _dispatch(s, tid)[0] == ['general']
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(origin, 'of_task', return_value=('stranger', 'a first message')), mock.patch.object(origin, 'hold', return_value=None), \
         mock.patch.object(origin, 'launch_mode', return_value='auto'):
        jobs, _ = _dispatch(s, tid)
    assert 'quick_work' not in jobs                                            # a stranger's task never takes the warm lane, whoever starts it
