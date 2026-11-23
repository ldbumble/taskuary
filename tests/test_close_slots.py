"""A task says what closes it: output slots on the checklist (spec 2026-10-05-task-close-slots-design.md).

The shape: one ask, four addressed drafts, each approved on its own. None of them closes the task - Mark done does (2026-10-18).
"""
import json
from unittest import mock

import pytest

from taskuary import slots
from taskuary.store import MemoryStore

FOUR = [{'to': 'paula@northwind.example', 'about': 'where tab 1 stands'}, {'to': 'ray@northwind.example', 'about': 'where tab 2 stands'},
        {'to': 'Gail Moreno', 'about': 'where tab 3 stands'}, {'to': 'erin@northwind.example', 'about': 'where tab 4 stands'}]


@pytest.fixture
def s():
    # ...an AI to start on: the one start (concierge.handoff_task) refuses before it makes anything without one
    with mock.patch('taskuary.capabilities.has_ai', return_value=True):
        v = MemoryStore(); yield v; v.close()


def typed(s, outputs=FOUR):
    tid = s.create_task({'Title': 'Check the four tabs', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    s.set_task_checklist(tid, ['Check the four tabs'], 'owner')
    slots.add(s, tid, outputs, 'owner')
    return tid


def test_clean_keeps_known_kinds_and_drops_junk():
    got = slots.clean([{'to': 'a@example.com', 'about': 'x'}, {'to': '', 'about': 'y'}, 'nope', {'about': 'z'},
                       {'to': 'b@example.com', 'about': 'w', 'kind': 'fax'}])
    assert [g['out'] for g in got] == [{'kind': 'email', 'to': 'a@example.com', 'subject': ''}]


def test_slots_ride_on_the_checklist(s):
    tid = typed(s)
    items = s.task_checklist(tid)
    assert len(items) == 5 and items[0].get('out') is None
    assert [i['out']['to'] for i in items[1:]] == [o['to'] for o in FOUR]
    assert len(slots.open_(s, tid)) == 4


def test_a_name_is_kept_as_said_never_guessed_into_an_address(s):
    tid = typed(s)
    assert slots.open_(s, tid)[2]['out']['to'] == 'Gail Moreno'


def test_rewording_another_item_keeps_the_slots(s):
    tid = typed(s); before = s.task_checklist(tid)
    slots.mark(s, tid, before[1]['id'], rid=77)
    s.set_task_checklist(tid, ['Check all four tabs'] + [i['text'] for i in before[1:]], 'owner')
    after = s.task_checklist(tid)
    assert after[1]['out'] == before[1]['out'] and after[1]['rid'] == 77


def test_the_agent_sees_its_slots_and_how_to_fill_them(s):
    tid = typed(s); sid = slots.open_(s, tid)[0]['id']
    md = s.checklist_markdown(tid)
    assert 'email to paula@northwind.example' in md and f'--slot {sid}' in md


def test_a_slot_draft_is_never_the_tasks_reply(s):
    tid = typed(s)
    s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': 'hi',
                  'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'subject': 'Tab 1', 'slot': 'x'})})
    assert s.pending_review(tid) is None and s.pending_review(tid, live_only=False) is None


# ── closing waits for every slot ─────────────────────────────────────────────────────────
from taskuary import wrapup, operations, outbound, verdicts

SENT = {'channel': 'email', 'to': ['x@example.com'], 'cc': []}


def draft(s, tid, i, text='Tab is fine.'):
    it = slots.all_(s, tid)[i]
    rid = s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': text,
                        'Deliver': json.dumps({'channel': 'email', 'to': [it['out']['to']], 'subject': 'Tab', 'slot': it['id'],
                                               'seen': slots.seen(s, tid)})})
    slots.mark(s, tid, it['id'], rid=rid)
    return rid


