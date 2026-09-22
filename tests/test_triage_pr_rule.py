"""The PR rule reaches an install that stopped following the template - and the general agent's
brain is a setting you can find.

Two fixes from 2026-09-16, both the same shape: something was decided in code where nobody could
see it. A regex in ingest overrode TRIAGE.md's PR rule and named no `kind`, so twelve pull
requests in a row went to the assistant instead of the coder; and `assistant_ai` - the general
agent's brain - sat on the Assistant tab calling itself the bubble's, so general work ran on Azure
while the owner's `default_brain` said claude and no page admitted it.
"""
import json
import tempfile
import unittest
from pathlib import Path

import taskuary
from taskuary import aidefaults, general, store as store_mod
from taskuary.store import MemoryStore, SQLiteStore

TEMPLATE = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')


def _azure(store) -> int:
    """The install ships a card per provider; a test turns one on the way the owner would."""
    row = store.get_connector_by_type('azure_openai')
    store.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1,
                          'ConfigJson': json.dumps({'model': 'gpt-5.4'})}, 'o')
    return row['ConnectorId']


class PrRuleTests(unittest.TestCase):
    """The migration runs in SQLiteStore.__init__, so these open a real file store twice: once to
    put the old rule in as an owner-edited doc, once to watch the fix land on reopen."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / 'taskuary.db'

    def _reopen(self, doc: str = None, keep_sentinel: bool = False):
        s = SQLiteStore(str(self.path))
        if doc is not None: s.save_doc('triage', doc, 'owner')
        if not keep_sentinel: s.cx.execute("DELETE FROM setting WHERE Name='triage_pr_rule_fixed'")
        s.cx.commit()
        return SQLiteStore(str(self.path))

    def test_the_migration_says_what_the_template_says(self):
        """_PR_RULE_NOW is a copy of a paragraph in templates/triage.md - the doc is the wording
        everyone else reads, so a rewording there that forgot this constant would leave every
        edited install on the old rule for ever."""
        for sentence in ('A PULL REQUEST is a task, and its kind is coding - whoever opened it.',
                         "A stranger's ISSUE is a different thing and keeps the skepticism"):
            self.assertIn(sentence, store_mod._PR_RULE_NOW)
            self.assertIn(sentence, TEMPLATE)
        self.assertNotIn(store_mod._PR_RULE_WAS, TEMPLATE)

    def test_a_doc_that_stopped_tracking_the_template_still_gets_the_fix(self):
        """The owner's TRIAGE.md is UpdatedBy='migration', so the template rightly no longer
        overwrites it - the rest of the document is theirs. One sentence is replaced, in place."""
        mine = "MY OWN RULE: anything from Maya is urgent.\n\n" + store_mod._PR_RULE_WAS + "And my last line."
        after = self._reopen(mine).doc('triage')
        self.assertNotIn(store_mod._PR_RULE_WAS, after)
        self.assertIn('A PULL REQUEST is a task, and its kind is coding', after)
        self.assertIn('MY OWN RULE: anything from Maya is urgent.', after)   # nothing else touched
        self.assertIn('And my last line.', after)

    def test_it_runs_once_and_never_edits_a_doc_again(self):
        """A one-shot repair, not a standing rule: put the old sentence back on purpose and it
        stays. Their document, their call."""
        s = self._reopen("plain " + store_mod._PR_RULE_WAS)
        self.assertEqual(s.get_settings().get('triage_pr_rule_fixed'), '1')
        s.save_doc('triage', 'I want it the old way: ' + store_mod._PR_RULE_WAS, 'owner')
        s.cx.commit()
        self.assertIn(store_mod._PR_RULE_WAS, SQLiteStore(str(self.path)).doc('triage'))


class GeneralBrainTests(unittest.TestCase):
    """Which brain works a general task is a SETTING with a card, not a tie-break in a function."""

    def test_the_general_agent_has_a_slot_on_the_ai_defaults_page(self):
        slot = aidefaults.SLOT.get('assistant_ai')
        self.assertIsNotNone(slot, 'the general agent needs a row on the page that says what runs')
        self.assertEqual(slot['pick'], 'brain')                  # a CLI or a connector, not CLIs only
        self.assertEqual(slot['model_setting'], 'assistant_model')

    def test_a_slot_with_its_own_model_setting_reads_it_back(self):
        """apply() writes the model to `assistant_model`; resolve() read the connector's instead,
        so an override you typed came back showing somebody else's value."""
        s = MemoryStore()
        _azure(s)
        aidefaults.apply(s, {}, 'assistant_ai', model='gpt-5.4-mini', actor='owner')
        self.assertEqual(s.get_settings().get('assistant_model'), 'gpt-5.4-mini')
        self.assertEqual(aidefaults.resolve(s, {}, 'assistant_ai')['model'], 'gpt-5.4-mini')

    def test_choosing_a_cli_is_what_the_general_session_then_runs(self):
        """The whole point: the setting has to reach general._selected, or the card is decoration."""
        s = MemoryStore()
        cid = _azure(s)
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        self.assertEqual(general._selected(s)[0], f'connector:{cid}')   # blank prefers the quick API path
        aidefaults.apply(s, {}, 'assistant_ai', value='cli:coder', actor='owner')
        self.assertEqual(general._selected(s)[0], 'cli:coder')
        self.assertIn('cli:coder', [o['pick'] for o in general.provider_options(s)])


if __name__ == '__main__':
    unittest.main()
