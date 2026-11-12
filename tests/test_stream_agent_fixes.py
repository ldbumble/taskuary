"""THE AGENT ON A STREAM OF CHAT LINES (the owner, 2026-11-09, after an audit replayed one colleague's afternoon of bug reports in a group chat):
the plumbing around the agent, not the model, made it tiring - a false "your earlier reply may already have gone out", a stale "the owner's
part now", the owner's one phone line wiping a six-point draft, a greeting that left the real asks with no agent, a fresh draft withdrawn as
old, a finished turn woken again, Resume's words on a carry-on nobody pressed, "remind me" setting the agent's alarm. Invented people.
"""
import json, shutil
from unittest import mock

from taskuary import agenttools, channels, config, general, hooks, ingest, outputs, server, wrapup
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


# ── F3: the owner's chat line re-reads the draft where no agent may take it (a reply task nothing works) ──────────────────────────────────
def own_line(text): return {'ConversationId': 'teams:robin', 'SentAt': stamp(), 'Channel': 'teams', 'BodyText': text}


def test_a_line_that_covers_the_draft_retires_it_with_why():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    with reads('covered'): channels.owner_line(s, tid, {'channel': 'teams'}, None, own_line('reset it, try now'))
    assert s.get_review(rid)['Status'] == 'superseded'
    assert any('yourself - no new response needed.' in c['Body'] and 'reset it' not in c['Body'] for c in s.list_comments(tid))


def test_a_line_that_covers_part_cuts_the_draft_to_what_is_left():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    before = s.get_review(rid)
    with reads('partly', 'The export fix lands tomorrow.'): channels.owner_line(s, tid, {'channel': 'teams'}, None, own_line('voice to text is fixed in 18'))
    rv = s.get_review(rid)
    assert (rv['Status'], rv['DraftText'], rv['MessageId']) == ('pending', 'The export fix lands tomorrow.', before['MessageId'])


def test_an_unread_line_keeps_the_draft_and_says_check_it():
    s = MemoryStore(); tid, _first, rid = teams_task(s)
    with mock.patch('taskuary.llm.build_llm', return_value=None): channels.owner_line(s, tid, {'channel': 'teams'}, None, own_line('on it'))
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


def test_a_draft_the_thread_moved_past_is_never_called_written_for_the_newest_message():
    # the owner, 2026-11-10: the agent drafted on a chat, the owner answered there from the phone, a minute later the sender asked something
    # new - the join re-pinned the old draft to the new line (its freshness marker), and the woken agent was told that draft was "written for
    # this message - keep it", so the answer to the first ask stood as the answer to the second
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); s.remember_trust('whatsapp', 'whatsapp:15550001', 'You vouched')
    wa = lambda ext, body, at: {'external_id': ext, 'channel': 'whatsapp', 'subject': 'Erin Blake', 'body': body, 'from_email': 'whatsapp:15550001',
                                'from_name': 'Erin Blake', 'conversation_id': 'wa:erin', 'sent_at': at, 'source_name': 'Erin Blake', 'mail_meta': {'dm': True}}
    llm = lambda sy, u, **k: json.dumps({'intent': 'reply_only', 'kind': 'task', 'why': 'w', 'asks_owner': True, 'title': 'Erin asks'})
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
        tid = ingest.ingest_message(s, wa('w1', 'Are we still on for Thursday?', stamp(-600)), llm=llm)['task_id']
        ingest.reply_to_agent(s, tid, s.pending_review(tid, kind='draft')['ReviewId'])          # the hand-over, as the spawn runs it
        general.OPENING.discard(tid)
        for who, kind, words in ((general.BRIEF_ACTOR, general.USER_TYPE, 'brief'), ('assistant', general.ASSISTANT_TYPE, 'Drafted it.')):
            s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (stamp(-500), s.add_comment(tid, who, kind, words)))
        rid = wrapup.agent_reply(s, tid, 'Hi Erin - yes, Thursday stands.', 'assistant')['review_id']
        spawn.reset_mock()
        try: ingest.ingest_message(s, wa('w2', 'great - and can you bring the budget sheet?', stamp(-60)), llm=llm)
        finally: general.OPENING.discard(tid)
    assert [c[0][0].__name__ for c in spawn.call_args_list] == ['_replan_general']           # the agent is woken to answer it
    said = general.latest_block(s, tid)
    assert 'THE NEWEST MESSAGE - from Erin Blake' in said and 'budget sheet' in said
    assert 'THE DRAFT WAITING NOW (' in said and 'written for this message' not in said and 'BEFORE the newest message' in said


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

def test_where_the_agent_reads_what_is_learned_it_is_told_how_a_rule_is_kept():
    "Asked to save a playbook, the agent on the real CLI read the learned facts, then wrote a file in the CLI's own memory folder - no card."
    assert '`propose` write_playbook' in agenttools.TOOLS['owner_memory'][1] and 'never written to a file of your own' in agenttools.TOOLS['owner_memory'][1]


