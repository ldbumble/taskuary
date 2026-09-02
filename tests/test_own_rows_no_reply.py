"""A row Taskuary wrote itself has nobody to answer.

Meeting prep closed and put a draft in Review - "I finished the prep review… Sincerely, Uri
Whitfield" - addressed to no one. The prep row is on channel `own` (ownwork.py: work that began
inside Taskuary rather than arriving from outside), and can_reply treats an unrecognised channel
as replyable on purpose: silently refusing to answer a channel a future connector added is the
worse failure. But `own` is not unrecognised - it is ours, and there is no correspondent behind
it. Same for `assistant`: the assistant talks to you here, not by mail.
"""
import unittest

from taskuary import assistant, ownwork
from taskuary.outbound import can_reply
from taskuary.store import MemoryStore


class SelfAuthoredRows(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def test_work_you_started_here_is_not_answerable(self):
        self.assertFalse(can_reply(self.s, ownwork.CHANNEL))

    def test_the_assistants_own_posts_are_not_answerable(self):
        self.assertFalse(can_reply(self.s, assistant.CHANNEL))

    def test_a_report_is_still_not_answerable(self):
        """The original member of the list - nobody sent a report either."""
        self.assertFalse(can_reply(self.s, 'report'))

    def test_a_channel_nobody_recognises_is_still_answerable(self):
        """The rule this must not break: an item pushed in over /api/ingest/push, or a channel a
        future connector adds, stays replyable rather than being silently refused."""
        self.assertTrue(can_reply(self.s, 'some_future_connector'))

    def test_email_is_untouched(self):
        self.assertTrue(can_reply(self.s, 'email'))


if __name__ == '__main__':
    unittest.main()
