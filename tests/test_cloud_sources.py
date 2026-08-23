"""Cloud object discovery (AWS/Azure) with per-object modes, plus the per-connector poll
fix: a connection whose source row is only a marker must poll even with NO source row -
that was the "Telegram Sync does nothing" bug (no '*' marker, so getUpdates never ran and
no chat could ever announce itself).
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import aws, azure, channels, messengers
from taskuary.store import MemoryStore

SINCE = datetime.now() - timedelta(hours=2)
FRESH = datetime.now() - timedelta(minutes=10)


def arm(s, typ, cfg=None, roles=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      **({'Roles': roles} if roles else {}),
                      **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


class FakeS3:
    def list_buckets(self): return {'Buckets': [{'Name': 'reports-prod'}, {'Name': 'archive'}]}
    def list_objects_v2(self, **kw):
        return {'Contents': [{'Key': 'daily/2026-08-23.csv', 'Size': 812, 'LastModified': FRESH}]}

class FakeLogs:
    def describe_log_groups(self, **kw): return {'logGroups': [{'logGroupName': '/aws/lambda/importer'}]}
    def filter_log_events(self, **kw):
        return {'events': [{'timestamp': int(FRESH.timestamp() * 1000), 'eventId': 'e1',
                            'message': 'ERROR invalid employee id'}]}

def fake_client(cfg, service): return FakeS3() if service == 's3' else FakeLogs()


class AwsDiscoveryTests(unittest.TestCase):
    def test_discovers_buckets_and_groups_as_report_only(self):
        s = MemoryStore(); c = arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            out = aws.discover(s, {}, c['ConnectorId'])
        self.assertEqual((out['found'], out['added']), (3, 3))
        rows = {x['Address']: x for x in s.list_sources() if x['Channel'] == 'aws'}
        self.assertEqual(set(rows), {'s3://reports-prod', 's3://archive', 'logs:///aws/lambda/importer'})
        for r in rows.values():
            self.assertEqual(json.loads(r['ConfigJson'])['mode'], 'report')   # default polls nothing

    def test_rediscovery_is_idempotent(self):
        s = MemoryStore(); c = arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {}, c['ConnectorId'])
            out = aws.discover(s, {}, c['ConnectorId'])
        self.assertEqual(out['added'], 0)
        self.assertEqual(len([x for x in s.list_sources() if x['Channel'] == 'aws']), 3)

    def test_report_mode_is_never_polled(self):
        s = MemoryStore(); arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {}, s.get_connector_by_type('aws')['ConnectorId'])
            channels.poll_channels(s)
        self.assertEqual(s.feed(), [])

    def test_feed_mode_puts_new_objects_on_the_timeline(self):
        s = MemoryStore(); arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {}, s.get_connector_by_type('aws')['ConnectorId'])
            src = next(x for x in s.list_sources() if x['Address'] == 's3://reports-prod')
            s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps({'mode': 'feed'})}, 't')
            channels.poll_channels(s)
        rows = [r for r in s.feed() if r['Channel'] == 'aws']
        self.assertEqual(len(rows), 1)
        self.assertIn('daily/2026-08-23.csv', rows[0]['Subject'])

    def test_log_group_batches_into_one_item(self):
        s = MemoryStore(); arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {}, s.get_connector_by_type('aws')['ConnectorId'])
            src = next(x for x in s.list_sources() if x['Address'].startswith('logs://'))
            s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps({'mode': 'feed'})}, 't')
            n = aws.poll_source(s, {}, s.get_source(src['SourceId']), SINCE, file_only=True)
        self.assertEqual(n, 1)
        row = next(r for r in s.feed() if r['Channel'] == 'aws')
        self.assertIn('1 matching log events', row['Subject'])


AZ_SUBS = {'value': [{'subscriptionId': 'sub1', 'displayName': 'Prod'}]}
AZ_ACCTS = {'value': [{'name': 'mfastorage'}]}
AZ_WS = {'value': [{'name': 'central-logs', 'properties': {'customerId': 'wid-123'}}]}
CONT_XML = '<EnumerationResults><Containers><Container><Name>reports</Name></Container></Containers></EnumerationResults>'


class AzureDiscoveryTests(unittest.TestCase):
    def _get(self, url, tok, **kw):
        class R:
            def __init__(self, j=None, text=''): self._j, self.text = j, text
            def json(self): return self._j
        if url.endswith('/subscriptions'): return R(AZ_SUBS)
        if 'Microsoft.Storage/storageAccounts' in url: return R(AZ_ACCTS)
        if 'OperationalInsights/workspaces' in url: return R(AZ_WS)
        if 'blob.core.windows.net' in url: return R(text=CONT_XML)
        raise AssertionError(f'unexpected url {url}')

    def test_discovers_containers_and_workspaces(self):
        s = MemoryStore(); c = arm(s, 'azure')
        with mock.patch.object(azure, 'token', return_value='t'), mock.patch.object(azure, '_get', self._get):
            out = azure.discover(s, {}, c['ConnectorId'])
        rows = {x['Address']: json.loads(x['ConfigJson']) for x in s.list_sources() if x['Channel'] == 'azure'}
        self.assertEqual(out['added'], 2)
        self.assertEqual(rows['blob://mfastorage/reports']['mode'], 'report')
        self.assertEqual(rows['law://central-logs']['workspace_id'], 'wid-123')   # remembered for the poll

    def test_workspace_feed_uses_its_saved_query(self):
        s = MemoryStore(); arm(s, 'azure')
        src = {'Address': 'law://central-logs', 'SourceId': 1,
               'ConfigJson': json.dumps({'mode': 'feed', 'workspace_id': 'wid-123', 'query': 'AppExceptions | take 5'})}
        with mock.patch.object(azure, 'run_azure_logs', return_value=('3 rows', '{"ProblemId": "KeyError"}')) as run:
            n = azure.poll_source(s, {}, src, SINCE, file_only=True)
        self.assertEqual(n, 1)
        self.assertEqual(run.call_args[0][0]['query'], 'AppExceptions | take 5')
        self.assertIn('3 rows', next(r for r in s.feed() if r['Channel'] == 'azure')['Subject'])


if __name__ == '__main__':
    unittest.main()
