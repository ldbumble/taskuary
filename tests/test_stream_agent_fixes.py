"""THE AGENT ON A STREAM OF CHAT LINES (the owner, 2026-11-09, after an audit replayed one colleague's afternoon of bug reports in a group chat):
the plumbing around the agent, not the model, made it tiring - a false "your earlier reply may already have gone out", a stale "the owner's
part now", the owner's one phone line wiping a six-point draft, a greeting that left the real asks with no agent, a fresh draft withdrawn as
old, a finished turn woken again, Resume's words on a carry-on nobody pressed, "remind me" setting the agent's alarm. Invented people.
"""
import json, shutil
from unittest import mock

from taskuary import agenttools, channels, config, general, hooks, ingest, outputs, server
from taskuary.store import MemoryStore
from test_carry_on import ingested, mail, store
from test_freshness_walk import reads, stamp, teams_task
from test_own_ask_no_reply import own_task
from test_withdraw_any_unsent import call


# ── F1: a reply that took the old one's place is said so, never "nothing to withdraw" ──────────────────────────────────────────────────
def test_a_draft_this_call_superseded_reads_as_replaced():
    s = MemoryStore(); tid = own_task(s, 'general')
    old = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Ray - noted.'})
    was = [{'rid': old, 'kind': 'draft_reply', 'to': 'ray@northwind.example', 'what': 'the reply to ray@northwind.example'}]
    s.decide_review(old, 'closed_unsent', None, 'agent', note='superseded - a later turn\'s reply took its place')   # the new reply did it
    doors = {'withdraw': lambda *a, **k: {'ok': False, 'why': 'nothing unsent is waiting on this task, so there is nothing to withdraw'}}
    got = agenttools.replaced(s, doors, tid, was, {'ok': True, 'review_id': old + 1}, str(old), 'the new reply takes its place')
    assert got['replaced'] == old and 'not_replaced' not in got
    # ...and one that is still waiting, or was never there, is still said as not replaced
    assert 'not_replaced' in agenttools.replaced(s, doors, tid, [], {'ok': True, 'review_id': old + 1}, '999', 'x')


def test_propose_reply_offers_no_replaces():
    d, schema = agenttools.TOOLS['propose_reply'][1:3]
    assert 'replaces' not in schema['properties'] and 'replaces' not in d
    assert 'replaces' in agenttools.TOOLS['propose_email'][2]['properties'] and 'replaces' in agenttools.TOOLS['propose'][1]


# ── F2, F9, F10: the turn's words ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_replan_turn_says_who_did_what_and_no_stale_owners_part():
    follow = {'why': 'another bug on the app', 'thread': {'asking': 'Ray reports a cut-off screen', 'your_part': 'Give Ray your view of the build',
                                                          'others': [{'who': 'Ray Colton', 'did': 'reported the cut-off screen'}]}}
    turn = ingest.replan_turn({'channel': 'whatsapp', 'from_name': 'Ray Colton', 'body': 'the screen is cut off'}, follow)
    assert 'Who did what: Ray Colton - reported the cut-off screen' in turn
    assert "owner's part" not in turn and 'Already handled' not in turn and 'Give Ray your view' not in turn


def test_a_carry_on_turn_is_never_resume():
    s = MemoryStore(); tid = own_task(s, 'general')
    turn = ingest.carry_on_turn(s, tid)
    assert turn.endswith(ingest.CARRY_ON_PROMPT) and 'Resume' not in turn


# ── F3: the owner's chat line re-reads the draft ───────────────────────────────────────────────────────────────────────────────────
def own_line(text): return {'ConversationId': 'teams:robin', 'SentAt': stamp(), 'Channel': 'teams', 'BodyText': text}


def test_a_line_that_covers_the_draft_retires_it_with_why():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    with reads('covered'): channels.retire_draft_answered_elsewhere(s, tid, own_line('reset it, try now'))
    assert s.get_review(rid)['Status'] == 'superseded'
    assert any(channels.COVERED in c['Body'] for c in s.list_comments(tid))


