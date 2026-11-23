"""Quick work is the task's ONE agent on its light gear (the owner, 2026-11-20: "We want quick agent if the task is classified as quick but
never 2 agents"). A warm agent used to take every quick or normal task first, wrote to the owner ("that takes many steps, so it can't be
done here") and handed on to a full agent that restarted half a minute later: two voices, the first often untrue, the work late. Now
every general task starts its own agent at once, and triage's class picks the gear it runs on (brainroute) - nothing else."""
import json, threading, time
from pathlib import Path
from unittest import mock
from taskuary import brainroute, general, ingest, llm, selfclose, senders, terminal, workerstate as ws
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

def said(a: dict) -> str:
    "What an agent's turn writes for an answer: its words, the reply it drafts, its one question, its close."
    return '\n\n'.join(x for x in (a.get('report'), a.get('draft') and f"[[TASKUARY-REPLY]]{a['draft']}[[/TASKUARY-REPLY]]",
                                   a.get('question') and f"{selfclose.ASK_MARKER} {a['question']}", a.get('done') and f"{selfclose.MARKER} {a.get('why')}") if x)

class Brain:
    "A fake brain: answers `answer` as an agent's turn writes it, records each call."
    def __init__(self, answer): self.answer, self.calls = answer, []
    def __call__(self, system, user, **k): self.calls.append((system, user, k)); return said(self.answer) if isinstance(self.answer, dict) else self.answer

ANSWER = {'report': 'Worth going: Erin is presenting.', 'draft': 'Yes, let us go.', 'question': None, 'done': False, 'why': ''}
CLAUDE = [{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]     # a brain for the turn to run on
REAL_START = general.start_session                       # conftest's guard; actor='owner' passes through

def opened(s, tid, *a, **k): return REAL_START(s, tid, pick='cli:claude')

def started(s, tid, brain):
    "The task's start as an arrival makes it (ingest._start_general) on a fake brain: (its result, build_llm's mock)."
    with mock.patch.object(llm, 'build_llm', return_value=brain) as build, mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(general, 'start_session', side_effect=opened):
        return ingest._start_general(s, tid), build

def filed(s, tid, answer, ask=ASK, **kw):
    "One turn of the task's agent on a fresh session; the session."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=Brain(answer)), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        ses = opened(s, tid)
        ses.send_prompt(ask, **{'brief': True, **kw})
        return ses


# ── ONE AGENT, AT ONCE ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_there_is_no_second_agent_to_hand_on_to():
    assert not (Path(general.__file__).parent / 'quickwork.py').exists()
    assert not hasattr(general.GeneralSession, 'quick') and not hasattr(general.GeneralSession, 'handed_on')
    assert 'quick' not in general.start_session.__code__.co_varnames[:general.start_session.__code__.co_argcount]

def test_every_arrival_starts_its_own_agent_whatever_triage_judged():
    for d in ('quick', 'standard', 'hard', None):
        s = home(); tid, spawned = arrived(s, d)
        assert spawned == ['_auto_general'], d
        with mock.patch.object(ingest, '_start_general', return_value=True) as start: ingest._auto_general(s, tid)
        start.assert_called_once_with(s, tid, None)

