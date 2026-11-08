"""AN OBSIDIAN VAULT (obsidian.py): read where it lies, inside the vault only - never its .obsidian folder, its .trash, or a path out."""
import json, tempfile, unittest
from pathlib import Path

from taskuary import channels, obsidian, reports, scopes
from taskuary.store import MemoryStore


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.v = root / 'Vault'
        for rel, text in {'Inbox.md': 'call Erin about the budget', 'Projects/Q3.md': '# Q3\nship the ledger export', '.obsidian/app.md': 'budget',
                          '.trash/old.md': 'budget draft', 'Projects/img.png': 'x'}.items():
            (self.v / rel).parent.mkdir(parents=True, exist_ok=True); (self.v / rel).write_text(text, encoding='utf-8')
        (root / 'secret.md').write_text('budget outside the vault', encoding='utf-8')
    def tearDown(self): self.tmp.cleanup()

    def test_lists_finds_and_reads_inside_the_vault_only(self):
        head, body = obsidian.run({'vault': str(self.v)})
        self.assertEqual((head, sorted(r['note'] for r in json.loads(body))), ('Obsidian: 2 notes', ['Inbox.md', 'Projects/Q3.md']))
        head, body = obsidian.run({'vault': str(self.v), 'search': 'Budget'})
        self.assertEqual([r['note'] for r in json.loads(body)], ['Inbox.md']); self.assertIn('call Erin', json.loads(body)[0]['around'])
        self.assertEqual(obsidian.run({'vault': str(self.v), 'note': 'Projects/Q3'})[1], '# Q3\nship the ledger export')
        for bad in ('../secret.md', '.obsidian/app.md', '.trash/old', 'Projects/img.png', 'nothing'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): obsidian.run({'vault': str(self.v), 'note': bad})
        with self.assertRaisesRegex(RuntimeError, 'no vault folder'): obsidian.run({})
        with self.assertRaisesRegex(RuntimeError, 'not a folder'): obsidian.run({'vault': str(self.v / 'Inbox.md')})

    def test_the_card_tests_and_a_report_reads_its_vault(self):
        s = MemoryStore(); c = s.get_connector_by_type('obsidian')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'vault': str(self.v)})}, 't')
        out = channels.test_connector(s, c['ConnectorId'])
        self.assertTrue(out['ok'], out); self.assertIn('2 notes', out['detail'])
        self.assertEqual((reports.card_of('obsidian_read'), scopes.needs('obsidian_read')), ('obsidian', 'read'))
        self.assertEqual(reports.executor_for('obsidian_read')(reports.resolve_cfg(s, {'type': 'obsidian_read'}))[0], 'Obsidian: 2 notes')


if __name__ == '__main__':
    unittest.main()
