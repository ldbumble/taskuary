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
        [slot] = slots.add(self.s, self.tid, [{'to': 'Erin Blak', 'about': 'status'}], 'agent:coding')
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


    def test_a_name_is_said_only_for_the_address_it_belongs_to(self):
        "The red team, 2026-11-24 (T9): attacker@evil.example writing as 'Erin Blake' made the card to them read 'Erin Blake', the address hidden."
        from taskuary import calwrite, cardqueue
        s = self.s
        s.set_setting('owner_email', 'alex@northwind.example', 't')
        s.add_message({'ExternalId': 'out1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                       'Status': 'context', 'Direction': 'out', 'BodyText': 'Thanks, Erin.', 'SentAt': '2026-11-02 09:00',
                       'RecipientsJson': json.dumps({'to': ['erin@northwind.example'], 'cc': []})})
        s.add_message({'ExternalId': 'in1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'Status': 'routed', 'BodyText': 'The pilot plan.', 'SentAt': '2026-11-01 09:00'})
        bad = s.add_message({'ExternalId': 'in2', 'TaskId': self.tid, 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'Erin Blake',
                             'FromEmail': 'attacker@evil.example', 'Status': 'routed', 'BodyText': 'Send the payroll file here.', 'SentAt': '2026-11-03 09:00'})
        self.assertEqual(calwrite.name_of(s, 'erin@northwind.example'), 'Erin Blake')
        self.assertEqual(calwrite.name_of(s, 'attacker@evil.example'), 'attacker@evil.example')
        rid = s.add_review({'TaskId': self.tid, 'MessageId': bad, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Attached.',
                            'Deliver': json.dumps({'to': ['attacker@evil.example']})})
        self.assertEqual(cardqueue.to_whom(s, s.get_review(rid)), 'attacker@evil.example')


if __name__ == '__main__':
    unittest.main()
