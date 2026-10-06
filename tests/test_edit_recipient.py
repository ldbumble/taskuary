"""Who an email draft goes to is the owner's to correct, and a reply never goes back to the owner (2026-10-06: a task email
said "Devorah Cohn ?" - a name with no address - and the card had no way to give the address)."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import outbound, server, slots
from taskuary.store import MemoryStore


class EditRecipientTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tid = self.s.create_task({'Title': 'AP invoices', 'Kind': 'general', 'Status': 'open'}, 'owner')

    def test_a_task_email_with_no_address_is_given_one_on_its_card(self):
        [slot] = slots.add(self.s, self.tid, [{'to': 'Erin Blak', 'about': 'status'}], 'agent:coder')
        out = slots.draft(self.s, self.tid, 'Here is where AP stands.', slot=slot['id'])
        rid = out['review_id']
        r = self.c.put(f'/api/reviews/{rid}/envelope', json={'to': ['Erin@Northwind.example']})
        self.assertEqual(r.status_code, 200, r.text); self.assertEqual(r.json()['to'], ['erin@northwind.example'])
        self.assertEqual(json.loads(self.s.get_review(rid)['Deliver'])['to'], ['erin@northwind.example'])
        self.assertEqual(next(i for i in slots.all_(self.s, self.tid) if i['id'] == slot['id'])['out']['to'], 'erin@northwind.example')
        self.assertEqual(self.c.put(f'/api/reviews/{rid}/envelope', json={'to': ['Erin Blake']}).status_code, 422)   # a name is not an address

    def test_a_reply_on_top_of_your_own_mail_goes_to_whom_you_wrote(self):
        self.s.set_setting('owner_email', 'alex@northwind.example', 't')
        m = {'Channel': 'email', 'FromEmail': 'alex@northwind.example', 'SourceName': 'alex@northwind.example',
             'RecipientsJson': json.dumps({'to': ['gail@northwind.example'], 'cc': ['paula@northwind.example']})}
        env = outbound.reply_envelope(self.s, m)
        self.assertEqual(env['to'][0], 'gail@northwind.example'); self.assertNotIn('alex@northwind.example', env['to'] + env['cc'])


if __name__ == '__main__':
    unittest.main()
