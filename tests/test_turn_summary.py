"""EVERY AGENT TURN ENDS WITH WHERE THE OWNER STANDS (Task 3.5, 2026-11-04).

The general agent closes each turn on a [[TASKUARY-SUMMARY]] block - what the task is about, what it did, what is on the owner, and
whether anything is left. The block never reaches the screen: it is filed as the turn's summary row, and its `on_you` steps become the
task's On you to-dos - a later turn replaces the ones not yet ticked. A turn without the block, or with a broken one, files as before.
A reply task that no agent works takes its On you from triage's reading instead.
"""
import json
from unittest import mock

from taskuary import byrecipient, general, ingest, selfclose
from taskuary.store import MemoryStore

STEP = 'confirm the pay date with AP before sending'


def block(**kw):
    return f"{selfclose.SUMMARY_OPEN}{json.dumps({'about': 'Gail wants the pay date', 'did': 'Read the pay calendar: the run is Friday', 'on_you': [STEP], 'nothing_left': False, **kw})}{selfclose.SUMMARY_CLOSE}"


def task(s):
    return s.create_task({'Title': 'Pay date', 'Kind': 'general', 'Status': 'in_progress'}, 't')


def turn(s, tid, answer, sess=None):
    if sess is None:
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: answer), mock.patch('taskuary.hooks.judge_ended'):
        return sess.send_prompt('when is payday?'), sess


def summaries(s, tid): return [c for c in s.list_comments(tid, internal=True) if c.get('ActorType') == general.SUMMARY_TYPE]
def on_you(s, tid): return [i for i in s.task_checklist(tid) if i.get('on_you')]


def test_the_block_is_read_and_always_taken_out():
    text, summ = selfclose.summary_marker(f'The run is Friday.\n{block()}')
    assert text == 'The run is Friday.' and summ == {'about': 'Gail wants the pay date', 'did': 'Read the pay calendar: the run is Friday',
                                                     'on_you': [STEP], 'nothing_left': False}
    assert selfclose.summary_marker(f'Hi.\n{selfclose.SUMMARY_OPEN}{{not json{selfclose.SUMMARY_CLOSE}') == ('Hi.', None)
    assert selfclose.SUMMARY_OPEN not in selfclose.for_screen(f'Working on it.\n{block()}')


def test_a_turn_ends_with_three_parts():
    s = MemoryStore(); tid = task(s)
    shown, _ = turn(s, tid, f'The pay run is Friday.\n\n{block()}')
    assert 'TASKUARY' not in shown and 'TASKUARY' not in general.history(s, tid)[-1]['content'][0]['text']
    assert general.shown_history(s, tid)[-1]['summary']['on_you'] == [STEP]
    (item,) = on_you(s, tid)
    assert (item['text'], item['done']) == (STEP, False)


def test_an_emptied_reply_reads_as_what_it_did():
    s = MemoryStore(); tid = task(s)
    shown, _ = turn(s, tid, block())
    assert shown == 'Read the pay calendar: the run is Friday'


def test_a_later_summary_replaces_only_unticked_on_you():
    s = MemoryStore(); tid = task(s)
    s.set_task_checklist(tid, ['find the pay date'], 'triage')
    _, sess = turn(s, tid, f'Friday.\n{block(on_you=["ask Erin for the cut-off", STEP])}')
    ticked = next(i for i in on_you(s, tid) if i['text'] == STEP)
    s.tick_checklist_item(tid, ticked['id'], True, 'owner')
    turn(s, tid, f'Done.\n{block(on_you=["reply to Gail once AP confirms"])}', sess)
    items = s.task_checklist(tid)
    assert [i['text'] for i in items if not i.get('on_you')] == ['find the pay date']
    assert sorted((i['text'], i['done']) for i in on_you(s, tid)) == [(STEP, True), ('reply to Gail once AP confirms', False)]
    assert len(summaries(s, tid)) == 2


def test_a_turn_without_the_block_is_today():
    s = MemoryStore(); tid = task(s)
    s.set_task_checklist(tid, ['find the pay date'], 'triage')
    before = s.task_checklist(tid)
    for answer in ('The pay run is Friday.', f'The pay run is Friday.\n{selfclose.SUMMARY_OPEN}{{not json{selfclose.SUMMARY_CLOSE}'):
        shown, _ = turn(s, tid, answer)
        assert shown == 'The pay run is Friday.'
    assert summaries(s, tid) == [] and s.task_checklist(tid) == before
    assert all('summary' not in m for m in general.shown_history(s, tid))


