"""A VENDOR'S REST API, READ WITH A KEY (apireads.py, the owner 2026-11-08): every row of apireads.json is a working card whose Test makes
its one cheap GET - each fed the answer its vendor's docs show - and nothing but a GET under its own base is ever sent. Nothing is reached."""
import json, re, unittest
from unittest import mock

from taskuary import apireads, channels, connectorcatalog, reports, scopes
from taskuary.store import MemoryStore

# the probe's answer, shaped as each vendor documents it (not live captures)
DOC = {'digitalocean': {'account': {'email': 'alex@northwind.example', 'status': 'active'}},
       'terraform_cloud': {'data': {'id': 'user-1', 'type': 'users', 'attributes': {'username': 'alex'}}},
       'better_stack': {'data': [{'id': '1', 'type': 'monitor', 'attributes': {'url': 'https://northwind.example'}}], 'pagination': {'next': None}},
       'circleci': {'id': 'u1', 'login': 'alex', 'name': 'Alex Doyle'},
       'buildkite': {'uuid': 't1', 'scopes': ['read_builds'], 'user': {'name': 'Alex Doyle', 'email': 'alex@northwind.example'}},
       'coda': {'name': 'Alex Doyle', 'loginId': 'alex@northwind.example', 'type': 'user'},
       'intrinio': {'id': 'com_1', 'ticker': 'AAPL', 'name': 'Apple Inc', 'cik': '0000320193'},
       'benzinga': [{'id': 1, 'title': 'A headline', 'created': 'Mon, 09 Nov 2026 10:00:00 -0400', 'stocks': [{'name': 'AAPL'}]}],
       'tradier': {'profile': {'id': 'id-1', 'name': 'Alex Doyle', 'account': {'account_number': 'VA000001'}}},
       'diffbot': {'name': 'Alex Doyle', 'plan': 'free', 'planCredits': 10000, 'status': 'active', 'usage': []},
       'jenkins': {'_class': 'hudson.model.Hudson', 'jobs': [{'name': 'ledger-build', 'color': 'blue'}]},
       'sonarqube': {'valid': True},
       'elastic': {'name': 'node-1', 'cluster_name': 'northwind', 'version': {'number': '9.1.0'}, 'tagline': 'You Know, for Search'},
       'splunk': {'links': {}, 'origin': 'https://splunk.example.com:8089/services/server/info', 'entry': [{'name': 'server-info'}], 'paging': {}},
       'dynatrace': {'totalCount': 1, 'pageSize': 1, 'types': [{'type': 'HOST', 'displayName': 'Host'}]},
       'kubernetes': {'major': '1', 'minor': '34', 'gitVersion': 'v1.34.0'},
       'mercury': {'accounts': [{'id': 'acc-1', 'name': 'Northwind Checking', 'availableBalance': 1200.5, 'kind': 'checking'}]},
       'lattice': {'id': 'u-1', 'name': 'Alex Doyle', 'email': 'alex@northwind.example', 'object': 'user'},
       'google_drive': {'user': {'displayName': 'Alex Doyle', 'emailAddress': 'alex@northwind.example'}},
       'onedrive': {'id': 'd1', 'driveType': 'business', 'owner': {'user': {'displayName': 'Alex Doyle'}}},
       'office365_files': {'value': [{'id': 'f1', 'name': 'Q3 plan.xlsx'}]},
       # the cards that sign in by OAuth (oauth.py) and the ones that bring work in (inboxes.py, tested there): their probe's answer
       'box': {'type': 'user', 'id': '11', 'name': 'Alex Doyle', 'login': 'alex@northwind.example'},
       'zoom': {'id': 'z1', 'email': 'alex@northwind.example', 'account_id': 'a1'},
       'zoom_chat': {'id': 'z1', 'email': 'alex@northwind.example', 'account_id': 'a1'},
       'webex': {'id': 'p1', 'orgId': 'o1', 'displayName': 'Alex Doyle'}, 'threads': {'id': 't1', 'username': 'alexdoyle'},
       'hubspot': {'results': [{'id': '77', 'email': 'alex@northwind.example'}]}, 'salesforce': {'user_id': '005000000000001AAA'},
       'docusign': {'folders': [{'folderId': 'f1', 'name': 'Inbox'}]}, 'basecamp_todos': {'id': 10, 'name': 'Alex Doyle'},
       'mailgun': {'items': [{'name': 'mg.northwind.example'}]}, 'sendgrid': {'scopes': ['mail.send']},
       'line': {'userId': 'U1', 'basicId': '@northwind', 'displayName': 'Northwind'}, 'substack': [],
       'pipedrive': {'success': True, 'data': {'id': 1, 'name': 'Alex Doyle', 'email': 'alex@northwind.example', 'company_name': 'Northwind'}},
       'copper': {'id': 1, 'name': 'Northwind'},
       'toggl': {'id': 1, 'email': 'alex@northwind.example', 'fullname': 'Alex Doyle', 'default_workspace_id': 7},
       'harvest': {'id': 1, 'first_name': 'Alex', 'last_name': 'Doyle', 'email': 'alex@northwind.example', 'is_active': True},
       'clockify': {'id': 'u1', 'email': 'alex@northwind.example', 'name': 'Alex Doyle', 'activeWorkspace': 'w1'}}
