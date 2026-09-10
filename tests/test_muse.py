"""Meta's Muse Spark, by both roads: the `muse` CLI as a coding agent, and the Meta Model API
as a triage brain.

The two exist separately on purpose. The muse installer exits `unsupported platform` on Windows
(Meta's answer is WSL2), so on the machine most owners arrive with, the CLI road is closed and
the connector is the only way to reach the model at all.
"""
import json, unittest
from unittest import mock

from taskuary import cliinstall, climodels, clis, clisetup, llm
from taskuary.store import MemoryStore


class CliRegistrationTests(unittest.TestCase):
    def test_headless_run_carries_the_approval_bypass(self):
        """A headless agent with no bypass flag parks on a prompt nobody can click - the exact
        failure clis.KNOWN documents. muse spells it `exec` + --yolo, codex's shape not claude's."""
        k = next(k for k in clis.KNOWN if k['name'] == 'muse')
        self.assertEqual((k['cmd'], k['args']), ('muse', ['exec', '--yolo']))
        self.assertEqual(clis.preset_args('muse'), ['exec', '--yolo'])
        self.assertEqual(clis.preset_args('/usr/local/bin/muse'), ['exec', '--yolo'])   # a path is still a muse

    def test_the_classifier_loses_its_hands(self):
        """Triage reads untrusted mail: the message IS the prompt, so a sentence in it saying
        'run this' must find nothing to run. Dropping --yolo restores approval AND the sandbox."""
        self.assertEqual(clis.readonly_args('muse', ['exec', '--yolo']), ['exec'])
        self.assertEqual(clis.report_read_args('muse', ['exec', '--yolo']), ['exec'])

    def test_windows_gets_no_install_button(self):
        """plan() is what the UI draws `installable` from - never a button over a road that
        hard-fails. There is no npm package and no triple-named archive, so posix or nothing."""
        self.assertEqual(cliinstall.plan('muse', has_npm=True, system='Windows'), [])
        for system in ('Darwin', 'Linux'):
            roads = cliinstall.plan('muse', has_npm=False, system=system)
            self.assertEqual([r['how'] for r in roads], ['script'], system)
            self.assertIn('dev.meta.ai/install.sh', roads[0]['cmd'][-1], system)

    def test_the_binary_is_named_and_the_first_run_is_ours_to_open(self):
        self.assertEqual(cliinstall.BINARY['muse'], 'muse')
        self.assertEqual(cliinstall.recipe_for('muse'), 'muse')
        self.assertEqual(cliinstall.recipe_for('/opt/muse'), 'muse')
        self.assertIn('muse', clisetup.SETUP)                      # browser sign-in at dev.meta.ai
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            with self.assertRaises(ValueError): clisetup.argv('muse')


class ModelTests(unittest.TestCase):
    def test_the_private_tier_leads_and_contributor_is_never_the_default(self):
        cat = climodels.catalog('muse')
        self.assertEqual(cat['choices'][0], 'muse-spark-1.3')
        self.assertIn('muse-spark-1.2-contributor', cat['choices'])
        contributor = next(m for m in cat['models'] if m['id'].endswith('-contributor'))
        self.assertIn('trains', contributor['desc'])               # the cost of the discount, said out loud

    def test_no_reasoning_levels_are_offered(self):
        """muse HAS reasoning levels, but the @effort pick emits codex's `-c
        model_reasoning_effort=` and muse spells it --reasoning-effort. Offering them would
        hand muse a flag it does not have."""
        self.assertEqual([m['efforts'] for m in climodels.catalog('muse')['models']], [[], [], []])

    def test_a_light_model_downshifts_triage_without_touching_the_coding_model(self):
        """One brain, two gears: the classifier reads one email on the cheap tier while the
        profile's main model stays reserved for coding sessions."""
        s = MemoryStore()
        s.upsert_agent('muse', 'coding', 'cli', json.dumps(
            {'cmd': 'muse', 'args': ['exec', '--yolo'], 'model': 'muse-spark-1.3', 'light_model': 'muse-spark-1.2'}))
        seen = {}
        with mock.patch('taskuary.agents.run_cli', side_effect=lambda prof, p, t, **kw: (seen.update(prof), ('{}', None, None))[1]):
            llm.make_cli_llm(s, 'muse')('sys', 'user')
        self.assertEqual(seen['model'], 'muse-spark-1.2')
        self.assertEqual(seen['args'], ['exec'])                   # and the classifier still has no hands


class ConnectorTests(unittest.TestCase):
    """The Meta Model API is OpenAI's chat-completions schema, so it needs no branch beyond a url."""

    def _capture(self, cfg, status=200, body=None):
        seen = {}
        def post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, headers=headers, body=json)
            return mock.Mock(status_code=status, json=lambda: body or {'choices': [{'message': {'content': 'ok'}}]}, text='')
        with mock.patch('taskuary.llm.requests.post', side_effect=post):
            out = llm.make_llm('meta', cfg, 'secret-key')('sys', 'user')
        return seen, out

    def test_it_reaches_meta_with_the_private_tier_by_default(self):
        seen, out = self._capture({})
        self.assertEqual(seen['url'], 'https://api.meta.ai/v1/chat/completions')
        self.assertEqual(seen['headers']['Authorization'], 'Bearer secret-key')
        self.assertEqual(seen['body']['model'], 'muse-spark-1.2')
        self.assertEqual(out, 'ok')

    def test_the_model_and_the_base_url_are_the_owners(self):
        seen, _ = self._capture({'model': 'muse-spark-1.2-contributor', 'base_url': 'https://gateway.internal/v1/'})
        self.assertEqual(seen['url'], 'https://gateway.internal/v1/chat/completions')
        self.assertEqual(seen['body']['model'], 'muse-spark-1.2-contributor')

    def test_a_key_is_required(self):
        with self.assertRaises(RuntimeError): llm.make_llm('meta', {}, '')

    def test_it_ships_as_a_card_and_can_be_picked_as_the_triage_brain(self):
        """The card is seeded by type like every other connector, and once it has a key and is
        switched on, Settings -> Triage & routing can name it."""
        self.assertIn('meta', llm.AI_TYPES)
        s = MemoryStore()
        row = s.get_connector_by_type('meta')
        self.assertIsNotNone(row, 'no meta connector card was seeded')
        cid = row['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        with mock.patch('taskuary.llm.make_llm', return_value=lambda *a, **k: 'ok') as m:
            self.assertIsNotNone(llm._build_llm(s, f'connector:{cid}'))
        self.assertEqual(m.call_args[0][0], 'meta')


if __name__ == '__main__': unittest.main()
