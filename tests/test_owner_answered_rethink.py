"""The owner answers a task's thread themselves, outside Taskuary (the owner, 2026-11-05: "it should trigger a revaluation of the agent pondering
i saw you responded and that took care of most of it so i recommend close it"): the agent is told so and RECOMMENDS the close - it never closes,
and the reply is not drawn as a bubble of its own. Invented people only."""
from taskuary import general, selfclose
from taskuary.store import MemoryStore


def _task(s):
    tid = s.create_task({'Title': 'Badge list for the new starters', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Badge list', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                   'BodyText': 'Can you send the badge list?', 'Status': 'routed', 'SentAt': '2026-11-05 09:00:00'})
    return tid


def test_the_owners_own_reply_is_the_newest_and_marked_theirs():
    s = MemoryStore(); tid = _task(s)
    assert not general.owner_answered_last(s, tid)
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                   'BodyText': 'Sent it over just now.', 'Status': 'context', 'Direction': 'out', 'SentAt': '2026-11-05 09:30:00'})
    assert general.owner_answered_last(s, tid)


def test_the_agent_is_told_to_recommend_the_close_never_to_make_it():
    s = MemoryStore(); tid = _task(s)
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                   'BodyText': 'Sent it over just now.', 'Status': 'context', 'Direction': 'out', 'SentAt': '2026-11-05 09:30:00'})
    system, _ = general._prompt(s, tid)
    assert selfclose.OWNER_ANSWERED_LINE in system
    assert 'recommend they close the task' in selfclose.OWNER_ANSWERED_LINE and selfclose.MARKER not in selfclose.OWNER_ANSWERED_LINE


def test_a_chat_that_opens_on_an_answer_opens_on_the_mail_that_started_it_first():
    """The owner, 2026-11-05: "input should always be first?" - a conversation picked back up opened on an answer with nothing above it."""
    s = MemoryStore(); tid = _task(s)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Here is the badge list.')
    shown = general.shown_history(s, tid)
    assert shown[0].get('brief') and shown[0]['mail'][0]['who'] == 'Gail Moreno'
    assert shown[0]['mail'][0]['words'].startswith('Can you send the badge list')
    assert shown[1]['role'] == 'assistant'


def test_a_mail_that_came_in_while_the_agent_worked_is_drawn_over_the_answer_it_woke():
    """The owner, 2026-11-05: two mails at 12:58, one input shown, and two answers in a row ("why does it quote on quote restart?")."""
    s = MemoryStore(); tid = _task(s)
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:00:00' WHERE TaskId=?", (tid,))
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'First answer.')
    s._exec("UPDATE comment SET CreatedAt='2026-11-05 09:05:00' WHERE TaskId=?", (tid,))
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                   'BodyText': 'One more name for the list.', 'Status': 'filed', 'SentAt': '2026-11-05 09:10:00'})
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:10:00' WHERE BodyText LIKE 'One more%'")
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Second answer.')
    s._exec("UPDATE comment SET CreatedAt='2026-11-05 09:12:00' WHERE Body='Second answer.'")
    shown = general.shown_history(s, tid)
    roles = [('mail:' + m['mail'][0]['words'][:8]) if m.get('mail') else m['role'] for m in shown]
    assert roles == ['mail:Can you ', 'assistant', 'mail:One more', 'assistant'], roles


