"""Connector secrets are sealed in the database (vault.py): the column never holds the password as text,
every with_secret read hands back the real one, and an old database's plain secrets are sealed in place."""
import json, sys, unittest
from unittest import mock
from taskuary import vault
from taskuary.store import MemoryStore


class FakeKeyring:
    def __init__(self): self.d = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


class VaultTests(unittest.TestCase):
    def setUp(self):
        # every test seals somewhere real: DPAPI on Windows, an in-memory keyring elsewhere
        self.kr = FakeKeyring()
        if sys.platform != 'win32':
            p = mock.patch.object(vault, '_keyring', return_value=self.kr); p.start(); self.addCleanup(p.stop)

    def raw(self, s, cid): return s._one('SELECT Secret FROM connector WHERE ConnectorId=?', (cid,))['Secret']

    def test_the_column_holds_it_sealed_and_a_with_secret_read_hands_back_the_real_one(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'imap', 'Name': 'Mail', 'Secret': 'hunter2 ünïcode', 'Active': 1}, 'o')
        self.assertTrue(vault.sealed(self.raw(s, cid)))
        self.assertNotIn('hunter2', self.raw(s, cid))
        self.assertEqual(s.get_connector(cid, with_secret=True)['Secret'], 'hunter2 ünïcode')
        self.assertEqual([r['Secret'] for r in s.connectors_by_type('imap', with_secret=True) if r['ConnectorId'] == cid], ['hunter2 ünïcode'])
        self.assertEqual(s.get_connector_by_type('imap', with_secret=True)['Secret'], 'hunter2 ünïcode')
        self.assertNotIn('Secret', s.get_connector(cid))                      # still write-only without with_secret
        s.save_connector({'ConnectorId': cid, 'Secret': 'rotated'}, 'o')       # a new password replaces the old
        self.assertEqual(s.get_connector(cid, with_secret=True)['Secret'], 'rotated')

    def test_an_old_databases_plain_secrets_are_sealed_at_startup(self):
        import os, tempfile
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'old.db')
        s = SQLiteStore(path)
        cid = s.save_connector({'Type': 'slack', 'Name': 'Chat'}, 'o')
        s._exec('UPDATE connector SET Secret=? WHERE ConnectorId=?', ('xoxb-plain', cid))   # what a database from before holds
        s.close()
        s = SQLiteStore(path)                                                               # the next start
        self.assertTrue(vault.sealed(self.raw(s, cid)))
        self.assertEqual(s.get_connector(cid, with_secret=True)['Secret'], 'xoxb-plain')
        s.close()

    def test_a_secret_that_cannot_be_opened_here_is_empty_never_ciphertext(self):
        self.assertEqual(vault.unseal('vault:dpapi:AAAA'), '')
        self.assertEqual(vault.unseal('vault:keyring:gone'), '')
        self.assertEqual(vault.unseal('plain stays plain'), 'plain stays plain')
        self.assertIsNone(vault.seal(None)); self.assertEqual(vault.seal(''), '')

    def test_plain_mode_turns_sealing_off(self):
        with mock.patch.dict('os.environ', {'TASKUARY_VAULT': 'plain'}):
            self.assertEqual(vault.seal('x'), 'x')

    def test_remove_connection_forgets_a_keychain_entry(self):
        with mock.patch.object(vault, 'mode', return_value='keyring'), mock.patch.object(vault, '_keyring', return_value=self.kr):
            s = MemoryStore()
            cid = s.save_connector({'Type': 'imap', 'Name': 'Mail', 'Secret': 'pw'}, 'o')
            self.assertEqual(len(self.kr.d), 1)
            s.reset_connector(cid)
            self.assertEqual(self.kr.d, {})

    # A SECRET A CARD KEEPS IN ITS CONFIG (an app's client secret, a sender password) sat in ConfigJson as text beside a sealed Secret.
    # What is sealed is what the card declares (connectorcatalog.json `secret_config`), never a key's name.
    def cfg_raw(self, s, cid): return json.loads(s._one('SELECT ConfigJson FROM connector WHERE ConnectorId=?', (cid,))['ConfigJson'])

    def test_a_declared_secret_config_field_is_sealed_on_save_and_opens_on_a_with_secret_read(self):
        from taskuary import connectorcatalog, guard, reports
        self.assertIn('sender_password', connectorcatalog.secret_keys('intacct'))
        s = MemoryStore()
        cfg = {'sender_id': 'nw-sender', 'sender_password': 'sp-invented-1', 'user_id': 'ws_user', 'company_id': 'northwind'}
        cid = s.save_connector({'Type': 'intacct', 'Name': 'Books', 'ConfigJson': json.dumps(cfg), 'Secret': 'up-invented'}, 'o')
        raw = self.cfg_raw(s, cid)
        self.assertTrue(vault.sealed(raw['sender_password'])); self.assertNotIn('sp-invented-1', json.dumps(raw))
        self.assertEqual({k: v for k, v in raw.items() if k != 'sender_password'}, {k: v for k, v in cfg.items() if k != 'sender_password'})
        self.assertEqual(json.loads(s.get_connector(cid, with_secret=True)['ConfigJson']), cfg)        # the connector still works
        self.assertEqual(reports.intacct_connection(s, cid)['sender_password'], 'sp-invented-1')
        # ...and the page shows it saved, never the value
        shown = guard.masked_config(s.get_connector(cid))
        self.assertNotIn('sender_password', json.loads(shown['ConfigJson'])); self.assertIn('sender_password', shown['ConfigSaved'])
        # a save from a with_secret read keeps the same seal; a value merged in later is sealed too
        s.save_connector({'ConnectorId': cid, 'ConfigJson': s.get_connector(cid, with_secret=True)['ConfigJson']}, 'o')
        self.assertEqual(self.cfg_raw(s, cid)['sender_password'], raw['sender_password'])
        s.merge_connector_config(cid, {'sender_password': 'sp-invented-2'})
        self.assertTrue(vault.sealed(self.cfg_raw(s, cid)['sender_password']))
        self.assertEqual(json.loads(s.get_connector(cid, with_secret=True)['ConfigJson'])['sender_password'], 'sp-invented-2')

    def test_a_field_its_card_does_not_declare_secret_stays_plain_whatever_its_name(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'intacct', 'Name': 'Books', 'ConfigJson': json.dumps({'entity_id': 'E1', 'client_secret': 'not-declared-here'})}, 'o')
        self.assertEqual(self.cfg_raw(s, cid), {'entity_id': 'E1', 'client_secret': 'not-declared-here'})

    def test_an_old_databases_plain_secret_config_is_sealed_once_at_startup(self):
        import os, tempfile
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'old.db')
        s = SQLiteStore(path)
        cid = s.save_connector({'Type': 'linkedin', 'Name': 'Social'}, 'o')
        old = {'client_id': 'app-1', 'client_secret': 'cs-invented'}
        s._exec('UPDATE connector SET ConfigJson=? WHERE ConnectorId=?', (json.dumps(old), cid))       # what a database from before holds
        s.close()
        s = SQLiteStore(path)                                                                           # the next start seals it
        first = self.cfg_raw(s, cid)
        self.assertTrue(vault.sealed(first['client_secret'])); self.assertEqual(first['client_id'], 'app-1')
        self.assertEqual(json.loads(s.get_connector(cid, with_secret=True)['ConfigJson']), old)
        s.close()
        s = SQLiteStore(path)                                                                           # ...and the one after leaves it be
        self.assertEqual(self.cfg_raw(s, cid), first)
        s.close()