def test_a_line_that_covers_part_cuts_the_draft_to_what_is_left():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    before = s.get_review(rid)
    with reads('partly', 'The export fix lands tomorrow.'): channels.retire_draft_answered_elsewhere(s, tid, own_line('voice to text is fixed in 18'))
    rv = s.get_review(rid)
    assert (rv['Status'], rv['DraftText'], rv['MessageId']) == ('pending', 'The export fix lands tomorrow.', before['MessageId'])


def test_an_unread_line_keeps_the_draft_and_says_check_it():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    with mock.patch('taskuary.llm.build_llm', return_value=None): channels.retire_draft_answered_elsewhere(s, tid, own_line('on it'))
    assert (s.get_review(rid)['Status'], s.get_review(rid)['DraftText']) == ('pending', 'ok give me 5 mins')
    assert any(channels.CHECK_IT in c['Body'] for c in s.list_comments(tid))


def test_email_keeps_its_retire():
    s = MemoryStore(); tid, _first, rid = teams_task(s, conv='AAQk-x')
    with mock.patch('taskuary.llm.build_llm', side_effect=AssertionError('no model read for a mail')):
        channels.retire_draft_answered_elsewhere(s, tid, {'ConversationId': 'AAQk-x', 'SentAt': stamp(), 'Channel': 'email', 'BodyText': 'Sent.'})
    assert s.get_review(rid)['Status'] == 'superseded'


# ── F4: the first real ask on a watched row starts an agent ────────────────────────────────────────────────────────────────────────
def test_real_work_joining_a_watch_row_starts_its_agent():
    s = store()
    with mock.patch('taskuary.ingest._spawn'), mock.patch('taskuary.senders.wrote_to', return_value=True):
        out = ingest.ingest_message(s, mail(body='Alex!'), llm=lambda *a, **k: json.dumps({'intent': 'watch', 'kind': 'task', 'why': 'Ray will update'}))
    tid = out['task_id']; assert s.get_task(tid)['Kind'] == 'task'
    _out, spawned = ingested(s, mail(external_id='x2', body='The login page errors on the new build', sent_at='2026-10-28 10:00'))
    t = s.get_task(tid)
    assert spawned == ['_auto_general'] and t['Kind'] == 'general' and not t.get('WatchedAt')
    assert not [c for c in s.list_comments(tid) if 'it is your own task' in c['Body']]


# ── F5: a draft written for the newest message is said so ──────────────────────────────────────────────────────────────────────────
def test_a_draft_for_the_newest_message_is_not_called_earlier():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Northwind app feedback', 'Kind': 'general', 'Status': 'open'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'wa1', 'ConversationId': 'wa:ops', 'Channel': 'whatsapp', 'FromName': 'Ray Colton',
                         'SentAt': '2026-11-08 09:00:00', 'BodyText': 'Keep posting here?', 'Status': 'routed'})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Noted the first bug.')
    s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes, keep posting here.'})
    said = general.latest_block(s, tid)
    assert 'written for this message - keep it or improve it' in said and 'BEFORE the newest message' not in said


# ── F6, F11: the to-do list and the owner's reminder ───────────────────────────────────────────────────────────────────────────────
def test_the_todos_tool_adds_rewords_and_folds_duplicates():
    s = MemoryStore(); tid = own_task(s, 'general')
    a, b = s.set_task_checklist(tid, ['Login error', 'Login page error on build 17'], 'triage')
    with mock.patch.object(server, 'store', s):
        got = json.loads(call(tid, 'todos', add=['Voice to text drops words'], merge=[{'ids': [a['id'], b['id']], 'text': 'Login page errors'}])[0])
        assert got['ok']
        said, bad = call(tid, 'todos', reword={'nope': 'x'})
        assert '"ok": false' in said and 'no to-do nope' in said
    assert [i['text'] for i in s.task_checklist(tid)] == ['Login page errors', 'Voice to text drops words']


def test_remind_sets_the_owners_reminder_not_the_agents_check_back():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        got = json.loads(call(tid, 'remind', when='2026-12-04')[0])
    t = s.get_task(tid)
    assert got['ok'] and str(t['RemindAt']).startswith('2026-12-04') and not t.get('CheckBackAt')
    assert 'remind tool' in agenttools.TOOLS['check_back'][1]


