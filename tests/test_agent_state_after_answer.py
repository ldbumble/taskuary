"""WHAT AN AGENT IS, AFTER IT ANSWERS, IS ONE SERVER READING (the email walk, 2026-10-29).

Three surfaces disagreed about one regular agent: the header read "answered · waiting on you" eight seconds into a start, while the
run had not begun; a Board card sat under "agent waiting on you" with "ready to send" on it, its body "Alex" - the sign-off of the
reply it drafted, the last line of its tail. The session's own word decides: one opened for a turn that has not taken is not
waiting, a parked one over its drafted reply is that reply waiting (taskstate), and the card shows what the turn said, from its start.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server, terminal, workerstate as ws
from taskuary.store import MemoryStore
from tests.test_general_turn_ends_short import a_claude, researcher, turn

REPLY = 'Hi Paula,\n\nThe announcement reads well. Two fixes before Monday: the date, and the link.\n\nBest,\nAlex'


class OpeningIsNotAnsweredTests(unittest.TestCase):
    def test_a_session_opened_for_a_turn_not_yet_taken_is_not_waiting(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            general.OPENING.add(tid); self.addCleanup(general.OPENING.discard, tid)
            sess = general.start_session(s, tid, pick='cli:claude')
            self.assertFalse(sess.waiting())
            self.assertFalse(sess.info()['waiting'])
            sess.spoke = True                                   # its turn ended - the door's OPENING mark may outlive it a moment
            self.assertTrue(sess.waiting())


class TheBoardCardShowsTheAnswerTests(unittest.TestCase):
    def test_a_parked_chat_card_carries_its_turns_answer_from_the_start(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, REPLY)
        sess = seen['session']
        self.assertTrue(sess.waiting())
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {sess.sid: sess}, clear=True):
            rows = TestClient(server.app).get('/api/runs/live').json()['data']
        card = next(r for r in rows if r['TaskId'] == tid)
        self.assertTrue(card['said'].startswith('Hi Paula,'))
        self.assertEqual(card['said'], ws.status(s, tid)['said'])


if __name__ == '__main__': unittest.main()
