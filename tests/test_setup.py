"""Discussion #23: a setup wizard, because a fresh install opens on an empty Timeline that looks
exactly like a working install on a quiet morning - and the three things standing between those
two states live on three different tabs with nothing pointing at them.

The checklist is DERIVED, never stored: a step is done when the thing it asks for actually works,
and un-does itself when the connection behind it is removed. A stored checklist would go on
saying "done" after somebody deleted the mailbox.
"""
import json
import unittest
from unittest import mock

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


class TheWizardActuallySetsUpTests(unittest.TestCase):
    """Pointing at a tab is not setting up: it hands the work back with directions attached. These
    walk the exact calls the panel makes and check the state moves - because a wizard that saves a
    key without testing it leaves you with a connected-looking install and an empty Timeline."""
    def _reset(self):
        for conn in server.store.list_connectors():      # not `c` - that is the TestClient
            if conn['Type'] in ('anthropic', 'gmail'):
                server.store.save_connector({'ConnectorId': conn['ConnectorId'], 'Active': 0, 'Secret': ''}, 't')

    def test_the_owner_step_writes_the_name_the_documents_use(self):
        was = server.store.owner().get('owner')
        try:
            self.assertEqual(c.put('/api/owner', json={'name': 'Dana Example',
                                                       'email': 'dana@example.org'}).status_code, 200)
            self.assertTrue(_step(c.get('/api/setup').json(), 'owner')['done'])
            self.assertEqual(server.store.owner()['owner_first'], 'Dana')   # what signs a reply
        finally:
            if was and was != 'the owner': c.put('/api/owner', json={'name': was})

    def test_connecting_a_brain_saves_it_and_only_counts_once_it_answers(self):
        """The test call is the point. A key that saved and does not work is exactly the state
        somebody discovers days later from a Timeline that never triaged anything."""
        self._reset()
        cid = server.store.get_connector_by_type('anthropic')['ConnectorId']
        r = c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'anthropic',
                                            'Name': 'Anthropic', 'Secret': 'sk-test', 'Active': True})
        self.assertEqual(r.status_code, 200)
        with mock.patch('taskuary.llm.test_ai', return_value='model responded: ok'):
            out = c.post(f'/api/connectors/{cid}/test', json={}).json()
        self.assertTrue(out['ok'], out)
        self.assertTrue(_step(c.get('/api/setup').json(), 'ai')['done'])

    def test_a_wrong_key_is_reported_and_leaves_the_step_undone(self):
        self._reset()
        cid = server.store.get_connector_by_type('anthropic')['ConnectorId']
        c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'anthropic', 'Name': 'Anthropic',
                                        'Secret': 'sk-wrong', 'Active': True})
        with mock.patch('taskuary.llm.test_ai', side_effect=RuntimeError('401 invalid x-api-key')):
            out = c.post(f'/api/connectors/{cid}/test', json={}).json()
        self.assertFalse(out['ok'])
        self.assertIn('401', out['detail'])          # the panel shows this verbatim
        self._reset()

    def test_connecting_a_mailbox_registers_the_source_that_makes_it_a_funnel(self):
        """A connector with no source behind it is half-connected. The IMAP test is what registers
        the mailbox, which is why the wizard tests rather than just saving."""
        self._reset()
        cid = server.store.get_connector_by_type('gmail')['ConnectorId']
        c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'gmail', 'Name': 'Gmail',
                                        'Secret': 'app-password',
                                        'ConfigJson': json.dumps({'address': 'dana@gmail.com'}),
                                        'Active': True})
        self.assertFalse(any(s['Channel'] == 'email' and s['Address'] == 'dana@gmail.com'
                             for s in server.store.list_sources(active_only=False)))
        with mock.patch('taskuary.imapmail.test_imap', return_value='logged in as dana@gmail.com') as t:
            def _register(store, conn):
                store.save_source({'Channel': 'email', 'Address': 'dana@gmail.com',
                                   'ConnectorId': conn['ConnectorId'], 'Active': 1}, 'connector-test')
                return 'logged in as dana@gmail.com'
            t.side_effect = _register
            self.assertTrue(c.post(f'/api/connectors/{cid}/test', json={}).json()['ok'])
        self.assertTrue(_step(c.get('/api/setup').json(), 'inbound')['done'])
        self._reset()


if __name__ == '__main__':
    unittest.main()
