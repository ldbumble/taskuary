"""EVERY AGENT TURN ENDS WITH WHERE THE OWNER STANDS (Task 3.5, 2026-11-04).

The general agent closes each turn on a [[TASKUARY-SUMMARY]] block - what the task is about, what it did, what is on the owner, and
whether anything is left. The block never reaches the screen: it is filed as the turn's summary row, and its `on_you` steps become the
task's On you to-dos - a later turn replaces the ones not yet ticked. A turn without the block, or with a broken one, files as before.
A reply task that no agent works takes its On you from triage's reading instead.
"""
import json
from unittest import mock

from taskuary import general, ingest, selfclose
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


def summaries(s, tid): return [c for c in s.list_comments(tid) if c.get('ActorType') == general.SUMMARY_TYPE]
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
