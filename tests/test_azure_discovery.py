"""Azure discovery must walk every subscription, following ARM's nextLink - it once stopped at five."""
import unittest
from unittest import mock

from taskuary import azure
from taskuary.store import MemoryStore

SIDS = [f'sub-{i}' for i in range(7)]
NEXT = f'{azure.ARM}/subscriptions?api-version=2022-12-01&$skiptoken=page-2'


class Resp:
    def __init__(self, j): self.j = j
    def json(self): return self.j


def fake_get(calls):
    def get(url, tok, params=None, **kw):
        calls.append((url, params))
        if url == f'{azure.ARM}/subscriptions':
            return Resp({'value': [{'subscriptionId': s} for s in SIDS[:4]], 'nextLink': NEXT})
        if url == NEXT: return Resp({'value': [{'subscriptionId': s} for s in SIDS[4:]]})
        sid = url.split('/subscriptions/')[1].split('/')[0]
        if url.endswith('/workspaces'):
            return Resp({'value': [{'name': f'ws-{sid}', 'properties': {'customerId': f'cid-{sid}'}}]})
        return Resp({'value': []})
    return get


class AzureDiscoveryTests(unittest.TestCase):
    def test_all_seven_subscriptions_are_read_across_pages(self):
        calls, store = [], MemoryStore()
        with mock.patch.object(azure, 'token', return_value='tok'), \
             mock.patch.object(azure, '_get', side_effect=fake_get(calls)):
            out = azure.discover(store, {}, connector_id=1)

        self.assertEqual(out, {'found': 7, 'added': 7})
        self.assertEqual({s['Address'] for s in store.list_sources(active_only=False) if s['Channel'] == 'azure'},
                         {f'law://ws-{s}' for s in SIDS})
        # the second page is fetched by its own URL - api-version rides in nextLink, not twice
        self.assertIn((NEXT, None), calls)

    def test_the_connection_check_counts_every_page(self):
        with mock.patch.object(azure, 'token', return_value='tok'), \
             mock.patch.object(azure, '_get', side_effect=fake_get([])):
            self.assertIn('7 subscription(s)', azure.test({})['detail'])


if __name__ == '__main__':
    unittest.main()
