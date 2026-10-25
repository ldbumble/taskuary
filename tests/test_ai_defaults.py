"""The AI defaults panel: one screen that says what will actually run, and writes each half
back to the screen that owns it.

The bug this exists for: Settings named a brain and never a model, so "which model triages my
mail" had a different answer on a different page for every kind of brain, and the Triage page
could not tell you any of them (the owner, 2026-09-10).
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import aidefaults, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))
    return s


def _cfg(key='claude', **gears):
    """The gears live on the BRAIN - the CLI connection - never on a profile (the owner, 2026-10-15)."""
    return {'cli_connections': {key: {'cmd': key, **gears}}}


@mock.patch('taskuary.agents.runs_here', lambda profile: True)       # the hints below are for a CLI that starts
class ResolveTests(unittest.TestCase):
    def test_a_cli_brain_reports_its_LIGHT_gear_not_its_coding_model(self):
        """The whole point of the two gears: triage must not quietly run the coding model."""
        s, cfg = _store(), _cfg(model='opus', light_model='haiku')
        s.set_setting('triage_ai', 'cli:claude', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual((r['model'], r['cli']), ('haiku', 'claude'))
        self.assertIn('light model', r['owner'])
        self.assertIn('haiku', r['choices'])

    def test_a_cli_brain_with_no_light_model_runs_the_small_one_and_says_so(self):
        """Blank meant the CODING model - triage on the expensive tier (the owner, 2026-09-24: "lower model for triage")."""
        s, cfg = _store(), _cfg(model='opus')
        s.set_setting('triage_ai', 'cli:claude', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual(r['model'], '')
        self.assertEqual(r['default_hint'], 'haiku - the light default'); self.assertEqual(r['note'], '')

    def test_codex_effort_only_light_gear_round_trips(self):
        """codex on a ChatGPT plan has no smaller model - its cheap gear IS the effort."""
        s, cfg = _store(), _cfg('codex', light_model='effort:low')
        s.set_setting('triage_ai', 'cli:codex', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual((r['model'], r['effort']), ('', 'low'))

    def test_auto_names_the_connector_it_currently_resolves_to(self):
        """'auto' told the owner nothing about which model reads their mail."""
        s = _store()
        row = s.get_connector_by_type('anthropic')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1,
                          'ConfigJson': json.dumps({'model': 'claude-sonnet-5'})}, 'o')
        r = aidefaults.resolve(s, {}, 'triage_ai')
        self.assertEqual(r['value'], '')                    # still auto
        self.assertEqual(r['model'], 'claude-sonnet-5')
        self.assertIn('Anthropic', r['note'])               # ...and it says which card that is
        self.assertIn('card', r['owner'])

    def test_a_blank_connector_model_reports_the_provider_default(self):
        s = _store()
        row = s.get_connector_by_type('meta')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', f"connector:{row['ConnectorId']}", 'o')
        r = aidefaults.resolve(s, {}, 'triage_ai')
        self.assertEqual(r['model'], '')
        self.assertIn('muse-spark-1.2', r['note'])          # blank is not "unconfigured"
        # ...and the picker's choices are the provider's own list for this key (/api/ai/models), never a typed-in one (2026-10-25)
        self.assertEqual(r['choices'], [])

    def test_no_key_anywhere_is_reported_not_guessed(self):
        r = aidefaults.resolve(_store(), {}, 'triage_ai')
        self.assertFalse(r['ready']); self.assertIn('no AI connector', r['note'])

    def test_the_coding_slot_reads_the_MAIN_model(self):
        s, cfg = _store(), _cfg(model='opus', light_model='haiku')
        s.set_setting('default_brain', 'claude', 'o')
        r = aidefaults.resolve(s, cfg, 'default_brain')
        self.assertEqual(r['model'], 'opus')                # not haiku
        # where it is saved is a PLACE the page can open (words.json): "agents" opened the Profiles shelf, where no
        # connection is (the 2026-10-19 UI walk) - the claude connection is on Connections' AI CLI agents page
        self.assertEqual(r['owner_link'], 'ai_apps')
        from taskuary.words import PLACES
        self.assertTrue(PLACES['ai_apps']['href'])

    def test_state_offers_cli_tools_never_profiles(self):
        """A profile is instructions on whichever brain runs it, so the coding picker lists the TOOLS - one per connection."""
        from taskuary import agents
        s, cfg = _store(), {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'opus'}, 'copilot': {'cmd': 'copilot'}}}
        s.upsert_agent('researcher', 'research', 'cli', json.dumps({'cmd': 'claude'}))
        with mock.patch.object(agents, 'connection_brains', agents.connection_brains.real), \
             mock.patch('taskuary.config.load', return_value=cfg):
            options = aidefaults.state(s, cfg)['agent_options']
        self.assertEqual([(o['value'], o['label']) for o in options], [('claude', 'claude'), ('copilot', 'copilot')])


class TheFifthSlotTests(unittest.TestCase):
    """Where runs go. The other four workers all have to be able to WRITE; this one answers four
    yes/nos about text somebody else produced, so a decision model belongs here and nowhere else."""

    def _with_jev(self):
        s = _store()
        cid = s.get_connector_by_type('typesafe')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
        return s, cid

    def test_the_fifth_slot_is_where_runs_go_and_it_defaults_to_today(self):
        st = aidefaults.state(_store(), {})
        self.assertIn('judge_ai', [x['key'] for x in st['slots']])
        judge = next(x for x in st['slots'] if x['key'] == 'judge_ai')
        self.assertEqual(judge['value'], '')                    # blank = the report's own brain
        self.assertIn('own brain', judge['note'] + judge['desc'])
        self.assertTrue(judge['ready'])                         # nothing to set up: it already works

    def test_it_carries_no_model_field(self):
        """The other four pair a brain with a model because the model changes how well the thing
        writes. This one answers four booleans; the model belongs with the summariser."""
        self.assertNotIn('model_setting', aidefaults.SLOT['judge_ai'])
        self.assertEqual(aidefaults.resolve(_store(), {}, 'judge_ai')['model'], '')

    def test_the_decision_model_is_offered_HERE_and_only_here(self):
        s, cid = self._with_jev()
        st = aidefaults.state(s, {})
        self.assertTrue([o for o in st['judge_options'] if str(cid) in str(o.get('value'))],
                        'the decision model cannot be chosen as the judge')
        self.assertEqual(st['judge_options'][0]['value'], '')    # the report's own brain leads

    def test_a_card_with_no_key_is_offered_but_not_ready(self):
        """Same rule as every other picker: you can see it, and it tells you what is missing."""
        s = _store()
        cid = s.get_connector_by_type('typesafe')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        got = next(o for o in aidefaults.state(s, {})['judge_options'] if str(cid) in str(o['value']))
        self.assertFalse(got['ready'])

    def test_choosing_it_says_what_will_run_and_says_when_it_cannot(self):
        s, cid = self._with_jev()
        aidefaults.apply(s, {}, 'judge_ai', f'connector:{cid}')
        r = aidefaults.resolve(s, {}, 'judge_ai')
        self.assertTrue(r['ready'])
        self.assertIn('Jev', r['display'])
        s.save_connector({'ConnectorId': cid, 'Secret': '', 'Active': 1}, 't')
        self.assertFalse(aidefaults.resolve(s, {}, 'judge_ai')['ready'])

    def test_an_ordinary_brain_is_still_a_legal_judge(self):
        """Two settings, because only one of the two jobs needs a model that can write - not
        because the judge stopped being allowed to be an ordinary brain."""
        s = _store()
        s.set_setting('judge_ai', 'cli:claude', 'o')
        self.assertEqual(aidefaults.resolve(s, _cfg(), 'judge_ai')['kind'], 'brain')
        self.assertEqual(aidefaults.resolve(s, _cfg(), 'judge_ai')['value'], 'cli:claude')


class WhatTheJudgeIsAskedTests(unittest.TestCase):
    """A rule you cannot read is a rule you cannot trust, and this slot IS four questions (the owner,
    2026-09-17: "show the wording for jev ... what are the decision choices it's going for")."""

    def test_the_card_says_what_it_actually_decides(self):
        from taskuary import reports
        r = aidefaults.resolve(_store(), {}, 'judge_ai')
        self.assertEqual([d['line'] for d in r['decides']], list(reports.LINES))
        self.assertIn(reports.LINE_SAYS['alert'], next(d['says'] for d in r['decides'] if d['line'] == 'alert'))
        self.assertEqual(r['evidence'], reports.EVIDENCE_RULE)

    def test_a_decision_model_says_it_is_one_so_the_report_card_can_show_typed_questions(self):
        s = _store()
        cid = s.get_connector_by_type('typesafe')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
        self.assertEqual(aidefaults.resolve(s, {}, 'judge_ai')['kind'], 'brain')
        aidefaults.apply(s, {}, 'judge_ai', f'connector:{cid}')
        self.assertEqual(aidefaults.resolve(s, {}, 'judge_ai')['kind'], 'decision')


class ApplyTests(unittest.TestCase):
    def test_setting_a_cli_brains_model_writes_the_light_model_and_leaves_coding_alone(self):
        s, cfg = _store(), {**_cfg(model='opus'), 'agents': {'coding': {'kind': 'coding'}}}
        s.set_setting('default_brain', 'claude', 'o'); s.set_setting('triage_ai', 'cli:claude', 'o')
        out = aidefaults.apply(s, cfg, 'triage_ai', model='haiku')
        self.assertEqual(out['model'], 'haiku')
        # the GEARS live on the brain, not on the profile - a profile has nothing to do with which model runs it
        # (the owner, 2026-09-16). Coding is still left alone, on the brain.
        self.assertEqual(cfg['cli_connections']['claude']['light_model'], 'haiku')
        self.assertEqual(cfg['cli_connections']['claude']['model'], 'opus')      # untouched
        self.assertNotIn('light_model', cfg['agents']['coding'])
        self.assertEqual(json.loads(s.get_agent('coding')['Config'])['light_model'], 'haiku')  # and mirrored to the row it runs

    def test_effort_without_a_model_is_written_as_codex_spells_it(self):
        s, cfg = _store(), _cfg('codex')
        s.set_setting('triage_ai', 'cli:codex', 'o')
        aidefaults.apply(s, cfg, 'triage_ai', model='', effort='low')
        self.assertEqual(cfg['cli_connections']['codex']['light_model'], 'effort:low')

    def test_setting_a_connector_brains_model_writes_the_connector_card(self):
        s = _store()
        row = s.get_connector_by_type('anthropic')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', f"connector:{row['ConnectorId']}", 'o')
        aidefaults.apply(s, {}, 'triage_ai', model='claude-haiku-4-5')
        conf = json.loads(s.get_connector(row['ConnectorId'])['ConfigJson'])
        self.assertEqual(conf['model'], 'claude-haiku-4-5')

    def test_clearing_a_model_removes_it_rather_than_saving_an_empty_string(self):
        """'' means back to the provider default, and a saved '' is not that."""
        s, cfg = _store(), _cfg(light_model='haiku')
        s.set_setting('triage_ai', 'cli:claude', 'o')
        aidefaults.apply(s, cfg, 'triage_ai', model='')
        self.assertNotIn('light_model', cfg.get('cli_connections', {}).get('claude', {}))

    def test_the_brain_and_the_model_can_be_set_in_one_call(self):
        s, cfg = _store(), _cfg()
        aidefaults.apply(s, cfg, 'triage_ai', value='cli:claude', model='haiku')
        self.assertEqual(s.get_settings()['triage_ai'], 'cli:claude')
        self.assertEqual(cfg['cli_connections']['claude']['light_model'], 'haiku')

    def test_an_unknown_slot_is_refused(self):
        with self.assertRaises(ValueError): aidefaults.apply(_store(), {}, 'not_a_slot', model='x')


class ApiTests(unittest.TestCase):
    def test_the_endpoint_returns_every_slot_with_its_owner(self):
        j = c.get('/api/ai/defaults').json()
        # one worker, one row: the general agent joined on 2026-09-16, because the page that exists
        # to say what will run was silent about the brain half the board's tasks use, and the judge
        # on 2026-09-17, because where a finished run goes is a fifth thing an AI decides, and Drafting on 2026-10-25, because
        # every reply was written by the triage brain and no card said so
        self.assertEqual([s['key'] for s in j['slots']],
                         ['triage_ai', 'draft_ai', 'default_brain', 'concierge_ai', 'assistant_ai', 'judge_ai'])
        for s in j['slots']:
            self.assertTrue(s['label'] and s['desc'] and s['why'])     # every row explains itself
            for k in ('model', 'effort', 'choices', 'efforts', 'owner', 'note'): self.assertIn(k, s)

    def test_a_bad_slot_is_a_422_not_a_500(self):
        self.assertEqual(c.post('/api/ai/defaults', json={'slot': 'nope', 'model': 'x'}).status_code, 422)


if __name__ == '__main__': unittest.main()


@mock.patch('taskuary.agents.runs_here', lambda profile: True)       # the hints below are for a CLI that starts
class AssistantModelTests(unittest.TestCase):
    def test_the_assistant_card_names_the_model_it_really_runs_on(self):
        """It said "the coding model, the expensive gear" while every turn ran on haiku (2026-09-24)."""
        s = _store(); s.set_setting('concierge_ai', 'cli:claude', 'owner')
        r = aidefaults.resolve(s, _cfg(), 'concierge_ai')
        self.assertEqual(r['default_hint'], 'sonnet - the Assistant default'); self.assertEqual(r['note'], '')
        s.set_setting('concierge_model', 'sonnet', 'owner')
        self.assertEqual(aidefaults.resolve(s, _cfg(), 'concierge_ai')['model'], 'sonnet')


class DefaultBrainTests(unittest.TestCase):
    def test_a_blank_brain_means_the_default_brain_never_the_first_connector(self):
        """"First connected should not matter" (the owner, 2026-09-24): blank = default_brain, the CLI tool itself."""
        from taskuary import agents
        real = agents.default_pick.real
        s = _store()
        with mock.patch.object(agents, 'connection_brains', agents.connection_brains.real), \
             mock.patch('taskuary.config.load', return_value=_cfg()):
            with mock.patch.object(agents, 'runs_here', return_value=False):
                self.assertEqual(real(s), '')                               # nothing set, nothing runs: no brain yet
            with mock.patch.object(agents, 'runs_here', return_value=True):
                self.assertEqual(real(s), 'cli:claude')                     # nothing set: the connected CLI, when it runs
                s.set_setting('default_brain', 'claude', 'o')
                self.assertEqual(real(s), 'cli:claude')                     # the tool, never the profile on it
                s.set_setting('default_brain', 'gemini', 'o')
                self.assertEqual(real(s), '')                               # a brain nothing here connects names nobody


class AliasTests(unittest.TestCase):
    """`sonnet` is not an id in the CLI's catalogue, so an alias pick used to show no effort picker and no version."""
    cat = {'models': [{'id': i, 'efforts': ['low', 'high']} for i in ('claude-sonnet-5', 'claude-sonnet-5-5', 'claude-opus-5-5')]}

    def test_alias_lands_on_the_newest_of_its_family(self):
        self.assertEqual(aidefaults._resolved(self.cat, 'sonnet'), 'claude-sonnet-5-5')
        self.assertEqual(aidefaults._efforts(self.cat, 'sonnet'), ['low', 'high'])

    def test_an_exact_id_resolves_to_nothing_extra(self):
        self.assertEqual(aidefaults._resolved(self.cat, 'claude-sonnet-5'), '')
        self.assertEqual(aidefaults._efforts(self.cat, 'claude-sonnet-5'), ['low', 'high'])

    def test_unknown_or_blank_has_no_efforts(self):
        self.assertEqual((aidefaults._efforts(self.cat, ''), aidefaults._efforts(self.cat, 'nope')), ([], []))