def test_a_quick_tasks_first_turn_is_its_agent_doing_the_work():
    """The first thing in the chat is the agent's own answer, on its first and only start: no warm turn told to hand on, no hand-on line,
    no second start behind it."""
    s = home(); tid, _ = arrived(s)
    b = Brain(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(ingest, '_auto_general') as again:
        ok, build = started(s, tid, b)
        assert ok and len(b.calls) == 1 and not again.called
    assert {c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'} == {'general'}
    system, user, _k = b.calls[0]
    assert not any(w in system + user for w in ('FULL-AGENT', 'QUICK AGENT', 'hand on')), system[-600:]
    turns = general.history(s, tid)
    assert [t['role'] for t in turns] == ['user', 'assistant'] and turns[0].get('brief') is True
    assert turns[1]['content'][0]['text'].startswith('Worth going')

def test_a_line_he_typed_while_it_was_held_rides_the_first_turn():
    s = home(); tid, _ = arrived(s)
    general.wait_line(s, tid, 'Tell her yes, send the form.')
    b = Brain(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True): started(s, tid, b)
    assert 'Tell her yes, send the form.' in b.calls[0][1] and not general.waiting_lines(s, tid)

def test_a_quick_answer_lands_as_the_agents_turn():
    s = home(); tid, _ = arrived(s)
    ses = filed(s, tid, ANSWER)
    turns = general.history(s, tid)
    assert [t['role'] for t in turns] == ['user', 'assistant'] and turns[1]['content'][0]['text'].startswith('Worth going')
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and 'Yes, let us go.' in rv['DraftText'] and rv['Status'] == 'pending'          # waits for Send - never sent
    assert any(e['Kind'] == 'turn_end' and e['Source'] == 'api' for e in ws.events(s, tid, ses.sid))

def test_a_quick_task_holds_a_desk_like_any_agent():
    "One agent is one agent: a quick task's session counts against Agents at once while it works, as every agent's does."
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.busy = True
        assert bb.live_count() == 1
        ses.busy = False; assert bb.live_count() == 0                    # ...parked, waiting on the owner, it holds none

def test_more_mail_on_a_live_task_is_the_same_agents_next_turn():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        ingest._start_general(s, tid); ses = general.session_for(tid)
        ingest._pass_general(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None})
        assert general.session_for(tid) is ses
        assert [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'] == ['general', 'general']

def test_more_mail_after_the_session_ended_carries_the_conversation_on():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)):
        ingest._start_general(s, tid); general.session_for(tid).alive = False
        new = {**mail(body='Erin Blake: also, can Gail Moreno come?', external_id='q2')}
        mid = s.list_messages(tid)[0]['MessageId']
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True):
            assert ingest._carry_on(s, tid, new, mid, {'intent': 'task', 'kind': 'general'}, 'triage')
        general.OPENING.discard(tid)
    assert spawn.call_args[0][0] is ingest._continue_general

def test_a_line_landing_mid_turn_is_passed_in_however_long_the_turn_takes():
    s = home(); tid, _ = arrived(s)
    gate, calls = threading.Event(), []
    def slow(system, user, **k): calls.append(user); gate.wait(5); return said(ANSWER)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(general, 'start_session', side_effect=opened), mock.patch.object(ingest, 'PASS_WAIT', .2):     # the turn outlasts the wait
        first = threading.Thread(target=ingest._start_general, args=(s, tid)); first.start()
        end = time.time() + 5
        while time.time() < end and not calls: time.sleep(.02)
        line = threading.Thread(target=ingest._pass_general, args=(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None}))
        line.start(); time.sleep(.6); gate.set()
        first.join(10); line.join(10)
    assert len(calls) == 2 and 'can Gail Moreno come' in calls[1]                 # the same agent's next turn, behind the first
    assert not any('could not be passed in' in c['Body'] for c in s.list_comments(tid))


