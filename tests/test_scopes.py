"""Per-action authority: the read/write/admin ceiling on a connection, and the tool gate."""
import unittest

from taskuary import scopes
from taskuary.store import MemoryStore


class ScopeTableTests(unittest.TestCase):
    def test_levels_are_ordered_and_cumulative(self):
        self.assertLess(scopes.rank('read'), scopes.rank('write'))
        self.assertLess(scopes.rank('write'), scopes.rank('admin'))
        at_admin = scopes.actions_at('admin')
        for s in ('read', 'write'):
            self.assertTrue(set(scopes.actions_at(s)) <= set(at_admin), f'{s} not contained in admin')

    def test_unclassified_action_needs_write_not_read(self):
        """Fail closed: a verb nobody tagged must not sneak through a read-only connection."""
        self.assertEqual(scopes.needs('obliterate_everything'), 'write')
        self.assertFalse(scopes.allows({'Type': 'jira', 'Scope': 'read'}, 'obliterate_everything'))

    def test_remote_code_is_admin_and_a_query_is_not(self):
        self.assertEqual(scopes.needs('winrm'), 'admin')
        self.assertEqual(scopes.needs('mssql'), 'read')
        self.assertEqual(scopes.needs('mcp'), 'write')      # an MCP server exposes anything

    def test_scope_falls_back_to_the_type_default(self):
        self.assertEqual(scopes.scope_of({'Type': 'jira'}), 'read')
        self.assertEqual(scopes.scope_of({'Type': 'winrm'}), 'admin')
        self.assertEqual(scopes.scope_of({'Type': 'jira', 'Scope': 'admin'}), 'admin')
        self.assertEqual(scopes.scope_of({'Type': 'nothing-we-ship'}), 'read')

    def test_new_connectors_start_read_only(self):
        for t in ('clickup', 'todoist', 'dropbox'):
            self.assertEqual(scopes.scope_of({'Type': t}), 'read', t)

    def test_refusal_names_the_dial_and_the_level(self):
        with self.assertRaises(PermissionError) as e:
            scopes.require({'Type': 'clickup', 'Scope': 'read'}, 'delete')
        msg = str(e.exception)
        self.assertIn('admin', msg)
        self.assertIn('clickup', msg)
        self.assertIn('Authority', msg)

    def test_allowed_action_does_not_raise(self):
        scopes.require({'Type': 'clickup', 'Scope': 'write'}, 'comment')
        scopes.require({'Type': 'mssql'}, 'mssql')


class ScopePersistenceTests(unittest.TestCase):
    def test_column_round_trips_and_defaults_stay_null(self):
        s = MemoryStore()
        c = s.get_connector_by_type('jira')
        self.assertIsNone(c.get('Scope'))                     # untouched db keeps the default
        self.assertEqual(scopes.scope_of(c), 'read')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Scope': 'write'}, 't')
        self.assertEqual(scopes.scope_of(s.get_connector_by_type('jira')), 'write')

    def test_reset_returns_a_connection_to_its_default_authority(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('winrm')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Scope': 'read'}, 't')
        self.assertEqual(scopes.scope_of(s.get_connector(cid)), 'read')
        s.reset_connector(cid)
        self.assertEqual(scopes.scope_of(s.get_connector(cid)), 'admin')


if __name__ == '__main__':
    unittest.main()