def test_the_drafted_reply_is_never_kept_in_the_summary():
    # the owner, 2026-11-04: what goes to the sender - and any login in it - lives in the draft, never in the summary as well
    s = MemoryStore(); tid = task(s)
    letter = 'Hi Gail,\nThe portal password is Tern-Vault-9081 until Friday.\nAlex'
    s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': letter})
    turn(s, tid, f"Drafted it.\n{block(did='Wrote: The portal password is Tern-Vault-9081 until Friday.', on_you=[letter, STEP])}")
    (row,) = summaries(s, tid)
    assert 'Tern-Vault-9081' not in row['Body'] and '(see the drafted reply)' in json.loads(row['Body'])['did']
    assert all('Tern-Vault-9081' not in i['text'] for i in s.task_checklist(tid))
    assert STEP in [i['text'] for i in on_you(s, tid)]


def _ingest(s, live=''):
    v = {'intent': 'reply_only', 'why': 'asks the pay date', 'title': 'Pay date', 'summary': 's',
         'thread': {'asking': 'Gail wants the pay date', 'your_part': 'say when', 'others': [], 'asks': [], 'aside': [], 'on_you': [STEP]}}
    msg = {'external_id': 'p1', 'channel': 'email', 'subject': 'Pay date', 'body': 'When is the pay run?',
           'from_name': 'Gail Moreno', 'from_email': 'gail@northwind.example'}
    with mock.patch('taskuary.ingest._spawn'), mock.patch.object(ingest, 'live_agent', return_value=live):
        return ingest.ingest_message(s, msg, llm=lambda *a, **k: json.dumps(v))['task_id']


def test_triage_on_you_only_where_no_agent_runs():
    s = MemoryStore(); tid = _ingest(s)
    assert s.get_task(tid)['Kind'] == 'reply' and [i['text'] for i in on_you(s, tid)] == [STEP]
    s2 = MemoryStore(); tid2 = _ingest(s2, live='general')
    assert on_you(s2, tid2) == []


# ── fix round 1 ──────────────────────────────────────────────────────────────────────────
def test_a_block_cut_short_never_reaches_the_screen():
    # a live line is cut to 300 or 400 characters before it is drawn (agents.py), so the tag can arrive with half its JSON - or half itself
    line = ('I read the pay calendar and the AP thread. ' * 4 + block())[:300]
    assert selfclose.SUMMARY_OPEN in line and selfclose.SUMMARY_CLOSE not in line
    assert selfclose.for_screen(line) == ('I read the pay calendar and the AP thread. ' * 4).strip()
    assert selfclose.for_screen('Reading the calendar.\n[[TASKUA') == 'Reading the calendar.'


def test_a_turn_whose_block_never_closes():
    s = MemoryStore(); tid = task(s)
    shown, _ = turn(s, tid, f'The pay run is Friday.\n{selfclose.SUMMARY_OPEN}{{"about": "Gail wants the pay date", "did": "Read')
    assert shown == 'The pay run is Friday.' and summaries(s, tid) == []


def test_a_broken_block_that_was_the_whole_answer_files_its_words():
    s = MemoryStore(); tid = task(s)
    shown, _ = turn(s, tid, f'{selfclose.SUMMARY_OPEN}The pay run is Friday.{selfclose.SUMMARY_CLOSE}')
    assert shown == 'The pay run is Friday.' and summaries(s, tid) == []


def test_an_owner_tick_landing_mid_write_is_kept():
    import threading
    s = MemoryStore(); tid = task(s)
    (item,) = s.set_on_you(tid, [STEP], 'assistant')
    real, ticker = s.task_checklist, []
    def read_then_tick(t):
        got = real(t)
        if not ticker:              # the owner ticks between this read and the write after it
            ticker.append(threading.Thread(target=s.tick_checklist_item, args=(tid, item['id'], True, 'owner'))); ticker[0].start(); ticker[0].join(0.3)
        return got
    with mock.patch.object(s, 'task_checklist', side_effect=read_then_tick): s.set_on_you(tid, [STEP, 'reply to Gail'], 'assistant')
    ticker[0].join(5)
    assert {i['text']: i['done'] for i in s.task_checklist(tid)} == {STEP: True, 'reply to Gail': False}