# a vendor that swaps the card's credentials for a bearer first answers its sign-in like this (each vendor's documented shape)
TOKENS = {'ups': {'token_type': 'Bearer', 'access_token': 'ups-tok', 'expires_in': '14399', 'status': 'approved'},
          'fedex': {'access_token': 'fx-tok', 'token_type': 'bearer', 'expires_in': 3599, 'scope': 'CXS'},
          'usps': {'access_token': 'usps-tok', 'token_type': 'Bearer', 'expires_in': 28799}}
KEYS = {}                                          # a key with a shape of its own; every other card's key is key-1


def resp(j, code=200):
    r = mock.Mock(); r.status_code, r.text = code, json.dumps(j); r.json.return_value = j
    return r


def card(s, t, key='key-1', **cfg):
    c = s.get_connector_by_type(t)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(cfg), **({'Secret': key} if key else {})}, 't')
    return c['ConnectorId']


class EveryRowIsAWorkingCard(unittest.TestCase):
    def test_the_table_and_the_catalogue_agree(self):
        from tests.test_apireads_signed import DOC as SIGNED       # the rows whose key is swapped, signed or rides in a body
        self.assertEqual(set(DOC) | set(SIGNED), {t for t, r in apireads.table().items() if r['probe']})
        for t, r in apireads.table().items():
            c = connectorcatalog.by_type(t)
            self.assertTrue(c and c['planned'] is False, t)
            self.assertTrue(r['docs'].startswith('https://') and (r['probe'] or r['example']).startswith('/'), t)
            self.assertTrue(r['probe'] or r.get('token'), t)                 # no cheap read: its Test is the sign-in
            self.assertTrue(r.get('base', 'https://').startswith('https://'), t)
            self.assertEqual((reports.card_of(f'{t}_read'), scopes.needs(f'{t}_read')), (t, 'read'), t)
            self.assertEqual(set(TOKENS) & {t}, {t} if r.get('token') else set(), t)

    def test_each_cards_test_makes_its_probe_with_the_key_where_the_vendor_wants_it(self):
        from taskuary import net
        s = MemoryStore()
        from taskuary import inboxes
        from tests.test_apireads_signed import DOC as SIGNED
        for t, r in apireads.table().items():
            if t in inboxes.TYPES or t in SIGNED: continue  # a card that brings work in tests through its source; a signed one in test_apireads_signed
            cfg = {'host': 'https://ci.northwind.example', 'user': 'alex', **{n: 'f1' for _, n in r.get('fields') or []}}
            cid, key = card(s, t, KEYS.get(t, 'key-1'), **cfg), KEYS.get(t, 'key-1')
            net._TOKENS.clear()
            with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC.get(t))) as g, \
                    mock.patch.object(apireads.requests, 'post', return_value=resp(TOKENS.get(t))) as p, \
                    mock.patch('taskuary.oauth.access', return_value='oa-tok'), \
                    mock.patch('taskuary.sheets._token', return_value='g-tok'), mock.patch('taskuary.sheets.google_sheets_connection', return_value={}), \
                    mock.patch('taskuary.outbound._graph_token', return_value='ms-tok'):
                out = channels.test_connector(s, cid)
            self.assertTrue(out['ok'], (t, out))
            if r.get('token'):
                self.assertEqual(p.call_count, 1, t); self.assertFalse(p.call_args.kwargs['allow_redirects'], t)
                if r['token']['url'].startswith('https://'): self.assertEqual(p.call_args.args[0], r['token']['url'], t)
            else: self.assertFalse(p.called, t)
            if not r['probe']: self.assertFalse(g.called, t); continue
            tok = apireads._dig(TOKENS[t], r['token'].get('take') or 'access_token') if r.get('token') else key
            vars_ = {k: apireads._dig(TOKENS[t], v) for k, v in (r.get('token') or {}).get('vars', {}).items()}
            url, kw = g.call_args.args[0], g.call_args.kwargs
            self.assertEqual(url, apireads.base_of(t, cfg, key) + r['probe'].format(**{**(r.get('defaults') or {}), **cfg, **vars_}), t)
            self.assertFalse(kw['allow_redirects'])
            h, q = kw['headers'], kw['params']
            want = {'query': lambda: q[r['param']] == tok, 'basic': lambda: h['Authorization'].startswith('Basic '),
                    'google': lambda: h['Authorization'] == 'Bearer g-tok', 'graph': lambda: h['Authorization'] == 'Bearer ms-tok',
                    'powerbi': lambda: h['Authorization'] == 'Bearer ms-tok', 'oauth': lambda: h['Authorization'] == 'Bearer oa-tok', 'ghost': lambda: h['Authorization'].startswith('Ghost ')}.get(r['auth'])
            self.assertTrue(want() if want else h[r.get('header') or 'Authorization'] == (r.get('format') or 'Bearer {key}').format(key=tok), (t, h, q))

    def test_the_documented_shapes_the_owner_relies_on(self):
        with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC['circleci'])) as g:
            apireads.runner('circleci')({'api_key': 'cc'})
        self.assertEqual(g.call_args.kwargs['headers']['Circle-Token'], 'cc')
        with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC['elastic'])) as g:
            apireads.runner('elastic')({'api_key': 'ZW5j', 'host': 'es.northwind.example:9243'})
        self.assertEqual((g.call_args.args[0], g.call_args.kwargs['headers']['Authorization']), ('https://es.northwind.example:9243/', 'ApiKey ZW5j'))
        with mock.patch.object(apireads.requests, 'get', return_value=resp([{'title': 'x'}])):
            self.assertEqual(apireads.runner('benzinga')({'api_key': 'b', 'path': '/news?tickers=AAPL'})[0], 'Benzinga: 1 items')
        # Substack has no API: its public feed, read as posts rather than markup
        rss = mock.Mock(status_code=200, text='<?xml version="1.0"?><rss><channel><title>Notes</title><item><title><![CDATA[On ledgers]]></title>'
                                              '<link>https://northwind.substack.com/p/on-ledgers</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>')
        rss.json.side_effect = ValueError
        with mock.patch.object(apireads.requests, 'get', return_value=rss) as g:
            head, body = apireads.runner('substack')({'host': 'northwind.substack.com'})
        self.assertEqual((g.call_args.args[0], head), ('https://northwind.substack.com/feed', 'Substack: 1 items'))
        self.assertEqual(json.loads(body)[0]['link'], 'https://northwind.substack.com/p/on-ledgers')


