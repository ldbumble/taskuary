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
        self.assertEqual(s3.calls, [
            {'Bucket': 'reports', 'MaxKeys': 200, 'Prefix': 'reports/2026/'},
            {'Bucket': 'reports', 'MaxKeys': 200, 'Prefix': 'reports/2026/',
             'ContinuationToken': 'page-2'},
        ])


if __name__ == '__main__':
    unittest.main()