def test_on_you_survives_an_owner_edit():
    s = MemoryStore(); tid = task(s)
    s.set_task_checklist(tid, ['find the pay date'], 'triage'); s.set_on_you(tid, [STEP], 'assistant')
    s.set_task_checklist(tid, ['find the pay date', STEP, 'call Erin'], 'owner')
    assert [i['text'] for i in on_you(s, tid)] == [STEP]


def test_a_summary_with_no_on_you_list_leaves_the_steps():
    s = MemoryStore(); tid = task(s)
    _, sess = turn(s, tid, f'Friday.\n{block()}')
    turn(s, tid, f'Still Friday.\n{block(on_you="nothing")}', sess)
    turn(s, tid, f'Still Friday.\n{selfclose.SUMMARY_OPEN}{{}}{selfclose.SUMMARY_CLOSE}', sess)
    assert [i['text'] for i in on_you(s, tid)] == [STEP] and len(summaries(s, tid)) == 2
    assert selfclose.summary_marker(f'Hi.{selfclose.SUMMARY_OPEN}{{"about": " ", "on_you": []}}{selfclose.SUMMARY_CLOSE}') == ('Hi.', None)


def test_a_restated_step_keeps_its_place_and_note():
    s = MemoryStore(); tid = task(s)
    s.set_on_you(tid, [STEP], 'assistant'); s.merge_task_checklist(tid, ['find the pay date'], 'triage', src=4)
    s.note_checklist_item(tid, on_you(s, tid)[0]['id'], 'AP said Thursday', 'owner')
    s.set_on_you(tid, [STEP, 'reply to Gail'], 'assistant')
    items = s.task_checklist(tid)
    assert [i['text'] for i in items] == [STEP, 'find the pay date', 'reply to Gail'] and items[0]['note'] == 'AP said Thursday'


# TASK 5.2 - a correction typed in the chat is learned the way the draft box's words were: quietly, no chip, no "Remembered" line
def draft_for(s, tid, who, n=1):
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'c{tid}-{n}', 'Channel': 'email', 'Subject': 's', 'FromEmail': who, 'BodyText': 'b', 'Status': 'routed'})
    return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi.'})


def review(s, rid): return next(r for r in s._rows('SELECT * FROM review WHERE ReviewId=?', (rid,)))


def test_a_redraft_word_is_kept_on_the_draft():
    s = MemoryStore(); tid = task(s); rid = draft_for(s, tid, 'ray@northwind.example')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Cc Gail on it')
    assert general.take_corrections(s, tid, [{'kind': 'redraft', 'review': None, 'said': 'Cc Gail on it'}]) == 1
    assert 'Cc Gail on it' in review(s, rid)['Instructions']


def test_said_twice_for_one_person_becomes_a_style_line():
    s = MemoryStore()
    for n in (1, 2):
        tid = task(s); draft_for(s, tid, 'ray@northwind.example', n)
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Make it shorter')
        general.take_corrections(s, tid, [{'kind': 'redraft', 'review': None, 'said': 'make it shorter'}])
    assert [w for w, _ in byrecipient.lines(s)] == ['ray@northwind.example']


def test_not_the_ask_is_an_owner_correction():
    s = MemoryStore(); tid = task(s)
    s.add_comment(tid, 'owner', general.USER_TYPE, 'No, the ask is the pay date, not the bonus')
    with mock.patch('taskuary.learn.learn_from') as lf:
        assert general.take_corrections(s, tid, [{'kind': 'ask', 'review': None, 'said': 'the ask is the pay date, not the bonus'}]) == 1
    lf.assert_called_once(); assert 'owner_correction' in lf.call_args[0][1] and 'the pay date, not the bonus' in lf.call_args[0][1]


