"""A chat task has no Continue button, so nothing said on one names it (the owner, 2026-11-07; the chat rulings of 2026-11-05: "Just type and
it continues"). A CLI that died mid-turn, a turn cut by a time limit, a check-back that could not wake the agent, a mail that could not be passed
in and a bulk stop all told the owner to press Continue on a chat task. They say "type to carry on" there; a coding task keeps its Continue."""
import unittest
from unittest import mock

from taskuary import bulk, checkback, clipool, general, ingest
from taskuary.store import MemoryStore


class TypeToCarryOn(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.chat = self.s.create_task({'Title': 'Plan the offsite with Erin Blake', 'Kind': 'general'}, 'o')
        self.code = self.s.create_task({'Title': 'Fix the export in northwind/ledger', 'Kind': 'coding'}, 'o')

    def test_the_words_follow_the_kind(self):
        self.assertEqual(general.carry_on(self.s.get_task(self.chat)), 'type to carry on')
        self.assertIn('Continue', general.carry_on(self.s.get_task(self.code)))

    def test_a_chat_agents_own_lines_never_name_continue(self):
        for said in (clipool.MID_TURN, general.timed_out_line()): self.assertNotIn('Continue', said)
        self.assertIn('type to carry on', clipool.MID_TURN)

    def test_a_cli_that_died_mid_turn_says_it_as_the_coding_chat_does(self):
        """The side-by-side walk, 2026-11-11: the coding chat said "the agent stopped in the middle of its turn ...", the general chat the same
        sentence led by "claude:" - one fact, one sentence, no process name."""
        from taskuary import agents
        with mock.patch.object(clipool, 'run', side_effect=clipool.Ended(f'{clipool.MID_TURN} (the CLI exited (3))')):
            with self.assertRaises(RuntimeError) as got:
                agents._run_live({}, 'claude', ['claude'], 'hi', lambda *a: None, 'task:1', None, None, None)
        # ...nor "(the CLI exited (3))" after it: machinery words the coding chat never showed (the overnight walk, 2026-11-11)
        self.assertEqual(str(got.exception), clipool.MID_TURN)

    def test_a_check_back_that_could_not_wake_the_agent(self):
        with mock.patch.object(general, 'session_for', return_value=None), \
             mock.patch.object(general, 'start_session', side_effect=RuntimeError('the CLI is signed out')):
            checkback.fire(self.s, self.chat, 'whether Erin answered')
        said = self.s.list_comments(self.chat)[-1]['Body']
        self.assertIn('type to carry on', said); self.assertNotIn('Continue', said)

    def test_a_mail_that_could_not_be_passed_in(self):
        with mock.patch.object(general, 'session_for', return_value=None), mock.patch.object(general, 'idled', return_value=False):
            ingest._pass_general(self.s, self.chat, {'from_name': 'Erin Blake', 'from_email': 'erin@northwind.example'})
        said = self.s.list_comments(self.chat)[-1]['Body']
        self.assertIn('type to carry on', said); self.assertNotIn('Continue', said)

    def test_a_bulk_stop_says_each_kinds_way_on(self):
        row = lambda tid, chat: {'tid': tid, 'title': 't', 'chat': chat}
        chats = bulk.stop_receipt({'done': [row(self.chat, True)], 'stuck': []})
        self.assertIn('typing in its chat carries it on', chats); self.assertNotIn('Continue', chats)
        self.assertIn('Continue picks it up', bulk.stop_receipt({'done': [row(self.code, False)], 'stuck': []}))
        both = bulk.stop_receipt({'done': [row(self.chat, True), row(self.code, False)], 'stuck': []})
        self.assertIn('typing in its chat', both); self.assertIn('a coding agent: Continue', both)


if __name__ == '__main__':
    unittest.main()
