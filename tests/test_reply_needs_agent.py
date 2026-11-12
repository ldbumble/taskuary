"""A reply that needs work gets an agent, never a placeholder (the owner, 2026-10-28).

The shapes that pinned it, with invented people: a reply task's thread got a second mail triage judged work for an agent, the join
dropped that verdict, and the tool-less writer drafted "I have to look into it and will send that separately"; a colleague pasted a
long draft update asking for thoughts and got "I'll review this and send you my thoughts." Now: an agent verdict joining a reply task
starts that agent (work it out, then draft the reply for the owner's Send); why no agent started is always written.
And since 2026-11-10 (the owner: "no more triage creates draft. agent should be doing it" ... "as it arrives of course") every reply owed
is the task's agent's from arrival (ingest.reply_to_agent): nothing drafts it in one tool-less call first - a quick fact included - and
the writer's NEEDS is only ever the answer to the owner's own Draft with AI press.
And a webinar invite whose thread fills with banter stays one task under its own title, with triage's offer one press away.
"""
import json
from unittest import mock

import pytest

from taskuary import general, ingest, responder, senders, triage
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

ME, ERIN = 'alex@northwind.example', 'erin@northwind.example'
SECTIONS = ['Pipeline: twelve new accounts in October, three of them from the partner referral scheme we started in August.',
            'Churn: two customers left after the price change; both cited the missing export, which ships in November.',
            'Support: first-response time is down to four hours since the rota changed, but weekend tickets still wait.',
            'Next quarter: hire one more account manager, run the customer day in January, and retire the old portal.']
DRAFT = ('Hi team, here is my draft of the quarterly update before it goes to everyone.\n\n'
         + '\n\n'.join(f'{x} ' + 'More of the detail the real update would carry on this point, so it runs long. ' * 5 for x in SECTIONS)
         + '\n\nBest,\nPaula')
FEEDBACK_ASK = f'Here is my draft update for the quarter - let me know your thoughts before I send it round.\n\n{DRAFT}\n\nPaula Vance\nNorthwind'


def store(**settings):
    s = MemoryStore()
    s.set_setting('owner_email', ME, 't'); s.set_setting('owner_name', 'Alex Doyle', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s


def mail(**kw):
    return {'external_id': 'm1', 'channel': 'email', 'subject': 'Quarterly update', 'body': 'Are you around Tuesday afternoon?',
            'from_email': ERIN, 'from_name': 'Erin Blake', 'conversation_id': 'AAQk-q', 'sent_at': '2026-10-28 09:00', 'source_name': ME, **kw}


def says(**v):
    return lambda sy, u, **k: json.dumps({'why': 'w', 'asks_owner': True, 'sender_class': 'person', **v})


def ingested(s, m, llm, wrote=True):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=wrote), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, m, llm=llm)
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def reply_task(s):
    out, spawned = ingested(s, mail(), says(intent='reply_only', kind='task', title='Erin asks if you are free Tuesday'))
    assert spawned == ['reply_to_agent'] and s.get_task(out['task_id'])['Kind'] == 'reply'
    assert not (s.pending_review(out['task_id'], kind='draft').get('DraftText') or '').strip()          # owed: nothing wrote it at arrival
    return out['task_id']


def lines(s, tid): return [c['Body'] for c in s.list_comments(tid)]


# ── the guide says what an agent is for (no model call: the words the model reads) ──────────────────────────────────────────
def test_the_guide_sends_thinking_reviewing_and_opinions_to_the_general_agent():
    g = ' '.join(triage.SHIPPED.split())
    assert 'here\'s my draft, let me know your thoughts' in g.lower() and 'what do you think of this plan' in g
    general_rule = g.split('- **general** -')[1].split('- **task** -')[0]
    assert 'thinking, reading, reviewing, research, judgement or an opinion' in general_rule
    assert 'Here\'s my draft update, let me know your thoughts' in general_rule and 'are general' in general_rule
    reply_rule = g.split('- **reply_only** -')[1].split('- **fyi** -')[0]
    assert 'a yes or no, a time, a confirmation, a quick fact' in reply_rule and 'is not this: it is a task' in reply_rule
    assert 'their own opinion or decision that someone asked them for' not in g         # an opinion is no longer the owner's own list
    assert 'lean general' in g