def test_the_models_statement_of_a_correction_is_trusted():
    "The owner, 2026-11-05: the model reads intent - a correction it states in its own words is kept, not only one quoted word for word."
    s = MemoryStore(); tid = task(s); rid = draft_for(s, tid, 'ray@northwind.example')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Gail should see this one too')
    assert general.take_corrections(s, tid, [{'kind': 'redraft', 'review': None, 'said': 'Cc Gail on the reply'}]) == 1
    assert 'Cc Gail on the reply' in review(s, rid)['Instructions']


def test_an_empty_or_secret_correction_or_one_with_no_owner_message_is_dropped():
    s = MemoryStore(); tid = task(s); rid = draft_for(s, tid, 'ray@northwind.example')
    with mock.patch('taskuary.learn.learn_from') as lf:
        assert general.take_corrections(s, tid, [{'kind': 'ask', 'review': None, 'said': 'wrong ask'}]) == 0      # nobody corrected anything
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Use the new portal key')
        assert general.take_corrections(s, tid, [{'kind': 'redraft', 'review': None, 'said': '  '},
                                                 {'kind': 'redraft', 'review': None, 'said': 'api_key: sk-abcdefghijklmnop1234'}]) == 0
    lf.assert_not_called(); assert 'sk-' not in (review(s, rid).get('Instructions') or '')


def test_corrections_ride_the_summary_block_and_stay_off_the_screen():
    c = [{'kind': 'ask', 'review': None, 'said': 'the pay date'}, {'kind': 'redraft', 'review': 7, 'said': 'Cc Gail'}, {'kind': 'x', 'said': 'no'}, 'junk']
    text, summ = selfclose.summary_marker(f'Done.\n{block(corrections=c)}')
    assert text == 'Done.' and summ['corrections'] == c[:2]


def test_the_advisor_is_told_nothing_is_left():
    from taskuary import advisor
    s = MemoryStore(); tid = task(s)
    assert advisor.summary_line(s, tid) == ''
    turn(s, tid, f'Done.\n{block(on_you=[], nothing_left=True)}')
    assert advisor.summary_line(s, tid) == "THE AGENT'S LAST SUMMARY: nothing left to do here"
    turn(s, tid, f'Still Friday.\n{block()}')
    assert advisor.summary_line(s, tid) == f"THE AGENT'S LAST SUMMARY: on you - {STEP}"


def test_a_pending_draft_is_not_nothing_left():
    from taskuary import advisor
    s = MemoryStore(); tid = task(s)
    turn(s, tid, f'Done.\n{block(on_you=[], nothing_left=True)}')
    with mock.patch.object(advisor, '_draft', return_value={'DraftText': 'Hi Gail'}):
        assert 'nothing left' not in advisor.summary_line(s, tid)


# ── each turn keeps the draft it wrote (the owner, 2026-11-05) ──────────────────────────────
def _redraft(s, tid, rid, text): s._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', (text, rid))


def test_a_turns_draft_keeps_its_own_words_after_a_later_redraft():
    s = MemoryStore(); tid = task(s)
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail, the run is Friday.'})
    _, sess = turn(s, tid, f'Drafted it.\n{block()}')
    _redraft(s, tid, rid, 'Hi Gail, the run moved to Thursday.')
    turn(s, tid, f'Redrafted it.\n{block()}', sess)
    turn(s, tid, f'Nothing new on the draft.\n{block()}', sess)
    answers = [m for m in general.shown_history(s, tid) if m.get('summary')]
    assert [[d['text'] for d in m.get('drafts_then', [])] for m in answers] == [['Hi Gail, the run is Friday.'], ['Hi Gail, the run moved to Thursday.'], []]
    assert [m['summary']['drafted'] for m in answers] == [[{'review': rid}], [{'review': rid}], []]


def test_the_kept_draft_never_puts_its_words_in_the_summary():
    s = MemoryStore(); tid = task(s)
    s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail,\nThe code is Tern-Vault-9081.\nAlex'})
    turn(s, tid, f'Drafted it.\n{block()}')
    (row,) = summaries(s, tid)
    assert 'Tern-Vault-9081' not in row['Body']
    assert 'Tern-Vault-9081' in general.shown_history(s, tid)[-1]['drafts_then'][0]['text']
    s.delete_task(tid)
    assert s._rows('SELECT * FROM draft_snapshot WHERE TaskId=?', (tid,)) == []
