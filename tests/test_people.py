"""Cross-channel people: handles stay reply addresses; joins are explicit and reversible."""
import os
import sqlite3
import tempfile
import unittest

from taskuary.ingest import notes_for
from taskuary.policy import evaluate
from taskuary.routing import score_candidate
from taskuary.store import MemoryStore, SQLiteStore, norm_handle


class PeopleTests(unittest.TestCase):
    def test_handle_normalization_never_guesses_a_country_code(self):
        self.assertEqual(norm_handle('imessage', '+1 (937) 555-0100'), '+19375550100')
        self.assertEqual(norm_handle('imessage', '937-555-0100'), '9375550100')
        self.assertNotEqual(norm_handle('imessage', '+1 (937) 555-0100'),
                            norm_handle('imessage', '937-555-0100'))
        self.assertEqual(norm_handle('email', ' Jane@Example.COM '), 'jane@example.com')

    def test_backfill_is_per_channel_and_preserves_raw_messages(self):
        path = os.path.join(tempfile.mkdtemp(), 'people.db')
        old = sqlite3.connect(path)
        old.execute('''CREATE TABLE message (MessageId INTEGER PRIMARY KEY, TaskId INTEGER, ExternalId TEXT,
          ConversationId TEXT, Channel TEXT, SourceName TEXT, Subject TEXT, FromName TEXT, FromEmail TEXT,
          SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT,
          Direction TEXT DEFAULT 'in', RecipientsJson TEXT)''')
        old.execute("INSERT INTO message (ExternalId,Channel,FromName,FromEmail,Status) VALUES ('a','email','Jane','same-handle','filed')")
        old.execute("INSERT INTO message (ExternalId,Channel,FromName,FromEmail,Status) VALUES ('b','telegram','Jane?','same-handle','filed')")
        old.commit(); old.close()

        s = SQLiteStore(path)
        ma, mb = s.get_message(1), s.get_message(2)
        self.assertEqual((ma['FromEmail'], mb['FromEmail']), ('same-handle', 'same-handle'))
        self.assertNotEqual(ma['PersonId'], mb['PersonId'])
        # Legacy handle policies still have their exact old, cross-channel string semantics.
        p = {'Name': 'old rule', 'Kind': 'sender', 'Pattern': 'same-handle',
             'Action': 'ignore', 'Reason': 'legacy'}
        self.assertEqual(evaluate({'from_email': 'same-handle'}, [p])['action'], 'ignore')
        s.cx.close()

    def test_merge_expands_person_reads_and_unmerge_restores_the_boundary(self):
        s = MemoryStore()
        email = s.ensure_identity('email', 'jane@example.com', 'Jane')
        phone = s.ensure_identity('imessage', '+1 937 555 0100', '+1 937 555 0100')
        tid = s.create_task({'Title': 'Quarterly close'}, 'test')
        s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email',
                       'FromEmail': 'jane@example.com', 'IdentityId': email['IdentityId'],
                       'BodyText': 'Please check the close.', 'Status': 'routed'})
        self.assertTrue(s.known_person_sender(email['CanonicalPersonId']))
        self.assertFalse(s.known_person_sender(phone['CanonicalPersonId']))

        root = s.merge_people(email['CanonicalPersonId'], phone['CanonicalPersonId'])
        joined_phone = s.identity(phone['IdentityId'])
        self.assertEqual(joined_phone['CanonicalPersonId'], root)
        snap = s.snapshots()[0]
        sig = score_candidate({'from_email': '+1 937 555 0100', 'person_id': root}, snap)
        self.assertEqual(sig['sender'], 1.0)

        s.add_memory({'Scope': 'person', 'ScopeKey': str(root), 'Note': 'Jane owns treasury questions.',
                      'Source': 'manual', 'Active': 1, 'CreatedBy': 'test'})
        s.update_person(root, notes='Jane prefers short replies.')
        self.assertEqual(notes_for(s, {'from_email': '+1 937 555 0100', 'person_id': root}),
                         ['Jane owns treasury questions.', 'Jane prefers short replies.'])

        self.assertTrue(s.unmerge_person(phone['PersonId']))
        separate = s.identity(phone['IdentityId'])
        self.assertNotEqual(separate['CanonicalPersonId'], root)
        self.assertFalse(s.known_person_sender(separate['CanonicalPersonId']))

    def test_owner_identity_is_structured_and_materialized_in_soul(self):
        s = MemoryStore()
        ident = s.register_owner_identity('email', 'uri@example.com', 'Uri Nussbaum', 7, verified=True)
        owner = s.owner_person()
        self.assertEqual(ident['CanonicalPersonId'], owner['PersonId'])
        soul = s.get_doc('soul')
        self.assertIn('## My connected identities', soul)
        self.assertIn('- email: Uri Nussbaum (uri@example.com)', soul)
        self.assertNotIn('token', soul.lower())
        self.assertNotEqual(ident['PersonId'], owner['PersonId'])
        self.assertTrue(s.unmerge_person(ident['PersonId']))
        from taskuary.docsync import sync_identities
        sync_identities(s, 'test')
        self.assertNotIn('uri@example.com', s.get_doc('soul'))

    def test_person_policy_is_explicit_and_first_time_sender_stays_legacy(self):
        s = MemoryStore()
        ident = s.ensure_identity('teams', 'jane@corp.example', 'Jane')
        person = {'Name': 'Jane urgent', 'Kind': 'person', 'Pattern': str(ident['CanonicalPersonId']),
                  'Action': 'escalate', 'Reason': 'Jane asked'}
        out = evaluate({'from_email': 'different-handle', 'person_id': ident['CanonicalPersonId']}, [person])
        self.assertEqual(out['action'], 'escalate')
        first_person = {'Name': 'new person', 'Kind': 'first_time_person', 'Pattern': None,
                        'Action': 'escalate', 'Reason': 'new'}
        self.assertEqual(evaluate({'person_id': ident['CanonicalPersonId']}, [first_person],
                                  known_sender=True, known_person=False)['action'], 'escalate')

    def test_people_api_joins_and_unjoins_without_deleting_people(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        old = server.store
        server.store = MemoryStore()
        try:
            client = TestClient(server.app)
            first = client.post('/api/identities', json={
                'channel': 'email', 'handle': 'jane@example.com', 'display_name': 'Jane'}).json()['identity']
            second = client.post('/api/identities', json={
                'channel': 'imessage', 'handle': '+1 937 555 0100'}).json()['identity']
            r = client.post(f"/api/people/{first['CanonicalPersonId']}/merge",
                            json={'source_person_id': second['CanonicalPersonId']})
            self.assertEqual(r.status_code, 200)
            joined = client.get('/api/directory/people').json()['data']
            jane = next(p for p in joined if p['PersonId'] == first['CanonicalPersonId'])
            self.assertEqual({i['Channel'] for i in jane['Identities']}, {'email', 'imessage'})
            self.assertTrue(any(m['PersonId'] == second['PersonId'] for m in jane['Members']))

            r = client.post(f"/api/people/{second['PersonId']}/unmerge")
            self.assertEqual(r.status_code, 200)
            separate = client.get('/api/directory/people').json()['data']
            self.assertIn(second['PersonId'], {p['PersonId'] for p in separate})
        finally:
            server.store = old

    def test_own_outbound_mail_never_mints_an_owner_identity(self):
        # the mailbox a reply left FROM is not proof of who sent it: a shared mailbox is everyone with access
        from taskuary.channels import ingest_outbound_mail
        s = MemoryStore()
        tid = s.create_task({'Title': 'Refund'}, 'test')
        s.add_message({'TaskId': tid, 'ExternalId': 'a', 'Channel': 'email', 'ConversationId': 'c1',
                       'FromEmail': 'res@x.example', 'Status': 'routed'})
        ingest_outbound_mail(s, 'shared@corp.example', {'id': 'o1', 'subject': 'RE: Refund', 'conversationId': 'c1',
                                                         'body': {'content': 'done'}})
        owner = next(p for p in s.list_people() if p['IsOwner'])
        self.assertEqual(owner['Identities'], [])
        self.assertNotIn('shared@corp.example', s.get_doc('soul'))

    def test_polled_mailbox_is_still_me_on_a_thread(self):
        # the person link ADDS to owner_addresses, it does not replace it (the shared-mailbox case)
        from taskuary.ingest import others_on_thread
        s = MemoryStore()
        res = s.ensure_identity('email', 'res@x.example', 'Res')
        shared = s.ensure_identity('email', 'shared@corp.example', 'Property Mgmt')
        for i, ident in enumerate((res, shared)):
            s.add_message({'ExternalId': f'm{i}', 'Channel': 'email', 'ConversationId': 'c1', 'FromEmail': ident['Handle'],
                           'FromName': ident['DisplayName'], 'IdentityId': ident['IdentityId'], 'SentAt': f'2026-08-0{i+1} 09:00:00', 'Status': 'filed'})
        msg = {'from_email': 'res@x.example', 'conversation_id': 'c1', 'person_id': res['CanonicalPersonId']}
        self.assertEqual(others_on_thread(s, msg, {'shared@corp.example'}), {})

    def test_adding_a_handle_to_a_member_cannot_write_a_cycle(self):
        s = MemoryStore()
        a = s.ensure_identity('email', 'jane@x.example', 'Jane')
        b = s.ensure_identity('slack', 'U1', 'jane')
        root = s.merge_people(a['CanonicalPersonId'], b['CanonicalPersonId'])
        s.ensure_identity('email', 'jane@x.example', person_id=b['PersonId'])       # a stale page names the member
        self.assertEqual(s.canonical_person_id(a['PersonId']), root)
        self.assertEqual(s.canonical_person_id(b['PersonId']), root)
        self.assertTrue(next(p for p in s.list_people() if p['PersonId'] == root)['Members'])

    def test_owner_verified_handle_stays_the_owners(self):
        s = MemoryStore()
        mine = s.register_owner_identity('email', 'uri@example.com', 'Uri', 7, verified=True)
        jane = s.ensure_identity('email', 'jane@x.example', 'Jane')
        s.ensure_identity('email', 'uri@example.com', person_id=jane['CanonicalPersonId'])
        owner = s.owner_person()['PersonId']
        self.assertEqual(s.identity(mine['IdentityId'])['CanonicalPersonId'], owner)
        self.assertEqual(s.canonical_person_id(jane['PersonId']), owner)

    def test_directory_cache_refreshes_after_every_kind_of_write(self):
        s = MemoryStore()
        a = s.ensure_identity('email', 'jane@x.example', 'Jane', connector_id=3)
        self.assertEqual(s.identity(a['IdentityId'])['PersonName'], 'Jane')
        s.update_person(a['PersonId'], name='Jane Doe')
        self.assertEqual(s.identity(a['IdentityId'])['PersonName'], 'Jane Doe')
        b = s.ensure_identity('slack', 'U1', 'jane')                       # new identity appears
        self.assertEqual(s.identity(b['IdentityId'])['Handle'], 'U1')
        root = s.merge_people(a['PersonId'], b['PersonId'])                # link is seen
        self.assertEqual(s.canonical_person_id(b['PersonId']), root)
        s.unmerge_person(b['PersonId'])                                    # and its undoing
        self.assertEqual(s.canonical_person_id(b['PersonId']), b['PersonId'])
        s.deactivate_connector_identities(3)                               # deactivation drops it from the page
        self.assertNotIn('jane@x.example', {i['Handle'] for p in s.list_people() for i in p['Identities']})


if __name__ == '__main__':
    unittest.main()
