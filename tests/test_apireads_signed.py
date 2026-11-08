"""THE KEYED READS WHOSE KEY IS NOT THE WHOLE STORY (apireads.py, the owner 2026-11-08: "hurry finish it all.. do all of it"): a token swapped
first (Docker Hub, Schwab, Workday, Dynamics 365, SAP, ADP, PointClickCare), a key signed into each call (NetSuite's OAuth 1.0a, Google
Cloud's service account, Epic and Cerner's SMART JWT), credentials riding in the body (Plaid), and vendors whose reads are POSTs. Each Test is
fed the answers its vendor's docs show; nothing is reached. Every person, account and record here is invented."""
import base64, hashlib, hmac, json, sys, types, unittest
from unittest import mock
from urllib.parse import quote, unquote, urlsplit, parse_qsl

from taskuary import apireads, channels, connectorcatalog, guard, reports, scopes
from taskuary.store import MemoryStore

DOC = {'docker_hub': {'count': 1, 'results': [{'name': 'ledger', 'namespace': 'northwind', 'pull_count': 42}]},
       'uptimerobot': {'stat': 'ok', 'account': {'email': 'alex@northwind.example', 'monitor_limit': 50, 'up_monitors': 3}},
       'heroku': {'email': 'alex@northwind.example', 'id': '01234567-89ab-cdef-0123-456789abcdef', 'name': 'Alex Doyle'},
       'gcp': {'projects': [{'projectId': 'northwind-ledger', 'name': 'ledger', 'lifecycleState': 'ACTIVE'}]},
       'browserbase': [{'id': 'p-1', 'name': 'northwind', 'concurrency': 3}],
       'oxylabs': {'sources': {'universal': {'result_count': 12}}, 'meta': {'date_from': '2026-11-01'}},
       'brightdata': [{'name': 'web_unlocker1', 'type': 'unblocker'}],
       'plaid': {'accounts': [{'account_id': 'acc-1', 'name': 'Plaid Checking', 'balances': {'current': 110.0, 'iso_currency_code': 'USD'}}],
                 'item': {'item_id': 'item-1'}, 'request_id': 'r1'},
       'ibkr': {'session': 's1', 'iserver': {'authStatus': {'authenticated': True, 'connected': True}}},
       'schwab': [{'accountNumber': '00001234', 'hashValue': 'HASH0001'}],
       'bamboohr': {'fields': [{'id': 'displayName', 'type': 'text'}], 'employees': [{'id': '1', 'displayName': 'Erin Blake'}]},
       'netsuite': {'links': [], 'count': 1, 'hasMore': False, 'items': [{'links': [], 'id': '1'}], 'offset': 0, 'totalResults': 1},
       'sap': {'d': {'results': [{'BusinessPartner': '1000001', 'BusinessPartnerFullName': 'Northwind Supply'}]}},
       'dynamics365': {'BusinessUnitId': 'bu-1', 'UserId': 'u-1', 'OrganizationId': 'o-1'},
       'workday': {'total': 1, 'data': [{'id': 'w1', 'descriptor': 'Gail Moreno'}]},
       'adp': {'workers': [{'associateOID': 'G3-1', 'person': {'legalName': {'formattedName': 'Ray Colton'}}}]},
       'epic': {'resourceType': 'CapabilityStatement', 'fhirVersion': '4.0.1', 'status': 'active'},
       'cerner': {'resourceType': 'CapabilityStatement', 'fhirVersion': '4.0.1', 'status': 'active'},
       'pointclickcare': {'data': [{'facId': 1, 'facilityName': 'Northwind Care Center'}], 'paging': {'hasMore': False}}}
TOKEN_URL = 'https://login.northwind.example/oauth2/token'
CFG = dict(host='https://ci.northwind.example', user='alex', subdomain='northwind', account='1234567_SB1', consumer_key='ck', consumer_secret='cs',
           token_id='tid', environment='sandbox', client_id='cid', client_secret='csec', access_token='access-sandbox-1', tenant='northwind',
           tenant_id='t-1', token_url=TOKEN_URL, cert_file='c.pem', key_file='c.key', org_uuid='org-1')
KEY = {'gcp': json.dumps({'type': 'service_account', 'client_email': 'reader@northwind-ledger.example'}),
       'epic': '-----BEGIN PRIVATE KEY----- AAAA BBBB -----END PRIVATE KEY-----', 'cerner': '-----BEGIN PRIVATE KEY----- AAAA BBBB -----END PRIVATE KEY-----'}