def test_the_guide_keeps_banter_off_the_title_and_asks_for_an_offer():
    g = ' '.join(triage.SHIPPED.split())
    assert 'banter or small talk about it' in triage.REFINES and 'keeps its title' in triage.REFINES
    assert 'Banter about the ask' in g and 'adds nothing to do' in g
    assert triage.OFFER.startswith('- **offer**') and 'I can register you for the webinar' in triage.OFFER
    assert '"offer": null' in triage.SHIPPED and 'offer' in triage.verdict_schema()['schema']['properties']['more']['properties']


# ── a long draft-for-feedback mail, judged general, goes to the assistant told its job ends in the reply ────────────────────
def test_a_draft_for_feedback_judged_general_starts_the_assistant_on_the_reply():
    s = store()
    out, spawned = ingested(s, mail(from_email='paula@northwind.example', from_name='Paula Vance', body=FEEDBACK_ASK),
                            says(intent='task', kind='general', title='Paula wants thoughts on her quarterly update draft'))
    tid = out['task_id']
    assert s.get_task(tid)['Kind'] == 'general' and spawned == ['_auto_general']
    job = ingest.reply_job(s, tid)
    assert 'REPLY OWED to Paula Vance' in job and 'your result for the owner is those thoughts' in job and 'never a promise' in job


# ── ruling 1: an agent verdict joining a reply task starts that agent ───────────────────────────────────────────────────────
WORK = dict(external_id='m2', sent_at='2026-10-28 10:00', body='Also - why did the October invoice total come out higher than September?')


def test_a_joining_general_verdict_on_a_reply_task_starts_the_assistant():
    s = store(); tid = reply_task(s)
    _out, spawned = ingested(s, mail(**WORK), says(intent='task', kind='general', title='Why the October invoice total is higher'))
    t = s.get_task(tid)
    assert t['Kind'] == 'general' and s.task_has_tag(tid, ingest.REPLY_TAG)
    assert spawned == ['_auto_general']                                              # the agent - and no second hand-over beside it
    assert any('needs the agent before it can be answered' in x and 'drafts the reply for your Send' in x for x in lines(s, tid))
    assert 'REPLY OWED to Erin Blake' in ingest.reply_job(s, tid)


def test_a_joining_coding_verdict_starts_the_coding_agent_which_picks_its_repository():
    s = store(); tid = reply_task(s)
    _out, spawned = ingested(s, mail(**WORK), says(intent='task', kind='coding', repository='northwind/ledger', title='Invoice total bug'))
    t = s.get_task(tid)
    assert t['Kind'] == 'coding' and 'repo' not in str(t.get('Tags') or '')            # where is the agent's pick (repochoice)
    assert spawned == ['_auto_code']


def test_the_started_assistant_is_told_the_reply_job():
    s = store(); tid = reply_task(s)
    ingested(s, mail(**WORK), says(intent='task', kind='general'))
    ses = mock.Mock()
    with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'history', return_value=[]):
        assert ingest._start_general(s, tid)
    assert ses.send_prompt.call_args[0][0].startswith('THIS TASK IS A REPLY OWED to Erin Blake')
    assert ses.send_prompt.call_args.kwargs.get('brief') is True       # Taskuary's instructions, never shown under YOU (the owner, 2026-10-30)


