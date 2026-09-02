"""Discussing an assistant note starts a conversation, rather than replaying the note.

Reported 2026-09-02: "I hit chat with assistant and the chat didn't start going." Nothing had
failed - /discuss returned 200, the workspace opened, and there was simply never anything to
start. The seeded first message was the assistant's own Timeline note, which the owner had just
read, and then it waited for them to type.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import assistant, general, server

c = TestClient(server.app)
S = server.store


def _idea(text='Rotate the pasted secrets and move her to a vault.', key='k'):
    mid = S.add_message({'ExternalId': f'assistant:{key}', 'Channel': 'assistant',
                         'FromEmail': 'assistant@taskuary', 'FromName': 'Your assistant',
                         'Subject': 'secrets in a chat', 'BodyText': text, 'Status': 'filed'})
    i = S.upsert_idea({'key': key, 'kind': 'thought', 'text': text, 'sig': 's',
                       'action': {'mid': mid, 'title': 'Rotate the pasted secrets',
                                  'why': 'they were pasted in plaintext at 13:5x'}},
                      '2026-09-02 15:00:00')
    return i['IdeaId']


class OpeningTests(unittest.TestCase):
    def test_discussing_a_note_asks_the_assistant_to_open(self):
        iid = _idea(key='opens')
        with mock.patch.object(server, '_assistant_opens') as opens:
            out = c.post(f'/api/assistant/ideas/{iid}/discuss', json={}).json()
        self.assertTrue(out['created'])
        opens.assert_called_once_with(out['taskId'])

    def test_reopening_the_same_discussion_does_not_open_it_again(self):
        """It is a conversation, not a greeting: coming back to it must not start over."""
        iid = _idea(key='again')
        with mock.patch.object(server, '_assistant_opens'):
            first = c.post(f'/api/assistant/ideas/{iid}/discuss', json={}).json()
        with mock.patch.object(server, '_assistant_opens') as opens:
            second = c.post(f'/api/assistant/ideas/{iid}/discuss', json={}).json()
        self.assertEqual(first['taskId'], second['taskId'])
        self.assertFalse(second['created'])
        opens.assert_not_called()

    def test_the_instruction_is_never_written_as_the_owners_words(self):
        """Putting words in the owner's mouth in their own transcript is the thing to avoid."""
        iid = _idea(key='mouth')
        with mock.patch.object(server, '_assistant_opens'):
            tid = c.post(f'/api/assistant/ideas/{iid}/discuss', json={}).json()['taskId']
        seen = {}
        class FakeSession:
            def send_prompt(self, text, **kw):
                seen['text'], seen['kw'] = text, kw
                S.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I would rotate both today.')
                return 'I would rotate both today.'
        with mock.patch.object(general, 'start_session', return_value=FakeSession()):
            server._assistant_opens(tid)
        self.assertFalse(seen['kw']['as_owner'])
        self.assertFalse(seen['kw']['echo'])
        self.assertIn('do not repeat it back', seen['text'])
        said = [x for x in S.list_comments(tid) if x['ActorType'] == general.USER_TYPE]
        self.assertEqual(said, [])                                  # the owner said nothing, and it shows
        self.assertTrue(any('rotate both today' in x['Body'] for x in S.list_comments(tid)))

    def test_a_brain_that_cannot_answer_leaves_the_chat_usable(self):
        """An opening line that could not be written costs a sentence - not the conversation."""
        iid = _idea(key='nobrain')
        with mock.patch.object(server, '_assistant_opens'):
            tid = c.post(f'/api/assistant/ideas/{iid}/discuss', json={}).json()['taskId']
        with mock.patch.object(general, 'start_session', side_effect=RuntimeError('no AI connector')):
            server._assistant_opens(tid)                            # must not raise
        self.assertTrue(S.get_task(tid))


class SendPromptTests(unittest.TestCase):
    def test_speaking_as_the_owner_stays_the_default(self):
        """Every existing caller is the owner typing; only the opening turn is not."""
        import inspect
        sig = inspect.signature(general.GeneralSession.send_prompt)
        self.assertIn('as_owner', sig.parameters)
        self.assertIs(sig.parameters['as_owner'].default, True)


if __name__ == '__main__':
    unittest.main()