def approve(s, rid):
    with mock.patch('taskuary.outbound.send_out', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learning.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def mail_task(s):
    from tests.test_review_delivery_safety import make_review
    return make_review(s, task_kind='reply')


def send_reply(s, rid):
    with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learning.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def test_four_slots_stay_open_through_all_four_sends(s):
    tid = typed(s, [*FOUR[:2], {'to': 'gail@northwind.example', 'about': 'where tab 3 stands'}, FOUR[3]]); rids = [draft(s, tid, n) for n in range(4)]
    for rid in rids[:3]:
        assert approve(s, rid)['ok'] and s.get_task(tid)['Status'] != 'done'
    assert s.get_review(rids[3])['Status'] == 'pending'
    assert approve(s, rids[3])['ok'] and s.get_task(tid)['Status'] == 'open'      # the last send closes nothing either
    assert all(i['done'] for i in slots.all_(s, tid))


def test_a_rejected_slot_is_dropped_and_counts_as_settled(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    with mock.patch('taskuary.learning.learn_from'): verdicts.decide(s, s.get_review(a), 'reject')
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'
    approve(s, b)
    assert s.get_task(tid)['Status'] == 'open' and all(i['done'] for i in slots.all_(s, tid))


@pytest.mark.parametrize('verb', ['no_reply', 'close_unsent'])
def test_not_sending_one_slot_drops_that_slot_not_the_task(s, verb):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    with mock.patch('taskuary.learning.learn_from'): verdicts.decide(s, s.get_review(a), verb)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'
    assert [i['done'] for i in slots.all_(s, tid)] == [True, False]


def test_a_reply_and_slots_all_sent_still_leave_the_task_open(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    send_reply(s, reply)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(a)['Status'] == 'pending'
    approve(s, a)
    assert s.get_task(tid)['Status'] != 'done'


def test_a_slot_sent_before_the_reply_leaves_the_reply_waiting(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    approve(s, a)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(reply)['Status'] == 'pending'


def test_a_task_without_slots_stays_open_after_its_reply(s):
    tid, mid, reply = mail_task(s)
    send_reply(s, reply)
    assert s.get_task(tid)['Status'] != 'done'


def test_the_closeout_redirect_never_sends_a_slot_as_the_reply(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    s.decide_review(reply, 'rejected', None, 'owner', 'gone')
    co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': 'merge',
                       'Deliver': json.dumps({'action': 'merge_pr'})})
    with mock.patch('taskuary.proposals.execute', return_value={'ok': True}), mock.patch('taskuary.proposals._action', return_value='merge_pr'), \
         mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch('taskuary.learning.learn_from'):
        verdicts.decide(s, s.get_review(co), 'approve', reply_text='thanks')
    assert not sent.called and s.get_review(a)['Status'] == 'pending'


def test_a_new_inbound_message_does_not_block_a_slot(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    later_inbound(s, tid)
    assert verdicts.context_moved(s, s.get_review(a))[0] is False


def test_a_finished_run_with_slots_open_waits_instead_of_closing(s):
    tid = typed(s, FOUR[:2]); draft(s, tid, 0)
    prev, wrapup.REFRESH = wrapup.REFRESH, None
    try: wrapup.finish(s, tid, {'summary': 'checked', 'outcome': 'did_work'})
    finally: wrapup.REFRESH = prev
    assert s.get_task(tid)['Status'] == 'waiting'
    assert [r['Status'] for r in s._rows('SELECT Status FROM review WHERE TaskId=?', (tid,))] == ['pending']


# ── the agent fills slots ────────────────────────────────────────────────────────────────
from taskuary import selfclose


def test_the_agent_fills_a_slot_by_id(s):
    tid = typed(s, FOUR[:2]); sid = slots.open_(s, tid)[1]['id']
    out = slots.draft(s, tid, 'Tab 2 is short by one feed.', slot=sid, agent='assistant')
    rv = s.get_review(out['review_id'])
    assert (rv['Kind'], rv['Status'], rv['DraftBy'], slots.of_review(rv)) == (slots.KIND, 'pending', 'agent:assistant', sid)
    assert json.loads(rv['Deliver'])['to'] == ['ray@northwind.example'] and slots.all_(s, tid)[1]['rid'] == rv['ReviewId']


def test_by_recipient_and_again_rewrites_the_same_draft_and_says_so_and_new_is_a_second_letter(s):
    """Saved to one person twice in its turn, a letter is rewritten in place (no duplicate copy - the owner) - and, the card audit 2026-11-22,
    the agent is told it rewrote it: told nothing, it said two emails were ready. A second, different letter to them (legit, the owner
    2026-11-13) is asked for with slot "new"."""
    tid = typed(s, FOUR[:1])
    a = slots.draft(s, tid, 'first', to='PAULA@northwind.example'); b = slots.draft(s, tid, 'second', to='paula@northwind.example')
    assert a['review_id'] == b['review_id'] and s.get_review(a['review_id'])['DraftText'] == 'second'
    assert 'rewrote' not in a and b['rewrote'] == a['review_id'] and 'slot="new"' in b['says']
    c = slots.draft(s, tid, 'And the venue for Friday.', to='paula@northwind.example', slot='new')
    assert c['ok'] and c['review_id'] != a['review_id'] and 'rewrote' not in c
    assert s.get_review(a['review_id'])['Status'] == s.get_review(c['review_id'])['Status'] == 'pending'


def test_a_chat_id_is_no_mailbox(s):
    # the night run, 2026-11-09: two emails were filed to whatsapp:1555... - a person known only by their chat
    tid = typed(s, FOUR[:1])
    out = slots.draft(s, tid, 'Your Q3 figures, please.', to='whatsapp:15550004444', subject='Q3 figures')
    assert not out['ok'] and 'is a chat, not a mailbox' in out['why']
    sid = slots.add(s, tid, [{'to': 'whatsapp:15550003333', 'about': 'status', 'kind': 'email'}], 'triage')[0]['id']    # ...or triage's slot named it
    out = slots.draft(s, tid, 'Where it stands.', slot=sid)
    assert not out['ok'] and 'whatsapp:15550003333 is a chat' in out['why']


def test_an_unmatched_recipient_adds_a_slot_and_says_so(s):
    tid = typed(s, FOUR[:1])
    out = slots.draft(s, tid, 'Tab 5 too.', to='omar@northwind.example', subject='Tab 5')
    assert out['added'] and len(slots.all_(s, tid)) == 2
    assert any('added' in c['Body'] for c in s.list_comments(tid))


def test_empty_text_or_nobody_is_refused(s):
    tid = typed(s, FOUR[:1])
    assert not slots.draft(s, tid, '  ', slot=slots.open_(s, tid)[0]['id'])['ok']
    assert not slots.draft(s, tid, 'hi')['ok']
    # ...and a recipient with no words files nothing, and says the two ways on (the owner, 2026-11-10: "just ask what should i reply?")
    out = slots.draft(s, tid, ' ', to='office@vendor.example')
    assert 'write the email in `text`, or ask the owner what it should say' in out['why']
    assert [i['out']['to'] for i in slots.open_(s, tid)] == ['paula@northwind.example']


def test_a_drafted_slot_on_a_mail_task_still_sends(s):
    tid, mid, _ = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner')
    out = slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')
    assert verdicts.context_moved(s, s.get_review(out['review_id']))[0] is False
    assert approve(s, out['review_id'])['ok']


def test_an_agent_email_never_goes_out_headed_with_the_task_title(s):
    tid = typed(s, FOUR[:2]); subj = lambda out: json.loads(s.get_review(out['review_id'])['Deliver'])['subject']
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Tab 2 numbers', 'FromEmail': 'ray@northwind.example',
                   'BodyText': 'Can you check tab 2?', 'SentAt': '2026-10-01 09:00:00', 'Status': 'routed'})
    assert subj(slots.draft(s, tid, 'Fine.', to='omar@northwind.example', subject='Lunch on Friday')) == 'Lunch on Friday'
    assert subj(slots.draft(s, tid, 'Tab 2 is fine.', to='ray@northwind.example')) == 'Re: Tab 2 numbers'
    assert subj(slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')) == 'Where tab 1 stands'
    assert 'Check the four tabs' not in {subj(slots.draft(s, tid, 'Hi.', to='gail@northwind.example'))}
    from taskuary import agenttools
    # ...whether one email or many in `items`: each carries its own subject (bulkcard.py)
    one, many = agenttools.TOOLS['propose_email'][2]['anyOf']
    assert {'to', 'subject', 'text'} <= set(one['required']) and many == {'required': ['items']}
    assert {'to', 'subject', 'text'} <= set(agenttools.TOOLS['propose_email'][2]['properties']['items']['items']['required'])


def test_a_chats_checklist_names_the_slot_and_a_coding_sessions_the_command(s):
    # one road for an email (the agent walk, 2026-11-10): the chat's copy names the line by its id - its own brief says how to fill it -
    # and the command stays where a session's only hands are its shell (the coding seed)
    from taskuary import general
    tid = s.create_task({'Title': 'Check the four tabs', 'Kind': 'general', 'Status': 'open'}, 'owner')
    sid = slots.add(s, tid, FOUR[:1], 'owner')[0]['id']
    chat, coding = s.checklist_markdown(tid, ids=True, shell=False), s.checklist_markdown(tid, ids=True)
    assert f'slot {sid} - to draft' in chat and 'taskuary' not in chat and f'taskuary --slot {sid} --draft' in coding
    handed = ' '.join(general._prompt(s, tid))
    assert handed.count(f'slot {sid} - to draft') == 1 and 'taskuary --slot' not in handed
    slots.draft(s, tid, 'Tab 1 is fine.', slot=sid)
    assert f'slot {sid} - drafted' in s.checklist_markdown(tid, ids=True, shell=False)




def test_the_chat_block_is_read_and_taken_out():
    text, found = selfclose.draft_markers('Done.\n[[TASKUARY-DRAFT to=paula@northwind.example subject="Tab 1"]]Tab 1 is fine.[[/TASKUARY-DRAFT]]')
    assert text == 'Done.' and found == [({'to': 'paula@northwind.example', 'subject': 'Tab 1'}, 'Tab 1 is fine.')]


def test_the_endpoint_files_the_draft_on_the_sessions_own_task(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    tid = typed(s, FOUR[:1])
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only', return_value=None):
        r = TestClient(server.app).post('/api/agent/draft', json={'task_id': tid, 'text': 'hi', 'to': 'paula@northwind.example'})
    assert r.json()['ok'] and slots.all_(s, tid)[0]['rid']


# ── triage and the assistant say what closes a task ──────────────────────────────────────
from taskuary import concierge, triage


def test_triage_lists_no_recipients_for_a_message():
    # the owner, 2026-11-10: "it created reply with nothing in it" - triage's "email to <them>, to draft" stood under the agent's turn with no
    # words. Who else is written to is the agent's to judge; the owner's own typed ask is his to word
    assert 'outputs' not in triage.verdict_schema()['schema']['properties']
    assert '"outputs"' not in triage.SHIPPED and '**outputs**' not in triage.SHIPPED


class Inline:                     # threading.Thread, run where it is started
    def __init__(self, target=None, args=(), **k): self.go = lambda: target(*args)
    def start(self): self.go()


def handoff(s, brain):
    session = mock.Mock()
    with mock.patch('taskuary.concierge.brain', **brain), mock.patch('taskuary.general.start_session', return_value=session), \
         mock.patch('taskuary.concierge.threading.Thread', Inline):
        made = concierge.handoff_task(s, 'Check the four tabs and draft an email to each owner', kind='general')
    return made, session


def test_a_new_ask_takes_the_one_reading_triage_made_and_its_agent_is_prompted_at_once(s):
    """Walk 2, 2026-11-21: a second model reading of New's words held its agent 46 s of a 61 s answer. Triage's reading - the one that asked
    whether the work was open already - is the task's; no model is asked again, and no email is listed for the agent before it writes one
    (an email nobody wrote is no debt)."""
    from taskuary import ingest
    seen, asked = [], []
    judge = lambda store, msg, llm, *a, **k: ({'intent': 'task', 'same_as': None, 'summary': 'Check the four tabs', 'checklist': ['Tab 1', 'Tab 2']}, {})
    session = mock.Mock(); session.send_prompt.side_effect = lambda *a, **k: seen.append(len(s.task_checklist(made_box[0])))
    made_box = []
    with mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: ''), mock.patch.object(ingest, 'judge', judge),          mock.patch('taskuary.concierge.brain', return_value=lambda *a, **k: asked.append(a) or '{}'),          mock.patch('taskuary.general.start_session', side_effect=lambda st, tid, **k: made_box.append(tid) or session),          mock.patch('taskuary.concierge.threading.Thread', Inline):
        made = concierge.handoff_task(s, 'Check the four tabs and draft an email to each owner', kind='general')
    assert seen == [1] and asked == [] and slots.open_(s, made['taskId']) == []      # ...his words, the one box New gives it (setup_task)


def test_a_handoff_reads_at_work_from_the_moment_it_is_made_until_its_first_turn_ends(s):
    """The bug hunt, 2026-11-12: New's box made an agent's job and opened its task at once - and for three seconds, while the job's outputs
    were read before the first turn, the task said "agent done" with Mark done lit, over an agent that had not begun. From the start it is at
    work, and the first turn's end lets it go."""
    from taskuary import general
    seen = []
    def llm(sys, user, **k): seen.append(('reading', general.working(s, made_box[0]))); return json.dumps({'summary': 's', 'checklist': [], 'outputs': []})
    # ...and no second reading stands before it (walk 2, 2026-11-21): the turn is the first thing, at work
    session, made_box = mock.Mock(busy=False), []
    session.send_prompt.side_effect = lambda text, **k: seen.append(('turn', general.working(s, made_box[0])))
    with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch('taskuary.general.start_session', side_effect=lambda st, tid, **k: made_box.append(tid) or session), \
         mock.patch('taskuary.general._live_of', return_value=None), mock.patch('taskuary.concierge.threading.Thread', Inline):
        concierge.handoff_task(s, 'Find three cafes near the office that cater lunch for 12', kind='general')
        assert seen == [('turn', True)] and not general.working(s, made_box[0])


def test_an_agent_the_assistant_starts_carries_his_words_alone_as_his_and_the_talk_before_them_as_taskuarys_brief(s):
    """Recorded on the real CLI, 2026-11-15: "start an agent to find two venues" made the task, and its bubble in his name read his ask
    followed by "What we were talking about: ..." - the Assistant's chat, which he never typed there."""
    from taskuary import general
    dock = general.dock_task(s, 'owner')[0]['TaskId']
    s.add_comment(dock, 'owner', general.USER_TYPE, 'remember that payroll questions go to Gail')
    s.add_comment(dock, 'assistant', general.ASSISTANT_TYPE, 'Got it - payroll questions go to Gail.')
    s.add_comment(dock, 'owner', general.USER_TYPE, 'start an agent to find two venues')
    told, session = [], mock.Mock(busy=False)
    session.send_prompt.side_effect = lambda text, **k: told.append((text, k))
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': [], 'outputs': []})
    with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch('taskuary.general.start_session', return_value=session),          mock.patch('taskuary.general._live_of', return_value=None), mock.patch('taskuary.concierge.threading.Thread', Inline):
        made = concierge.handoff_task(s, 'Find two venues for a 40-person offsite', kind='general', dock_tid=dock)
    own = ' '.join(str(c.get('Body') or '') for c in s.list_comments(made['taskId'], internal=True)) + ' ' + str(s.get_task(made['taskId']).get('Summary') or '')
    assert 'What we were talking about' not in own and 'payroll' not in own, own
    assert told and 'What we were talking about' in told[0][0] and told[0][1].get('brief') is True


def test_a_task_the_assistant_starts_is_his_sentence_as_typed_and_its_polished_ask_reaches_the_agent_as_taskuarys_brief(s):
    """The live shape, 2026-11-15: he typed a short sloppy line into the Assistant; its model called the hand-off with a polished ask
    and a sentence he never said ("Tell me whether it exists, where it is, and its exact name."), and the new task drew that as "You" -
    its own message, its Summary and its checklist. "i only typed this? did the agent add on more to my prompt???" """
    from taskuary import general, terminal
    his = 'can you login to the portal and see if there is report named REvenue Journal'
    polished = ('Log in to the portal and check whether there is a report named Revenue Journal. '
                'Tell me whether it exists, where it is, and its exact name.')
    call = 'On it.\nCALL: ' + json.dumps({'kind': 'task.create_from_text', 'params': {'kind': 'general', 'text': polished}})
    told, session = [], mock.Mock(busy=False)
    session.send_prompt.side_effect = lambda text, **k: told.append((text, k))
    fast = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': [], 'outputs': []})
    with mock.patch('taskuary.capabilities.has_ai', return_value=True), mock.patch('taskuary.concierge.brain', return_value=fast), \
         mock.patch('taskuary.general.start_session', return_value=session), mock.patch('taskuary.general._live_of', return_value=None), \
         mock.patch('taskuary.concierge.threading.Thread', Inline), mock.patch.object(terminal, 'live_sessions', return_value=[]), \
         mock.patch('taskuary.server.store', s):
        out = concierge.say(s, his, llm=lambda *a, **k: call)
    tid = int(out['open'].split('=')[1])
    t, rows = s.get_task(tid), s.list_comments(tid, internal=True)
    owners = [str(c.get('Body') or '') for c in rows if c.get('Actor') == 'owner']
    assert owners and all(his in b for b in owners) and not any('Tell me whether' in b for b in owners), owners
    assert t['Summary'] == his and [i['text'] for i in s.task_checklist(tid)][:1] == [his]
    assert 'Tell me whether' not in t['Title']                       # no title named: his words name it, not the rewording
    from taskuary import ownwork
    ownwork.ensure(s, tid)
    assert ownwork.row_for(s, tid)['BodyText'] == his               # the row signed "You"
    # ...and what the Assistant made of it still reaches the agent - as Taskuary's brief, never a line in his name
    assert told and 'Tell me whether it exists' in told[0][0] and told[0][1].get('brief') is True


def test_a_coding_hand_off_and_a_walk_through_keep_his_words_as_his_and_file_the_rewording_as_taskuarys(s):
    from taskuary import brief, general
    his, polished = 'fix the export thing erin hit', 'Fix the CSV export crash Erin Blake reported. Add a test that reproduces it.'
    s.set_setting('developer_mode', '1', 'test')              # ...a coding hand-off is a coding agent's only in Developer mode
    with mock.patch('taskuary.ingest._spawn'), mock.patch('taskuary.concierge._handoff_title', return_value='Export crash'),          mock.patch('taskuary.capabilities.can_code', return_value=True):
        coding = concierge.handoff_task(s, polished, kind='coding', said=his)['taskId']
    walk = concierge.setup_task(s, polished, said=his)['taskId']
    for tid in (coding, walk):
        mine = [str(c.get('Body') or '') for c in s.list_comments(tid, internal=True) if c.get('Actor') == 'owner']
        assert s.get_task(tid)['Summary'] == his and mine and all(his in b and 'Add a test' not in b for b in mine), mine
    assert 'Add a test' in brief.handoff(s, coding)                 # the coding agent reads it as Taskuary's (terminal seed)
    briefs = [c for c in s.list_comments(walk, internal=True) if general.is_brief(c)]
    assert [c['Body'] for c in briefs] == [polished]                # the walk hears it as Taskuary's turn


def test_a_start_the_model_reads_as_open_work_goes_to_that_tasks_agent_never_a_second_task(s):
    """One job is one task at every door (the owner's live app, 2026-11-18): the open tasks go to the model before a task is made, and the
    same work hears his line on its own task. Triage is what reads it (ingest.same_work), as it reads every message."""
    from taskuary import general
    there = s.create_task({'Title': 'Find two venues for the offsite', 'Kind': 'general', 'Status': 'open'}, 'owner')
    told, had = [], len(s.list_tasks(None))
    with mock.patch('taskuary.capabilities.has_ai', return_value=True), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: ''),          mock.patch('taskuary.ingest.judge', return_value=({'intent': 'task', 'same_as': there}, {})),          mock.patch.object(general, 'take_line', lambda st, tid, text, files=None, actor='owner', **k: told.append((tid, text))),          mock.patch('taskuary.general.start_session') as began:
        made = concierge.handoff_task(s, 'Find venues for the 40-person offsite too', kind='general')
    assert (made['taskId'], made.get('joined')) == (there, True) and len(s.list_tasks(None)) == had and not began.called
    assert told == [(there, 'Find venues for the 40-person offsite too')]


def test_a_handoff_whose_brain_fails_is_made_anyway(s):
    made, session = handoff(s, {'side_effect': RuntimeError('no brain')})
    assert s.get_task(made['taskId']) and slots.all_(s, made['taskId']) == [] and session.send_prompt.called


def test_a_triaged_message_that_asks_for_emails_gets_no_slots():
    from datetime import datetime
    from fastapi.testclient import TestClient
    from taskuary import server
    verdict = json.dumps({'intent': 'task', 'kind': 'task', 'why': 'asks for two updates', 'title': 'Send the tab updates',
                          'summary': 'Marcus Reed wants Erin and Gail told where the tabs stand.', 'checklist': ['Tell Erin and Gail'],
                          'outputs': [{'to': 'erin@northwind.example', 'about': 'the tabs'}, {'to': 'Gail Moreno', 'about': 'the tabs'}]})
    st, prev = MemoryStore(), server.store
    server.store = st; st.set_setting('coding_auto_enabled', '0', 'test')
    try:
        body = {'external_id': 'slots-1', 'channel': 'teams', 'conversation_id': 'teams:19:slots@thread.v2', 'from_name': 'Marcus Reed',
                'subject': 'Tab updates', 'body': 'Could you let Erin and Gail know where each tab stands?',
                'sent_at': datetime.now().isoformat(sep=' ', timespec='seconds')}
        with mock.patch('taskuary.server._llm', return_value=lambda sys_, usr_, **kw: verdict):
            TestClient(server.app).post('/api/ingest/push', json=body)
        tid = next(t['TaskId'] for t in st.list_tasks(active_only=True))
        assert slots.all_(st, tid) == [], 'the agent decides who else is written to'
    finally: server.store = prev


def test_an_output_to_the_sender_is_their_reply_never_an_email(s):
    # The prompt says "a reply to the sender is never an output" and the model wrote one anyway - on a chat message, so
    # the close-out showed the reply twice: once for the thread, once as an email opening "Hi Erin," (2026-10-06).
    # The sender is matched as a person: "Last, First at Company" is the same Erin as "Erin Blake".
    tid = s.create_task({'Title': 'Fix the logins', 'Kind': 'general', 'Status': 'open', 'Source': 'teams'}, 'router')
    got = slots.add(s, tid, [{'to': 'Erin Blake', 'about': 'it is fixed'}, {'to': 'erin@northwind.example', 'about': 'again'},
                             {'to': 'Gail Moreno', 'about': 'the cause'}], 'triage',
                    sender={'name': 'Blake, Erin at Northwind', 'address': 'erin@northwind.example'})
    assert [i['out']['to'] for i in got] == ['Gail Moreno']
    # ...and somebody who only shares a first name is not the sender
    assert [i['out']['to'] for i in slots.add(s, tid, [{'to': 'Erin Vance', 'about': 'x'}], 'triage', sender={'name': 'Erin Blake'})] == ['Erin Vance']


def test_the_rail_shows_one_row_per_task_with_its_count(s):
    from taskuary import funnel
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    rows = [r for r in funnel.build(s)['items'] if r.get('tid') == tid]
    # the NEWEST draft leads
    assert len(rows) == 1 and rows[0]['rid'] == b and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why']
    approve(s, b)
    rows = [r for r in funnel.build(s)['items'] if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['rid'] == a and '1 email ' in rows[0]['why']


def test_a_task_already_on_the_rail_is_not_listed_again_for_its_emails(s):
    # A task with a reply drafted AND an email drafted sat on the rail twice - its reply row and an email row - and so
    # did a task whose own row was its message (2026-10-06). The task's card lists its emails; the rail lists the task.
    from taskuary import funnel
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); draft(s, tid, 0)
    assert len([i for i in funnel.build(s)['items'] if i.get('tid') == tid]) == 1
    # ...and a task with nothing else on the rail still gets its one email row
    other = typed(s, FOUR[1:2]); draft(s, other, 0)
    assert len([i for i in funnel.build(s)['items'] if i.get('tid') == other]) == 1


def test_the_processing_rail_calls_them_emails_not_a_reply():
    import sys, os; sys.path.insert(0, os.path.dirname(__file__))
    from taskuary import funnel, processing_unread
    from test_funnel import ago, store
    st = store(); tid = typed(st, FOUR[:2]); draft(st, tid, 0); draft(st, tid, 1)
    def rail():
        st.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return processing_unread.build(st, live_state=[])['items']
    rail(); st.activate_processing_reads(fixed_now=ago(0), live_state=[])
    rows = [r for r in rail() if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why'] and 'reply' not in rows[0]['why']


# ── final review: the seams where slots meet older roads ─────────────────────────────────
def later_inbound(s, tid):
    s.add_message({'TaskId': tid, 'ExternalId': f'graph:later-{tid}', 'ConversationId': f'fixture-thread-{tid}', 'Channel': 'email',
                   'SourceName': 'alex@example.com', 'Subject': 'Repair the export', 'FromEmail': 'erin@example.com',
                   'BodyText': 'Actually, tab 1 changed.', 'SentAt': '2026-10-01 10:00:00', 'Status': 'routed', 'Direction': 'in'})


def api(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    return TestClient(server.app), mock.patch.object(server, 'store', s)


def test_a_slot_is_never_rewritten_into_a_reply_and_sends_the_words_shown(s):
    tid, mid, _ = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner')
    rid = slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')['review_id']
    later_inbound(s, tid)
    c, p = api(s)
    with p, mock.patch('taskuary.server._refresh_chat_context', return_value={}), mock.patch('taskuary.responder.write_draft') as rewrite, \
         mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learning.learn_from'):
        out = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve'}).json()
    assert out.get('ok') and not rewrite.called and sent.called and s.get_review(rid)['DraftText'] == 'Tab 1 is fine.'


def test_the_redraft_door_refuses_a_slot(s):
    tid = typed(s, FOUR[:1]); rid = slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')['review_id']
    c, p = api(s)
    with p: r = c.post(f'/api/reviews/{rid}/draft', json={})
    assert r.status_code == 422 and s.get_review(rid)['DraftText'] == 'Tab 1 is fine.'


def test_the_last_slot_never_closes_past_a_pending_closeout(s):
    tid = typed(s, FOUR[:1]); a = draft(s, tid, 0)
    co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': 'merge', 'Deliver': json.dumps({'action': 'merge_pr'})})
    with mock.patch('taskuary.proposals._action', return_value='merge_pr'): approve(s, a)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(co)['Status'] == 'pending'


def test_the_last_slot_never_closes_while_an_agent_works(s):
    tid = typed(s, FOUR[:1]); a = draft(s, tid, 0)
    with mock.patch('taskuary.funnel.working_tids', return_value={tid}): approve(s, a)
    assert s.get_task(tid)['Status'] != 'done'


def test_the_last_slot_never_closes_past_a_held_reply(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    s.hold_reviews(tid, 'agent working')
    approve(s, a)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(reply)['Status'] == 'held'


def test_a_mail_tasks_slots_show_on_the_processing_rail():
    import sys, os; sys.path.insert(0, os.path.dirname(__file__))
    from taskuary import funnel, processing_unread
    from test_funnel import ago, mail, store
    st = store(); mid = mail(st, 'Tab updates', who='Marcus Reed', email='marcus@northwind.example', body='Tell Paula and Ray where the tabs stand.')
    tid = st.create_task({'Title': 'Tab updates', 'Kind': 'task', 'Status': 'open'}, 'triage')
    st._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mid))
    slots.add(st, tid, FOUR[:2], 'triage'); slots.draft(st, tid, 'a', to=FOUR[0]['to']); slots.draft(st, tid, 'b', to=FOUR[1]['to'])
    def rail():
        st.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return processing_unread.build(st, live_state=[])['items']
    rail(); st.activate_processing_reads(fixed_now=ago(0), live_state=[])
    rows = [r for r in rail() if r.get('tid') == tid]
    assert rows and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why']


def test_ticking_a_drafted_slot_drops_its_draft(s):
    tid = typed(s, FOUR[:2]); a = draft(s, tid, 0); sid = slots.all_(s, tid)[0]['id']
    c, p = api(s)
    with p, mock.patch('taskuary.learning.learn_from'): c.patch(f'/api/tasks/{tid}/checklist/{sid}', json={'done': True})
    assert s.get_review(a)['Status'] == 'rejected' and slots.all_(s, tid)[0]['done']


def test_dropping_the_last_undrafted_slot_leaves_a_typed_task_open(s):
    tid = typed(s, FOUR[:1]); sid = slots.all_(s, tid)[0]['id']
    c, p = api(s)
    with p: r = c.patch(f'/api/tasks/{tid}/checklist/{sid}', json={'done': True}).json()
    assert r['closed'] is False and s.get_task(tid)['Status'] == 'open' and slots.all_(s, tid)[0]['done']


def test_the_assistants_drop_rejects_the_pending_draft(s):
    tid = typed(s, FOUR[:2]); a = draft(s, tid, 0)
    c, p = api(s)
    with p, mock.patch('taskuary.learning.learn_from'):
        pr = c.post('/api/operations', json={'kind': 'task.checklist', 'target': tid, 'params': {'drop': [FOUR[0]['to']]}}).json()
        c.post(f"/api/operations/{pr['id']}/execute", json={'version': pr['version']})
    assert s.get_review(a)['Status'] == 'rejected'


def test_the_printed_command_parses(s):
    import re, shlex, argparse
    tid = typed(s, FOUR[:1]); sid = slots.open_(s, tid)[0]['id']
    cmd = re.search(r'`(taskuary [^`]+)`', s.checklist_markdown(tid)).group(1)
    ap = argparse.ArgumentParser(); ap.add_argument('--draft'); ap.add_argument('--slot')
    a = ap.parse_args(shlex.split(cmd)[1:])
    assert a.slot == sid and a.draft == '<text>'


def test_the_phone_shows_a_slot_draft_with_its_recipient(s):
    from taskuary import remote_assistant
    tid = typed(s, FOUR[:1]); rid = slots.draft(s, tid, 'Tab 1 is fine.', to=FOUR[0]['to'])['review_id']
    said = remote_assistant._draft_text(s, {'rid': rid})
    assert 'Tab 1 is fine.' in said and FOUR[0]['to'] in said


def test_an_agent_added_email_is_marked(s):
    tid = typed(s, FOUR[:1])
    slots.draft(s, tid, 'x', to='omar@northwind.example')
    assert [i['out'].get('by') for i in slots.all_(s, tid)] == [None, 'agent']


def test_a_named_slot_takes_the_address_the_agent_found(s):
    tid = typed(s, FOUR[2:3]); sid = slots.open_(s, tid)[0]['id']
    slots.draft(s, tid, 'Tab 3 is fine.', slot=sid, to='gail@northwind.example')
    assert [i['out']['to'] for i in slots.all_(s, tid)] == ['gail@northwind.example']


def test_an_email_with_no_address_is_never_sent(s):
    tid = typed(s, FOUR[2:3]); sid = slots.open_(s, tid)[0]['id']
    rid = slots.draft(s, tid, 'Tab 3 is fine.', slot=sid)['review_id']
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch('taskuary.learning.learn_from'):
        out = verdicts.decide(s, s.get_review(rid), 'approve')
    assert not out['ok'] and not sent.called and 'address' in out['send_error']


# ── cleanup batch (2026-10-05) ───────────────────────────────────────────────────────────
def test_an_email_already_sent_is_not_owed_again(s):
    tid = typed(s, FOUR[:1]); a = draft(s, tid, 0); approve(s, a)
    s.update_task(tid, {'Status': 'open'}, 'owner')
    assert slots.add(s, tid, [{'to': FOUR[0]['to'], 'about': 'tab 1, said differently'}], 'triage') == []


def test_a_name_and_the_address_it_resolves_to_are_one_person(s):
    import json as _j
    s.add_message({'ExternalId': 'o1', 'ConversationId': 'o1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                   'FromName': 'You', 'FromEmail': 'alex@northwind.example', 'Subject': 'x', 'BodyText': 'x', 'SentAt': '2026-10-01 09:00:00',
                   'Status': 'context', 'Direction': 'out', 'RecipientsJson': _j.dumps({'to': ['gail.moreno@northwind.example'], 'cc': []})})
    tid = typed(s, [{'to': 'Gail Moreno', 'about': 'tab 3'}])
    assert slots.add(s, tid, [{'to': 'GAIL.MORENO@northwind.example', 'about': 'tab 3 again'}], 'triage') == []


def test_a_sent_or_dropped_email_cannot_be_drafted_again(s):
    tid = typed(s, FOUR[:2]); sid = slots.all_(s, tid)[0]['id']     # two: dropping the only one would close the task
    slots.drop(s, tid, sid, 'owner')
    out = slots.draft(s, tid, 'one more time', slot=sid)
    assert not out['ok'] and 'already' in out['why']


def test_no_email_is_drafted_on_a_closed_task(s):
    tid = typed(s, FOUR[:1]); s.update_task(tid, {'Status': 'done'}, 'owner')
    assert not slots.draft(s, tid, 'late', to=FOUR[0]['to'])['ok']


def test_triage_never_adds_emails_to_a_list_the_owner_already_wrote(s):
    from taskuary import ingest
    tid = s.create_task({'Title': 'Tabs', 'Summary': 'plain'}, 'owner')
    s.set_task_checklist(tid, ['My own list'], 'owner')
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': ['x'], 'outputs': [{'to': 'erin@northwind.example', 'about': 'y'}]})
    ingest._enrich(s, tid, {'BodyText': 'Tell Erin', 'Subject': 'Tabs'}, 'plain', llm)
    assert slots.all_(s, tid) == []


def test_no_wrap_up_card_while_emails_still_wait(s):
    tid, mid, first = mail_task(s); s.decide_review(first, 'rejected', None, 'owner', 'redrafted')
    slots.add(s, tid, FOUR[:1], 'owner'); draft(s, tid, 0)
    reply = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Done.',
                          'Deliver': json.dumps({'kind': 'reply', 'to': ['erin@example.com'], 'cc': [], 'mode': 'reply_to'})})
    send_reply(s, reply)                                   # the reply is the newest review, as when an agent finishes last
    assert s.get_task(tid)['Status'] != 'done'


def test_the_slot_card_names_the_recipient_once(s):
    tid = typed(s, FOUR[:1])
    rv = s.get_review(slots.draft(s, tid, 'Tab 1 is fine.', to=FOUR[0]['to'], agent='assistant')['review_id'])
    assert FOUR[0]['to'] not in rv['Reason']


# ── "Name <address>" is a name and an address, never a recipient (2026-10-05) ───────────
def test_a_display_name_and_address_keep_only_the_address_as_the_recipient():
    got = slots.clean([{'to': 'Paula Vance <paula@northwind.example>', 'about': 'tab 1'}])
    assert got[0]['out']['to'] == 'paula@northwind.example' and got[0]['out']['name'] == 'Paula Vance'


def test_an_agent_draft_to_a_display_name_sends_to_the_address(s):
    tid = typed(s, [])
    out = slots.draft(s, tid, 'Tab 1 is fine.', to='Paula Vance <paula@northwind.example>', agent='coding')
    rv = s.get_review(out['review_id'])
    assert json.loads(rv['Deliver'])['to'] == ['paula@northwind.example'] and slots.all_(s, tid)[0]['out']['to'] == 'paula@northwind.example'


def test_drafts_already_stored_with_a_display_name_are_repaired_on_start(tmp_path):
    from taskuary.store import SQLiteStore
    db = str(tmp_path / 't.db'); a = SQLiteStore(db)
    tid = a.create_task({'Title': 'Tabs'}, 'owner')
    a._write_checklist(tid, [{'id': 'x1', 'text': 'Email Ray', 'done': False, 'out': {'kind': 'email', 'to': 'Ray Colton <ray@northwind.example>', 'subject': ''}}], 'owner')
    rid = a.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'hi',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['Ray Colton <ray@northwind.example>'], 'subject': 's', 'slot': 'x1'})})
    a.close()
    b = SQLiteStore(db)
    try:
        assert json.loads(b.get_review(rid)['Deliver'])['to'] == ['ray@northwind.example']
        assert slots.all_(b, tid)[0]['out'] == {'kind': 'email', 'to': 'ray@northwind.example', 'subject': '', 'name': 'Ray Colton'}
    finally: b.close()