# ── ruling 4: why no agent started is written on the task ───────────────────────────────────────────────────────────────────
def test_auto_start_off_keeps_the_reply_and_says_why_once():
    s = store(general_auto_enabled='0'); tid = reply_task(s)
    _out, spawned = ingested(s, mail(**WORK), says(intent='task', kind='general'))
    assert s.get_task(tid)['Kind'] == 'reply' and '_auto_general' not in spawned
    said = [x for x in lines(s, tid) if x.startswith('No agent started:')]
    assert len(said) == 1 and said[0].startswith('No agent started: Starting an agent by itself is switched off in Settings')
    ingested(s, mail(**{**WORK, 'external_id': 'm3', 'sent_at': '2026-10-28 11:00'}), says(intent='task', kind='general'))
    assert len([x for x in lines(s, tid) if x.startswith('No agent started:')]) == 1          # the same reason is not said again


def test_a_stranger_on_a_reply_task_is_held_with_the_reason():
    s = store(); tid = reply_task(s)
    _out, spawned = ingested(s, mail(**{**WORK, 'from_email': 'rep@vendor.example', 'from_name': 'Sam Rook'}),
                             says(intent='task', kind='general'), wrote=False)
    assert s.get_task(tid)['Kind'] == 'reply' and s.task_has_tag(tid, ingest.HOLD_TAG)
    assert any(x.startswith('No agent started:') and 'never written to them' in x for x in lines(s, tid))


def test_carry_on_that_cannot_start_says_why():
    s = store()
    out, _ = ingested(s, mail(body='Can you draft a pilot plan for the new site?'), says(intent='task', kind='general'))
    tid = out['task_id']
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote the pilot plan.')
    s.update_task(tid, {'Status': 'done'}, 't')
    s.set_setting('general_auto_enabled', '0', 't')
    with mock.patch.object(general, 'history', return_value=[{'role': 'user'}]):
        ingested(s, mail(**WORK), says(intent='task', kind='general'))
    assert any(x.startswith('No agent started: Starting an agent by itself is switched off') for x in lines(s, tid))


# ── ruling 3, as it stands since 2026-11-10: the reply is handed to the general agent at arrival - no writer, no placeholder ────────────
def handed(s, tid, wrote=True):
    "The arrival's hand-over run as its spawned thread runs it: (the review after, what it set going)."
    rv = s.pending_review(tid, kind='draft')
    with mock.patch('taskuary.llm.build_llm', side_effect=AssertionError('nothing drafts at arrival')), mock.patch('taskuary.ingest._spawn') as spawn, \
         mock.patch.object(senders, 'wrote_to', return_value=wrote), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        went = ingest.reply_to_agent(s, tid, rv['ReviewId'])
    return s.get_review(rv['ReviewId']), [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list], went


def test_the_writer_is_told_never_to_promise_and_to_say_needs():
    "The owner's own Draft with AI press still reaches the writer: its rule stands."
    assert 'never write a placeholder' in responder.NOT_YET and responder.NEEDS in responder.NOT_YET
    assert 'you will pick it up' not in responder.NOT_YET


def test_a_reply_owed_starts_the_general_agent_and_leaves_no_draft():
    s = store(); tid = reply_task(s)
    rv, spawned, went = handed(s, tid)
    assert went and spawned == ['_auto_general'] and s.get_task(tid)['Kind'] == 'general' and s.task_has_tag(tid, ingest.REPLY_TAG)
    assert not (rv.get('DraftText') or '').strip() and not rv.get('DraftNeeds') and not rv.get('DraftError') and rv['Status'] == 'pending'
    job = ingest.reply_job(s, tid)
    assert job.startswith('THIS TASK IS A REPLY OWED to Erin Blake. Work out the answer') and 'never a promise' in job
    assert 'reply writer' not in job and not [x for x in lines(s, tid) if 'reply writer' in x]         # no second voice is quoted to it


def test_with_auto_start_off_the_reply_waits_and_the_task_says_why():
    s = store(general_auto_enabled='0'); tid = reply_task(s)
    rv, spawned, went = handed(s, tid)
    assert not went and spawned == [] and s.get_task(tid)['Kind'] == 'reply'
    assert not (rv.get('DraftText') or '').strip() and rv['Status'] == 'pending'                       # still a reply owed, the owner's to start
    assert [x for x in lines(s, tid) if x.startswith('No agent started: Starting an agent by itself is switched off')]


