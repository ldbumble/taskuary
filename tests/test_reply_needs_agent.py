"""A reply that needs work gets an agent, never a placeholder (the owner, 2026-10-28).

The shapes that pinned it, with invented people: a reply task's thread got a second mail triage judged work for an agent, the join
dropped that verdict, and the tool-less writer drafted "I have to look into it and will send that separately"; a colleague pasted a
long draft update asking for thoughts and got "I'll review this and send you my thoughts." Now: an agent verdict joining a reply task
starts that agent (work it out, then draft the reply for the owner's Send); a writer that cannot answer says NEEDS and the task goes to
the general agent; a placeholder is never a draft; why no agent started is always written; a quick fact is still drafted at once.
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
    assert spawned == ['_auto_draft'] and s.get_task(out['task_id'])['Kind'] == 'reply'
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
    assert '"offer": null' in triage.SHIPPED and 'offer' in triage.verdict_schema([], None, [], [])['schema']['properties']


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
    assert spawned == ['_auto_general']                                              # the agent - and no tool-less redraft beside it
    assert any('needs the assistant before it can be answered' in x and 'drafts the reply for your Send' in x for x in lines(s, tid))
    assert 'REPLY OWED to Erin Blake' in ingest.reply_job(s, tid)


def test_a_joining_coding_verdict_takes_its_repository_and_starts_the_coding_agent():
    s = store(); tid = reply_task(s)
    with mock.patch.object(ingest, 'repo_candidates', return_value=[{'repo': 'northwind/ledger', 'about': 'invoicing'}]):
        _out, spawned = ingested(s, mail(**WORK), says(intent='task', kind='coding', repository='northwind/ledger', repo_reason='the invoice code',
                                                        title='Invoice total bug', needs_repo_choice=False))
    assert s.get_task(tid)['Kind'] == 'coding' and s.task_has_tag(tid, f'{ingest.TRIAGE_REPO_TAG}northwind/ledger')
    assert spawned == ['_auto_code']


def test_the_started_assistant_is_told_the_reply_job():
    s = store(); tid = reply_task(s)
    ingested(s, mail(**WORK), says(intent='task', kind='general'))
    ses = mock.Mock()
    with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'history', return_value=[]):
        assert ingest._start_general(s, tid)
    assert ses.send_prompt.call_args[0][0].startswith('THIS TASK IS A REPLY OWED to Erin Blake')


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


# ── ruling 3: no placeholder drafts; NEEDS hands the reply to the general agent ────────────────────────────────────────────
def writer(*said):
    calls, said = [], list(said)
    def llm(system, user, **k): calls.append({'system': system, 'user': user, **k}); return said.pop(0) if len(said) > 1 else said[0]
    return llm, calls


def drafted(s, tid, llm):
    rv = s.pending_review(tid, kind='draft')
    with mock.patch('taskuary.llm.build_llm', lambda *a, **k: llm), mock.patch('taskuary.ingest._spawn') as spawn, \
         mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        ingest._auto_draft(s, tid, rv['ReviewId'])
    return s.get_review(rv['ReviewId']), [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def test_the_writer_is_told_never_to_promise_and_to_say_needs():
    assert 'never write a placeholder' in responder.NOT_YET and responder.NEEDS in responder.NOT_YET
    assert 'you will pick it up' not in responder.NOT_YET


def test_needs_leaves_no_draft_and_starts_the_general_agent():
    s = store(); tid = reply_task(s)
    rv, spawned = drafted(s, tid, writer('NEEDS: the October invoice run, to see why the total moved')[0])
    assert not (rv.get('DraftText') or '').strip() and 'needs the October invoice run' in rv['DraftNeeds'] and not rv.get('DraftError')
    assert spawned == ['_auto_general'] and s.get_task(tid)['Kind'] == 'general'
    assert 'the reply writer said it needs the October invoice run' in ingest.reply_job(s, tid)


def test_a_short_mail_the_writer_cannot_answer_is_no_draft():
    """The writer says it can't answer (its NEEDS) - its judgement, not a phrase list (the owner, 2026-10-28) - so no draft is
    parked and the work goes to the agent."""
    s = store(); tid = reply_task(s)
    llm, calls = writer('NEEDS: the export logs, to see why the total moved')
    rv, spawned = drafted(s, tid, llm)
    assert len(calls) == 1 and not (rv.get('DraftText') or '').strip()
    assert 'needs the export logs' in rv['DraftNeeds'] and spawned == ['_auto_general']


def test_a_reply_it_cannot_write_with_auto_start_off_lights_send_to_agent_with_the_reason():
    s = store(general_auto_enabled='0'); tid = reply_task(s)
    rv, spawned = drafted(s, tid, writer('NEEDS: the export logs')[0])
    assert spawned == [] and s.get_task(tid)['Kind'] == 'reply'
    assert 'An agent can work it out' in rv['DraftNeeds']
    assert any(x.startswith('No agent started:') for x in lines(s, tid))


def test_a_quick_fact_is_still_drafted_at_once():
    s = store(); tid = reply_task(s)
    rv, spawned = drafted(s, tid, writer('Hi Erin,\n\nYes - Tuesday from 2 works for me.\n\nAlex')[0])
    assert 'Tuesday from 2 works' in rv['DraftText'] and not rv.get('DraftError') and not rv.get('DraftNeeds') and spawned == []
    assert s.get_task(tid)['Kind'] == 'reply'


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
        assert s.get_task(tid)['Kind'] == 'general' and ingest.offer_of(s, tid) == ''
        assert c.post(f'/api/tasks/{tid}/offer').status_code == 409                 # taken once