# ── F7: a finished turn is never woken ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_turn_its_summary_calls_finished_is_not_judged():
    assert hooks.owner_presses_only({'nothing_left': True})
    assert hooks.owner_presses_only({'on_you': ['Press Send on the reply to Ray', 'Decide whether to add a blank box']})
    assert not hooks.owner_presses_only({'on_you': ['Call the vendor about the credit']}) and not hooks.owner_presses_only(None)
    brain = mock.Mock(side_effect=AssertionError('never read'))
    hooks.judge_ended(MemoryStore(), 1, 's1', 'Ready for your Mark done.', brain=brain, wait=True, then=brain, summ={'nothing_left': True})
    assert 'Send or decision is finished, not unfinished' in hooks.ENDED_SYSTEM


# ── F13: the calendar's Connect link, the chat file in the task folder ─────────────────────────────────────────────────────────────
def test_no_calendar_gives_the_connect_link():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s), mock.patch('taskuary.calendar.reachable', return_value=False):
        said, bad = call(tid, 'calendar')
    assert not bad and '[Connect a calendar](' in said


def test_a_file_sent_in_the_chat_lands_in_the_task_folder():
    tid = 9871
    up = config.home() / 'attachments' / 'prompt' / '202611' / '20261108-210300-a1b2c3-permission slip.pdf'
    up.parent.mkdir(parents=True, exist_ok=True); up.write_bytes(b'%PDF-1.4 slip')
    try:
        got = outputs.take_in(tid, [str(up), 'C:/elsewhere/not-ours.txt'])
        assert got[0] == str(outputs.folder(tid) / 'permission slip.pdf') and got[1] == 'C:/elsewhere/not-ours.txt'
        assert outputs.named(tid, 'permission slip.pdf').read_bytes() == b'%PDF-1.4 slip'
        assert outputs.take_in(tid, [str(up)]) == got[:1]                    # the same file twice is one copy
    finally: shutil.rmtree(outputs.folder(tid), True); up.unlink()


def test_the_owners_own_line_is_drawn_at_the_time_they_wrote_it():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Northwind app feedback', 'Kind': 'general', 'Status': 'open'}, 'router')
    at = lambda table, key, rid, t: s._exec(f'UPDATE {table} SET CreatedAt=? WHERE {key}=?', (t, rid))
    ray = s.add_message({'TaskId': tid, 'ExternalId': 'wa1', 'ConversationId': 'wa:ops', 'Channel': 'whatsapp', 'FromName': 'Ray Colton',
                         'SentAt': '2026-11-08 21:00:00', 'BodyText': 'The login page errors', 'Status': 'routed'})
    at('message', 'MessageId', ray, '2026-11-08 21:00:00')
    at('comment', 'CommentId', s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Ray wrote'), '2026-11-08 21:01:00')
    at('comment', 'CommentId', s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'A workaround is to reload.'), '2026-11-08 21:05:00')
    late = s.add_message({'TaskId': tid, 'ExternalId': 'wa2', 'ConversationId': 'wa:ops', 'Channel': 'whatsapp', 'FromName': 'Ray Colton',
                          'SentAt': '2026-11-08 21:30:00', 'BodyText': 'Downloads pop up too', 'Status': 'routed'})
    at('message', 'MessageId', late, '2026-11-08 21:30:00')
    mine = s.add_message({'TaskId': tid, 'ExternalId': 'wa0', 'ConversationId': 'wa:ops', 'Channel': 'whatsapp', 'FromName': 'You',
                          'SentAt': '2026-11-08 21:00:30', 'BodyText': 'Ray, which build?', 'Status': 'context', 'Direction': 'out'})
    at('message', 'MessageId', mine, '2026-11-08 21:40:00')                  # filed on the task late, written early
    order = [w['words'] for m in general.shown_history(s, tid) for w in m.get('mail') or []]
    assert order.index('Ray, which build?') < order.index('Downloads pop up too')
