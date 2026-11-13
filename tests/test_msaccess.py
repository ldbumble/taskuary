"""Every Microsoft card says which kind of permission it reads with - a person's sign-in or a company app - and what it needs against
what the token holds (msaccess.access). Offline: the token is minted here, never fetched."""
import base64, json, unittest
from unittest import mock

from taskuary import channels, msaccess
from taskuary.store import DEFAULT_ROLES, SQLiteStore


def jwt(claims):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return f"{b({'alg': 'none'})}.{b(claims)}.sig"


def card(store, kind, cfg, secret='s3cret-value'):
    cid = store.get_connector_by_type(kind)['ConnectorId']
    store.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': secret, 'Roles': DEFAULT_ROLES.get(kind, ''), 'ConfigJson': json.dumps(cfg)}, 'test')
    return store.get_connector(cid)


class AccessTests(unittest.TestCase):
    def setUp(self): msaccess._CACHE.clear(); self.store = SQLiteStore(':memory:')

    def ask(self, c, tok):
        with mock.patch.object(channels, 'graph_token', return_value=tok) as minted:
            return msaccess.access(self.store, c), minted

    def test_a_company_app_says_so_and_lists_each_permission_from_the_tokens_roles(self):
        c = card(self.store, 'teams', {'tenant_id': 'tid-1', 'client_id': 'cid-1'})
        tok = jwt({'app_displayname': 'Northwind Reader', 'roles': ['Chat.Read.All', 'ChatMessage.Read.All', 'Chat.ReadBasic.All']})
        a, _ = self.ask(c, tok)
        self.assertEqual(a['kind'], 'app')
        self.assertTrue(a['line'].startswith('Company app: Northwind Reader - reads across your organisation; your admin approves'), a['line'])
        got = {x['name']: x['granted'] for x in a['needs']}
        self.assertEqual(got, {'Chat.Read.All': True, 'ChatMessage.Read.All': True, 'User.ReadBasic.All': False})
        self.assertNotIn(tok, json.dumps(a)); self.assertNotIn('s3cret', json.dumps(a))      # never the token, never the secret

    def test_a_sign_in_says_whose_and_how_and_reads_the_scp_claim(self):
        c = card(self.store, 'outlook', {'auth': 'user', 'client_id': 'cid-1', 'account': 'alex@northwind.example',
                                         'signed_in_via': 'browser', 'signed_in_at': '2026-11-12T09:30:00'})
        a, _ = self.ask(c, jwt({'scp': 'User.Read Mail.ReadWrite Mail.Send People.Read'}))
        self.assertEqual(a['kind'], 'user')
        self.assertEqual(a['line'], 'Signed in as alex@northwind.example - sees what you can see (browser sign-in, 12 Nov 2026)')
        got = {x['name']: x['granted'] for x in a['needs']}
        self.assertTrue(got['Mail.ReadWrite'] and got['Mail.Send'])
        self.assertFalse(got['Calendars.ReadWrite'])
        self.assertTrue(next(x for x in a['needs'] if x['name'] == 'Contacts.Read')['optional'])

    def test_a_token_that_says_nothing_says_that_plainly(self):
        c = card(self.store, 'outlook', {'auth': 'user', 'client_id': 'cid-1', 'account': 'alex@northwind.example'})
        a, _ = self.ask(c, 'EwBwA8l6BAAU-opaque')                      # a personal account's token is not a JWT
        self.assertFalse(a['known'])
        self.assertIn('does not say what it was granted', a['note'])
        self.assertTrue(all(x['granted'] is None for x in a['needs']))

    def test_asked_once_then_cached_briefly(self):
        c = card(self.store, 'teams', {'tenant_id': 'tid-1', 'client_id': 'cid-1'})
        with mock.patch.object(channels, 'graph_token', return_value=jwt({'roles': ['Chat.Read.All']})) as minted:
            for _ in range(3): msaccess.access(self.store, c)
        self.assertEqual(minted.call_count, 1)

    def test_the_teams_behind_line_rides_on_the_card(self):
        c = card(self.store, 'teams', {'tenant_id': 'tid-1', 'client_id': 'cid-1'})
        self.store.touch_connector(c['ConnectorId'], 'Teams messages are behind: 2 chats newer than what came in')
        a, _ = self.ask(self.store.get_connector(c['ConnectorId']), jwt({'roles': ['Chat.Read.All']}))
        self.assertTrue(a['behind'].startswith('Teams messages are behind: 2 chats'))

    def test_a_card_with_nothing_to_read_with_says_nothing(self):
        c = card(self.store, 'teams', {}, secret='')
        a, minted = self.ask(c, 'x')
        self.assertEqual(a['kind'], ''); minted.assert_not_called()

    def test_what_covers_what(self):
        self.assertTrue(msaccess.covers('Mail.ReadWrite', 'Mail.Read'))
        self.assertTrue(msaccess.covers('Sites.ReadWrite.All', 'Sites.Read.All'))
        self.assertTrue(msaccess.covers('User.Read.All', 'User.ReadBasic.All'))
        self.assertFalse(msaccess.covers('Mail.Read', 'Mail.ReadWrite'))
        self.assertFalse(msaccess.covers('Chat.ReadBasic.All', 'Chat.Read.All'))
        self.assertFalse(msaccess.covers('Files.Read', 'Files.Read.All'))


if __name__ == '__main__': unittest.main()