# ── a restart keeps every email draft (2026-10-05, TQ-0957) ──────────────────────────────
def test_a_restart_keeps_every_pending_email_draft(tmp_path):
    from taskuary.store import SQLiteStore
    db = str(tmp_path / 'r.db'); a = SQLiteStore(db)
    tid = a.create_task({'Title': 'Tabs'}, 'owner'); slots.add(a, tid, FOUR[:2] + FOUR[3:], 'owner')
    rids = [slots.draft(a, tid, f'email {n}', to=FOUR[n]['to'])['review_id'] for n in (0, 1)]
    a.close()
    b = SQLiteStore(db)
    try: assert [b.get_review(r)['Status'] for r in rids] == ['pending', 'pending']
    finally: b.close()


def test_drafts_a_restart_wrongly_retired_come_back(tmp_path):
    from taskuary.store import SQLiteStore
    db = str(tmp_path / 'r2.db'); a = SQLiteStore(db)
    tid = a.create_task({'Title': 'Tabs'}, 'owner'); slots.add(a, tid, FOUR[:2], 'owner')
    r1, r2 = [slots.draft(a, tid, f'email {n}', to=FOUR[n]['to'])['review_id'] for n in (0, 1)]
    a._exec("UPDATE review SET Status='superseded' WHERE ReviewId=?", (r1,))           # what the old heal did
    a.close()
    b = SQLiteStore(db)
    try: assert b.get_review(r1)['Status'] == 'pending'
    finally: b.close()


