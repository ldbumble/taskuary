"""S3 feed polling must inspect every page, not the first lexicographic slice."""
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import aws
from taskuary.store import MemoryStore


class PagedS3:
    def __init__(self, old, fresh):
        self.old, self.fresh, self.calls = old, fresh, []

    def list_objects_v2(self, **kw):
        self.calls.append(kw)
        if not kw.get('ContinuationToken'):
            return {'Contents': [{'Key': 'reports/2026/a-old.csv', 'Size': 1,
                                  'LastModified': self.old}],
                    'IsTruncated': True, 'NextContinuationToken': 'page-2'}
        return {'Contents': [{'Key': 'reports/2026/z-new.csv', 'Size': 2,
                              'LastModified': self.fresh}],
                'IsTruncated': False}


class S3PollPagingTests(unittest.TestCase):
    def test_a_new_object_after_the_first_page_reaches_the_timeline(self):
        since = datetime.now().astimezone() - timedelta(hours=2)
        s3 = PagedS3(since - timedelta(minutes=1), since + timedelta(minutes=1))
        src = {'SourceId': 1, 'Address': 's3://reports', 'Channel': 'aws',
               'ConfigJson': json.dumps({'mode': 'feed', 'region': 'us-east-2',
                                         'prefix': 'reports/2026/'})}
        store = MemoryStore()

        with mock.patch.object(aws, 'client', return_value=s3):
            count = aws.poll_source(store, {}, src, since, file_only=True)

        self.assertEqual(count, 1)
        self.assertIn('reports/2026/z-new.csv', store.feed()[0]['Subject'])
        # the prefix reaches every page and the token reaches the second - the page size is not the point
        self.assertEqual([c.get('Prefix') for c in s3.calls], ['reports/2026/', 'reports/2026/'])
        self.assertEqual([c.get('ContinuationToken') for c in s3.calls], [None, 'page-2'])

    def test_a_bucket_that_never_ends_is_walked_to_the_cap_and_no_further(self):
        since = datetime.now().astimezone() - timedelta(hours=2)

        class Endless:
            calls = 0
            def list_objects_v2(self, **kw):
                self.calls += 1
                return {'Contents': [], 'IsTruncated': True, 'NextContinuationToken': f'page-{self.calls + 1}'}

        s3 = Endless()
        src = {'SourceId': 1, 'Address': 's3://huge', 'Channel': 'aws', 'ConfigJson': json.dumps({'mode': 'feed'})}
        from loguru import logger
        seen, sink = [], None
        try:
            sink = logger.add(lambda m: seen.append(str(m)), level='WARNING')
            with mock.patch.object(aws, 'client', return_value=s3):
                aws.poll_source(MemoryStore(), {}, src, since, file_only=True)
        finally:
            if sink is not None: logger.remove(sink)
        self.assertEqual(s3.calls, aws.S3_PAGE_CAP)
        self.assertTrue(any('stopped after' in m for m in seen), seen)


if __name__ == '__main__':
    unittest.main()