def test_a_strangers_reply_is_held_with_the_reason():
    s = store()
    out, spawned = ingested(s, mail(from_email='rep@vendor.example', from_name='Sam Rook'), says(intent='reply_only', kind='task'), wrote=False)
    tid = out['task_id']; assert spawned == ['reply_to_agent']
    _rv, spawned, went = handed(s, tid, wrote=False)
    assert not went and spawned == [] and s.get_task(tid)['Kind'] == 'reply' and s.task_has_tag(tid, ingest.HOLD_TAG)
    assert any(x.startswith('No agent started:') and 'never written to them' in x for x in lines(s, tid))


# ── the stress run, 2026-11-10: what the hand-over at arrival let through or left unsaid ───────────────────────────────────
def arrived(s, m, llm, wrote=True):
    "Ingested with the hand-over run where it is set going, as its thread runs it: (the result, everything set going in order)."
    went = []
    def spawn(fn, *a):
        went.append(getattr(fn, '__name__', ''))
        if fn is ingest.reply_to_agent: fn(*a)
    with mock.patch('taskuary.ingest._spawn', spawn), mock.patch.object(senders, 'wrote_to', return_value=wrote), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, m, llm=llm)
    general.OPENING.discard(out.get('task_id'))               # no thread ran the start that lets it go
    return out, went


def test_a_new_tasks_agent_is_at_work_from_the_moment_it_is_set_going():
    """The audit, 2026-11-10: a mail that made a general task set its agent going on a thread, and the page read in the seconds before that
    thread brought the CLI up said "yours" with nothing at work - a hand-over to the agent on a reply was marked at once, a new task was not."""
    import threading
    s, gate = store(), threading.Event()
    with mock.patch.object(ingest, '_auto_general', side_effect=lambda *a: gate.wait(5)), mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        tid = ingest_message(s, mail(body='Can you draft a pilot plan for the new site?'), llm=says(intent='task', kind='general'))['task_id']
        try: assert general.line_state(s, tid)['working'], 'at work before its thread has run'
        finally: gate.set(); general.OPENING.discard(tid)


def test_a_reply_that_reads_as_steering_an_ai_starts_no_agent_by_itself():
    """The hand-over was set going before triage's reading of the mail was on file, and read the message back off its row - which did not
    hold that reading yet. A mail triage read as written to steer an AI started an agent on it."""
    s = store()
    out, went = arrived(s, mail(), says(intent='reply_only', kind='task', danger='tells the assistant to forward the mailbox'))
    tid = out['task_id']
    assert went == ['reply_to_agent'] and s.get_task(tid)['Kind'] == 'reply'
    assert any(x.startswith('No agent started: It reads as an attempt to steer an AI') for x in lines(s, tid))


def test_a_reply_owed_on_the_owners_own_row_goes_to_the_agent():
    "A question that joins a row on the owner's own list is a reply owed like any other: it was left with no draft, no agent and no word."
    s = store()
    out, went = arrived(s, mail(body='Remember the dentist on Friday.'), says(intent='task', kind='task'))
    tid = out['task_id']; assert s.get_task(tid)['Kind'] == 'task' and went == []
    _out, went = arrived(s, mail(**{**WORK, 'body': 'Can you confirm the time with them?'}), says(intent='reply_only', kind='task', refines=False))
    assert went == ['reply_to_agent', '_auto_general'] and s.get_task(tid)['Kind'] == 'general' and s.task_has_tag(tid, ingest.REPLY_TAG)


