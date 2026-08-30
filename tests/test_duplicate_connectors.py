"""Multiple named instances of every connector type."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from taskuary import outbound
from taskuary.llm import build_llm
from taskuary.reports import resolve_cfg
from taskuary.store import SQLiteStore


class DuplicateConnectors(unittest.TestCase):
    def test_existing_unique_type_database_is_widened_without_changing_ids(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'old.db'
            cx = sqlite3.connect(db)
            cx.executescript('''
                CREATE TABLE connector (ConnectorId INTEGER PRIMARY KEY, Type TEXT UNIQUE, Name TEXT,
                  ConfigJson TEXT, Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT,
                  Roles TEXT, Scope TEXT);
                CREATE TABLE source (SourceId INTEGER PRIMARY KEY, Channel TEXT, Address TEXT,
                  Owner TEXT, ConnectorId INTEGER, Active INTEGER DEFAULT 1, ConfigJson TEXT, LastPolledAt TEXT);
                INSERT INTO connector (ConnectorId, Type, Name, Active) VALUES (77, 'imap', 'Operations mailbox', 1);
                INSERT INTO source (SourceId, Channel, Address, ConnectorId, Active)
                  VALUES (88, 'email', 'ops@example.com', 77, 1);
            ''')
            cx.commit(); cx.close()

            store = SQLiteStore(str(db))
            second = store.save_connector({'Type': 'imap', 'Name': 'Support mailbox'}, 'test')
            self.assertEqual(store.get_source(88)['ConnectorId'], 77)
            self.assertEqual([(c['ConnectorId'], c['Name']) for c in store.connectors_by_type('imap')],
                             [(77, 'Operations mailbox'), (second, 'Support mailbox')])
            store.cx.close()

            # Startup seeds a missing type, not another copy of every existing type.
            reopened = SQLiteStore(str(db))
            self.assertEqual(len(reopened.connectors_by_type('imap')), 2)
            reopened.cx.close()

    def test_report_source_selects_a_specific_connector_instance(self):
        store = SQLiteStore(':memory:')
        first = store.get_connector_by_type('database')['ConnectorId']
        store.save_connector({'ConnectorId': first, 'ConfigJson': json.dumps({'server': 'first'}),
                              'Secret': 'one', 'Active': 1}, 'test')
        second = store.save_connector({'Type': 'database', 'Name': 'Finance database',
                                       'ConfigJson': json.dumps({'server': 'second'}),
                                       'Secret': 'two', 'Active': 1}, 'test')
        cfg = resolve_cfg(store, {'type': 'database', 'connector_id': second, 'query': 'select 1'})
        self.assertEqual((cfg['server'], cfg['password'], cfg['connector_id']), ('second', 'two', second))

    def test_ai_brain_selects_a_specific_connector_instance(self):
        store = SQLiteStore(':memory:')
        first = store.get_connector_by_type('ollama')['ConnectorId']
        store.save_connector({'ConnectorId': first, 'ConfigJson': json.dumps({'model': 'first'}), 'Active': 1}, 'test')
        second = store.save_connector({'Type': 'ollama', 'Name': 'Local reasoning',
                                       'ConfigJson': json.dumps({'model': 'second'}), 'Active': 1}, 'test')
        with mock.patch('taskuary.llm.make_llm', side_effect=lambda typ, cfg, secret: (typ, cfg, secret)):
            typ, cfg, _ = build_llm(store, f'connector:{second}')
        self.assertEqual((typ, cfg['model']), ('ollama', 'second'))

    def test_chat_reply_uses_the_instance_that_owns_the_source(self):
        store = SQLiteStore(':memory:')
        second = store.save_connector({'Type': 'telegram', 'Name': 'Support bot', 'Active': 1,
                                       'Secret': 'support-token'}, 'test')
        store.save_source({'Channel': 'telegram', 'Address': '222', 'ConnectorId': second, 'Active': 1}, 'test')
        msg = {'Channel': 'telegram', 'ConversationId': 'telegram:222'}
        with mock.patch('taskuary.messengers.tg_send', return_value={'ok': True}) as send:
            outbound.reply_to_message(store, msg, 'resolved')
        send.assert_called_once_with(store, '222', 'resolved', second)


if __name__ == '__main__':
    unittest.main()
