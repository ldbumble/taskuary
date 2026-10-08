"""Connector secrets are sealed in the database (vault.py): the column never holds the password as text,
every with_secret read hands back the real one, and an old database's plain secrets are sealed in place."""
import sys, unittest
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
        s.cx.close()
        s = SQLiteStore(path)                                                               # the next start
        self.assertTrue(vault.sealed(self.raw(s, cid)))
        self.assertEqual(s.get_connector(cid, with_secret=True)['Secret'], 'xoxb-plain')
        s.cx.close()

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