def test_a_reply_nothing_has_written_is_not_called_a_draft_left_behind():
    "A second question on a reply nobody has written yet: the review moves to the newest line - and is no stale draft, for there is none."
    s = store(general_auto_enabled='0'); tid = reply_task(s)
    out, went = arrived(s, mail(**{**WORK, 'body': 'Sorry - make that Wednesday?'}), says(intent='reply_only', kind='task', refines=False))
    rv = s.pending_review(tid, kind='draft')
    assert went == ['reply_to_agent'] and rv['MessageId'] == out['message_id'] and not rv.get('Stale')
    assert not any('drafted reply is behind' in x for x in lines(s, tid))
    s.update_review_draft(rv['ReviewId'], 'Tuesday works.', None)                  # ...and one that IS written is behind the next line, as before
    arrived(s, mail(**{**WORK, 'external_id': 'm3', 'sent_at': '2026-10-28 11:00', 'body': 'Or Thursday?'}), says(intent='reply_only', kind='task', refines=False))
    assert s.pending_review(tid, kind='draft').get('Stale') and any('drafted reply is behind' in x for x in lines(s, tid))


def test_a_reply_owed_that_no_road_takes_to_an_agent_says_so():
    """A question on a task whose conversation is open reaches its agent by that conversation's road - and where that road is switched
    off it was kept quiet there, so the reply sat with nobody writing it and nothing said."""
    s = store(answer_to_agent='off')
    out, _ = arrived(s, mail(body='Can you draft a pilot plan for the new site?'), says(intent='task', kind='general')); tid = out['task_id']
    with mock.patch.object(general, 'history', return_value=[{'role': 'user'}]):
        _o, went = arrived(s, mail(**{**WORK, 'body': 'And when can it start?'}), says(intent='reply_only', kind='task', refines=False))
    assert went == ['reply_to_agent'] and s.pending_review(tid, kind='draft')
    assert any(x.startswith('No agent started: passing lines to the agent is switched off - ') for x in lines(s, tid))


def test_a_machine_or_the_owner_is_owed_no_reply_and_the_work_is_the_agents():
    """The owner, 2026-11-10: "github emails are not supposed to be respodned to". A notice triage read as a question - a build service's
    "reply to re-run", a list's "reply with your RSVP", the owner's own mail from another device - opened a reply owed and started the agent
    told THIS TASK IS A REPLY OWED to it, while every reply door refused one: the empty reply sat on the task for good, nothing to press."""
    ci = mail(from_email='builds@ci.example', from_name='CI Builds', body='Build 4512 failed on main. Reply to re-run.', sender_class='automated')
    for m, cls in ((ci, 'automated'), (mail(from_email='news@list.example', from_name='Ops Digest', body='Reply with your RSVP'), 'bulk'),
                   (mail(from_email=ME, from_name='Alex Doyle', body='ask Erin for the Q3 numbers'), 'person')):
        s = store(); out, went = arrived(s, m, says(intent='reply_only', kind='task', sender_class=cls)); tid = out['task_id']
        assert s.pending_review(tid) is None and not s.task_has_tag(tid, ingest.REPLY_TAG), m['from_email']
        assert s.get_task(tid)['Kind'] == 'general' and 'reply_to_agent' not in went, m['from_email']
        assert went == ['_auto_general'] or any(x.startswith('No agent started:') for x in lines(s, tid)), m['from_email']
    # ...and a machine's question joining a person's thread opens no reply owed there either
    s = store(); out, _ = arrived(s, mail(body='Can you draft a pilot plan?'), says(intent='task', kind='general')); tid = out['task_id']
    arrived(s, {**ci, **WORK, 'body': 'Reply to re-run.'}, says(intent='reply_only', kind='task', sender_class='automated', refines=False))
    assert s.pending_review(tid) is None


