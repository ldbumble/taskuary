"""Discussion #23: a setup wizard, because a fresh install opens on an empty Timeline that looks
exactly like a working install on a quiet morning - and the three things standing between those
two states live on three different tabs with nothing pointing at them.

The checklist is DERIVED, never stored: a step is done when the thing it asks for actually works,
and un-does itself when the connection behind it is removed. A stored checklist would go on
saying "done" after somebody deleted the mailbox.
"""
import unittest

from fastapi.testclient import TestClient
from taskuary import server, setup
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _fresh():
    return MemoryStore()


def _with_ai(s, typ='anthropic', secret='sk-x', active=1):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': secret, 'Active': active}, 't')
    return s


def _with_mailbox(s):
    cid = s.get_connector_by_type('outlook')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
    s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
    return s


def _step(st, key):
    return next(x for x in st['steps'] if x['key'] == key)


class WhatCountsAsSetUpTests(unittest.TestCase):
    def test_a_fresh_install_has_nothing_done_and_says_which_three(self):
        st = setup.state(_fresh())
        self.assertEqual((st['done'], st['total'], st['ready']), (0, 3, False))
        self.assertEqual([x['key'] for x in st['steps'] if not x.get('optional')],
                         ['owner', 'ai', 'inbound'])
        # every step explains ITSELF - "go to Connectors" is navigation, not a reason
        for x in st['steps']:
            self.assertGreater(len(x['why']), 40, f"{x['key']} has no reason to exist")

    def test_the_owner_step_is_not_fooled_by_the_fallback_name(self):
        """store.owner() answers the literal string "the owner" when nothing is set, so a naive
        truthiness check reads a fresh install as done and never sends anybody to the one field
        that signs their mail."""
        s = _fresh()
        self.assertFalse(_step(setup.state(s), 'owner')['done'])
        s.set_setting('owner_name', 'Dana Example', 't')
        self.assertTrue(_step(setup.state(s), 'owner')['done'])
        self.assertEqual(_step(setup.state(s), 'owner')['detail'], 'Dana Example')

    def test_an_ai_card_with_no_key_is_not_a_brain(self):
        s = _fresh()
        _with_ai(s, secret=None, active=1)
        self.assertFalse(_step(setup.state(s), 'ai')['done'])
        _with_ai(s, secret='sk-real')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_local_model_counts_without_a_key(self):
        """Ollama carries no secret, so "has a key" is the wrong test for it - and getting this
        wrong would tell somebody running a local model that they have no AI."""
        s = _fresh()
        cid = s.get_connector_by_type('ollama')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_connector_with_no_source_behind_it_is_only_half_connected(self):
        """It looks done on the Connectors tab and delivers nothing. That is exactly the state a
        checklist exists to catch."""
        s = _fresh()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])
        s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'inbound')['done'])

    def test_a_report_only_connection_is_not_a_funnel(self):
        """AWS brings no work in. Counting it would call an install ready that can never show a
        single message."""
        s = _fresh()
        cid = s.get_connector_by_type('aws')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'k', 'Active': 1}, 't')
        s.save_source({'Channel': 'aws', 'Address': 's3://b', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])

    def test_three_of_three_is_ready_and_the_rest_stay_optional(self):
        s = _fresh()
        s.set_setting('owner_name', 'Dana Example', 't')
        _with_ai(s); _with_mailbox(s)
        st = setup.state(s)
        self.assertEqual((st['done'], st['total'], st['ready']), (3, 3, True))
        self.assertFalse(_step(st, 'agent')['done'])          # optional, and still not done
        self.assertTrue(_step(st, 'agent')['optional'])

    def test_it_un_does_itself_when_a_connection_is_removed(self):
        """The whole reason it is derived rather than stored."""
        s = _fresh()
        _with_ai(s)
        self.assertTrue(_step(setup.state(s), 'ai')['done'])
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 0}, 't')
        self.assertFalse(_step(setup.state(s), 'ai')['done'])


class PuttingItAwayTests(unittest.TestCase):
    def test_dismissing_sticks_and_can_be_undone(self):
        """A checklist you cannot hide is nagging; one you cannot get back is worse."""
        self.assertFalse(c.get('/api/setup').json()['dismissed'])
        self.assertTrue(c.post('/api/setup/dismiss', json={'dismissed': True}).json()['dismissed'])
        self.assertTrue(c.get('/api/setup').json()['dismissed'])      # survives the next read
        self.assertFalse(c.post('/api/setup/dismiss', json={'dismissed': False}).json()['dismissed'])

    def test_dismissing_changes_nothing_about_what_is_actually_done(self):
        before = c.get('/api/setup').json()
        c.post('/api/setup/dismiss', json={'dismissed': True})
        after = c.get('/api/setup').json()
        c.post('/api/setup/dismiss', json={'dismissed': False})
        self.assertEqual((before['done'], before['ready']), (after['done'], after['ready']))

    def test_the_endpoint_answers_the_same_shape_the_panel_reads(self):
        d = c.get('/api/setup').json()
        for k in ('steps', 'done', 'total', 'ready', 'dismissed'):
            self.assertIn(k, d)
        for x in d['steps']:
            for k in ('key', 'title', 'why', 'done', 'where'):
                self.assertIn(k, x)


if __name__ == '__main__':
    unittest.main()