def resp(j, code=200):
    r = mock.Mock(); r.status_code, r.text = code, json.dumps(j); r.json.return_value = j
    return r


def card(s, t, key='key-1', **cfg):
    c = s.get_connector_by_type(t)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(cfg), **({'Secret': key} if key else {})}, 't')
    return c['ConnectorId']


class Fakes:
    "requests.get / requests.post, answering a token swap with a token and every read with its vendor's documented answer."
    def __init__(self, t): self.t, self.calls = t, []
    def _r(self, method, url, **kw):
        self.calls.append((method, url, kw))
        tok = method == 'POST' and (url == TOKEN_URL or 'grant_type' in (kw.get('data') or {}) or url.endswith('/v2/auth/token'))
        return resp({'access_token': 'tok-1', 'expires_in': 3600, 'token_type': 'Bearer'} if tok else DOC[self.t])
    def get(self, url, **kw): return self._r('GET', url, **kw)
    def post(self, url, **kw): return self._r('POST', url, **kw)


def google_and_jwt():
    "google-auth and PyJWT as the cards meet them - stand-ins, so the test needs neither installed."
    class Creds:
        token = 'gcp-tok'
        def refresh(self, req): pass
    sa = types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_info=lambda info, scopes: Creds()))
    jwt = types.SimpleNamespace(encode=lambda payload, key, algorithm, headers=None: f'jwt.{algorithm}.{payload["iss"]}')
    return mock.patch.dict(sys.modules, {'google': types.SimpleNamespace(), 'google.oauth2': types.SimpleNamespace(service_account=sa),
                                         'google.oauth2.service_account': sa, 'google.auth': types.SimpleNamespace(),
                                         'google.auth.transport': types.SimpleNamespace(),
                                         'google.auth.transport.requests': types.SimpleNamespace(Request=lambda: None), 'jwt': jwt})


def run_test(t, **over):
    s, f = MemoryStore(), Fakes(t)
    cid = card(s, t, KEY.get(t, 'key-1'), **{**CFG, **over})
    with mock.patch.object(apireads.requests, 'get', f.get), mock.patch.object(apireads.requests, 'post', f.post), google_and_jwt():
        out = channels.test_connector(s, cid)
    assert out['ok'], (t, out)
    return out, f.calls