# THE OWNER'S OWN START (New, the Board, Send to agent reach POST /dispatch): the same one agent, on the gear its class picks
def _dispatch(s, tid, **body):
    from fastapi.testclient import TestClient
    from taskuary import capabilities, server
    with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(capabilities, 'has_ai', return_value=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build, mock.patch.object(ingest, '_auto_general') as auto:
        r = TestClient(server.app).post(f'/api/tasks/{tid}/dispatch', json={'kind': 'general', 'pick': 'cli:claude', **body})
        assert r.status_code == 200, r.text
        return [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') not in (None, 'judge')], auto

def test_an_owner_started_quick_job_is_its_one_agent():
    for d in ('quick', 'hard'):
        s = home(); tid, _ = arrived(s, d)
        jobs, auto = _dispatch(s, tid)
        assert jobs == ['general'] and not auto.called, (d, jobs)
        assert general.history(s, tid)[0].get('brief') is True                 # pressed with nothing typed: the Summary is Taskuary's brief


# ── WHAT A TURN FILES (one road for every turn, GeneralSession._file) ─────────────────────────────────────────────────────────

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

def test_a_question_waits_on_the_owner():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = filed(s, tid, {**ANSWER, 'draft': None, 'question': 'Do you want to go Friday or send Erin alone?'})
        terminal.SESSIONS[ses.sid] = ses
        req = ws.asking_of(s, ses)
        assert req['kind'] == 'input_needed' and req['text'].startswith('Do you want to go Friday')
        assert ses.info()['state'] == 'asking'

def test_done_never_closes_the_task():
    # the owner, 2026-11-05: "agent should never close once it's open until we hit close" - a turn that says done leaves it open
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'draft': None, 'done': True, 'why': 'Answered: worth going.'})
    time.sleep(.5)                                     # past the 0.1s the close used to wait
    assert s.get_task(tid)['Status'] not in ('done', 'waiting', 'dropped')
    assert not any('The agent closed this itself' in (c['Body'] or '') for c in s.list_comments(tid))

def test_unmark_takes_every_taskuary_tag_and_only_those():
    for marked in ('Go [[TASKUARY-ATTACH: C:/a.txt]] on [[/TASKUARY-REPLY]] Friday [[ taskuary_propose ]].', 'Go on Friday. [[TASKUARY-DONE]] [[TASKUARY-ASK]] x',
                   'Go <TASKUARY-HUB>{"title": "t"}</TASKUARY-HUB> on Friday TASKUARY-PROPOSE'):     # the envelopes _file reads too
        got = selfclose.unmark(marked)
        assert 'TASKUARY' not in got.upper() and got.startswith('Go') and 'Friday' in got, got
    assert selfclose.unmark('Plain [[link]] text') == 'Plain [[link]] text'        # only Taskuary's own tags come out
    assert selfclose.unmark('Go <TASKUARY-HUB>{"title": "t",\n "x": 1}</TASKUARY-HUB> Friday') == 'Go  Friday'   # the Hub's JSON goes with its tags

def test_a_tag_no_road_read_never_reaches_his_screen():
    """The 2026-11-18 walk: "[[TASKUARY-FULL-AGENT]] Paying on pay.payworth.example needs a browser..." stood in the chat - a mark a
    conversation from before 2026-11-20 may still write. Whatever no road reads comes out where his words are made: the progress line
    (for_screen) and the filed answer (general._file, by the same selfclose.unmark)."""
    line = '[[TASKUARY-FULL-AGENT]] Paying on pay.payworth.example needs a browser to sign in.'
    assert selfclose.for_screen(line) == 'Paying on pay.payworth.example needs a browser to sign in.'
    assert 'reply = selfclose.unmark(reply)' in open(general.__file__, encoding='utf8').read()

def test_raw_answers_are_told_from_text():
    assert all(selfclose.is_raw(t) for t in ('{"report": "x"}', '```json\n{\n  "report": "Worth', '  { "draft": null, "report": "x"'))
    assert not any(selfclose.is_raw(t) for t in ('Worth going.', '{"title": "t"}', 'The report says {"report": 1}'))

DRAFT = 'great, tell Gail the first month is free while we set her up - send me her email'

def test_a_draft_is_not_said_inside_the_agents_turn():
    """The draft is a reply in the owner's voice; left in the turn it read as the owner's own words in Taskuary's column. It waits in
    Close out, and the pane's notice says it was drafted (agentDraftAsk.noticeLine)."""
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'report': 'Gail Moreno asks what it costs.', 'draft': DRAFT, 'question': 'First month free, or a price now?'})
    got = general.history(s, tid)[-1]['content'][0]['text']
    assert got.startswith('Gail Moreno asks') and DRAFT not in got
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and DRAFT in rv['DraftText']

