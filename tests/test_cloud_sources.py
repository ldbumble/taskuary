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
    # S3 is one global namespace, so a bucket is asked where it actually lives - a client
    # pointed at the wrong region gets a 301 the moment it reads objects
    def get_bucket_location(self, Bucket=None): return {'LocationConstraint': 'us-east-2'}
    def list_objects_v2(self, **kw):
        return {'Contents': [{'Key': 'daily/2026-08-23.csv', 'Size': 812, 'LastModified': FRESH}]}

class FakeLogs:
    def __init__(self, region=None): self.region = region
    def describe_log_groups(self, **kw):
        # log groups are PER REGION: same account, different lists
        name = f'/aws/lambda/importer-{self.region}' if self.region else '/aws/lambda/importer'
        return {'logGroups': [{'logGroupName': name}]}
    def filter_log_events(self, **kw):
        return {'events': [{'timestamp': int(FRESH.timestamp() * 1000), 'eventId': 'e1',
                            'message': 'ERROR invalid employee id'}]}

def fake_client(cfg, service, region=None):
    return FakeS3() if service == 's3' else FakeLogs(region)


class AwsRegionTests(unittest.TestCase):
    """One card, many regions. CloudWatch log groups exist PER REGION, so a single region field
    left half an account invisible with nothing on screen to say so."""

    def test_the_field_takes_a_list_and_a_single_value_still_means_one_region(self):
        self.assertEqual(aws.regions({'region': 'us-east-2'}), ['us-east-2'])
        self.assertEqual(aws.regions({'region': 'us-east-2, us-east-1'}), ['us-east-2', 'us-east-1'])
        self.assertEqual(aws.regions({'region': 'us-east-1;us-west-2  eu-west-1'}),
                         ['us-east-1', 'us-west-2', 'eu-west-1'])
        self.assertEqual(aws.regions({'region': 'us-east-1, us-east-1'}), ['us-east-1'])   # deduped
        self.assertEqual(aws.regions({}), [None])          # blank = boto3's own default chain

    def test_every_region_is_swept_and_each_object_remembers_where_it_lives(self):
        s = MemoryStore(); c = arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            out = aws.discover(s, {'region': 'us-east-2, us-east-1'}, c['ConnectorId'])
        rows = {x['Address']: json.loads(x['ConfigJson']) for x in s.list_sources() if x['Channel'] == 'aws'}
        self.assertIn('logs:///aws/lambda/importer-us-east-2', rows)
        self.assertIn('logs:///aws/lambda/importer-us-east-1', rows)      # the half that was invisible
        self.assertEqual(rows['logs:///aws/lambda/importer-us-east-1']['region'], 'us-east-1')
        self.assertEqual(rows['s3://reports-prod']['region'], 'us-east-2')   # asked, not assumed
        self.assertEqual(out['regions'], ['us-east-2', 'us-east-1'])

    def test_s3_is_listed_once_however_many_regions_there_are(self):
        """One global namespace - listing it per region would register the same buckets twice."""
        s = MemoryStore(); c = arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {'region': 'us-east-2, us-east-1, eu-west-1'}, c['ConnectorId'])
        buckets = [x for x in s.list_sources() if x['Address'].startswith('s3://')]
        self.assertEqual(len(buckets), 2)

    def test_two_regions_holding_the_same_name_are_two_different_objects(self):
        """/aws/lambda/ingest in us-east-1 and in us-east-2 are unrelated log groups. Keyed on
        the name alone, whichever came first won and the other vanished."""
        s = MemoryStore(); c = arm(s, 'aws')
        same = lambda cfg, service, region=None: FakeS3() if service == 's3' else FakeLogs()
        with mock.patch.object(aws, 'client', same):
            aws.discover(s, {'region': 'us-east-2, us-east-1'}, c['ConnectorId'])
        rows = [x for x in s.list_sources() if x['Address'] == 'logs:///aws/lambda/importer']
        self.assertEqual(sorted(json.loads(r['ConfigJson'])['region'] for r in rows),
                         ['us-east-1', 'us-east-2'])

    def test_rediscovery_across_regions_adds_nothing_the_second_time(self):
        s = MemoryStore(); c = arm(s, 'aws')
        with mock.patch.object(aws, 'client', fake_client):
            aws.discover(s, {'region': 'us-east-2, us-east-1'}, c['ConnectorId'])
            out = aws.discover(s, {'region': 'us-east-2, us-east-1'}, c['ConnectorId'])
        self.assertEqual(out['added'], 0)

    def test_a_region_that_refuses_does_not_cost_the_others(self):
        """A key with no permission in eu-west-1 is a reason to skip eu-west-1, not to discover
        nothing at all."""
        s = MemoryStore(); c = arm(s, 'aws')
        def picky(cfg, service, region=None):
            if service == 'logs' and region == 'eu-west-1': raise RuntimeError('AccessDenied')
            return FakeS3() if service == 's3' else FakeLogs(region)
        with mock.patch.object(aws, 'client', picky):
            aws.discover(s, {'region': 'eu-west-1, us-east-1'}, c['ConnectorId'])
        addrs = {x['Address'] for x in s.list_sources() if x['Channel'] == 'aws'}
        self.assertIn('logs:///aws/lambda/importer-us-east-1', addrs)

    def test_polling_an_object_uses_its_own_region_not_the_cards_first(self):
        s = MemoryStore()
        seen = {}
        def spy(cfg, service, region=None):
            seen['region'] = region
            return FakeLogs(region)
        src = {'SourceId': 1, 'Address': 'logs:///aws/lambda/importer', 'Channel': 'aws',
               'ConfigJson': json.dumps({'mode': 'feed', 'region': 'us-east-1'})}
        with mock.patch.object(aws, 'client', spy):
            aws.poll_source(s, {'region': 'us-east-2'}, src, SINCE, file_only=True)
        self.assertEqual(seen['region'], 'us-east-1')

    def test_the_same_events_in_two_regions_are_two_items_not_one_duplicate(self):
        """external_id used to be group+event, so the second region's batch deduped away."""
        s = MemoryStore()
        src = lambda reg: {'SourceId': 1, 'Address': 'logs:///aws/lambda/importer', 'Channel': 'aws',
                           'ConfigJson': json.dumps({'mode': 'feed', 'region': reg})}
        with mock.patch.object(aws, 'client', fake_client):
            aws.poll_source(s, {}, src('us-east-2'), SINCE, file_only=True)
            aws.poll_source(s, {}, src('us-east-1'), SINCE, file_only=True)
        rows = [m for m in s.feed() if m['Channel'] == 'aws']
        self.assertEqual(len(rows), 2)
        self.assertTrue(any('us-east-1' in (m['Subject'] or '') for m in rows))   # and it says which


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
