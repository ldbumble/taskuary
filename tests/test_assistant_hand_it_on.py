"""SENT ON TO A PERSON, IN WORDS (the owner, 2026-11-03: "it did nothing and responded nothing??"). An FYI was made a task with Should be a
task, the owner typed "this should be sent to <an outside address>", and the Assistant answered that nothing had been forwarded and they
could forward it from their own mail: its task.handoff missed twice on "Name the task (TQ-0123), or open it first", and the last pass was
told to say "what they can do". Hand it to a person must come up filled in, and a turn that truly cannot act says why in Taskuary's terms."""
import unittest
from contextlib import ExitStack
from unittest import mock

from taskuary import concierge, funnel, server
from tests.assistant_queries import _guards, _scripted, _world, c

GAIL = 'gail@vendor.example'


def turn(s, text, key, answers, seen=None):
    seen = [] if seen is None else seen
    with ExitStack() as st:
        _guards(st); st.enter_context(mock.patch.object(server, 'store', s))
        return concierge.say(s, text, key=key, llm=_scripted(answers, seen)), seen


def made_task(s, mid=5):
    "Should be a task, pressed on the FYI: the task it made"
    from taskuary import ingest
    with mock.patch.object(ingest, 'ask_later'): return ingest.task_from_message(s, mid, 'owner', 'task', 'owner')


class HandItOn(unittest.TestCase):
    def test_on_a_task_hand_it_to_a_person_comes_up_with_the_address_and_note(self):
        out, _ = turn(_world(), f'send this to {GAIL}', 'msg:1', [c('task.handoff', who=GAIL, note='Can you take this?')])
        self.assertEqual(out['light']['verb'], 'forward')
        self.assertEqual(out['light']['hand'], {'to': GAIL, 'note': 'Can you take this?'})
        self.assertEqual(out['say'], '')

    def test_on_an_fyi_its_task_is_made_and_the_form_comes_up_on_it_nothing_sent(self):
        s = _world()
        out, _ = turn(s, f'this should be sent to {GAIL}', 'msg:5', [c('task.handoff', who=GAIL)])
        t = int(s.get_message(5)['TaskId'])
        self.assertEqual((out['light']['verb'], out['light']['tid'], out['light']['hand']['to']), ('forward', t, GAIL))
        self.assertEqual(out['decision'], {'verb': 'setting'}, 'the page reads the rail again: the row is a task now')
        self.assertNotIn(s.get_task(t)['Status'], ('done', 'dropped', 'waiting'), 'nothing went out')

    def test_a_row_read_before_should_be_a_task_went_through_finds_the_task_its_mail_became(self):
        s = _world()
        stale = funnel.item_for_key(s, 'msg:5')
        t = made_task(s)
        with ExitStack() as st:
            _guards(st); st.enter_context(mock.patch.object(server, 'store', s))
            out = concierge.call_turn(s, 0, {'kind': 'task.handoff', 'params': {'who': GAIL}}, stale, f'send this to {GAIL}')
        self.assertEqual((out['light']['verb'], out['light']['tid']), ('forward', t))

    def test_nothing_on_the_table_the_miss_names_the_task_the_chat_just_made(self):
        s = _world()
        t = made_task(s)
        ref = f'TQ-{t:04d}'
        # the press's receipt, as receipt_turn records it in the dock (a words card carrying the task's ref)
        tid = int(s.get_setting('assistant_dock_task_id') or 0) or None
        if not tid:
            turn(s, 'hello', None, ['Hello.'])
            tid = int(s.get_setting('assistant_dock_task_id'))
        concierge.record(s, tid, 'assistant', f'Done - Should be a task · {ref}.', {'kind': 'words', 'key': None, 'title': 'Should be a task',
                                                                                 'chips': [], 'tid': None, 'ref': ref})
        def retry(user):
            self.assertIn(f'ref {ref}', user)
            return c('task.handoff', who=GAIL, ref=ref)
        out, _ = turn(s, f'This should be sent to {GAIL}', None, [c('task.handoff', who=GAIL), retry])
        self.assertEqual((out['light']['verb'], out['light']['tid'], out['light']['hand']['to']), ('forward', t, GAIL))

    def test_a_turn_that_cannot_act_is_never_told_to_send_the_owner_to_their_own_mail(self):
        seen = []
        turn(_world(), f'This should be sent to {GAIL}', None, [c('task.handoff', who=GAIL)] * 2 + ['It needs a task first.'], seen)
        asks = [u for _, u in seen[1:]]
        self.assertTrue(asks and all('outside Taskuary' in u for u in asks), asks)
        self.assertFalse(any('what they can do' in u for u in asks))

    def test_a_row_button_called_by_its_id_is_the_tool_its_row_runs(self):
        self.assertEqual(concierge.parse_call(c('forward', who=GAIL))[1], {'kind': 'task.handoff', 'params': {'who': GAIL}})
        self.assertEqual(concierge.parse_call(c('watch'))[1], {'kind': 'button.light', 'params': {'button': 'watch'}})

    def test_the_index_says_any_address_will_do(self):
        from taskuary import toolcatalog
        self.assertIn('any email address', toolcatalog.PURPOSE['task.handoff'])
        self.assertNotIn('address that has written here', toolcatalog.PURPOSE['task.handoff'])


if __name__ == '__main__':
    unittest.main()