def test_a_question_on_a_coding_task_whose_agent_stopped_carries_that_agent_on():
    """The owner, 2026-11-10: "job of agent is to be helpful and do as much as possible". Ray asks "which branch will it land on?" on a bug
    the coding agent fixed and left: the question is that agent's next turn - its session reopened by itself - never a reply owed with
    nobody writing it. Where no agent may start by itself, the task says why."""
    s = store(coding_auto_enabled='0')
    out, went = arrived(s, mail(body='late_fee in northwind/ledger is wrong - fix it.'), says(intent='task', kind='coding')); tid = out['task_id']
    assert s.get_task(tid)['Kind'] == 'coding' and went == []
    arrived(s, mail(**{**WORK, 'body': 'Which branch will it land on?'}), says(intent='reply_only', kind='task', refines=False))
    assert s.get_task(tid)['Kind'] == 'coding' and s.pending_review(tid, kind='draft')
    _rv, went, ok = handed(s, tid)
    assert not ok and went == [] and [x for x in lines(s, tid) if x.startswith('No agent started: ')], lines(s, tid)
    s.set_setting('coding_auto_enabled', '1', 't')
    with mock.patch.object(ingest, '_resumable_coding', return_value=(True, '')), mock.patch.object(ingest, 'has_room', return_value=True):
        try: _rv, went, ok = handed(s, tid)
        finally: general.OPENING.discard(tid)          # the start is mocked away, so nothing lets go of it
    assert ok and went == ['_continue_coding'], (went, lines(s, tid))
    assert any('the coding agent reopens its own session here by itself' in x for x in lines(s, tid))


def test_a_second_line_while_the_first_start_is_on_its_way_starts_no_second_agent():
    "A general task's agent was set going a beat ago and has nothing to show yet: a question right behind it is not a second start."
    s = store()
    out, went = arrived(s, mail(body='Can you draft a pilot plan for the new site?'), says(intent='task', kind='general')); tid = out['task_id']
    assert went == ['_auto_general']
    _o, went = arrived(s, mail(**{**WORK, 'body': 'And when can it start?'}), says(intent='reply_only', kind='task', refines=False))
    assert went == ['reply_to_agent'] and not any(x.startswith('No agent started:') for x in lines(s, tid))


# ── the add-on: a webinar invite and its banter are one task under one title, with the offer one press away ────────────────
INVITE = dict(external_id='w1', subject='Webinar tomorrow', from_email='omar@vendor.example', from_name='Omar Keller', conversation_id='AAQk-web',
              body='Hi Alex, do you want to join our ledger automation webinar tomorrow at 11? Happy to save you a seat.',
              sent_at='2026-10-28 08:00')
OFFER = 'I can register you for the webinar and put it on your calendar.'
BANTER = [('w2', 'Ha - bring coffee, it runs a full hour.'), ('w3', 'Paula says the last one was the best they have done.'),
          ('w4', 'Looking forward to it either way!')]


def webinar(s):
    out, _ = ingested(s, mail(**INVITE), says(intent='reply_only', kind='task', title='Join the ledger automation webinar tomorrow?',
                                              summary='Omar Keller invites you to a webinar tomorrow at 11.', offer=OFFER))
    tid = out['task_id']
    for n, (eid, body) in enumerate(BANTER):
        o, _ = ingested(s, mail(**{**INVITE, 'external_id': eid, 'body': body, 'sent_at': f'2026-10-28 0{n + 8}:30'}),
                        says(intent='fyi', kind='task', title=f'Banter {n}', refines=False, asks_owner=False, offer=None))
        assert o['task_id'] == tid
    return tid


def test_banter_keeps_the_webinar_one_task_under_its_own_title_with_one_offer():
    s = store(); tid = webinar(s)
    assert len(s.list_tasks(active_only=False)) == 1
    assert s.get_task(tid)['Title'] == 'Join the ledger automation webinar tomorrow?'
    assert ingest.offer_of(s, tid) == OFFER


def test_accepting_the_offer_starts_the_assistant_with_that_job():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = store(); tid = webinar(s)
    ses = mock.Mock(provider='claude', model=None); ses.info.return_value = {}
    with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', return_value=ses), \
         mock.patch.object(general, 'history', return_value=[]):
        c = TestClient(server.app)
        assert c.get(f'/api/tasks/{tid}').json()['offer'] == OFFER
        r = c.post(f'/api/tasks/{tid}/offer')
        assert r.status_code == 200, r.text
        prompt = ses.send_prompt.call_args[0][0]
        assert OFFER in prompt and "waits for the owner's yes" in prompt and 'Nothing is sent' in prompt
        # ...the job is Taskuary's words about a press, never a line the owner typed (the agent walk, 2026-11-09: it stood in their bubble)
        assert ses.send_prompt.call_args[1].get('brief') is True
        assert [m for m in general.press_lines(s, tid) if 'accepted the offer' in m['content'][0]['text']], general.press_lines(s, tid)
        assert s.get_task(tid)['Kind'] == 'general' and ingest.offer_of(s, tid) == ''
        assert c.post(f'/api/tasks/{tid}/offer').status_code == 409                 # taken once


