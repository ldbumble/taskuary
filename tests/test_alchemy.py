"""Alchemy's documented response shapes and the report/connection wiring."""

import json
import unittest
from unittest import mock

from taskuary import alchemy, channels, reports, scopes
from taskuary.store import MemoryStore


def response(body, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = body
    return r


class AlchemyReports(unittest.TestCase):
    def test_prices_are_rows_and_the_key_stays_out_of_output(self):
        payload = {'data': [{'symbol': 'ETH', 'prices': [
            {'currency': 'USD', 'value': '3000.00', 'lastUpdatedAt': '2026-09-18T10:00:00Z'}], 'error': None}]}
        with mock.patch.object(alchemy.requests, 'request', return_value=response(payload)) as send:
            head, body = alchemy.run_alchemy_prices({'api_key': 'private-key', 'symbols': 'ETH'})
        self.assertEqual(head, '1 prices')
        self.assertEqual(json.loads(body), {'symbol': 'ETH', 'currency': 'USD', 'price': 3000.0,
                                            'updated': '2026-09-18T10:00:00Z', 'error': None})
        self.assertEqual(send.call_args.kwargs['params'], {'symbols': 'ETH'})
        self.assertNotIn('private-key', body)

    def test_wallet_paginates_and_converts_hex_atomic_balances(self):
        token = {'address': '0xabc', 'network': 'eth-mainnet', 'tokenAddress': None,
                 'tokenBalance': '0xde0b6b3a7640000',
                 'tokenMetadata': {'decimals': 18, 'symbol': 'ETH', 'name': 'Ethereum'},
                 'tokenPrices': [{'currency': 'usd', 'value': '3000'}]}
        pages = [response({'data': {'tokens': [token], 'pageKey': 'next'}}),
                 response({'data': {'tokens': [], 'pageKey': None}})]
        with mock.patch.object(alchemy.requests, 'request', side_effect=pages) as send:
            head, body = alchemy.run_alchemy_wallet({'api_key': 'private-key', 'address': '0xabc',
                                                    'networks': 'eth-mainnet,base-mainnet'})
        self.assertEqual(head, '1 tokens')
        row = json.loads(body)
        self.assertEqual(row['balance'], '1')
        self.assertEqual(row['value_usd'], 3000.0)
        self.assertEqual(send.call_args_list[1].kwargs['json']['pageKey'], 'next')
        self.assertEqual(send.call_args_list[0].kwargs['json']['addresses'][0]['networks'],
                         ['eth-mainnet', 'base-mainnet'])

    def test_partial_network_failure_is_not_reported_as_complete(self):
        partial = {'data': {'tokens': []}, 'error': {'partialErrors': [
            {'network': 'base-mainnet', 'message': 'Internal server error'}]}}
        with mock.patch.object(alchemy.requests, 'request', return_value=response(partial)):
            with self.assertRaisesRegex(alchemy.AlchemyError, 'incomplete: base-mainnet'):
                alchemy.run_alchemy_wallet({'api_key': 'key', 'address': '0xabc'})

    def test_token_metadata_failure_stays_visible_without_guessing_a_balance(self):
        token = {'network': 'eth-mainnet', 'tokenAddress': '0x123', 'tokenBalance': '0x10',
                 'error': 'metadata unavailable'}
        with mock.patch.object(alchemy.requests, 'request', return_value=response({'data': {'tokens': [token]}})):
            _, body = alchemy.run_alchemy_wallet({'api_key': 'key', 'address': '0xabc'})
        row = json.loads(body)
        self.assertIsNone(row['balance'])
        self.assertEqual(row['raw_balance'], '0x10')
        self.assertEqual(row['error'], 'metadata unavailable')

    def test_missing_key_and_http_error_do_not_expose_secret(self):
        with self.assertRaisesRegex(alchemy.AlchemyError, 'Connections -> Alchemy'):
            alchemy.run_alchemy_prices({})
        with mock.patch.object(alchemy.requests, 'request', return_value=response({'message': 'bad key'}, 401)):
            with self.assertRaises(alchemy.AlchemyError) as ctx:
                alchemy.run_alchemy_prices({'api_key': 'private-key'})
        self.assertNotIn('private-key', str(ctx.exception))

    def test_both_types_are_registered_as_reads_on_one_card(self):
        for kind in ('alchemy_prices', 'alchemy_wallet'):
            self.assertIn(kind, reports.REGISTRY)
            self.assertEqual(reports.card_of(kind), 'alchemy')
            self.assertIn(kind, reports.CONNECTION_OF)
            self.assertEqual(scopes.ACTIONS[kind], 'read')
        self.assertEqual(scopes.DEFAULT_SCOPE['alchemy'], 'read')

    def test_new_store_seeds_the_finance_card(self):
        store = MemoryStore()
        try:
            cards = store.connectors_by_type('alchemy')
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]['Roles'], 'report,tool')
        finally:
            store.close()

    def test_connection_test_uses_saved_key_and_records_result(self):
        store = MemoryStore()
        try:
            cid = store.connectors_by_type('alchemy')[0]['ConnectorId']
            store.save_connector({'ConnectorId': cid, 'Secret': 'private-key'}, 'test')
            with mock.patch.object(alchemy, 'probe', return_value='1 prices - ETH 3000 USD') as probe:
                result = channels.test_connector(store, cid)
            self.assertTrue(result['ok'])
            self.assertIn('ETH 3000 USD', result['detail'])
            probe.assert_called_once_with({'api_key': 'private-key'})
            self.assertIsNone(store.get_connector(cid)['LastError'])
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