def _finish_with_a_written_email(s, written=None):
    """A mail task whose agent wrote the email it was asked for (to someone else), then finished."""
    tid, mid, rid = mail_task(s)
    s.decide_review(rid, 'no_reply', None, 'owner', 'cleared for the test')
    slots.draft(s, tid, 'Passing you the import failure.', to='gail@northwind.example', agent='coding')
    prev, wrapup.REFRESH = wrapup.REFRESH, None
    try:
        with mock.patch.object(wrapup, 'raise_reply') as raised:
            if written is None: wrapup.finish(s, tid, {'summary': 'handed it to Gail', 'outcome': 'did_work'})
            else:
                with mock.patch.object(slots, 'written', return_value=written): wrapup.finish(s, tid, {'summary': 'x', 'outcome': 'did_work'})
    finally: wrapup.REFRESH = prev
    return tid, raised


def test_an_email_the_agent_wrote_is_the_answer_no_reply_all_beside_it(s):
    # "hand it off to her" came back as the agent's email AND a reply-all to the first sender - two drafts on one task (2026-10-08)
    tid, raised = _finish_with_a_written_email(s)
    raised.assert_not_called()
    assert s.get_task(tid)['Status'] == 'waiting'
    assert any('no reply to the original sender' in c['Body'] for c in s.list_comments(tid))