def test_a_raw_answer_stored_as_a_turn_reads_back_as_its_report():
    "A turn whose body is the object itself - whole, fenced or cut short (stored before 2026-11-13) - is shown, and carried on, as its report."
    s = home(); tid, _ = arrived(s)
    raw = json.dumps({**ANSWER, 'report': 'Gail Moreno asks what it costs.\n\nShe wants it.', 'draft': DRAFT})
    for body in (raw, f'```json\n{raw}\n```', raw[:60]):
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, body)
        got = general.history(s, tid)[-1]['content'][0]['text']
        assert '"report"' not in got and got.startswith('Gail Moreno asks what it costs'), got
    assert '"report"' not in general.conversation_text(s, tid)

def test_a_turn_writes_its_hand_over_down_so_a_draft_the_owner_answered_past_is_set_aside_before_it_is_told():
    """Recorded on the real CLI, 2026-11-13 (invented people): the agent drafted the reply; the owner answered in the chat himself; the turn
    that heard that must set the draft aside BEFORE its call reads the prompt, and read at work while it runs."""
    from taskuary import conversation, proposals
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(general, 'provider_options', return_value=CLAUDE), mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        ingest._start_general(s, tid)
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
        general.OPENING.add(tid)
        try: general.session_for(tid).send_prompt('THE THREAD CHANGED: you already answered - the words of the owner:\nErin - yes, we will be there.', brief=True)
        finally: general.OPENING.discard(tid)
    assert seen == [('superseded', True)], seen
    assert not general.working(s, tid)
    assert proposals.passed(s.get_review(rv['ReviewId'])) and conversation.heard(s, tid, 'mail', [own]) and not s.waiting_on_owner(tid)

def test_a_turn_that_ends_with_the_reply_owed_and_unwritten_leaves_on_its_card_what_the_agent_needs():
    """The owner, 2026-11-13: an empty reply box is drawn only where its record says why it is empty. The end of the turn keeps, from what
    the turn itself recorded (its question; never its prose), what the agent needs - and the card stands in that turn."""
    from taskuary import chatlog, conversation
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
            chatlog.settled(); got = conversation.items(s, tid); turn = [x for x in got['items'] if x['kind'] == 'turn'][-1]     # the card's worker has put it
            if want == q:       # ...its question open is the ONE thing asked (the owner's rule, 2026-11-15): no empty reply box beside it
                assert turn['cards'] == [] and got['asking'] and q in got['asking']['text'], (turn, got['asking'])
            else: assert [(c['review'], c['status']) for c in turn['cards']] == [(rid, 'pending')] and got['letters'] == turn['id'], turn
    # ...and where he answers and the next turn still cannot write it, the card is THAT turn's, with what it needs now
    s = home(); tid, _ = arrived(s); rid = owed(s, tid)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'provider_options', return_value=CLAUDE):
        ses = opened(s, tid); terminal.SESSIONS[ses.sid] = ses
        with mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'draft': None, 'question': q})): ses.send_prompt(ASK, brief=True)
        t = time.time()
        while time.time() < t + 1.1: time.sleep(0.05)
        with mock.patch.object(llm, 'build_llm', return_value=Brain({**ANSWER, 'draft': None, 'question': 'Morning or afternoon?'})):
            ses.send_prompt('Friday, I think.', brief=False)
        chatlog.settled(); got = conversation.items(s, tid); turns = [x for x in got['items'] if x['kind'] == 'turn']
        assert s.get_review(rid)['DraftNeeds'] == 'Morning or afternoon?'
        # ...and while that question is open it is the ONE thing asked (the owner's rule; 2026-11-15): no empty card under it
        assert [[c['review'] for c in x['cards']] for x in turns] == [[], []] and not got['letters'], [(x['id'], x['cards']) for x in turns]
        assert got['asking'] and 'Morning or afternoon?' in got['asking']['text'], got['asking']
    # ...a turn that wrote the reply needs nothing: the draft is the card
    s = home(); tid, _ = arrived(s); rid = owed(s, tid)
    filed(s, tid, ANSWER)
    assert not any(r.get('DraftNeeds') for r in s._rows('SELECT DraftNeeds FROM review WHERE TaskId=?', (tid,)))