# ── F7: a finished turn is never woken ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_turn_its_summary_calls_finished_is_not_judged():
    assert hooks.finished({'nothing_left': True})
    assert not hooks.finished({'on_you': ['Press Send on the reply to Ray']}) and not hooks.finished(None)
    brain = mock.Mock(side_effect=AssertionError('never read'))
    hooks.judge_ended(MemoryStore(), 1, 's1', 'Ready for your Mark done.', brain=brain, wait=True, then=brain, summ={'nothing_left': True})
    assert 'has to answer, decide, send or press first' in hooks.ENDED_SYSTEM


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


# ── the owner's line on a chat: the agent's to re-plan, never a side read in its name (the owner, 2026-11-09 and 2026-11-10) ──────────────
CONV = 'wa:erin'


def chat_task(s, live=False):
    "A general task on a WhatsApp chat: Erin asked, the agent answered and left a draft; `live`: its next turn is already at work."
    tid = s.create_task({'Title': 'Budget meeting today?', 'Kind': 'general', 'Status': 'open'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'wa1', 'ConversationId': CONV, 'Channel': 'whatsapp', 'FromName': 'Erin Blake',
                         'FromEmail': 'whatsapp:15550001', 'SentAt': stamp(-600), 'BodyText': 'still on for 3pm? and is the room booked?', 'Status': 'routed'})
    for who, kind, words in ((general.BRIEF_ACTOR, general.USER_TYPE, 'brief'), ('assistant', general.ASSISTANT_TYPE, 'Drafted the answer.')):
        s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (stamp(-500), s.add_comment(tid, who, kind, words)))
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'ConversationId': CONV, 'Kind': 'draft_reply', 'Status': 'pending', 'SentAt': stamp(-600),
                        'DraftText': 'Hi Erin - yes, 3pm stands, and the room is booked till 4.'})
    if live: general.OPENING.add(tid)
    return tid, rid


def say_on_chat(s, text='yes 3pm, same room', at=None):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(channels, 'reread', side_effect=AssertionError('a side read')), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
        channels.ingest_own_message(s, {'external_id': 'me1', 'channel': 'whatsapp', 'conversation_id': CONV, 'sent_at': at or stamp(-60), 'body': text,
                                        'from_email': 'me'}, 'your line in the chat')
    return [(c[0][0].__name__, c[0][-1]) for c in spawn.call_args_list]


def test_the_owners_line_over_a_waiting_draft_wakes_the_agent_and_nothing_else_touches_the_draft():
    # the owner, 2026-11-09: "if we respond show on left side and then agent reevaluates if action still required" - a second model retired or
    # cut the agent's draft in its name, and the agent never heard the line until something else woke it
    s = MemoryStore(); tid, rid = chat_task(s)
    try: went = say_on_chat(s)
    finally: general.OPENING.discard(tid)
    assert [w for w, _ in went] == ['_replan_general'] and 'yes 3pm, same room' in went[0][1] and 'you already answered on WhatsApp' in went[0][1]
    rv = s.get_review(rid)
    assert rv['Status'] == 'pending' and rv['DraftText'] == 'Hi Erin - yes, 3pm stands, and the room is booked till 4.'     # the agent's to keep or withdraw
    lb = general.latest_block(s, tid)
    assert 'WHAT THE OWNER REPLIED ON THE THREAD THEMSELVES' in lb and 'yes 3pm, same room' in lb and 'THE DRAFT WAITING NOW (' in lb


def test_the_owners_line_while_a_turn_works_is_its_next_turn():
    # the night run, 2026-11-09: a turn started a second before the owner's "yes 3pm, same room" ended "check your calendar before Send" - its
    # closing words were re-read by a side model; now the line is the agent's own next turn, queued behind the one at work
    s = MemoryStore(); tid, _ = chat_task(s, live=True)
    try: went = say_on_chat(s)
    finally: general.OPENING.discard(tid)
    assert [w for w, _ in went] == ['_replan_pass'] and 'yes 3pm, same room' in went[0][1]


def test_a_line_with_no_draft_and_no_turn_at_work_stays_context_for_the_next_turn():
    # the owner, 2026-11-08: "it should show what i sent ... even if it does not trigger as a prompt"
    s = MemoryStore(); tid, rid = chat_task(s); s.decide_review(rid, 'sent', None, 'owner')
    assert say_on_chat(s) == [] and 'yes 3pm, same room' in general.latest_block(s, tid)


def test_where_no_agent_may_take_the_line_the_one_read_still_settles_the_draft():
    s = MemoryStore(); s.set_setting('answer_to_agent', 'off', 't'); tid, rid = chat_task(s)
    with reads('covered'), mock.patch('taskuary.ingest._spawn') as spawn:
        channels.ingest_own_message(s, {'external_id': 'me1', 'channel': 'whatsapp', 'conversation_id': CONV, 'sent_at': stamp(-60),
                                        'body': 'yes 3pm, same room', 'from_email': 'me'}, 'your line in the chat')
    assert not spawn.called and s.get_review(rid)['Status'] == 'superseded'


