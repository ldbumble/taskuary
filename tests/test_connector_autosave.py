"""Every field on a connection card saves itself, and only itself; Remove is one press (the owner, 2026-11-05).

"what saves with one click while other hit the save buttons. it's just confusing" - a field's save posts the keys it changed
(ConfigPatch) and the server merges them over the config as it is NOW (store.merge_config), so a poller's watermark written between
the page's read and the owner's edit survives it (#242). Remove takes a card added beside another of its kind off the list whole."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import guard, server
from taskuary.store import MemoryStore


class FieldSaves(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tg = self.s.get_connector_by_type('telegram')['ConnectorId']
        self.s.save_connector({'ConnectorId': self.tg, 'Secret': 'bot-token', 'ConfigJson': json.dumps({'poll_seconds': 30})}, 'test')

    def cfg(self, cid): return json.loads(self.s.get_connector(cid)['ConfigJson'])

    def test_a_field_save_leaves_the_pollers_watermark_and_every_other_key_alone(self):
        # the page read the card, then the poller moved its offset, then the owner changed one box
        self.s.set_connector_config(self.tg, {'poll_seconds': 30, 'tg_offset': 4711, 'bot_username': 'northwind_bot'})
        r = self.c.post('/api/connectors', json={'ConnectorId': self.tg, 'ConfigPatch': {'poll_seconds': 60}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.cfg(self.tg), {'poll_seconds': 60, 'tg_offset': 4711, 'bot_username': 'northwind_bot'})
        self.assertTrue(self.s.get_connector(self.tg)['HasSecret'])                  # the sign-in is not touched by a field

    def test_a_key_sent_as_null_is_removed_and_nothing_else_is(self):
        self.s.set_connector_config(self.tg, {'poll_seconds': 30, 'tg_offset': 9, 'chat_hint': 'x'})
        self.c.post('/api/connectors', json={'ConnectorId': self.tg, 'ConfigPatch': {'chat_hint': None}})
        self.assertEqual(self.cfg(self.tg), {'poll_seconds': 30, 'tg_offset': 9})

    def test_a_roles_save_beside_a_patch_saves_both_and_the_config_is_merged(self):
        self.s.set_connector_config(self.tg, {'tg_offset': 12})
        self.c.post('/api/connectors', json={'ConnectorId': self.tg, 'Roles': 'trigger', 'ConfigPatch': {'mode': 'tasks'}})
        self.assertEqual((self.s.get_connector(self.tg)['Roles'], self.cfg(self.tg)), ('trigger', {'tg_offset': 12, 'mode': 'tasks'}))

    def test_a_blank_write_only_key_keeps_the_stored_secret(self):
        li = self.s.get_connector_by_type('linkedin')['ConnectorId']
        key = guard.WRITE_ONLY_CONFIG['linkedin'][0]
        self.s.set_connector_config(li, {key: 'kept-secret', 'client_id': 'app-1'})
        self.c.post('/api/connectors', json={'ConnectorId': li, 'ConfigPatch': {key: '', 'client_id': 'app-2'}})
        self.assertEqual(json.loads(self.s.get_connector(li, with_secret=True)['ConfigJson']), {key: 'kept-secret', 'client_id': 'app-2'})

    def test_a_sealed_key_saved_by_patch_is_sealed_in_the_row(self):
        gm = self.s.get_connector_by_type('gmail')['ConnectorId']
        k = self.s.SEALED_CONFIG[0]
        with mock.patch('taskuary.vault.seal', side_effect=lambda v: f'sealed:{v}'), \
             mock.patch('taskuary.vault.sealed', side_effect=lambda v: str(v).startswith('sealed:')):
            self.c.post('/api/connectors', json={'ConnectorId': gm, 'ConfigPatch': {k: 'refresh-1', 'address': 'alex@northwind.example'}})
        raw = json.loads(self.s._one('SELECT ConfigJson FROM connector WHERE ConnectorId=?', (gm,))['ConfigJson'])
        self.assertEqual(raw, {k: 'sealed:refresh-1', 'address': 'alex@northwind.example'})

    def test_a_patch_is_refused_beside_a_whole_config_or_for_a_new_card(self):
        post = lambda body: self.c.post('/api/connectors', json=body).status_code
        self.assertEqual(post({'ConnectorId': self.tg, 'ConfigJson': '{}', 'ConfigPatch': {'a': 1}}), 422)
        self.assertEqual(post({'Type': 'telegram', 'Name': 'Second bot', 'ConfigPatch': {'a': 1}}), 422)
        self.assertEqual(post({'ConnectorId': 99999, 'ConfigPatch': {'a': 1}}), 404)

    def test_a_source_field_save_keeps_its_watermark(self):
        sid = self.s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'Active': 1,
                                  'ConfigJson': json.dumps({'folders': ['Inbox'], 'delta': 'cursor-7'})}, 'test')
        r = self.c.post('/api/sources', json={'SourceId': sid, 'ConfigPatch': {'folders': ['Inbox', 'Projects']}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads(self.s.get_source(sid)['ConfigJson']), {'folders': ['Inbox', 'Projects'], 'delta': 'cursor-7'})


class RemoveIsOnePress(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_a_second_card_is_gone_in_one_call_and_undo_puts_it_back_whole(self):
        cid = self.s.save_connector({'Type': 'imap', 'Name': 'Work mail', 'Active': 1, 'Secret': 'app-password',
                                     'ConfigJson': json.dumps({'address': 'alex@northwind.example'})}, 'test')
        before = self.s.get_connector(cid)
        out = self.c.post(f'/api/connectors/{cid}/reset').json()
        self.assertTrue(out['ok'] and out['gone'])
        self.assertIsNone(self.s.get_connector(cid))
        self.assertNotIn(cid, [c['ConnectorId'] for c in self.c.get('/api/connectors').json()['data']])
        self.c.post(f"/api/deleted/{out['deleted']}/restore")
        self.assertEqual(self.s.get_connector(cid), before)

    def test_the_last_card_of_its_kind_is_wiped_back_to_the_catalogues_blank_one(self):
        cid = self.s.get_connector_by_type('imap')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'app-password',
                               'ConfigJson': json.dumps({'address': 'alex@northwind.example'})}, 'test')
        out = self.c.post(f'/api/connectors/{cid}/reset').json()
        c = self.s.get_connector(cid)
        self.assertFalse(out['gone'])
        self.assertEqual((c['HasSecret'], c['Active'], c['ConfigJson']), (0, 0, None))


if __name__ == '__main__': unittest.main()
