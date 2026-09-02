"""Database-by-connection-string, AWS and Azure connectors - all faked (no cloud, no
engines), so these run anywhere. Review-queue visibility lives in test_reviews.py.
"""
import json, unittest
from unittest import mock
from taskuary import aws, azure, db
from taskuary.reports import REGISTRY, PLANNED, card_of, resolve_cfg
from taskuary.store import MemoryStore


class DbTests(unittest.TestCase):
    def test_password_placeholder(self):
        cs = db.conn_str({'conn_str': 'postgresql://u:{password}@h/db', 'password': 'pw'})
        self.assertEqual(cs, 'postgresql://u:pw@h/db')
        self.assertEqual(db.conn_str({'conn_str': 'DSN=x'}), 'DSN=x')   # no placeholder, untouched

    def test_no_string_is_loud(self):
        with self.assertRaises(RuntimeError): db.conn_str({})

    def test_url_vs_odbc_road(self):
        self.assertTrue(db.is_url('mysql+pymysql://u@h/db'))
        self.assertFalse(db.is_url('DRIVER={x};SERVER=y'))

    def test_run_report_via_registry(self):
        with mock.patch.object(db, '_rows_odbc', return_value=[{'A': 1}, {'A': 2}]):
            head, body = REGISTRY['database']({'conn_str': 'DSN=x', 'query': 'SELECT 1'})
        self.assertEqual(head, '2 rows'); self.assertIn('"A": 2', body)

    def test_test_reports_engine(self):
        with mock.patch.object(db, '_rows_sqlalchemy', return_value=[{'x': 1}]):
            r = db.test({'conn_str': 'postgresql://u:p@h/db'})
        self.assertTrue(r['ok']); self.assertEqual(r['engine'], 'postgresql')


class FakeS3Body:
    def __init__(self, data): self.data = data
    def read(self, n): return self.data[:n]

class FakeAws:
    def __init__(self): self.calls = []
    def get_caller_identity(self): return {'Account': '123', 'Arn': 'arn:aws:iam::123:user/u'}
    def list_objects_v2(self, **kw):
        self.calls.append(kw)
        return {'Contents': [{'Key': 'a.csv', 'Size': 5, 'LastModified': 'now'}]}
    def get_object(self, **kw): return {'Body': FakeS3Body(b'hello rows'), 'ContentLength': 10}
    def filter_log_events(self, **kw):
        return {'events': [{'timestamp': 1755900000000, 'logStreamName': 's', 'message': 'ERROR boom'}]}
    def list_buckets(self): return {'Buckets': [{'Name': 'b1'}, {'Name': 'b2'}]}


class AwsTests(unittest.TestCase):
    def test_test_and_s3_and_logs(self):
        with mock.patch.object(aws, 'client', return_value=FakeAws()):
            self.assertIn('account 123', aws.test({})['detail'])
            head, body = aws.run_s3_object({'bucket': 'b', 'prefix': 'r/'})
            self.assertEqual(head, '1 objects'); self.assertIn('a.csv', body)
            head, body = aws.run_s3_object({'bucket': 'b', 'key': 'a.csv'})
            self.assertIn('10 bytes', head); self.assertIn('hello rows', body)
            head, body = aws.run_cloudwatch_logs({'log_group': '/aws/x', 'pattern': '?ERROR'})
            # the headline names the WINDOW now, which is what answers "only 1 event?"
            self.assertEqual(head, '1 events in the last 24h'); self.assertIn('ERROR boom', body)

    def test_generic_call_unwraps_the_one_list(self):
        with mock.patch.object(aws, 'client', return_value=FakeAws()):
            head, body = aws.run_aws({'service': 's3', 'operation': 'list_buckets'})
        self.assertEqual(head, '2 items'); self.assertIn('b1', body)

    def test_dot_path(self):
        self.assertEqual(aws.dot_path({'a': [{'b': 7}]}, 'a.0.b'), 7)


