"""A log group belongs to ONE region, and the picker handed back a bare name.

So a group discovered in us-east-2, chosen from a list, ran against the card's FIRST region and
came back "The specified log group does not exist" - which is true of the region it asked about
and completely misleading about the group. The region has to travel with the pick.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from taskuary import aws, server
from taskuary.reports import resolve_cfg

c = TestClient(server.app)


def _has_botocore():
    try:
        import botocore.session          # noqa: F401 - boto3 is an optional extra ([aws])
        return True
    except ImportError:
        return False


class TheRegionTravelsWithThePickTests(unittest.TestCase):
    @unittest.skipUnless(_has_botocore(), 'boto3/botocore is an optional extra')
    def test_every_discovered_object_names_its_region(self):
        for addr, reg in (('logs:///aws/lambda/east2-only', 'us-east-2'),
                          ('logs:///aws/lambda/east1-only', 'us-east-1'),
                          ('s3://a-bucket', 'eu-west-1')):
            server.store.save_source({'Channel': 'aws', 'Address': addr, 'Active': 1,
                                      'ConfigJson': '{"mode": "report", "region": "%s"}' % reg}, 'test')
        d = c.get('/api/aws/catalog').json()
        by = {g['name']: g['region'] for g in d['log_groups']}
        self.assertEqual(by.get('/aws/lambda/east2-only'), 'us-east-2')
        self.assertEqual(by.get('/aws/lambda/east1-only'), 'us-east-1')
        self.assertEqual({b['name']: b['region'] for b in d['buckets']}.get('a-bucket'), 'eu-west-1')

    def test_a_sources_region_beats_the_cards_first_one(self):
        """resolve_cfg lets a source override the card, which is the whole mechanism: the card's
        region list is a default for discovery, not a decision about one log group."""
        from taskuary import reports
        card = {'region': 'us-east-1, us-east-2', 'access_key_id': 'k', 'secret_access_key': 's'}
        # CONNECTION_OF captured the function at import, so patching the module attribute would
        # change nothing - the dict entry is what resolve_cfg actually calls
        wired = {**reports.CONNECTION_OF, 'cloudwatch_logs': lambda _s: card}
        with mock.patch.object(reports, 'CONNECTION_OF', wired):
            cfg = resolve_cfg(server.store, {'type': 'cloudwatch_logs',
                                             'log_group': '/aws/lambda/east2-only', 'region': 'us-east-2'})
            bare = resolve_cfg(server.store, {'type': 'cloudwatch_logs', 'log_group': '/x'})
        self.assertEqual(aws.regions(cfg)[0], 'us-east-2')
        # and with no region on the source it still falls back to the card's first
        self.assertEqual(aws.regions(bare)[0], 'us-east-1')

    def test_the_call_is_made_in_the_sources_region(self):
        seen = {}
        class Fake:
            def filter_log_events(self, **kw): return {'events': []}
        with mock.patch.object(aws, 'client', lambda cfg, svc, region=None: seen.update(svc=svc, region=region) or Fake()):
            aws.run_cloudwatch_logs({'log_group': '/aws/lambda/x', 'region': 'eu-west-1', 'hours': 1})
        self.assertEqual((seen['svc'], seen['region']), ('logs', 'eu-west-1'))


class TheErrorNamesTheRegionTests(unittest.TestCase):
    """AWS cannot say "it exists in another region" - it only knows the one it was asked about.
    We know which one we asked, so the message says it."""
    def _boom(self, text):
        err = type('ResourceNotFoundException', (Exception,), {})
        class Fake:
            def filter_log_events(self, **kw): raise err(text)
        return Fake()

    def test_a_missing_group_blames_the_region_not_the_name(self):
        fake = self._boom('An error occurred (ResourceNotFoundException) when calling the '
                          'FilterLogEvents operation: The specified log group does not exist.')
        with mock.patch.object(aws, 'client', lambda *a, **k: fake), self.assertRaises(RuntimeError) as e:
            aws.run_cloudwatch_logs({'log_group': '/aws/lambda/testing', 'region': 'us-east-1'})
        msg = str(e.exception)
        self.assertIn('/aws/lambda/testing', msg)
        self.assertIn('us-east-1', msg)                       # WHICH region was asked
        self.assertIn('belongs to ONE region', msg)           # and why that is the likely cause
        self.assertNotIn('ResourceNotFoundException', msg)    # the class name helps nobody

    def test_a_blank_region_says_the_default_rather_than_nothing(self):
        fake = self._boom('The specified log group does not exist.')
        with mock.patch.object(aws, 'client', lambda *a, **k: fake), self.assertRaises(RuntimeError) as e:
            aws.run_cloudwatch_logs({'log_group': '/x'})
        self.assertIn('the default region', str(e.exception))

    def test_any_other_failure_is_passed_through_untouched(self):
        """A permissions error must not be reported as a region mistake."""
        class Fake:
            def filter_log_events(self, **kw): raise RuntimeError('AccessDeniedException: no logs:FilterLogEvents')
        with mock.patch.object(aws, 'client', lambda *a, **k: Fake()), self.assertRaises(RuntimeError) as e:
            aws.run_cloudwatch_logs({'log_group': '/x', 'region': 'us-east-1'})
        self.assertIn('AccessDenied', str(e.exception))
        self.assertNotIn('belongs to ONE region', str(e.exception))


if __name__ == '__main__':
    unittest.main()