def test_a_draft_rewritten_in_a_later_turn_is_that_turns_card_and_the_old_one_its_record():
    # the owner, 2026-11-10 ("terrible bug?? why did this not create the draft email action card?"): a reply already waited - written before
    # any turn of the agent's - and his line asked for a short one with a file. The agent's new letter was written INTO that old review, so its
    # card stayed at the old draft's place far above, and the new turn drew no card at all
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor review', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'FromName': 'Paula Vance', 'FromEmail': 'paula@vendor.example',
                         'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Your review of the tool?', 'Status': 'routed'})
    old = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'A long review of every flaw.'})
    s._exec("UPDATE review SET CreatedAt='2026-11-10 08:01:00' WHERE ReviewId=?", (old,))
    for at, who, kind, words in (('2026-11-10 08:02:00', 'assistant', general.ASSISTANT_TYPE, 'Read it.'),
                                 ('2026-11-10 09:00:00', 'owner', general.USER_TYPE, 'reply with the file attached, short, keep the real flaws')):
        s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (at, s.add_comment(tid, who, kind, words)))
    new = wrapup.agent_reply(s, tid, 'Short version: two real flaws, sheet attached.', 'assistant')['review_id']
    assert new != old, 'a new review - its card stands in the turn that wrote it'
    assert s.get_review(old)['Status'] == 'closed_unsent' and s.get_review(old)['DecideNote'] == wrapup.REPLACED
    turn = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Replaced the waiting draft with the short one.')
    assert s.snap_draft(new, turn)
    [d] = general.draft_turns(s, tid)
    assert (d['review'], d['turn']) == (new, f'comment-{turn}')


def test_a_draft_the_agent_keeps_after_the_owner_prompted_is_raised_again_as_the_new_turn_s_card():
    # the owner, 2026-11-10: "The second you write ptompt on email action it should go gray and then it should generate new email action box under
    # it" - the page greys the old card for good once he has prompted past it, so a letter the agent files again unchanged (its own, from an
    # earlier turn) is a new card in this turn - written into the old review it stayed grey, and no card was live
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor review', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'FromName': 'Paula Vance', 'FromEmail': 'paula@vendor.example',
                         'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Your review of the tool?', 'Status': 'routed'})
    old = wrapup.agent_reply(s, tid, 'Two real flaws, details below.', 'assistant')['review_id']
    s._exec("UPDATE review SET CreatedAt='2026-11-10 08:01:00' WHERE ReviewId=?", (old,))
    s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', ('2026-11-10 09:00:00', s.add_comment(tid, 'owner', general.USER_TYPE, 'is that the right tone?')))
    new = wrapup.agent_reply(s, tid, 'Two real flaws, details below.', 'assistant')['review_id']
    assert new != old and s.get_review(old)['Status'] == 'closed_unsent' and s.get_review(old)['DecideNote'] == wrapup.REPLACED
    assert s.get_review(old)['DraftText'] == 'Two real flaws, details below.', 'the old card keeps its words'
    # ...and saved twice in the turn that wrote it, it is one card, rewritten in place
    assert wrapup.agent_reply(s, tid, 'Two real flaws - and one small one.', 'assistant')['review_id'] == new


def test_a_draft_made_before_the_owner_s_line_is_not_the_card_of_the_turn_that_answered_it():
    # the recorded walk, 2026-11-10: a reply drafted on arrival stood under the mail; the owner typed a line, the agent answered it and left the
    # draft alone - and the card jumped from above his line to under that answer's Next steps. The first answer after a draft wrote it only
    # when no line came in between: an answer after his line was his line's
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor review', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'FromName': 'Paula Vance', 'FromEmail': 'paula@vendor.example',
                         'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Your review of the tool?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'A long review of every flaw.'})
    s._exec("UPDATE review SET CreatedAt='2026-11-10 08:01:00' WHERE ReviewId=?", (rid,))
    for at, who, kind, words in (('2026-11-10 09:00:00', 'owner', general.USER_TYPE, 'make it shorter and attach the sheet'),
                                 ('2026-11-10 09:00:30', 'assistant', general.ASSISTANT_TYPE, 'Ok.')):
        s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (at, s.add_comment(tid, who, kind, words)))
    [d] = general.draft_turns(s, tid)
    assert (d['review'], d['turn']) == (rid, None), 'it stands by its time, under the mail it answers'
    # ...and one written while a turn worked is still that turn's, its answer stamped when the turn ends
    s._exec("UPDATE review SET CreatedAt='2026-11-10 09:00:10' WHERE ReviewId=?", (rid,))
    [d] = general.draft_turns(s, tid)
    assert d['turn'] is not None and d['turn'].startswith('comment-')