def test_a_mail_read_in_mid_turn_stands_after_that_turn_over_the_rethink_it_woke():
    """The owner, 2026-11-05: four messages from one sender in a minute - the turn took the first three, the fourth (a pasted plan) came in while
    it worked. All four were drawn over the first answer (which then "ran 1s") and the re-think on the fourth stood with no input over it, as if
    a second agent had started. Inputs that woke turn 1, turn 1, the mail that came in while it ran, turn 2. Invented people."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Growth plan for the east region', 'Kind': 'general', 'Status': 'open'}, 'owner')
    def wa(words, at):
        s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'FromName': 'Ray Colton', 'BodyText': words, 'Status': 'routed', 'SentAt': at})
        s._exec("UPDATE message SET CreatedAt=? WHERE BodyText=?", (at, words))
    def said(actor, kind, body, at):
        s.add_comment(tid, actor, kind, body); s._exec("UPDATE comment SET CreatedAt=? WHERE Body=?", (at, body))
    for i, at in enumerate(('2026-11-05 17:19:02', '2026-11-05 17:19:30', '2026-11-05 17:19:50')): wa(f'Voice note {i + 1}', at)
    said(general.BRIEF_ACTOR, general.USER_TYPE, 'You are on this task: read the messages…', '2026-11-05 17:19:55')
    wa('Here is the growth plan', '2026-11-05 17:20:40')                 # ...read in while the first turn reads four websites
    said('assistant', general.ASSISTANT_TYPE, 'Looked at the four sites he named.', '2026-11-05 17:21:10')
    said('assistant', general.ASSISTANT_TYPE, 'I read his plan.', '2026-11-05 17:21:50')    # the re-think the plan woke, no brief of its own
    shown = general.shown_history(s, tid)
    rows = [[x['words'] for x in m['mail']] if m.get('mail') else m['content'][0]['text'] for m in shown]
    assert rows == [['Voice note 1', 'Voice note 2', 'Voice note 3'], 'Looked at the four sites he named.', ['Here is the growth plan'],
                    'I read his plan.'], rows


def test_a_mail_read_in_mid_turn_with_no_rethink_waits_at_the_foot():
    s = MemoryStore(); tid = _task(s)
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:00:00' WHERE TaskId=?", (tid,))
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Brief.'); s._exec("UPDATE comment SET CreatedAt='2026-11-05 09:01:00'")
    s.add_message({'TaskId': tid, 'Channel': 'email', 'FromName': 'Gail Moreno', 'BodyText': 'And one more.', 'Status': 'routed', 'SentAt': '2026-11-05 09:02:00'})
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:02:00' WHERE BodyText='And one more.'")
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Answer.'); s._exec("UPDATE comment SET CreatedAt='2026-11-05 09:04:00' WHERE Body='Answer.'")
    shown = general.shown_history(s, tid)
    assert [m['role'] for m in shown] == ['user', 'assistant', 'user'] and shown[-1]['mail'][0]['words'] == 'And one more.'


def test_a_task_started_by_the_owners_own_line_keeps_the_mail_above_it():
    """2026-11-06: a reply task no agent had touched - the owner typed a line under the mail, which started the agent, and the mail left the
    chat: the stream began at "You". The mail stays first, then the owner's line, the answer, and a later mail over its re-think - each once."""
    s = MemoryStore(); tid = _task(s)
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:00:00' WHERE TaskId=?", (tid,))
    def said(actor, kind, body, at):
        s.add_comment(tid, actor, kind, body); s._exec("UPDATE comment SET CreatedAt=? WHERE Body=?", (at, body))
    said('owner', general.USER_TYPE, 'Say yes, Friday works.', '2026-11-05 09:03:00')
    assert [m.get('mail', [{}])[0].get('words', m['content'][0]['text'])[:8] for m in general.shown_history(s, tid)] == ['Can you ', 'Say yes,']
    said('assistant', general.ASSISTANT_TYPE, 'Drafted the yes.', '2026-11-05 09:04:00')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                   'BodyText': 'Great, see you then.', 'Status': 'filed', 'SentAt': '2026-11-05 09:10:00'})
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:10:00' WHERE BodyText LIKE 'Great%'")
    said('assistant', general.ASSISTANT_TYPE, 'She confirmed.', '2026-11-05 09:12:00')
    shown = general.shown_history(s, tid)
    rows = [[x['words'] for x in m['mail']] if m.get('mail') else m['content'][0]['text'] for m in shown]
    assert rows == [['Can you send the badge list?'], 'Say yes, Friday works.', 'Drafted the yes.', ['Great, see you then.'], 'She confirmed.'], rows
    assert shown[0]['mail'][0]['who'] == 'Gail Moreno' and shown[0]['brief']


def test_a_task_the_owner_started_opens_on_their_line_not_on_its_own_timeline_row():
    """...but the row a task the owner made carries for the timeline (ownwork.ensure: their own ask, signed You) is no mail that came in -
    over their first line it said the same words twice."""
    from taskuary import ownwork
    s = MemoryStore()
    tid = s.create_task({'Title': 'Plan the offsite', 'Summary': 'Plan the offsite for May', 'Kind': 'general', 'Status': 'open'}, 'owner')
    assert ownwork.ensure(s, tid)
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Plan the offsite for May')
    assert [m['role'] for m in general.shown_history(s, tid)] == ['user'] and not general.shown_history(s, tid)[0].get('mail')