class EverySignedRowIsAWorkingCard(unittest.TestCase):
    def setUp(self): apireads._TOK.clear()

    def test_each_test_reads_with_what_the_vendor_wants(self):
        for t in DOC:
            with self.subTest(t=t):
                out, calls = run_test(t)
                self.assertTrue(out['ok'], (t, out))
                self.assertIs(connectorcatalog.by_type(t)['planned'], False)
                self.assertEqual((reports.card_of(f'{t}_read'), scopes.needs(f'{t}_read')), (t, 'read'))
                method, url, kw = calls[-1]
                self.assertFalse(kw['allow_redirects'])
                r, h = apireads.table()[t], kw['headers']
                mode = apireads.auth_of(r, CFG)
                if mode in ('jwt_swap', 'refresh', 'client_credentials', 'smart'): self.assertEqual(h['Authorization'], 'Bearer tok-1')
                if mode == 'gcp_sa': self.assertEqual(h['Authorization'], 'Bearer gcp-tok')
                self.assertEqual(method, 'POST' if r.get('post_only') or 'probe_body' in r else 'GET')

    def test_the_documented_shapes(self):
        _, c = run_test('plaid')
        self.assertEqual((c[-1][1], c[-1][2]['json']), ('https://sandbox.plaid.com/accounts/get', {'client_id': 'cid', 'secret': 'key-1', 'access_token': 'access-sandbox-1'}))
        _, c = run_test('uptimerobot')
        self.assertEqual((c[-1][1], c[-1][2]['data']), ('https://api.uptimerobot.com/v2/getAccountDetails', {'api_key': 'key-1'}))
        _, c = run_test('bamboohr')
        self.assertEqual(c[-1][1], 'https://api.bamboohr.com/api/gateway.php/northwind/v1/employees/directory')
        self.assertEqual(base64.b64decode(c[-1][2]['headers']['Authorization'][6:]).decode(), 'key-1:x')
        _, c = run_test('docker_hub', token_url='')
        self.assertEqual((c[0][1], c[0][2]['json']), ('https://hub.docker.com/v2/auth/token', {'identifier': 'alex', 'secret': 'key-1'}))
        self.assertEqual(c[-1][1], 'https://hub.docker.com/v2/namespaces/alex/repositories?page_size=1')
        _, c = run_test('schwab', token_url='')
        self.assertEqual((c[0][1], c[0][2]['data'], c[0][2]['auth']), ('https://api.schwabapi.com/v1/oauth/token',
                         {'grant_type': 'refresh_token', 'refresh_token': 'key-1'}, ('cid', 'csec')))
        _, c = run_test('dynamics365', host='https://northwind.crm.dynamics.com', token_url='')
        self.assertEqual(c[0][1], 'https://login.microsoftonline.com/t-1/oauth2/v2.0/token')
        self.assertEqual(c[0][2]['data'], {'grant_type': 'client_credentials', 'scope': 'https://northwind.crm.dynamics.com/.default', 'client_id': 'cid', 'client_secret': 'key-1'})
        _, c = run_test('workday', host='https://wd2-impl-services1.workday.com', token_url='')
        self.assertEqual(c[0][1], 'https://wd2-impl-services1.workday.com/ccx/oauth2/northwind/token')
        self.assertEqual(c[-1][1], 'https://wd2-impl-services1.workday.com/ccx/api/v1/northwind/workers?limit=1')
        _, c = run_test('workday', client_id='', token_url='')                  # an ISU's password: basic, no swap
        self.assertEqual((len(c), base64.b64decode(c[-1][2]['headers']['Authorization'][6:]).decode()), (1, 'alex:key-1'))
        _, c = run_test('sap', token_url='')
        self.assertTrue(c[-1][2]['headers']['Authorization'].startswith('Basic '))
        _, c = run_test('adp', token_url='')
        self.assertEqual([x[2]['cert'] for x in c], [('c.pem', 'c.key')] * 2)          # the partner certificate on the swap AND the read
        _, c = run_test('gcp')
        self.assertEqual(c[-1][1], 'https://cloudresourcemanager.googleapis.com/v1/projects')
        _, c = run_test('epic')
        d = c[0][2]['data']
        self.assertEqual((d['grant_type'], d['client_assertion_type'], d['client_assertion']),
                         ('client_credentials', 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer', 'jwt.RS384.cid'))
        self.assertEqual(c[-1][2]['headers']['Accept'], 'application/fhir+json')
        _, c = run_test('pointclickcare', host='', token_url='')
        self.assertEqual((c[0][1], c[-1][1]), ('https://login.pointclickcare.com/oauth2/token', 'https://connect.pointclickcare.com/api/public/preview1/orgs/org-1/facs'))
        _, c = run_test('ibkr', host='https://localhost:5000/v1/api')
        self.assertIs(c[-1][2]['verify'], False)                           # the gateway's own certificate, on this computer only
        _, c = run_test('ibkr', host='https://gateway.northwind.example/v1/api')
        self.assertNotIn('verify', c[-1][2])

    def test_netsuite_signs_each_call_with_oauth1_hmac_sha256(self):
        _, c = run_test('netsuite')
        method, url, kw = c[-1]
        self.assertEqual((method, url, kw['json'], kw['headers']['Prefer']),
                         ('POST', 'https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql?limit=1', {'q': 'SELECT id FROM currency'}, 'transient'))
        auth = kw['headers']['Authorization']
        self.assertTrue(auth.startswith('OAuth realm="1234567_SB1", '))
        o = {k: unquote(v.strip('"')) for k, v in (p.split('=', 1) for p in auth[6:].split(', '))}
        e = lambda x: quote(str(x), safe='~')
        ps = sorted((e(k), e(v)) for k, v in [('limit', '1'), *((k, v) for k, v in o.items() if k.startswith('oauth_') and k != 'oauth_signature')])
        base = '&'.join(['POST', e('https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql'), e('&'.join(f'{k}={v}' for k, v in ps))])
        self.assertEqual(o['oauth_signature'], base64.b64encode(hmac.new(b'cs&key-1', base.encode(), hashlib.sha256).digest()).decode())
        self.assertEqual((o['oauth_signature_method'], o['oauth_consumer_key'], o['oauth_token']), ('HMAC-SHA256', 'ck', 'tid'))

    @unittest.skipUnless(__import__('importlib').util.find_spec('jwt') and __import__('importlib').util.find_spec('cryptography'), 'PyJWT[crypto] not installed')
    def test_the_smart_jwt_is_rs384_signed_for_the_token_url(self):
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        f = Fakes('epic')
        with mock.patch.object(apireads.requests, 'post', f.post):
            apireads._swap('epic', apireads.table()['epic'], {**CFG, 'kid': 'k1'}, pem.replace('\n', ' '))     # pasted into a one-line box
        a = f.calls[0][2]['data']['client_assertion']
        claims = jwt.decode(a, k.public_key(), algorithms=['RS384'], audience=TOKEN_URL)
        self.assertEqual((claims['iss'], claims['sub'], jwt.get_unverified_header(a)['kid']), ('cid', 'cid', 'k1'))
        self.assertLessEqual(claims['exp'] - claims['iat'], 300)


class StillOnlyReads(unittest.TestCase):
    def setUp(self): apireads._TOK.clear()

    def test_a_body_goes_only_to_a_path_the_row_names_as_a_read(self):
        with mock.patch.object(apireads.requests, 'post') as p, mock.patch.object(apireads.requests, 'get') as g:
            with self.assertRaisesRegex(PermissionError, 'not one of the reads'):
                apireads.call('browserbase', {}, 'k', '/sessions/s-1', body={'status': 'REQUEST_RELEASE'})
            with self.assertRaisesRegex(PermissionError, 'reads by POST'):
                apireads.call('plaid', {'environment': 'sandbox', 'client_id': 'c'}, 'k', '/transfer/create')
            with self.assertRaisesRegex(PermissionError, 'not one of the reads'):
                apireads.call('plaid', {'environment': 'sandbox', 'client_id': 'c'}, 'k', '/item/remove', body={})
            with self.assertRaisesRegex(PermissionError, 'not one of the reads'):
                apireads.call('tradier', {}, 'k', '/accounts/VA000001/orders', body={'class': 'equity', 'side': 'buy'})
        p.assert_not_called(); g.assert_not_called()
        p = mock.Mock(return_value=resp({'id': 's-1', 'connectUrl': 'wss://connect.browserbase.example'}))
        with mock.patch.object(apireads.requests, 'post', p):
            apireads.runner('browserbase')({'api_key': 'k', 'path': '/sessions', 'body': {}})
        self.assertEqual((p.call_args.args[0], p.call_args.kwargs['headers']['X-BB-API-Key']), ('https://api.browserbase.com/v1/sessions', 'k'))

    def test_a_host_placeholder_cannot_carry_a_url_and_google_paths_name_a_service(self):
        for bad in ('evil.example/x', 'a@b', 'x y', ''):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError): apireads.base_of('bamboohr', {'subdomain': bad})
        self.assertEqual(apireads.url_of('gcp', {}, '/run/v2/projects/p/locations/-/services'), 'https://run.googleapis.com/v2/projects/p/locations/-/services')
        with self.assertRaises(ValueError): apireads.url_of('gcp', {}, '/evil.example/x')

    def test_the_sign_in_fields_are_the_cards_own(self):
        q = reports.query_only({'path': '/x', 'token_url': 'https://evil.example/t', 'subdomain': 'evil', 'access_token': 'a', 'cert_file': 'x', 'conn_str': 'mongodb://evil'})
        self.assertEqual(q, {'path': '/x'})
        self.assertEqual(guard.WRITE_ONLY_CONFIG['netsuite'], ('consumer_secret',))
        self.assertEqual(guard.masked_config({'Type': 'plaid', 'ConfigJson': json.dumps({'client_id': 'c', 'access_token': 'access-1'})})['ConfigJson'], '{"client_id": "c"}')

    def test_a_missing_library_says_which_extra(self):
        from taskuary.deps import Missing
        with mock.patch.dict(sys.modules, {'google.oauth2': None}), self.assertRaisesRegex(Missing, r'taskuary\[gcp\]'):
            apireads._swap('gcp', apireads.table()['gcp'], {}, '{}')
        with mock.patch.dict(sys.modules, {'jwt': None}), self.assertRaisesRegex(Missing, r'taskuary\[fhir\]'):
            apireads._swap('cerner', apireads.table()['cerner'], CFG, 'k')


class BingIsRetired(unittest.TestCase):
    def test_the_retired_card_is_gone_and_the_search_cards_it_pointed_to_work(self):
        self.assertIsNone(connectorcatalog.by_type('bing_search'))             # Microsoft retired the Bing Search APIs on 2025-08-11
        for t in ('brave_search', 'exa', 'tavily'): self.assertIs(connectorcatalog.by_type(t)['planned'], False)


if __name__ == '__main__':
    unittest.main()
