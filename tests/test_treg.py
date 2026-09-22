"""treg: searching the catalogue is free, calling it is always the owner's click.

The catalogue is ~3,600 endpoints behind one card. Two properties have to hold or the card is a
hole rather than a door: an agent must be able to LOOK without spending or approval, and it must
never be able to CALL - because that door spends real money and reaches endpoints that publish,
post and place orders.
"""
import unittest
from unittest import mock

from taskuary import scopes, treg
from taskuary.reports import CARD_OF, REGISTRY


class TheLadder(unittest.TestCase):
    def test_looking_is_a_read_and_calling_is_a_write(self):
        self.assertEqual(scopes.ACTIONS['treg_tools'], 'read')
        self.assertEqual(scopes.ACTIONS['treg_search'], 'read')
        self.assertEqual(scopes.ACTIONS['treg_call'], 'write')
        self.assertEqual(scopes.DEFAULT_SCOPE['treg'], 'read')

    def test_at_its_default_scope_an_agent_may_search_but_never_call(self):
        card = {'Type': 'treg', 'Scope': scopes.DEFAULT_SCOPE['treg']}
        scopes.require(card, 'treg_search')          # free, changes nothing
        scopes.require(card, 'treg_tools')
        with self.assertRaises(PermissionError):     # spends money, may publish
            scopes.require(card, 'treg_call')

    def test_all_three_resolve_to_the_card(self):
        for t in ('treg_tools', 'treg_search', 'treg_call'):
            self.assertIn(t, REGISTRY)
            self.assertEqual(CARD_OF[t], 'treg')


class TheCall(unittest.TestCase):
    def test_a_call_always_carries_a_cost_ceiling(self):
        """treg applies no default cap: X-Treg-Route-Max-Cost is the only thing between a retry
        loop and a bill, so max_cost is never absent."""
        with mock.patch.object(treg, '_one', return_value='{}') as one:
            treg.run_treg_call({'token': 't', 'endpoint': 'hunter.x.domain-finder'})
        payload = one.call_args[0][2]
        self.assertEqual(payload['max_cost'], treg.DEFAULT_MAX_COST)
        self.assertTrue(float(payload['max_cost']) > 0)

    def test_the_owner_can_raise_the_ceiling(self):
        with mock.patch.object(treg, '_one', return_value='{}') as one:
            treg.run_treg_call({'token': 't', 'endpoint': 'x.y', 'max_cost': '2.50'})
        self.assertEqual(one.call_args[0][2]['max_cost'], '2.50')

    def test_search_asks_for_the_job_not_the_vendor(self):
        with self.assertRaises(ValueError) as e:
            treg.run_treg_search({'token': 't'})
        self.assertIn('capability', str(e.exception))

    def test_a_call_needs_an_endpoint_id(self):
        with self.assertRaises(ValueError):
            treg.run_treg_call({'token': 't'})

    def test_no_token_says_where_to_get_one(self):
        with self.assertRaises(RuntimeError) as e:
            treg.tools({})
        self.assertIn('treg.to', str(e.exception))

    def test_args_may_arrive_as_json_text(self):
        with mock.patch.object(treg, '_one', return_value='{}') as one:
            treg.run_treg_call({'token': 't', 'endpoint': 'x.y', 'args': '{"domain": "example.com"}'})
        self.assertEqual(one.call_args[0][2]['params'], {'domain': 'example.com'})

    def test_the_card_url_is_a_connection_key_not_an_argument(self):
        """An agent must not be able to point the card's token at a host of its choosing."""
        from taskuary import reports
        self.assertIn('url', reports.CONNECTION_KEYS)
        self.assertIn('token', reports.CONNECTION_KEYS)


if __name__ == '__main__':
    unittest.main()
