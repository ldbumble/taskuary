"""A VENDOR'S REST API, READ WITH A KEY (apireads.py, the owner 2026-11-08): every row of apireads.json is a working card whose Test makes
its one cheap GET - each fed the answer its vendor's docs show - and nothing but a GET under its own base is ever sent. Nothing is reached."""
import json, unittest
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
       'google_drive': {'user': {'displayName': 'Alex Doyle', 'emailAddress': 'alex@northwind.example'}},
       'onedrive': {'id': 'd1', 'driveType': 'business', 'owner': {'user': {'displayName': 'Alex Doyle'}}},
       'office365_files': {'value': [{'id': 'f1', 'name': 'Q3 plan.xlsx'}]}}


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
        self.assertEqual(set(DOC) | set(SIGNED), set(apireads.types()))
        for t, r in apireads.table().items():
            c = connectorcatalog.by_type(t)
            self.assertTrue(c and c['planned'] is False, t)
            self.assertTrue(r['docs'].startswith('https://') and r['probe'].startswith('/'), t)
            self.assertTrue(r.get('base', 'https://').startswith('https://'), t)
            self.assertEqual((reports.card_of(f'{t}_read'), scopes.needs(f'{t}_read')), (t, 'read'), t)

    def test_each_cards_test_makes_its_probe_with_the_key_where_the_vendor_wants_it(self):
        s = MemoryStore()
        for t, r in ((t, apireads.table()[t]) for t in DOC):
            cid = card(s, t, host='https://ci.northwind.example', user='alex')
            with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC[t])) as g, \
                    mock.patch('taskuary.sheets._token', return_value='g-tok'), mock.patch('taskuary.sheets.google_sheets_connection', return_value={}), \
                    mock.patch('taskuary.outbound._graph_token', return_value='ms-tok'):
                out = channels.test_connector(s, cid)
            self.assertTrue(out['ok'], (t, out))
            url, kw = g.call_args.args[0], g.call_args.kwargs
            self.assertEqual(url, (r.get('base') or 'https://ci.northwind.example') + r['probe'], t)
            self.assertFalse(kw['allow_redirects'])
            h, q = kw['headers'], kw['params']
            want = {'query': lambda: q[r['param']] == 'key-1', 'basic': lambda: h['Authorization'].startswith('Basic '),
                    'google': lambda: h['Authorization'] == 'Bearer g-tok', 'graph': lambda: h['Authorization'] == 'Bearer ms-tok'}.get(r['auth'])
            self.assertTrue(want() if want else h[r.get('header') or 'Authorization'] == (r.get('format') or 'Bearer {key}').format(key='key-1'), (t, h, q))

    def test_the_documented_shapes_the_owner_relies_on(self):
        with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC['circleci'])) as g:
            apireads.runner('circleci')({'api_key': 'cc'})
        self.assertEqual(g.call_args.kwargs['headers']['Circle-Token'], 'cc')
        with mock.patch.object(apireads.requests, 'get', return_value=resp(DOC['elastic'])) as g:
            apireads.runner('elastic')({'api_key': 'ZW5j', 'host': 'es.northwind.example:9243'})
        self.assertEqual((g.call_args.args[0], g.call_args.kwargs['headers']['Authorization']), ('https://es.northwind.example:9243/', 'ApiKey ZW5j'))
        with mock.patch.object(apireads.requests, 'get', return_value=resp([{'title': 'x'}])):
            self.assertEqual(apireads.runner('benzinga')({'api_key': 'b', 'path': '/news?tickers=AAPL'})[0], 'Benzinga: 1 items')


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


if __name__ == '__main__':
    unittest.main()