def test_without_a_written_email_the_reply_is_still_drafted(s):
    tid, raised = _finish_with_a_written_email(s, written=[])
    raised.assert_called_once()


def routine_run(s, job='Total the newest vendor spend export and email the summary to ray@northwind.example every Monday.'):
    "A run task of a routine the owner saved with `job` as its agent's instructions."
    sid = s.save_source({'Channel': 'report', 'Address': 'Weekly vendor follow-up', 'Owner': 'o', 'Active': 1,
                         'ConfigJson': json.dumps({'type': 'agent', 'title': 'Weekly vendor follow-up', 'prompt': job})}, 'o')
    return s.create_task({'Title': 'Weekly vendor follow-up - Mon', 'Kind': 'general', 'Status': 'open', 'Source': 'workflow',
                          'SourceRef': f'workflow:{sid}'}, 'routine')


def test_a_routines_own_email_goes_at_once_and_his_own_task_waits_for_his_send(s):
    """The owner, 2026-11-17: "routines should send on their own too" - approval is only for what answers input from outside. A routine run's
    agent email to an address he saved into the routine is sent by the very press his Send makes, at once; the same email on a task of his
    own still waits on his Send."""
    run = routine_run(s)
    own = s.create_task({'Title': 'Follow up with Ray', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as send, mock.patch.object(outbound, 'send_block', return_value=''),             mock.patch('taskuary.learning.learn_from'):
        went = slots.draft(s, run, 'Hi Ray, any update on the quote? Alex', 'ray@northwind.example', 'Quote')
        held = slots.draft(s, own, 'Hi Ray, any update on the quote? Alex', 'ray@northwind.example', 'Quote')
    assert went['sent'] is True and send.call_count == 1, went
    assert s.get_review(went['review_id'])['Status'] == 'approved'
    assert 'sent' not in held and s.get_review(held['review_id'])['Status'] == 'pending', held
    with mock.patch('taskuary.outbound.send_out', side_effect=RuntimeError('SMTP 535')), mock.patch.object(outbound, 'send_block', return_value=''):
        failed = slots.draft(s, routine_run(s, 'Send erin@northwind.example the schedule.'), 'Hi Erin, the schedule is attached. Alex',
                             'erin@northwind.example', 'Schedule')
    assert failed.get('send_error') and 'sent' not in failed, failed


# ONE HOLD, WHOEVER CALLS (design round 2, 2026-11-18): a routine run's agent used the draft tool, "and this run sent it before you could
# approve it". What a routine sends without a press is what the owner saved into it - an address in its own words, or himself; an address the
# run's agent chose is its card, held at the one door every send goes through (verdicts.decide), nothing sent
def test_a_routine_runs_email_to_an_address_its_agent_chose_is_a_card_and_nothing_goes(s):
    s.set_setting('owner_email', 'alex@northwind.example', 'owner')
    run = routine_run(s, 'Total the newest vendor spend export and email me the top five.')
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as send, mock.patch.object(outbound, 'send_block', return_value=''),             mock.patch('taskuary.learning.learn_from'):
        chose = slots.draft(s, run, 'Hi Gail, the October spend is attached. Alex', 'gail@northwind.example', 'October spend')
        assert send.call_count == 0 and 'sent' not in chose and s.get_review(chose['review_id'])['Status'] == 'pending', chose
        # ...and no other caller gets past it by pressing in the routine's name
        out = verdicts.decide(s, s.get_review(chose['review_id']), 'approve', actor=slots.ROUTINE)
        assert not out['ok'] and out.get('held') and send.call_count == 0, out
        mine = slots.draft(s, run, 'October spend: 103,190 in all. Alex', 'alex@northwind.example', 'October spend')
    assert mine['sent'] is True and send.call_count == 1, mine


# THE AGENT HEARS WHICH EMAIL WENT (the stress round, 2026-11-18): with two emails out, a Send told it "the message was sent" - no card, no
# person - while a No names the card and whom it was to (cardqueue.said_no). One sentence says a card, for the yes as for the no
def test_the_agent_is_told_which_of_its_emails_went(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    told = []
    with mock.patch('taskuary.general.approved', lambda st, t, press, what, *x, **k: told.append(what)):
        assert approve(s, a)['ok'] and told == [], 'a card still stands behind it: the row is not over (cardqueue.row_over)'
        assert approve(s, b)['ok']
    assert len(told) == 1 and told[0].startswith(f'rv{b} (the email to ray@northwind.example) was sent'), told

def test_the_agent_on_a_routine_run_is_told_its_email_went_not_that_it_waits(s):
    # a routine run's agent drafted to Ray: the email went at once, and its tool still answered that the card "waits and nothing went" -
    # so the agent told the owner a sent email was waiting for his Send
    from taskuary import agenttools
    from taskuary.selfclose import CARD_SAID
    run = routine_run(s, 'Ask ray@northwind.example and erin@northwind.example where the quote and the schedule stand.')
    with mock.patch('taskuary.outbound.send_out', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
            mock.patch('taskuary.learning.learn_from'):
        went = agenttools.said_once(slots.draft(s, run, 'Hi Ray, any update on the quote? Alex', 'ray@northwind.example', 'Quote'))
    assert went['shown'] != CARD_SAID and went['shown'].startswith('Sent to ray@northwind.example'), went
    with mock.patch('taskuary.outbound.send_out', side_effect=RuntimeError('SMTP 535')), mock.patch.object(outbound, 'send_block', return_value=''):
        held = agenttools.said_once(slots.draft(s, run, 'Hi Erin, the schedule is attached. Alex', 'erin@northwind.example', 'Schedule'))
    assert held['shown'].startswith('Not sent to erin@northwind.example') and "owner's Send" in held['shown'], held


def test_a_sent_email_is_named_by_whom_it_went_to_not_by_its_cards_reason(s):
    # a routine's email failed at night and the owner's Send got it out in the morning: the task said "Sent: Not sent: ..." - the card's
    # reason from the failed try - and an email sent at the first press read "Sent: assistant wrote this email - approve to send."
    tid = s.create_task({'Title': 'Follow up with Ray', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    with mock.patch('taskuary.outbound.send_out', side_effect=RuntimeError('SMTP 451 try later')), mock.patch.object(outbound, 'send_block', return_value=''):
        rid = slots.draft(s, tid, 'Hi Ray, any update on the quote? Alex', 'ray@northwind.example', 'Quote', agent='assistant')['review_id']
        verdicts.decide(s, s.get_review(rid), 'approve', actor='owner')
    with mock.patch('taskuary.outbound.send_out', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
            mock.patch('taskuary.learning.learn_from'):
        assert verdicts.decide(s, s.get_review(rid), 'approve', actor='owner')['ok']
    said = s.list_comments(tid)[-1]['Body']
    assert said.startswith('Sent: the email to ray@northwind.example. ') and 'Not sent' not in said and 'approve to send' not in said, said


# HIS OWN ASK OWES HIM NO EMAIL (a walk, 2026-11-18): "set it up for my press" was read as an email owed to the owner, its agent drafted
# "please approve the note" to him, and he had to drop it. He is the sender of his own ask: his press on the card is the approval


def test_an_address_he_gave_in_his_memory_is_no_guess(s):
    """Round 3, 2026-11-22: Paula's address stood in his memory under "Your people", and the agent was told it had guessed it and asked him for
    it. An address in his own words is known: found by her name, and never refused as a guess."""
    from taskuary import people
    s.save_doc('learned', '## Your people\n- Paula Vance (paula.vance@northwind.example) handles payroll\n', 'owner')
    assert people.resolve(s, 'Paula Vance') == {'address': 'paula.vance@northwind.example'}
    tid = typed(s, FOUR[:1])
    out = slots.draft(s, tid, 'Hi Paula - the payroll file is attached.', to='paula.vance@northwind.example', guessed=['paula.vance@northwind.example'])
    assert out['ok'], out


def test_an_address_made_from_a_name_whose_person_writes_from_another_is_refused_with_theirs(s):
    """Walk 5, 2026-11-22: the agent put gail.moreno@ on a Send card 20 seconds after Gail wrote from gail@ - it called it a guess in its answer
    and passed none as guessed. Her own address is the one to use; someone new at the company is still drafted to."""
    tid = typed(s, FOUR[:1])
    s.add_message({'TaskId': tid, 'ExternalId': 'g-w5', 'Channel': 'email', 'Subject': 'Budget', 'FromName': 'Gail Moreno',
                   'FromEmail': 'gail@northwind.example', 'SentAt': '2026-11-22 08:00:00', 'BodyText': 'Can you send the total?', 'Status': 'routed'})
    out = slots.draft(s, tid, 'Hi Gail - 34.75 hours.', to='gail.moreno@northwind.example')
    assert out['ok'] is False and 'gail@northwind.example' in out['why']
    assert slots.draft(s, tid, 'Hi Omar - welcome aboard.', to='omar.keller@northwind.example')['ok'] is True