# ── a reply owed on a GENERAL task no agent has run on goes to the assistant too (Task 3.2, 2026-11-04): only a reply task did, so a
# general task asking the owner for details their own files hold stopped with no agent ever run on it ────────────────────────────────
def general_ask(s, kind='general'):
    from taskuary.testing import Factory
    f = Factory(s)
    tid = f.task(title='Ray asks for the vendor-portal login', kind=kind)
    mid = f.message(tid, from_email='ray@northwind.example', from_name='Ray Colton', subject='Portal login',
                    body='Can you send Gail the vendor-portal login so she can upload the payment file?')
    f.review(tid, mid)
    return tid


def test_a_reply_owed_on_a_general_task_starts_the_assistant_once_told_the_reply_job():
    s = store(); tid = general_ask(s)
    _rv, spawned, went = handed(s, tid)
    assert went and spawned == ['_auto_general'] and s.get_task(tid)['Kind'] == 'general'
    assert ingest.first_ask(s, tid).startswith('THIS TASK IS A REPLY OWED to Ray Colton')


def test_a_reply_owed_under_a_live_agent_starts_nothing_new():
    s = store(); tid = general_ask(s, kind='general')
    general.OPENING.add(tid)
    try: _rv, spawned, went = handed(s, tid)
    finally: general.OPENING.discard(tid)
    assert not went and spawned == [] and not s.task_has_tag(tid, ingest.REPLY_TAG)


def test_a_reply_owed_on_a_coding_task_nothing_ran_on_starts_its_coding_agent():
    "A coding task stays coding: the question goes to a coding agent, started as a fresh task's would be - never the general one beside it."
    s = store(); tid = general_ask(s, kind='coding')
    try: _rv, spawned, went = handed(s, tid)
    finally: general.OPENING.discard(tid); general.OPENING.discard(tid)
    assert went and spawned == ['_auto_code'] and s.get_task(tid)['Kind'] == 'coding', (spawned, lines(s, tid))


def test_the_hand_over_keeps_a_general_kind_and_holds_the_start_against_a_second_one():
    s = store(); tid = general_ask(s, kind='research')
    try:
        _rv, spawned, went = handed(s, tid)
        assert went and spawned == ['_auto_general'] and s.get_task(tid)['Kind'] == 'research'
        assert tid in general.OPENING                     # opening from the hand-over on: a second one meanwhile is an agent live on it
        assert handed(s, tid)[1:] == ([], False)
    finally: general.OPENING.discard(tid)


def test_a_reply_owed_on_a_general_task_with_a_conversation_already_starts_nothing():
    s = store(); tid = general_ask(s)
    with mock.patch.object(general, 'history', return_value=[{'role': 'user', 'content': 'earlier'}]):
        _rv, spawned, went = handed(s, tid)
    assert not went and spawned == [] and not s.task_has_tag(tid, ingest.REPLY_TAG) and tid not in general.OPENING



@pytest.mark.parametrize('where', ['_reads_quick', 'has_room'])
def test_a_start_that_fails_before_it_opens_lets_the_hold_go(where):
    s = store(); tid = general_ask(s); general.OPENING.add(tid)
    with mock.patch.object(ingest, '_reads_quick', return_value=False), \
         mock.patch.object(ingest, where, side_effect=RuntimeError('the queue is unreadable')), pytest.raises(RuntimeError):
        ingest._auto_general(s, tid)
    assert tid not in general.OPENING
