"""Two cards of one type, side by side: each its own credentials, each polled, each answering for its own mail.

The owner, 2026-10-20: "does every connector allow multiple of the same connector? Like Outlook - I only see a way to
connect one". The store and the pollers already kept instances apart; these pin the roads that still reached for the
first card of a type - setup's Connect, a second Microsoft sign-in, the history reader, attachments, and GitHub.
Nothing here reaches a real provider: Graph, Microsoft's sign-in and GitHub are fakes."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import channels, firstrun, histgen, msauth, outbound, server
from taskuary.store import DEFAULT_ROLES, SQLiteStore

A, B = 'alex@northwind.example', 'alex@contoso.example'


def outlook(store, name, account, rt):
    cid = store.save_connector({'Type': 'outlook', 'Name': name, 'Active': 1, 'Secret': rt, 'Roles': DEFAULT_ROLES['outlook'],
                                'ConfigJson': json.dumps({'auth': 'user', 'account': account})}, 'test')
    store.save_source({'Channel': 'email', 'Address': account, 'ConnectorId': cid, 'Active': 1}, 'test')
    return cid


def two_outlooks():
    store = SQLiteStore(':memory:')
    first = store.get_connector_by_type('outlook')['ConnectorId']
    store.save_connector({'ConnectorId': first, 'Active': 1, 'Secret': 'rt-northwind',
                          'ConfigJson': json.dumps({'auth': 'user', 'account': A})}, 'test')
    store.save_source({'Channel': 'email', 'Address': A, 'ConnectorId': first, 'Active': 1}, 'test')
    return store, first, outlook(store, 'Contoso mailbox', B, 'rt-contoso')


# a Graph token that says whose sign-in minted it: the refresh token is the card's own secret
fake_token = lambda cfg, secret=None: f'tok:{secret}'


class R:
    def __init__(self, code=202, body=None): self.status_code, self._b, self.text = code, body or {}, json.dumps(body or {})
    def json(self): return self._b


class TwoOutlookCards(unittest.TestCase):
    def test_each_card_is_polled_with_its_own_sign_in(self):
        store, first, second = two_outlooks()
        jobs = {c['ConnectorId'] for c, _ in channels._poll_jobs(store)}
        self.assertTrue({first, second} <= jobs, 'both Outlook cards are polled')
        read = []
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(channels, '_mail_folder', side_effect=lambda tok, s, folder, *a, **k: read.append((tok, s['Address'])) or 0):
            for cid in (first, second): channels._poll_one(store, store.get_connector(cid), True, 0, None, False)
        self.assertEqual({(t, a) for t, a in read}, {('tok:rt-northwind', A), ('tok:rt-contoso', B)})

    def test_a_reply_leaves_through_the_card_its_mail_came_in_on(self):
        store, _first, _second = two_outlooks()
        sent = []
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(outbound.requests, 'post', side_effect=lambda url, headers, **k: sent.append((url, headers['Authorization'])) or R()):
            outbound.reply_to_message(store, {'Channel': 'email', 'ExternalId': 'graph:M2', 'SourceName': B,
                                              'FromEmail': 'erin@vendor.example', 'Subject': 'Invoice'}, 'Thanks - paid today.')
        self.assertEqual(sent, [(f'{outbound.GRAPH}/users/{B}/messages/M2/reply', 'Bearer tok:rt-contoso')])

    def test_a_new_mail_with_no_mailbox_named_leaves_from_an_outlook_mailbox(self):
        store = SQLiteStore(':memory:')
        # an IMAP card's mailbox listed FIRST: Graph cannot send as it, so it is not the default sender
        imap = store.get_connector_by_type('imap')['ConnectorId']
        store.save_connector({'ConnectorId': imap, 'Active': 1, 'ConfigJson': json.dumps({'address': 'ops@vendor.example'})}, 'test')
        store.save_source({'Channel': 'email', 'Address': 'ops@vendor.example', 'ConnectorId': imap, 'Active': 1}, 'test')
        outlook(store, 'Contoso mailbox', B, 'rt-contoso')
        self.assertEqual([s['Address'] for s in store.list_sources() if s['Channel'] == 'email'][0], 'ops@vendor.example')
        self.assertEqual(outbound._mailbox(store), B)

    def test_history_reads_every_outlook_card_with_its_own_token(self):
        store, _first, _second = two_outlooks()
        seen = []
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(histgen, '_page', side_effect=lambda tok, url, params, cap: seen.append((tok, url.split('/users/')[1].split('/')[0])) or []), \
             mock.patch.object(histgen, '_status'):
            _sent, _inbox, n = histgen._graph_mail(store, 30)
        self.assertEqual(n, 2)
        self.assertEqual(set(seen), {('tok:rt-northwind', A), ('tok:rt-contoso', B)})


class SecondMicrosoftSignIn(unittest.TestCase):
    """The live server's endpoints, on the suite's scratch database (conftest)."""
    c = TestClient(server.app)

    def _card(self, name):
        return self.c.post('/api/connectors', json={'Type': 'outlook', 'Name': name}).json()['connectorId']

    def _sign_in(self, cid, account, rt):
        start = {'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin', 'expires_in': 900, 'interval': 5}
        with mock.patch.object(msauth, 'device_start', return_value=start):
            flow = self.c.post(f'/api/connectors/{cid}/ms/signin').json()['flow']
        with mock.patch.object(msauth, 'device_poll', return_value={'access_token': 'A', 'refresh_token': rt, 'expires_in': 3600}), \
             mock.patch.object(msauth, 'me', return_value={'account': account, 'name': 'Alex Doyle'}), \
             mock.patch.object(server, '_poll_reports'):
            return self.c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()

    def test_a_second_account_signs_in_on_its_own_card(self):
        one, two = self._card('Northwind mail (multi)'), self._card('Contoso mail (multi)')
        self.assertEqual(self._sign_in(one, 'multi-one@northwind.example', 'rt-1')['status'], 'ok')
        self.assertEqual(self._sign_in(two, 'multi-two@contoso.example', 'rt-2')['status'], 'ok')
        st = server.store
        self.assertEqual((st.get_connector(one, with_secret=True)['Secret'], st.get_connector(two, with_secret=True)['Secret']), ('rt-1', 'rt-2'))
        owner = {s['Address']: s['ConnectorId'] for s in st.list_sources() if s['Channel'] == 'email'}
        self.assertEqual((owner['multi-one@northwind.example'], owner['multi-two@contoso.example']), (one, two))

    def test_the_same_account_twice_is_refused_on_the_second_card(self):
        one, two = self._card('Same account A'), self._card('Same account B')
        self.assertEqual(self._sign_in(one, 'same@northwind.example', 'rt-a')['status'], 'ok')
        r = self._sign_in(two, 'same@northwind.example', 'rt-b')
        self.assertEqual(r['status'], 'error'); self.assertIn('Same account A', r['detail'])
        self.assertFalse(server.store.get_connector(two, with_secret=True).get('Secret'), 'the second card keeps no token')

    def test_attachments_are_fetched_through_the_card_that_owns_the_mailbox(self):
        one, two = self._card('Attach A'), self._card('Attach B')
        self._sign_in(one, 'attach-one@northwind.example', 'rt-att-1'); self._sign_in(two, 'attach-two@contoso.example', 'rt-att-2')
        from taskuary.ingest import ingest_message
        mid = ingest_message(server.store, file_only=True, msg={'external_id': 'graph:ATT2', 'channel': 'email', 'subject': 'Files',
                             'body': 'see attached', 'from_email': 'erin@vendor.example', 'source_name': 'attach-two@contoso.example'})['message_id']
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(channels, 'fetch_mail_attachments', return_value=0) as fetch:
            self.assertEqual(self.c.post(f'/api/messages/{mid}/attachments/fetch').status_code, 200)
        self.assertEqual(fetch.call_args.args[2], 'tok:rt-att-2')


class TwoMailboxesInSetup(unittest.TestCase):
    def test_connect_on_the_second_gmail_card_leaves_the_first_alone(self):
        store = SQLiteStore(':memory:')
        first = store.get_connector_by_type('gmail')['ConnectorId']
        store.save_connector({'ConnectorId': first, 'Active': 1, 'Secret': 'pw-one', 'ConfigJson': json.dumps({'address': A})}, 'test')
        second = store.save_connector({'Type': 'gmail', 'Name': 'Second Gmail'}, 'test')
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True}):
            out = firstrun.connect_mail(store, 'gmail', B, 'pw two', cid=second)
        self.assertTrue(out['ok'], out)
        one, two = store.get_connector(first, with_secret=True), store.get_connector(second, with_secret=True)
        self.assertEqual((json.loads(one['ConfigJson'])['address'], one['Secret']), (A, 'pw-one'))
        self.assertEqual((json.loads(two['ConfigJson'])['address'], two['Secret'], two['Active']), (B, 'pwtwo', 1))

    def test_a_card_of_another_type_is_not_written_through(self):
        store = SQLiteStore(':memory:')
        ol = store.get_connector_by_type('outlook')['ConnectorId']
        out = firstrun.connect_mail(store, 'imap', B, 'pw', cid=ol)
        self.assertFalse(out['ok'])
        self.assertFalse(store.get_connector(ol, with_secret=True).get('Secret'))


class TwoGithubAccounts(unittest.TestCase):
    def setUp(self):
        self.store = s = SQLiteStore(':memory:')
        self.one = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': self.one, 'Active': 1, 'Secret': 'pat-one', 'ConfigJson': json.dumps({'reply_comments': False})}, 'test')
        self.two = s.save_connector({'Type': 'github', 'Name': 'Org GitHub', 'Active': 1, 'Secret': 'pat-two',
                                     'ConfigJson': json.dumps({'reply_comments': True})}, 'test')
        s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'ConnectorId': self.one, 'Active': 1}, 'test')
        s.save_source({'Channel': 'github', 'Address': 'northwind/portal', 'ConnectorId': self.two, 'Active': 1}, 'test')

    def test_each_repo_resolves_to_the_card_that_reaches_it(self):
        s = self.store
        self.assertEqual(s.github_for('northwind/portal', with_secret=True)['Secret'], 'pat-two')
        self.assertEqual(s.github_for('Northwind/Ledger', with_secret=True)['Secret'], 'pat-one')
        self.assertEqual(s.github_for('org/app')['ConnectorId'], self.one, 'an unknown repo falls back to the default card')
        self.assertEqual((s.github_replies_ok('northwind/portal'), s.github_replies_ok('northwind/ledger')), (True, False))

    def test_a_comment_goes_out_with_the_token_and_switch_of_the_repos_card(self):
        msg = {'Channel': 'github', 'ConversationId': 'gh:northwind/portal#7', 'ExternalId': 'gh:northwind/portal#7'}
        with mock.patch('taskuary.github.comment_issue', return_value='https://github.example/c/1') as post:
            outbound.reply_to_message(self.store, msg, 'Fixed in the next release.')
        self.assertEqual(post.call_args.args[:3], ('pat-two', 'northwind/portal', 7))
        # ...and the first card's switch is off, so its repo is refused
        with self.assertRaises(outbound.Fixable):
            outbound.reply_to_message(self.store, {**msg, 'ConversationId': 'gh:northwind/ledger#3', 'ExternalId': 'gh:northwind/ledger#3'}, 'x')

    def test_ci_reads_a_pr_with_the_token_of_the_repos_card(self):
        from taskuary import ci
        self.assertEqual(ci._conn(self.store, 'northwind/portal')['Secret'], 'pat-two')
        self.assertEqual(ci._conn(self.store)['Secret'], 'pat-one')


def teams(store, name, account, rt, cid=None):
    """A Teams card signed in as its own Microsoft account (MsSignIn), its chats under that UPN."""
    row = {'Active': 1, 'Secret': rt, 'Roles': DEFAULT_ROLES['teams'], 'ConfigJson': json.dumps({'auth': 'user', 'account': account})}
    cid = store.save_connector({**row, 'ConnectorId': cid} if cid else {**row, 'Type': 'teams', 'Name': name}, 'test')
    store.save_source({'Channel': 'teams', 'Address': account, 'ConnectorId': cid, 'Active': 1}, 'test')
    return cid


def two_teams():
    store = SQLiteStore(':memory:')
    first = teams(store, None, A, 'rt-teams-northwind', cid=store.get_connector_by_type('teams')['ConnectorId'])
    return store, first, teams(store, 'Contoso Teams', B, 'rt-teams-contoso')


class TwoTeamsCards(unittest.TestCase):
    """Two Teams connections, each signed in like Outlook: each its own token, its own chats, its own replies. Graph is a fake."""
    def test_each_card_is_polled_with_its_own_sign_in_on_the_person_road(self):
        store, first, second = two_teams()
        self.assertTrue({first, second} <= {c['ConnectorId'] for c, _ in channels._poll_jobs(store)}, 'both Teams cards are polled')
        read = []
        def feed(tok, since_iso, cap=200):
            read.append(tok)
            return [{'id': f'm-{tok}', 'chatId': f'19:{tok}', 'messageType': 'message', 'createdDateTime': '2026-10-20T10:00:00Z',
                     'from': {'user': {'id': 'u-erin', 'displayName': 'Erin Blake'}}, 'body': {'content': '<p>can you send the deck?</p>'}}]
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(channels, '_teams_user_delta', side_effect=feed), \
             mock.patch.object(channels, '_teams_delta', side_effect=AssertionError('the app-only feed is not this road')), \
             mock.patch.object(channels, '_chat_meta', return_value=('', 'oneOnOne')), \
             mock.patch.object(channels, '_graph_user', return_value=('Erin Blake', 'erin@vendor.example')), \
             mock.patch.object(channels, 'hosted_images', return_value=[]), \
             mock.patch.object(channels.requests, 'get', return_value=R(200, {'id': 'u-me'})):
            for cid in (first, second): channels._poll_one(store, store.get_connector(cid), True, 0, None, False)
        self.assertEqual(sorted(read), ['tok:rt-teams-contoso', 'tok:rt-teams-northwind'])
        rows = {m['ConversationId']: m['SourceName'] for m in store.feed() if m['Channel'] == 'teams'}
        self.assertEqual(rows, {'teams:19:tok:rt-teams-northwind': A, 'teams:19:tok:rt-teams-contoso': B})

    def test_a_reply_leaves_through_the_card_that_owns_the_chat(self):
        store, _first, _second = two_teams()
        self.assertTrue(outbound.can_reply(store, 'teams'), 'a person signed in may answer in their chats')
        sent = []
        with mock.patch.object(channels, 'graph_token', side_effect=fake_token), \
             mock.patch.object(outbound.requests, 'post', side_effect=lambda url, headers, **k: sent.append((url, headers['Authorization'])) or R(201)):
            outbound.reply_to_message(store, {'Channel': 'teams', 'ConversationId': 'teams:19:abc@thread.v2', 'SourceName': B}, 'Sending it now.')
        self.assertEqual(sent, [(f'{outbound.GRAPH}/chats/19:abc@thread.v2/messages', 'Bearer tok:rt-teams-contoso')])

    def test_an_app_only_card_still_cannot_post(self):
        store = SQLiteStore(':memory:')
        tm = store.get_connector_by_type('teams')['ConnectorId']
        store.save_connector({'ConnectorId': tm, 'Active': 1, 'Secret': 'app-secret',
                              'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'})}, 'test')
        self.assertFalse(outbound.can_reply(store, 'teams'))
        self.assertIn('answer it in Teams', outbound.send_block(store, 'teams'))

    def test_no_sign_in_of_its_own_reads_through_the_same_accounts_outlook_card_never_the_first(self):
        store = SQLiteStore(':memory:')
        o_first = store.get_connector_by_type('outlook')['ConnectorId']
        store.save_connector({'ConnectorId': o_first, 'Active': 1, 'Secret': 'rt-ol-northwind',
                              'ConfigJson': json.dumps({'auth': 'user', 'account': A})}, 'test')
        o_two = outlook(store, 'Contoso mailbox', B, 'rt-ol-contoso')
        tm = store.get_connector_by_type('teams')['ConnectorId']
        store.save_connector({'ConnectorId': tm, 'Active': 1}, 'test')
        # naming no account, it borrows nothing: two Microsoft accounts, and the first is not a guess worth making
        self.assertFalse(channels.graph_creds(store, store.get_connector(tm, with_secret=True))[2])
        store.save_source({'Channel': 'teams', 'Address': B, 'ConnectorId': tm, 'Active': 1}, 'test')
        cfg, sec, borrowed = channels.graph_creds(store, store.get_connector(tm, with_secret=True))
        self.assertEqual((sec, borrowed, cfg['_cid']), ('rt-ol-contoso', True, o_two))
        self.assertEqual(cfg['_scope'], msauth.TEAMS_CHAT, 'the same sign-in, asked for chats')
        # ...and a tenant app on another domain is not borrowed either
        store2 = SQLiteStore(':memory:')
        o = store2.get_connector_by_type('outlook')['ConnectorId']
        store2.save_connector({'ConnectorId': o, 'Active': 1, 'Secret': 's', 'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'})}, 'test')
        store2.save_source({'Channel': 'email', 'Address': A, 'ConnectorId': o, 'Active': 1}, 'test')
        outlook(store2, 'Contoso mailbox', B, 'rt-ol-contoso')
        t2 = store2.get_connector_by_type('teams')['ConnectorId']
        store2.save_source({'Channel': 'teams', 'Address': 'paula@fabrikam.example', 'ConnectorId': t2, 'Active': 1}, 'test')
        self.assertFalse(channels.graph_creds(store2, store2.get_connector(t2, with_secret=True))[2])

    def test_one_sign_in_mints_a_mail_token_and_a_chat_token_apart(self):
        msauth._CACHE.clear()
        asked = []
        def post(url, data, timeout): asked.append(data['scope']); return R(200, {'access_token': f"A:{data['scope'][:30]}", 'expires_in': 3600})
        try:
            with mock.patch('requests.post', side_effect=post):
                mail = msauth.access_token({'auth': 'user', 'granted_scope': msauth.SCOPES}, 'RT')
                chat = msauth.access_token({'auth': 'user', '_scope': msauth.TEAMS_SCOPES}, 'RT')
            self.assertNotEqual(mail, chat); self.assertEqual(asked[1], msauth.TEAMS_SCOPES)
        finally: msauth._CACHE.clear()


class TeamsSignsInOnItsOwnCard(unittest.TestCase):
    """On the suite's shared scratch server: every card made here is signed out again, so no later test meets a Teams
    card that answers chats or a poller that reaches for Microsoft."""
    c = TestClient(server.app)

    def setUp(self): self.made = []
    def tearDown(self):
        for cid in self.made:
            self.c.post(f'/api/connectors/{cid}/ms/signout')
            for s in server.store.list_sources(active_only=False):
                if s.get('ConnectorId') == cid: server.store.save_source({**s, 'Active': 0}, 'test')

    def _card(self, name, kind='teams'):
        cid = self.c.post('/api/connectors', json={'Type': kind, 'Name': name}).json()['connectorId']
        self.made.append(cid); return cid

    def _sign_in(self, cid, account, rt):
        start = {'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin', 'expires_in': 900, 'interval': 5}
        with mock.patch.object(msauth, 'device_start', return_value=start) as ds:
            flow = self.c.post(f'/api/connectors/{cid}/ms/signin').json()['flow']
        self.assertEqual(ds.call_args.args[1], msauth.TEAMS_SCOPES, 'a Teams card asks for chats, not mail')
        with mock.patch.object(msauth, 'device_poll', return_value={'access_token': 'A', 'refresh_token': rt, 'expires_in': 3600}), \
             mock.patch.object(msauth, 'me', return_value={'account': account, 'name': 'Alex Doyle'}), \
             mock.patch.object(server, '_poll_reports'):
            return self.c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()

    def test_two_tenants_two_cards_each_its_own_chats(self):
        one, two = self._card('Northwind Teams (multi)'), self._card('Contoso Teams (multi)')
        self.assertEqual(self._sign_in(one, 'teams-one@northwind.example', 'rt-t1')['status'], 'ok')
        self.assertEqual(self._sign_in(two, 'teams-two@contoso.example', 'rt-t2')['status'], 'ok')
        st = server.store
        owner = {s['Address']: s['ConnectorId'] for s in st.list_sources() if s['Channel'] == 'teams'}
        self.assertEqual((owner['teams-one@northwind.example'], owner['teams-two@contoso.example']), (one, two))
        self.assertEqual(json.loads(st.get_connector(two)['ConfigJson'])['auth'], 'user')

    def test_the_same_account_on_two_teams_cards_is_refused(self):
        one, two = self._card('Same Teams A'), self._card('Same Teams B')
        self.assertEqual(self._sign_in(one, 'same-teams@northwind.example', 'rt-ta')['status'], 'ok')
        r = self._sign_in(two, 'same-teams@northwind.example', 'rt-tb')
        self.assertEqual(r['status'], 'error'); self.assertIn('Same Teams A', r['detail'])
        self.assertFalse(server.store.get_connector(two, with_secret=True).get('Secret'))

    def test_the_same_account_as_an_outlook_card_is_not_refused(self):
        ol = self._card('Mail beside Teams', 'outlook')
        server.store.save_connector({'ConnectorId': ol, 'Active': 1, 'Secret': 'rt-o',
                                     'ConfigJson': json.dumps({'auth': 'user', 'account': 'both@northwind.example'})}, 'test')
        self.assertEqual(self._sign_in(self._card('Teams beside mail'), 'both@northwind.example', 'rt-tt')['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
