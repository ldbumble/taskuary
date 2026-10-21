"""A Remove acts at once, and is taken back (recentlydeleted.py; the owner, 2026-10-21: no "are you sure").

Remove report, Remove workflow, a routing rule's bin, Remove profile, Remove connection, a mailbox's bin and Sign out each asked
first and could not be undone. Each now runs on the press, keeps what it took, and Undo / Restore puts it back as it was. Reports,
workflows, rules and profiles stay under Recently deleted for 30 days; a connection's sign-in only for the Undo line's minutes."""
import json, time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, recentlydeleted as rd, server, vault
from taskuary.store import MemoryStore

DAY = 86400


class RecentlyDeletedTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.cfg = {**server.cfg, 'agents': {}, 'cli_connections': {}}
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'cfg', self.cfg),
                  mock.patch.object(config, 'save', lambda cfg: None)):
            p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def report(self, title='AP ageing', **cfg):
        return self.s.save_source({'Channel': 'report', 'Address': title, 'Active': 1,
                                   'ConfigJson': json.dumps({'type': 'sql', 'title': title, 'daily_at': '07:00', **cfg})}, 'test')

    def test_a_report_is_removed_at_once_and_restored_exactly_under_its_old_id(self):
        sid = self.report()
        before = self.s.get_source(sid)
        out = self.c.delete(f'/api/sources/{sid}').json()
        self.assertEqual((out['ok'], out['title'], out['kind']), (True, 'AP ageing', 'report'))
        self.assertIsNone(self.s.get_source(sid))                                      # gone from every reader at once
        listed = self.c.get('/api/deleted').json()['data']
        self.assertEqual([(d['id'], d['kind'], d['title'], d['days_left']) for d in listed], [(out['deleted'], 'report', 'AP ageing', 29)])
        self.assertEqual(self.c.post(f"/api/deleted/{out['deleted']}/restore").status_code, 200)
        self.assertEqual(self.s.get_source(sid), before)                               # its id, its config, its switch
        self.assertEqual(self.c.get('/api/deleted').json()['data'], [])
        self.assertEqual(self.c.post(f"/api/deleted/{out['deleted']}/restore").status_code, 404)   # restored once is restored

    def test_the_list_names_a_report_and_a_workflow_apart_and_a_mailbox_is_an_undo_line_alone(self):
        wf = self.s.save_source({'Channel': 'report', 'Address': 'Vendor setup', 'Active': 1,
                                 'ConfigJson': json.dumps({'type': 'agent', 'access': 'write', 'title': 'Vendor setup'})}, 'test')
        box = self.s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'Active': 1}, 'test')
        self.assertEqual(self.c.delete(f'/api/sources/{wf}').json()['kind'], 'workflow')
        undo = self.c.delete(f'/api/sources/{box}').json()
        self.assertEqual([d['kind'] for d in self.c.get('/api/deleted').json()['data']], ['workflow'])
        self.assertEqual([d['kind'] for d in self.c.get('/api/deleted', params={'kinds': 'workflow,source'}).json()['data']], ['source', 'workflow'])
        self.c.post(f"/api/deleted/{undo['deleted']}/restore")
        self.assertEqual(self.s.get_source(box)['Address'], 'alex@northwind.example')

    def test_restore_takes_a_new_id_when_its_old_one_was_given_to_another(self):
        sid = self.report()
        did = self.c.delete(f'/api/sources/{sid}').json()['deleted']
        other = self.report('Cash position')                                           # sqlite hands the freed id back out
        self.c.post(f'/api/deleted/{did}/restore')
        titles = sorted(json.loads(r['ConfigJson'])['title'] for r in self.s.list_sources(active_only=False))
        self.assertEqual([t for t in titles if t in ('AP ageing', 'Cash position')], ['AP ageing', 'Cash position'])
        self.assertEqual(json.loads(self.s.get_source(other)['ConfigJson'])['title'], 'Cash position')

    def test_thirty_days_on_it_goes_for_good(self):
        sid = self.report()
        did = self.c.delete(f'/api/sources/{sid}').json()['deleted']
        self.assertEqual(rd.purge(self.s, time.time() + 29 * DAY), [])
        self.assertEqual(rd.purge(self.s, time.time() + 31 * DAY), [did])
        self.assertEqual(self.c.post(f'/api/deleted/{did}/restore').status_code, 404)

    def test_a_rule_is_removed_and_restored(self):
        pid = self.s.save_policy({'Name': 'Mute the newsletter', 'Kind': 'sender', 'Pattern': 'news@vendor.example', 'Action': 'ignore',
                                  'Active': 1}, 'test')
        out = self.c.delete(f'/api/policies/{pid}').json()
        self.assertEqual((out['kind'], out['title']), ('rule', 'Mute the newsletter'))
        self.assertEqual(self.s.list_policies(active_only=False), [])
        self.c.post(f"/api/deleted/{out['deleted']}/restore")
        self.assertEqual([(p['PolicyId'], p['Name']) for p in self.s.list_policies()], [(pid, 'Mute the newsletter')])

    def test_a_profile_comes_back_whole_and_never_over_a_new_one_of_its_name(self):
        self.cfg['agents']['researcher'] = {'kind': 'general', 'purpose': 'looks things up'}
        self.s.upsert_agent('researcher', 'general', 'cli', '{"kind": "general"}')
        out = self.c.delete('/api/agents/researcher').json()
        self.assertNotIn('researcher', self.cfg['agents']); self.assertIsNone(self.s.get_agent('researcher'))
        self.assertEqual(self.c.get('/api/deleted').json()['data'][0]['kind'], 'profile')
        self.cfg['agents']['researcher'] = {'kind': 'general', 'purpose': 'a new one'}
        self.assertEqual(self.c.post(f"/api/deleted/{out['deleted']}/restore").status_code, 409)
        del self.cfg['agents']['researcher']
        self.assertEqual(self.c.post(f"/api/deleted/{out['deleted']}/restore").status_code, 200)
        self.assertEqual(self.cfg['agents']['researcher']['purpose'], 'looks things up')
        self.assertEqual(self.s.get_agent('researcher')['Kind'], 'general')

    def _mail_card(self):
        cid = self.s.save_connector({'Type': 'imap', 'Name': 'Northwind mail', 'ConfigJson': json.dumps({'host': 'mail.northwind.example'}),
                                     'Secret': 'app-password', 'Active': 1}, 'test')
        box = self.s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Active': 1}, 'test')
        return cid, box

    def test_remove_connection_wipes_at_once_and_undo_puts_its_sign_in_and_mailboxes_back(self):
        cid, box = self._mail_card()
        sealed = self.s._one('SELECT Secret FROM connector WHERE ConnectorId=?', (cid,))['Secret']
        with mock.patch.object(vault, 'forget') as forget:
            out = self.c.post(f'/api/connectors/{cid}/reset').json()
            c = self.s.get_connector(cid)
            self.assertEqual((c['HasSecret'], c['Active'], c['ConfigJson'], self.s.get_source(box)['Active']), (0, 0, None, 0))
            self.assertEqual(self.c.get('/api/deleted').json()['data'], [])          # an Undo line's, never Recently deleted's
            self.c.post(f"/api/deleted/{out['deleted']}/restore")
            forget.assert_not_called()
        self.assertEqual(self.s._one('SELECT Secret FROM connector WHERE ConnectorId=?', (cid,))['Secret'], sealed)
        self.assertEqual((self.s.get_connector(cid)['Active'], self.s.get_source(box)['Active']), (1, 1))
        self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson'])['host'], 'mail.northwind.example')

    def test_a_removed_connections_sign_in_is_forgotten_once_its_undo_has_passed(self):
        cid, _ = self._mail_card()
        sealed = self.s._one('SELECT Secret FROM connector WHERE ConnectorId=?', (cid,))['Secret']
        self.c.post(f'/api/connectors/{cid}/reset')
        with mock.patch.object(vault, 'forget') as forget:
            rd.purge(self.s, time.time() + rd.UNDO_SECONDS - 5); forget.assert_not_called()
            rd.purge(self.s, time.time() + rd.UNDO_SECONDS + 5); forget.assert_called_once_with(sealed)

    def test_chatgpt_sign_out_is_at_once_and_the_session_is_ended_at_openai_only_after_undo_passed(self):
        cid = self.s.save_connector({'Type': 'chatgpt', 'Name': 'ChatGPT', 'Active': 1, 'Secret': 'refresh-1',
                                     'ConfigJson': json.dumps({'host_id': 'h1', 'account': 'alex@northwind.example', 'client_id': 'app'})}, 'test')
        from taskuary import chatgptauth
        with mock.patch.object(chatgptauth, 'revoke') as revoke:
            out = self.c.post(f'/api/connectors/{cid}/chatgpt/signout').json()
            self.assertEqual((out['kind'], self.s.get_connector(cid)['HasSecret'], self.s.get_connector(cid)['Active']), ('signout', 0, 0))
            self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson']), {'host_id': 'h1'})
            revoke.assert_not_called()                                                 # a revoked session could never be undone
            self.c.post(f"/api/deleted/{out['deleted']}/restore")
            self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson'])['account'], 'alex@northwind.example')
            self.assertEqual(self.s.get_connector(cid, with_secret=True)['Secret'], 'refresh-1')
            out = self.c.post(f'/api/connectors/{cid}/chatgpt/signout').json()
            rd.purge(self.s, time.time() + rd.UNDO_SECONDS + 5)
            revoke.assert_called_once()
            self.assertEqual(revoke.call_args[0], ({'host_id': 'h1', 'account': 'alex@northwind.example', 'client_id': 'app'}, 'refresh-1'))

    def test_microsoft_sign_out_is_undone_with_its_account(self):
        cid = self.s.save_connector({'Type': 'outlook', 'Name': 'Outlook mail', 'Active': 1, 'Secret': 'rt-1',
                                     'ConfigJson': json.dumps({'auth': 'user', 'account': 'alex@northwind.example', 'tenant_id': 't'})}, 'test')
        out = self.c.post(f'/api/connectors/{cid}/ms/signout').json()
        self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson']), {'tenant_id': 't'})
        self.c.post(f"/api/deleted/{out['deleted']}/restore")
        self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson'])['account'], 'alex@northwind.example')
        self.assertEqual((self.s.get_connector(cid)['Active'], self.s.get_connector(cid)['HasSecret']), (1, 1))

    def test_a_cli_disconnected_comes_back_with_the_profiles_that_ran_on_it(self):
        self.cfg['cli_connections']['claude'] = {'cmd': 'claude', 'args': ['-p']}
        self.cfg['agents']['coding'] = {'kind': 'coding', 'provider': 'cli:claude', 'cmd': 'claude'}
        from taskuary import cli_connections, pathcache
        with mock.patch.object(cli_connections, 'sync'), mock.patch.object(pathcache, 'forget'):
            out = self.c.delete('/api/cli/connections/claude', params={'detach': 1}).json()
            self.assertNotIn('claude', self.cfg['cli_connections']); self.assertNotIn('provider', self.cfg['agents']['coding'])
            self.c.post(f"/api/deleted/{out['deleted']}/restore")
        self.assertEqual(self.cfg['cli_connections']['claude'], {'cmd': 'claude', 'args': ['-p']})
        self.assertEqual(self.cfg['agents']['coding']['provider'], 'cli:claude')


if __name__ == '__main__':
    unittest.main()