class OnlyReads(unittest.TestCase):
    def test_the_path_cannot_leave_the_base(self):
        for bad in ('https://evil.example/x', '//evil.example', 'v2/droplets', '/../x', '/x@evil.example', '/a\\b'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): apireads._path(bad)

    def test_no_verb_but_get_and_a_listed_post_exists_and_a_missing_key_or_address_says_so(self):
        src = open(apireads.__file__, encoding='utf-8').read()
        self.assertNotRegex(src, r'requests\.(put|patch|delete|request)\(')          # a POST only to a row's `post` paths: test_apireads_signed
        with self.assertRaisesRegex(RuntimeError, 'no Tradier key'): apireads.runner('tradier')({})
        with self.assertRaisesRegex(RuntimeError, 'Jenkins needs its address'): apireads.runner('jenkins')({'api_key': 'k'})
        self.assertEqual(apireads.base_of('sonarqube', {}), 'https://sonarcloud.io')
        with mock.patch.object(apireads.requests, 'get', return_value=resp({'message': 'Unauthorized'}, 401)), \
                self.assertRaisesRegex(RuntimeError, 'DigitalOcean answered 401 - the key was refused'):
            apireads.runner('digitalocean')({'api_key': 'bad'})


class DynamoDBReads(unittest.TestCase):
    def test_lists_scans_and_gets_and_its_test_lists_tables(self):
        from taskuary import aws
        db = mock.Mock()
        db.list_tables.return_value = {'TableNames': ['orders', 'vendors']}
        db.scan.return_value = {'Items': [{'id': {'S': 'o-1'}}], 'Count': 1, 'ScannedCount': 1}
        db.get_item.return_value = {'Item': {'id': {'S': 'o-1'}, 'total': {'N': '42'}}}
        with mock.patch.object(aws, 'client', return_value=db):
            self.assertIn('2', aws.run_dynamodb({})[0])
            self.assertIn('o-1', aws.run_dynamodb({'table': 'orders'})[1])
            self.assertIn('1 item', aws.run_dynamodb({'table': 'orders', 'key': {'id': {'S': 'o-1'}}})[0])
            s = MemoryStore(); out = channels.test_connector(s, card(s, 'dynamodb', 'sk', access_key_id='AKIA', region='us-east-1'))
        self.assertTrue(out['ok'], out)
        self.assertFalse({'put_item', 'update_item', 'delete_item'} & {c[0] for c in db.method_calls})
        self.assertEqual((reports.card_of('dynamodb'), scopes.needs('dynamodb')), ('dynamodb', 'read'))