class FakeResp:
    def __init__(self, j=None, text='', status=200):
        self.status_code, self._j, self.text, self.content = status, j, text, text.encode()
    def json(self): return self._j


class AzureTests(unittest.TestCase):
    def test_token_needs_creds(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(RuntimeError): azure.token({}, 'scope')

    def test_arm_list_and_single(self):
        cfg = {'tenant_id': 't', 'client_id': 'c', 'client_secret': 's', 'path': '/subscriptions'}
        with mock.patch.object(azure, 'token', return_value='tok'), \
             mock.patch.object(azure, '_get', return_value=FakeResp(j={'value': [{'name': 'sub1'}]})):
            head, body = azure.run_azure(cfg)
        self.assertEqual(head, '1 items'); self.assertIn('sub1', body)
        with mock.patch.object(azure, 'token', return_value='tok'), \
             mock.patch.object(azure, '_get', return_value=FakeResp(j={'name': 'one-app'})):
            head, body = azure.run_azure(cfg)
        self.assertEqual(head, 'ok'); self.assertIn('one-app', body)

    def test_blob_list_parses_xml(self):
        xml = ('<Blobs><Blob><Name>r/a.csv</Name><Properties><Last-Modified>Mon</Last-Modified>'
               '<Content-Length>42</Content-Length></Properties></Blob></Blobs>')
        with mock.patch.object(azure, 'token', return_value='tok'), \
             mock.patch.object(azure, '_get', return_value=FakeResp(text=xml)):
            head, body = azure.run_azure_blob({'account': 'acct', 'container': 'c'})
        self.assertEqual(head, '1 blobs'); self.assertIn('r/a.csv', body); self.assertIn('42', body)


class WiringTests(unittest.TestCase):
    def test_registry_and_planned(self):
        for t in ('database', 'aws', 's3_object', 'cloudwatch_logs', 'azure', 'azure_blob', 'azure_logs'):
            self.assertIn(t, REGISTRY)
            self.assertNotIn(t, PLANNED)

    def test_card_of(self):
        self.assertEqual(card_of('s3_object'), 'aws')
        self.assertEqual(card_of('azure_logs'), 'azure')
        self.assertEqual(card_of('database'), 'database')

    def _arm(self, s, typ, cfg, secret):
        cid = s.get_connector_by_type(typ)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(cfg), 'Secret': secret, 'Active': 1}, 't')

    def test_resolve_cfg_pulls_the_card(self):
        s = MemoryStore()
        self._arm(s, 'aws', {'region': 'us-east-2', 'access_key_id': 'AK'}, 'SK')
        got = resolve_cfg(s, {'type': 's3_object', 'bucket': 'b'})
        self.assertEqual((got['region'], got['secret_access_key'], got['bucket']), ('us-east-2', 'SK', 'b'))

    def test_azure_borrows_outlook_app(self):
        s = MemoryStore()
        self._arm(s, 'outlook', {'tenant_id': 'T', 'client_id': 'C'}, 'GSEC')
        got = resolve_cfg(s, {'type': 'azure_logs', 'workspace_id': 'w', 'query': 'q'})
        self.assertEqual((got['tenant_id'], got['client_secret']), ('T', 'GSEC'))
        # its own card wins once set
        self._arm(s, 'azure', {'tenant_id': 'T2', 'client_id': 'C2'}, 'ASEC')
        got = resolve_cfg(s, {'type': 'azure_logs', 'workspace_id': 'w', 'query': 'q'})
        self.assertEqual((got['tenant_id'], got['client_secret']), ('T2', 'ASEC'))

    def test_seeded_cards_carry_roles(self):
        s = MemoryStore()
        for t in ('database', 'aws', 'azure'):
            self.assertEqual(s.get_connector_by_type(t)['Roles'], 'report,tool')


if __name__ == '__main__':
    unittest.main()
