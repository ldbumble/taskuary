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


if __name__ == '__main__':
    unittest.main()
