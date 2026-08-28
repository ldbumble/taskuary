"""Mail folders: a mailbox reads the folders its source names (Inbox alone by default); the
sign-in starts the first sync; a failing brain is said in the caption, not hidden in rows."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import channels, ingest, msauth, server
from taskuary.store import MemoryStore
from taskuary.ingest import ingest_message

c_api = TestClient(server.app)


class R:
    def __init__(self, code, body): self.status_code, self._b = code, body
    def json(self): return self._b
    def raise_for_status(self):
        if self.status_code >= 400: raise channels.requests.HTTPError(str(self.status_code))


class FolderTests(unittest.TestCase):
    def test_source_folders_defaults_to_the_inbox(self):
        self.assertEqual(channels.source_folders({'ConfigJson': None}), ['inbox'])
        self.assertEqual(channels.source_folders({'ConfigJson': '{"folders": []}'}), ['inbox'])
        self.assertEqual(channels.source_folders({'ConfigJson': '{"folders": ["inbox", "AAMk-vendors"]}'}), ['inbox', 'AAMk-vendors'])

    def test_the_folder_list_leads_with_the_inbox_and_hides_the_plumbing(self):
        body = {'value': [{'id': 'AAMk-sent', 'displayName': 'Sent Items', 'wellKnownName': 'sentitems', 'totalItemCount': 9},
                          {'id': 'AAMk-vend', 'displayName': 'Vendors', 'totalItemCount': 42},
                          {'id': 'AAMk-in', 'displayName': 'Inbox', 'wellKnownName': 'inbox', 'totalItemCount': 120},
                          {'id': 'AAMk-junk', 'displayName': 'Junk Email', 'wellKnownName': 'junkemail'}]}
        with mock.patch.object(channels.requests, 'get', return_value=R(200, body)):
            fs = channels.mail_folders('T', 'me@x.com')
        self.assertEqual([f['id'] for f in fs], ['inbox', 'AAMk-vend'])             # inbox by its well-known name, plumbing dropped
        self.assertEqual(fs[1], {'id': 'AAMk-vend', 'name': 'Vendors', 'count': 42, 'well_known': ''})

    def test_the_poll_reads_every_chosen_folder(self):
        s = MemoryStore()
        o = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'Secret': 'S', 'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'})}, 't')
        s.save_source({'Channel': 'email', 'Address': 'me@x.com', 'ConnectorId': o['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'folders': ['inbox', 'AAMk-vend']})}, 't')
        seen = []
        def msgs(tok, upn, since, folder='inbox'):
            seen.append(folder)
            return [] if folder == 'sentitems' else [{'id': f'{folder}-1', 'subject': f'from {folder}', 'receivedDateTime': '2026-08-28T10:00:00Z',
                                                      'from': {'emailAddress': {'name': 'V', 'address': 'v@vendor.example'}}, 'body': {'content': 'hi'}, 'isRead': True}]
        with mock.patch.object(channels, 'graph_token', return_value='T'), mock.patch.object(channels, '_mail_msgs', side_effect=msgs), \
             mock.patch.object(channels, '_body', return_value='hi'), mock.patch.object(channels, '_addrs', return_value=[]):
            n = channels.poll_channels(s)
        self.assertEqual(sorted(set(seen)), ['AAMk-vend', 'inbox', 'sentitems'])
        self.assertEqual(n, 2)

    def test_the_endpoint_is_an_outlook_card_thing(self):
        slack = next(x for x in server.store.list_connectors() if x['Type'] == 'slack')
        self.assertEqual(c_api.get(f"/api/connectors/{slack['ConnectorId']}/mail/folders", params={'mailbox': 'x'}).status_code, 404)


class SignInSyncTests(unittest.TestCase):
    def test_a_finished_sign_in_starts_the_first_sync(self):
        cid = next(x for x in server.store.list_connectors() if x['Type'] == 'outlook')['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}):
            flow = c_api.post(f'/api/connectors/{cid}/ms/signin').json()['flow']
        with mock.patch.object(msauth, 'device_poll', return_value={'access_token': 'A', 'refresh_token': 'RT', 'expires_in': 3600}), \
             mock.patch.object(msauth, 'me', return_value={'account': 'new@x.com', 'name': 'New'}), \
             mock.patch.object(server.threading, 'Thread') as th:
            r = c_api.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()
        self.assertEqual((r['status'], r['syncing']), ('ok', True))
        self.assertEqual(th.call_args[1]['target'], server._poll_reports); th.return_value.start.assert_called_once()


class BrainFailureTests(unittest.TestCase):
    def test_a_failing_brain_is_recorded_and_cleared_when_it_answers(self):
        s = MemoryStore()
        s.save_connector({'ConnectorId': s.get_connector_by_type('anthropic')['ConnectorId'], 'Active': 1, 'Secret': 'k'}, 't')
        boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("codex exit 2: unexpected argument '--skip-git-repo-check'"))
        out = ingest_message(s, {'external_id': 'b1', 'channel': 'email', 'subject': 's', 'body': 'the importer fails', 'from_email': 'a@b.com'}, llm=boom)
        self.assertEqual(out['status'], 'filed')
        self.assertIn('skip-git-repo-check', s.get_settings()['triage_last_error'])
        with mock.patch.object(server, 'store', s):
            self.assertIn('skip-git-repo-check', c_api.get('/api/ingest/status').json()['triageError'])
        # a body the keyword rules cannot settle, so the brain is actually asked - and answers
        ok = lambda *a, **k: '{"intent": "fyi", "why": "n"}'
        ingest_message(s, {'external_id': 'b2', 'channel': 'email', 'subject': 'Q3 numbers', 'body': 'could you glance at the payroll figures when you have a moment', 'from_email': 'a@b.com'}, llm=ok)
        self.assertEqual(s.get_settings()['triage_last_error'], '')
