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

    # ...AND ONE IT DOES NOT DECLARE IS SEALED BY ITS SHAPE (red team #3): an MCP card's headers, a local server's env, a dsn, a webhook
    # address sat in the column as text. Sealed at rest; every read the card's own code makes still gets the value.
    SHAPES = {'url': 'https://mcp.vendor.example/v1', 'headers': {'Authorization': 'Bearer hb-invented', 'X-Team': 'ops'},
              'env': {'API_KEY': 'ek-invented'}, 'conn_str': 'Server=db.example;Pwd=cs-invented', 'dsn': 'postgres://u:dp-invented@db.example/x',
              'cookie': 'sid=ck-invented', 'passphrase': 'pp-invented', 'webhook_url': 'https://hooks.example/wh-invented',
              'apiKey': 'ak-invented', 'accessToken': 'at-invented', 'nested': {'auth': {'client_secret': 'ns-invented'}},
              'callback': 'https://ops:cb-invented@hooks.example/x', 'region': 'eu', 'retries': 3}

    def test_a_secret_shaped_field_its_card_does_not_declare_is_sealed_at_rest_and_still_reads(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'mcp', 'Name': 'Tools', 'ConfigJson': json.dumps(self.SHAPES)}, 'o')
        raw = json.dumps(self.cfg_raw(s, cid))
        self.assertNotIn('-invented', raw)
        self.assertEqual((self.cfg_raw(s, cid)['region'], self.cfg_raw(s, cid)['url']), ('eu', self.SHAPES['url']))
        self.assertEqual(json.loads(s.get_connector(cid, with_secret=True)['ConfigJson']), self.SHAPES)
        self.assertEqual(json.loads(s.get_connector(cid)['ConfigJson']), self.SHAPES)          # ...a plain read too: it was text before
        self.assertEqual(json.loads(next(r for r in s.list_connectors() if r['ConnectorId'] == cid)['ConfigJson']), self.SHAPES)
        before = self.cfg_raw(s, cid)
        s.save_connector({'ConnectorId': cid, 'ConfigJson': s.get_connector(cid)['ConfigJson']}, 'o')
        self.assertEqual(self.cfg_raw(s, cid), before)                                       # a save of what it read keeps each seal

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


class OwnerTokenTests(unittest.TestCase):
    """Red team F2: config.toml held the owner token as text, so a session that read it - by file://, or by loading this package - became
    the owner. On disk it is sealed; the owner's own processes open it, a session's never does, and a task's proof makes it an agent's call."""
    setUp = VaultTests.setUp

    def home(self):
        import os, tempfile
        from pathlib import Path
        from taskuary import config
        d = Path(tempfile.mkdtemp()); p = mock.patch.object(config, 'home', return_value=d); p.start(); self.addCleanup(p.stop)
        (d / 'config.toml').write_text('[server]\ntoken = "owner-plain-token"\nagent_token = "agent-tok"\n', encoding='utf-8')
        e = mock.patch.dict(os.environ); e.start(); self.addCleanup(e.stop)
        os.environ.pop('TASKUARY_TOKEN', None)
        return d

    def test_the_token_lives_in_the_servers_memory_alone_and_the_old_one_is_deleted_and_refused(self):
        """The owner, 2026-11-25: sealed on disk it was still a file the OS opens for any process of his account. Minted at each start, it
        is written nowhere; one an older build stored, sealed or plain, is taken off config.toml and refused."""
        from taskuary import config, guard
        d = self.home()
        (d / 'config.toml').write_text(f'[server]\ntoken = "{vault.seal("owner-old-token")}"\nagent_token = "agent-tok"\n', encoding='utf-8')
        with mock.patch.dict(config._LIVE, clear=True):
            srv = config.load()['server']
            tok = srv['token']
            self.assertTrue(tok); self.assertNotEqual(tok, 'owner-old-token')
            self.assertEqual(config.load()['server']['token'], tok, 'one token for the whole run')
            config.save(config.load())
            for f in (p for p in d.rglob('*') if p.is_file()): self.assertNotIn(tok.encode(), f.read_bytes(), f)
            disk = (d / 'config.toml').read_text(encoding='utf-8')
            self.assertNotIn('token =', disk.replace('agent_token =', '')); self.assertIn('agent-tok', disk)
            self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'owner-old-token'}), guard.ANON)
            self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': tok}), guard.OWNER)
        with mock.patch.dict(config._LIVE, clear=True): self.assertNotEqual(config.load()['server']['token'], tok, 'a restart mints another')

    def test_where_no_keychain_seals_it_the_file_is_his_alone_and_no_backup_carries_a_token(self):
        """Red team #2, T3: on Linux/mac with no keychain the vault is plain - config.toml was left 0644 by every save but a token's (an atomic
        replace takes the temp file's mode), and config.before-cli-connections.toml, a copy taken before a migration, held both tokens in clear."""
        import os, stat
        from taskuary import config
        d = self.home()
        with mock.patch.dict(os.environ, {'TASKUARY_VAULT': 'plain'}):
            config.load(); config.save({'agents': {'coding': {'kind': 'coding'}}, 'github': {'token': 'ghp-plain', 'default_repo': 'northwind/ledger'}})
            if os.name != 'nt': self.assertEqual(stat.S_IMODE((d / 'config.toml').stat().st_mode), 0o600)
            config.backup('config.before-cli-connections.toml')
        b = d / 'config.before-cli-connections.toml'
        kept = b.read_text(encoding='utf-8')
        for secret in ('owner-plain-token', 'agent-tok', 'ghp-plain'): self.assertNotIn(secret, kept)
        self.assertIn('northwind/ledger', kept)                                     # ...the rest of it is there to go back to
        if os.name != 'nt': self.assertEqual(stat.S_IMODE(b.stat().st_mode), 0o600)

    def test_a_sessions_process_never_opens_it(self):
        import os
        from taskuary import config
        self.home(); config.load()
        os.environ['TASKUARY_TASK'] = '7'
        self.assertNotEqual(config.load()['server']['token'], 'owner-plain-token')

    def test_the_owners_token_with_a_tasks_proof_is_an_agents_call(self):
        from taskuary import guard
        srv = {'token': 'owner-plain-token', 'agent_token': 'agent-tok'}
        self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'owner-plain-token'}), guard.OWNER)
        stolen = {'X-Taskuary-Token': 'owner-plain-token', guard.TASK_HDR: guard.task_proof(srv, 7)}
        self.assertEqual(guard.scope_of(srv, stolen), guard.AGENT)
