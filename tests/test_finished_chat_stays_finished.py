"""Reading a closed conversation is reading, not resuming.

TQ-0291 was answered, closed and marked done at 16:21:21. Fourteen seconds later a session
started on it, parked, and sat there for forty-five minutes under "Waiting on you" with nothing
to answer - and clicking it showed nothing, because there was nothing.

Nobody picked it back up. GeneralWorkspace posts to /assistant/session on MOUNT, so opening the
finished chat started the session; BoardView.laneOf reads a session that began after ClosedAt as
"somebody picked this back up" (deliberately - that rule is right), and a done task reappeared as
work waiting on the owner.

Sending a message still starts one. That IS picking it back up.
"""
import unittest

from fastapi.testclient import TestClient

from taskuary import general, server

c = TestClient(server.app)


def _chat(status='open'):
    tid = c.post('/api/tasks', json={'Title': 'competitor research', 'Kind': 'general',
                                     'Summary': 'what are the others doing?'}).json()['taskId']
    if status != 'open':
        c.patch(f'/api/tasks/{tid}', json={'Status': status})
    return tid


class AFinishedChatStaysFinished(unittest.TestCase):
    def tearDown(self):
        """Close what we opened. drop_session only forgets DEAD sessions, so a live one has to be
        closed first - left behind, an assistant session shows up in /api/terminals and the
        terminal suite's "nothing is running" assertion fails several files later."""
        from taskuary import terminal
        for t in getattr(self, '_tids', []):
            sess = general.session_for(t)
            if sess is not None:
                try: terminal.close(sess.sid)
                except Exception: pass
            try: general.drop_session(t)
            except Exception: pass

    def test_opening_a_done_chat_starts_no_session(self):
        tid = _chat('done'); self._tids = [tid]
        r = c.post(f'/api/tasks/{tid}/assistant/session', json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()['session'])
        self.assertIsNone(general.session_for(tid))

    def test_opening_a_dropped_chat_starts_no_session(self):
        tid = _chat('dropped'); self._tids = [tid]
        self.assertIsNone(c.post(f'/api/tasks/{tid}/assistant/session', json={}).json()['session'])

    def test_the_conversation_still_comes_back(self):
        """Refusing to resume must not mean refusing to READ - the history is the point."""
        tid = _chat('done'); self._tids = [tid]
        d = c.post(f'/api/tasks/{tid}/assistant/session', json={}).json()
        self.assertIn('messages', d)
        self.assertIn('providers', d)

    def test_an_open_chat_is_untouched(self):
        """The ordinary case must keep working exactly as it did."""
        tid = _chat(); self._tids = [tid]
        r = c.post(f'/api/tasks/{tid}/assistant/session', json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(r.json()['session'])

    def test_closing_reaps_the_session_and_opening_it_again_does_not_bring_it_back(self):
        """The exact sequence behind TQ-0291. Marking done already closes the live session - that
        part always worked. What did not: mounting the workspace on the closed task started a
        SECOND one, fourteen seconds later, which is why the Board could tell it had been picked
        back up. It had not been."""
        tid = _chat(); self._tids = [tid]
        c.post(f'/api/tasks/{tid}/assistant/session', json={})
        self.assertIsNotNone(general.session_for(tid))
        c.patch(f'/api/tasks/{tid}', json={'Status': 'done'})
        self.assertIsNone(general.session_for(tid), 'marking done should reap it')
        c.post(f'/api/tasks/{tid}/assistant/session', json={})      # the page mounting again
        self.assertIsNone(general.session_for(tid), 'and opening it must not start another')


if __name__ == '__main__':
    unittest.main()