class TheNewerShapes(unittest.TestCase):
    "Fields on the card in the URL and headers, a POST only where the vendor reads that way, and a sign-in minted once."
    def setUp(self):
        from taskuary import net
        net._TOKENS.clear()

    def test_copper_reads_by_search_at_its_allowlisted_paths_only(self):
        cfg = {'api_key': 'cp', 'user': 'alex@northwind.example', 'path': '/opportunities/search', 'body': {'page_size': 5}}
        with mock.patch.object(apireads.requests, 'post', return_value=resp([{'id': 1, 'name': 'Renewal'}])) as p:
            self.assertEqual(apireads.runner('copper')(cfg)[0], 'Copper: 1 items')
        h = p.call_args.kwargs['headers']
        self.assertEqual((p.call_args.args[0], p.call_args.kwargs['json']), ('https://api.copper.com/developer_api/v1/opportunities/search', {'page_size': 5}))
        self.assertEqual((h['X-PW-AccessToken'], h['X-PW-UserEmail'], h['X-PW-Application']), ('cp', 'alex@northwind.example', 'developer_api'))
        for bad in ('/people/1', '/opportunities/search/../x', '/webhooks'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): apireads.runner('copper')({**cfg, 'path': bad})
        with self.assertRaisesRegex(ValueError, 'read by GET only'): apireads.runner('pipedrive')({'api_key': 'k', 'path': '/deals', 'body': {}})
        with self.assertRaisesRegex(RuntimeError, 'Copper needs its user'): apireads.runner('copper')({'api_key': 'cp'})

    def test_a_sign_in_is_minted_once_and_rides_as_the_bearer(self):
        cfg = {'api_key': 'sec', 'client_id': 'cid', 'path': '/api/track/v1/details/1Z999AA10123456784'}
        track = {'trackResponse': {'shipment': [{'package': [{'trackingNumber': '1Z999AA10123456784', 'currentStatus': {'description': 'Delivered'}}]}]}}
        with mock.patch.object(apireads.requests, 'post', return_value=resp(TOKENS['ups'])) as p,                 mock.patch.object(apireads.requests, 'get', return_value=resp(track)) as g:
            apireads.runner('ups')(cfg); apireads.runner('ups')(cfg)
        self.assertEqual(p.call_count, 1)
        self.assertEqual((p.call_args.kwargs['auth'], p.call_args.kwargs['data']), (('cid', 'sec'), {'grant_type': 'client_credentials'}))
        self.assertEqual(g.call_args.kwargs['headers']['Authorization'], 'Bearer ups-tok')
        self.assertEqual(g.call_args.kwargs['headers']['transactionSrc'], 'taskuary')
        with mock.patch.object(apireads.requests, 'post', return_value=resp({'errors': [{'code': 'NOT.AUTHORIZED.ERROR'}]}, 401)),                 self.assertRaisesRegex(RuntimeError, 'FedEx refused the sign-in'):
            apireads.runner('fedex')({'api_key': 'bad', 'client_id': 'c', 'path': '/track/v1/trackingnumbers', 'body': {}})
        with self.assertRaisesRegex(RuntimeError, 'USPS needs a path'): apireads.runner('usps')({'api_key': 's', 'client_id': 'c'})

    def test_a_card_field_inside_a_url_is_a_name_never_a_path(self):
        for bad in ('../evil', 'a/b', 'evil.example/x?'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'plain name'):
                apireads._names('/a/{shop}', apireads.Fields('pipedrive', {'shop': bad}))
        self.assertEqual(apireads._names('/a/{shop}', apireads.Fields('pipedrive', {'shop': 'abc-1'})), '/a/abc-1')


if __name__ == '__main__':
    unittest.main()
