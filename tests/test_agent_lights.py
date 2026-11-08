"""THE AGENT PICKS THE LIT BUTTON (the owner, 2026-11-08). On a task an agent works the light is read off the agent's own latest turn - the
Send of a card it set up (never one whose channel is not connected), Mark done where it said nothing is left, else nothing - and no model
reads it. The bar has no Reply or Hand it to a person while an AI is connected: the agent does those from the chat. And a press the agent's
turn said it waits on (its summary's `after_press`) starts its next turn, once. Invented Northwind people only (CLAUDE.md)."""
import json
from unittest import mock

from taskuary import advisor, capabilities, concierge, general, selfclose, verdicts
from taskuary.store import MemoryStore


def agent_task(s, summary=None):
    tid = s.create_task({'Title': 'Post the safety numbers', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote the post.')
    if summary is not None: s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps(summary))
    return tid


def lit(s, tid):
    def no_model(*a, **kw): raise AssertionError('no model reads an agent task')
    with mock.patch.object(advisor, 'build_llm', no_model): return advisor.decide(s, f'task:{tid}')


def test_the_agents_nothing_left_lights_mark_done_and_no_model_reads_it():
    s = MemoryStore(); tid = agent_task(s, {'about': 'Erin asked', 'did': 'Erin answered herself', 'nothing_left': True})
    d = lit(s, tid)
    assert (d['verb'], d['by'], d['line']) == ('close', 'agent', ''), d


def test_a_turn_that_leaves_nothing_said_lights_nothing():
    s = MemoryStore(); tid = agent_task(s, {'about': 'Erin asked', 'did': 'Looked it up', 'on_you': []})
    assert lit(s, tid)['verb'] is None


def test_a_post_whose_network_is_not_connected_lights_nothing():
    s = MemoryStore(); tid = agent_task(s, {'about': 'a post', 'did': 'Wrote the post'})
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'a LinkedIn post',
                  'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A year without a lost-time injury.'})})
    with mock.patch.object(advisor, 'pressable', return_value=''): assert lit(s, tid)['verb'] is None
    with mock.patch('taskuary.outbound.connect_fix', return_value=None), mock.patch.object(advisor, 'pressable', return_value=''):
        assert lit(s, tid)['verb'] in ('approve', 'send_close'), 'connected, its Send is the move'


def test_with_an_ai_the_row_has_no_reply_or_hand_off_and_without_one_it_does():
    s = MemoryStore()
    mid = s.add_message({'ExternalId': 'e1', 'Channel': 'email', 'Subject': 'Invoice', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                         'BodyText': 'Can you check it?', 'Status': 'routed'})
    tid = s.create_task({'Title': 'Check the invoice', 'Kind': 'reply', 'Status': 'open'}, 'router'); s.attach_message(mid, tid)
    it = {'kind': 'task', 'tid': tid, 'mid': mid, 'key': f'task:{tid}', 'channel': 'email'}
    verbs = lambda: {b['verb'] for b in concierge.row_buttons(s, it)}
    with mock.patch.object(capabilities, 'has_ai', return_value=False): assert {'reply', 'forward'} <= verbs()
    with mock.patch.object(capabilities, 'has_ai', return_value=True): assert not {'reply', 'forward'} & verbs()


def test_the_summary_keeps_the_press_it_waits_on():
    b = lambda **kw: f"{selfclose.SUMMARY_OPEN}{json.dumps({'about': 'a', 'did': 'b', **kw})}{selfclose.SUMMARY_CLOSE}"
    assert selfclose.summary_marker(b(after_press='send'))[1]['after_press'] == 'send'
    assert 'after_press' not in selfclose.summary_marker(b(after_press='dance'))[1]
    assert 'after_press' in selfclose.SUMMARY_LINE


def test_the_press_it_waits_on_starts_one_turn_and_no_other_does():
    s = MemoryStore(); tid = agent_task(s, {'about': 'a', 'did': 'Drafted the forward to Ray', 'after_press': 'send'})
    with mock.patch.object(general, 'start_session') as go, mock.patch.object(general.threading, 'Thread') as th:
        th.side_effect = lambda target, **kw: mock.Mock(start=target)
        assert not general.follow_up(s, tid, 'handoff')
        assert general.follow_up(s, tid, 'send') and go.return_value.send_prompt.call_args.kwargs['as_owner'] is False
        assert not general.follow_up(s, tid, 'send'), 'once per turn'
    tid2 = agent_task(s, {'about': 'a', 'did': 'b'})
    with mock.patch.object(general, 'follow_up') as f, mock.patch.object(verdicts, '_decide', return_value={'ok': True}):
        verdicts.decide(s, {'ReviewId': 1, 'TaskId': tid2}, 'approve', 'text')
        verdicts.decide(s, {'ReviewId': 1, 'TaskId': tid2}, 'reject')
    assert [c.args[1:3] for c in f.call_args_list] == [(tid2, 'send')]


def test_an_agents_email_draft_with_no_mailbox_lights_nothing():
    """A bare review row has no Channel: the mail it answers says it is email, and no mailbox is connected - the card says Connect email."""
    s = MemoryStore(); tid = agent_task(s, {'about': 'Erin asked', 'did': 'Drafted the answer'})
    mid = s.add_message({'ExternalId': 'e2', 'Channel': 'email', 'Subject': 'Overtime', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'BodyText': 'September overtime?', 'Status': 'routed', 'TaskId': tid})
    s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, 2,140 hours.'})
    with mock.patch.object(advisor, 'pressable', return_value=''): assert lit(s, tid)['verb'] is None
