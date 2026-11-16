"""THE OWNER'S WORDS FOR A DRAFT ARE KEPT (phase B, 2026-10-23): on its review, read back by the person it goes to (byrecipient.instructions) -
the app's own words for a chase are not his. The press log that sat beside them went with the Advisor's lit button (2026-11-15)."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import byrecipient, server
from taskuary.store import MemoryStore
from tests.test_row_decision import _Rail


class InstructionTests(_Rail):
    def _mail(self, s):
        t = s.create_task({'Title': 'Invoice question', 'Status': 'open', 'Kind': 'reply'}, 'owner')
        mid = s.add_message({'ConversationId': 'c-inv', 'Channel': 'email', 'Subject': 'Invoice', 'FromEmail': 'erin@vendor.example',
                             'FromName': 'Erin Blake', 'BodyText': 'When do you pay?', 'Status': 'routed', 'TaskId': t})
        return t, mid

    def test_the_owners_words_for_a_draft_are_kept_on_the_review_and_read_back_by_person(self):
        s = MemoryStore(); t, mid = self._mail(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
             mock.patch('taskuary.responder.write_draft', lambda *a, **k: 'Hi Erin, Friday.'):
            c = TestClient(server.app)
            rid = c.post(f'/api/messages/{mid}/reply', json={'instruction': 'say we pay on Friday'}).json()['reviewId']
            c.post(f'/api/reviews/{rid}/draft', json={'instruction': 'say we pay on Friday'})     # the same words handed on: kept once
            c.post(f'/api/reviews/{rid}/draft', json={'instruction': 'shorter'})
            c.post(f'/api/messages/{mid}/reply', json={'redraft': True})                         # a redraft with no words keeps what was said
        said = json.loads(s.get_review(rid)['Instructions'])
        self.assertEqual([x['text'] for x in said], ['say we pay on Friday', 'shorter'])
        got = byrecipient.instructions(s, to='erin@vendor.example')
        self.assertEqual([(x['rid'], x['domain'], x['text']) for x in got], [(rid, 'vendor.example', 'say we pay on Friday'), (rid, 'vendor.example', 'shorter')])
        self.assertEqual(byrecipient.instructions(s, domain='northwind.example'), [])

    def test_a_chases_brief_is_the_apps_words_not_the_owners(self):
        s = MemoryStore(); t, mid = self._mail(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
             mock.patch('taskuary.responder.write_draft', lambda *a, **k: 'Hi Erin'):
            rid = server.open_reply(mid, server.OpenReplyBody(instruction='a short chase to erin', app_words=True))['reviewId']
        self.assertFalse(s.get_review(rid).get('Instructions'))

    def test_an_outbound_redraft_follows_the_instruction(self):
        from taskuary import outbox
        s = MemoryStore()
        t = s.create_task({'Title': 'Results to Ray', 'Status': 'open'}, 'owner')
        rid = s.add_review({'TaskId': t, 'Kind': 'draft', 'Status': 'pending', 'Deliver': json.dumps({'channel': 'email', 'to': ['ray@northwind.example']})})
        with mock.patch.object(outbox, 'draft_message', lambda store, ch, to, about, **k: about) as _d:
            got = outbox.redraft_review(s, s.get_review(rid), resolution='', instruction="THE OWNER'S INSTRUCTION: warmer")
        self.assertIn('warmer', got)
