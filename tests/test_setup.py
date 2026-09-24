"""Discussion #23: a setup wizard, because a fresh install opens on an empty Timeline that looks
exactly like a working install on a quiet morning - and the three things standing between those
two states live on three different tabs with nothing pointing at them.

The checklist is DERIVED, never stored: a step is done when the thing it asks for actually works,
and un-does itself when the connection behind it is removed. A stored checklist would go on
saying "done" after somebody deleted the mailbox.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from taskuary import server, setup
from taskuary.store import MemoryStore, SQLiteStore

c = TestClient(server.app)


def _fresh():
    return MemoryStore()


def _with_ai(s, typ='anthropic', secret='sk-x', active=1):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': secret, 'Active': active}, 't')
    return s


def _with_mailbox(s):
    cid = s.get_connector_by_type('outlook')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
    s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
    return s


def _step(st, key):
    return next(x for x in st['steps'] if x['key'] == key)


class WhatCountsAsSetUpTests(unittest.TestCase):
    def test_a_fresh_install_has_nothing_done_and_says_which_five(self):
        st = setup.state(_fresh())
        self.assertEqual((st['done'], st['total'], st['complete']), (0, 5, False))
        self.assertEqual([x['key'] for x in st['steps']],
                         ['owner', 'ai', 'models', 'inbound', 'sync'])
        # every step explains ITSELF - "go to Connections" is navigation, not a reason
        for x in st['steps']:
            self.assertGreater(len(x['why']), 40, f"{x['key']} has no reason to exist")

    def test_there_is_no_second_tier_left_to_count(self):
        """Eight rows in two tiers became five in one. A leftover guide_* counter would be a second
        number nobody updates, which is how the headline and the pill disagreed before."""
        st = setup.state(_fresh())
        for gone in ('ready', 'guide_done', 'guide_total'):
            self.assertNotIn(gone, st)
        for x in st['steps']:
            self.assertNotIn('optional', x)
            self.assertNotIn('where', x)

    def test_every_step_says_where_it_goes(self):
        """A row that points nowhere is the old wizard's inline form with the form removed."""
        tabs = {'Assistant', 'Board', 'Tasks', 'Review', 'Reports', 'Connections', 'Docs', 'Settings', 'Hub'}
        for x in setup.state(_fresh())['steps']:
            self.assertIn(x['goto']['tab'], tabs, x['key'])
            self.assertIsInstance(x['goto']['hash'], str)
        by = {x['key']: x['goto'] for x in setup.state(_fresh())['steps']}
        self.assertEqual(by['owner'], {'tab': 'Settings', 'hash': 'settings=about', 'label': 'Open About you'})
        self.assertEqual(by['ai'], {'tab': 'Connections', 'hash': 'cli-agents', 'label': 'Open AI CLI agents'})
        self.assertEqual(by['models'], {'tab': 'Settings', 'hash': 'settings=config&group=Triage%20%26%20agents',
                                        'label': 'Open Triage & agents'})

    def test_no_two_rows_wear_the_same_button(self):
        """The button says what it OPENS. Labelled by tab, rows 2 and 4 both read "Connections" and
        went to the AI CLI agents page and the connector list - a first-time owner cannot tell those
        apart, and they are the two rows most likely to be pressed in the wrong order."""
        steps = setup.state(_fresh())['steps']
        labels = [x['goto']['label'] for x in steps]
        self.assertTrue(all(labels), 'every row names its destination')
        self.assertEqual(len(set(labels)), len(labels), labels)
        # ...and a label that is only the tab name is the defect wearing a new field
        self.assertFalse([x['key'] for x in steps if x['goto']['label'] == x['goto']['tab']])

    def test_the_owner_step_is_not_fooled_by_the_fallback_name(self):
        """store.owner() answers the literal string "the owner" when nothing is set, so a naive
        truthiness check reads a fresh install as done and never sends anybody to the one field
        that signs their mail."""
        s = _fresh()
        self.assertFalse(_step(setup.state(s), 'owner')['done'])
        s.set_setting('owner_name', 'Dana Example', 't')
        self.assertTrue(_step(setup.state(s), 'owner')['done'])
        # the detail says what it IS, not just what it holds: a bare name in the done-green sat
        # directly above the instructions and read as a heading for them (2026-09-17)
        self.assertEqual(_step(setup.state(s), 'owner')['detail'], 'signed as Dana Example')

    def test_an_ai_card_with_no_key_is_not_a_brain(self):
        s = _fresh()
        _with_ai(s, secret=None, active=1)
        self.assertFalse(_step(setup.state(s), 'ai')['done'])
        _with_ai(s, secret='sk-real')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_local_model_counts_without_a_key(self):
        """Ollama carries no secret, so "has a key" is the wrong test for it - and getting this
        wrong would tell somebody running a local model that they have no AI."""
        s = _fresh()
        cid = s.get_connector_by_type('ollama')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_connector_with_no_source_behind_it_is_only_half_connected(self):
        """It looks done on the Connections tab and delivers nothing. That is exactly the state a
        checklist exists to catch."""
        s = _fresh()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])
        s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'inbound')['done'])

    def test_a_report_only_connection_is_not_a_funnel(self):
        """AWS brings no work in. Counting it would call an install ready that can never show a
        single message."""
        s = _fresh()
        cid = s.get_connector_by_type('aws')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'k', 'Active': 1}, 't')
        s.save_source({'Channel': 'aws', 'Address': 's3://b', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])

    def test_a_tracker_alone_is_not_somewhere_work_arrives(self):
        """GitHub brings issues in and it is a real source, but an install with GitHub and no
        mailbox has a Timeline with no mail in it - and the row said it was done (2026-09-17)."""
        s = _fresh()
        cid = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'ghp_x', 'Active': 1}, 't')
        s.save_source({'Channel': 'github', 'Address': 'ours/repo', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])
        _with_mailbox(s)
        self.assertTrue(_step(setup.state(s), 'inbound')['done'])

    def test_the_seeded_reports_are_not_your_first_messages(self):
        """Also found by running it: the Morning digest and Automation ideas file their own rows
        on first start, so "something is in the timeline" was true before a single message had
        ever been read."""
        s = _fresh()
        s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'Subject': 'Morning digest',
                       'BodyText': 'x', 'Status': 'report'})
        self.assertFalse(_step(setup.state(s), 'sync')['done'])
        s.add_message({'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'a real one',
                       'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        self.assertTrue(_step(setup.state(s), 'sync')['done'])

    def test_no_step_shows_a_number_it_cannot_make_true(self):
        """The sync step samples the feed, so any count it printed would be the sample size:
        "2 read" on an install holding thousands."""
        s = _fresh()
        for i in range(9):
            s.add_message({'ExternalId': f'm{i}', 'Channel': 'email', 'Subject': 's',
                           'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        self.assertEqual(_step(setup.state(s), 'sync')['detail'], 'messages are arriving')

    def test_five_of_five_is_complete_and_the_counter_is_finished(self):
        s = _fresh()
        s.set_setting('owner_name', 'Dana Example', 't')
        s.set_setting(setup.SEEN_MODELS, '1', 't')
        _with_ai(s); _with_mailbox(s)
        s.add_message({'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'hello',
                       'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        st = setup.state(s)
        self.assertEqual((st['done'], st['total'], st['complete']), (5, 5, True))

    def test_it_un_does_itself_when_a_connection_is_removed(self):
        """The whole reason it is derived rather than stored."""
        s = _fresh()
        _with_ai(s)
        self.assertTrue(_step(setup.state(s), 'ai')['done'])
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 0}, 't')
        self.assertFalse(_step(setup.state(s), 'ai')['done'])


class ACliCountsAsABrainTests(unittest.TestCase):
    """Most people arriving here already pay for Claude Code or Codex and have no separate API
    key. Treating "a key exists" as the only definition of a brain told them they had none while
    the thing sat on their PATH - and sent them to Settings to fix it."""
    def test_an_agent_alone_is_not_the_brain_until_triage_points_at_it(self):
        s = _fresh()
        s.upsert_agent('claude', 'coding', 'cli', '{"cmd": "claude"}')
        self.assertFalse(_step(setup.state(s), 'ai')['done'])
        s.set_setting('triage_ai', 'cli:claude', 't')
        st = _step(setup.state(s), 'ai')
        self.assertTrue(st['done'])
        self.assertIn('CLI', st['detail'])          # says WHICH kind of brain it is

    def test_pointing_at_an_agent_that_is_gone_is_not_a_brain(self):
        s = _fresh()
        s.set_setting('triage_ai', 'cli:vanished', 't')
        self.assertFalse(_step(setup.state(s), 'ai')['done'])

    def test_a_key_still_counts_when_no_cli_is_chosen(self):
        s = _fresh()
        _with_ai(s)
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_detection_finds_what_is_on_PATH_and_what_is_configured(self):
        from taskuary import clis
        s = _fresh()
        s.upsert_agent('my-own-cli', 'coding', 'cli', '{"cmd": "whatever"}')
        found = {x['name']: x for x in clis.detect(s)}
        self.assertIn('my-own-cli', found)                       # configured here, so offered
        self.assertTrue(found['my-own-cli']['configured'])
        for x in found.values():
            self.assertIn('installed', x)
        # the flags are not decoration: a headless claude without them blocks on an approval
        # nobody can click, so an agent added from here would hang on first use
        claude = next(k for k in clis.KNOWN if k['name'] == 'claude')
        self.assertIn('--dangerously-skip-permissions', claude['args'])

    def test_the_endpoint_answers_without_a_store_full_of_agents(self):
        d = c.get('/api/cli/detect').json()
        self.assertIn('data', d)
        for x in d['data']:
            for k in ('name', 'label', 'installed', 'configured'):
                self.assertIn(k, x)


class PuttingItAwayTests(unittest.TestCase):
    def test_dismissing_sticks_and_can_be_undone(self):
        """A checklist you cannot hide is nagging; one you cannot get back is worse."""
        self.assertFalse(c.get('/api/setup').json()['dismissed'])
        self.assertTrue(c.post('/api/setup/dismiss', json={'dismissed': True}).json()['dismissed'])
        self.assertTrue(c.get('/api/setup').json()['dismissed'])      # survives the next read
        self.assertFalse(c.post('/api/setup/dismiss', json={'dismissed': False}).json()['dismissed'])

    def test_dismissing_changes_nothing_about_what_is_actually_done(self):
        before = c.get('/api/setup').json()
        c.post('/api/setup/dismiss', json={'dismissed': True})
        after = c.get('/api/setup').json()
        c.post('/api/setup/dismiss', json={'dismissed': False})
        self.assertEqual((before['done'], before['complete']), (after['done'], after['complete']))

    def test_the_endpoint_answers_the_same_shape_the_panel_reads(self):
        d = c.get('/api/setup').json()
        for k in ('steps', 'done', 'total', 'complete', 'dismissed'):
            self.assertIn(k, d)
        for x in d['steps']:
            for k in ('key', 'title', 'why', 'done', 'goto'):
                self.assertIn(k, x)
            for k in ('tab', 'hash', 'label'):        # the label is the button's words, over the wire
                self.assertIn(k, x['goto'], x['key'])


class TheWizardActuallySetsUpTests(unittest.TestCase):
    """Pointing at a tab is not setting up: it hands the work back with directions attached. These
    walk the exact calls the panel makes and check the state moves - because a wizard that saves a
    key without testing it leaves you with a connected-looking install and an empty Timeline."""
    def _reset(self):
        for conn in server.store.list_connectors():      # not `c` - that is the TestClient
            if conn['Type'] in ('anthropic', 'gmail'):
                server.store.save_connector({'ConnectorId': conn['ConnectorId'], 'Active': 0, 'Secret': ''}, 't')

    def test_the_owner_step_writes_the_name_the_documents_use(self):
        was = server.store.owner().get('owner')
        try:
            self.assertEqual(c.put('/api/owner', json={'name': 'Dana Example',
                                                       'email': 'dana@example.org'}).status_code, 200)
            self.assertTrue(_step(c.get('/api/setup').json(), 'owner')['done'])
            self.assertEqual(server.store.owner()['owner_first'], 'Dana')   # what signs a reply
        finally:
            if was and was != 'the owner': c.put('/api/owner', json={'name': was})

    def test_connecting_a_brain_saves_it_and_only_counts_once_it_answers(self):
        """The test call is the point. A key that saved and does not work is exactly the state
        somebody discovers days later from a Timeline that never triaged anything."""
        self._reset()
        cid = server.store.get_connector_by_type('anthropic')['ConnectorId']
        r = c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'anthropic',
                                            'Name': 'Anthropic', 'Secret': 'sk-test', 'Active': True})
        self.assertEqual(r.status_code, 200)
        with mock.patch('taskuary.llm.test_ai', return_value='model responded: ok'):
            out = c.post(f'/api/connectors/{cid}/test', json={}).json()
        self.assertTrue(out['ok'], out)
        self.assertTrue(_step(c.get('/api/setup').json(), 'ai')['done'])

    def test_a_wrong_key_is_reported_and_leaves_the_step_undone(self):
        self._reset()
        cid = server.store.get_connector_by_type('anthropic')['ConnectorId']
        c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'anthropic', 'Name': 'Anthropic',
                                        'Secret': 'sk-wrong', 'Active': True})
        with mock.patch('taskuary.llm.test_ai', side_effect=RuntimeError('401 invalid x-api-key')):
            out = c.post(f'/api/connectors/{cid}/test', json={}).json()
        self.assertFalse(out['ok'])
        self.assertIn('401', out['detail'])          # the panel shows this verbatim
        self._reset()

    def test_connecting_a_mailbox_registers_the_source_that_makes_it_a_funnel(self):
        """A connector with no source behind it is half-connected. The IMAP test is what registers
        the mailbox, which is why the wizard tests rather than just saving."""
        self._reset()
        cid = server.store.get_connector_by_type('gmail')['ConnectorId']
        c.post('/api/connectors', json={'ConnectorId': cid, 'Type': 'gmail', 'Name': 'Gmail',
                                        'Secret': 'app-password',
                                        'ConfigJson': json.dumps({'address': 'dana@gmail.com'}),
                                        'Active': True})
        self.assertFalse(any(s['Channel'] == 'email' and s['Address'] == 'dana@gmail.com'
                             for s in server.store.list_sources(active_only=False)))
        with mock.patch('taskuary.imapmail.test_imap', return_value='logged in as dana@gmail.com') as t:
            def _register(store, conn):
                store.save_source({'Channel': 'email', 'Address': 'dana@gmail.com',
                                   'ConnectorId': conn['ConnectorId'], 'Active': 1}, 'connector-test')
                return 'logged in as dana@gmail.com'
            t.side_effect = _register
            self.assertTrue(c.post(f'/api/connectors/{cid}/test', json={}).json()['ok'])
        self.assertTrue(_step(c.get('/api/setup').json(), 'inbound')['done'])
        self._reset()


class TheOneStoredStepTests(unittest.TestCase):
    """Every other row reads real state. This one cannot: the defaults already work, so there is
    nothing to detect. Opening the page is what it asks for and what it records."""
    def _clear(self):
        server.store.set_setting(setup.SEEN_MODELS, '0', 't')

    def test_looking_at_the_page_is_what_ticks_it(self):
        self._clear()
        self.assertFalse(_step(c.get('/api/setup').json(), 'models')['done'])
        out = c.post('/api/setup/seen', json={'step': 'models'})
        self.assertEqual(out.status_code, 200)
        self.assertTrue(_step(out.json(), 'models')['done'])
        self.assertTrue(_step(c.get('/api/setup').json(), 'models')['done'])   # survives the next read

    def test_a_step_nobody_defined_is_refused_rather_than_silently_stored(self):
        """A typo'd step name that returns 200 is a row that can never tick and a setting nobody
        can find."""
        self.assertEqual(c.post('/api/setup/seen', json={'step': 'whatever'}).status_code, 422)

    def test_it_is_recorded_in_the_audit_like_every_other_setting(self):
        self._clear()
        c.post('/api/setup/seen', json={'step': 'models'})
        self.assertTrue(any(r['Action'] == 'setup_seen' for r in server.store.list_audit(limit=20)))

    def test_seeing_it_again_writes_nothing_new(self):
        """AiDefaults posts this on every mount of the models page - a second, third, hundredth
        visit must not keep appending audit rows for a fact that has not changed."""
        self._clear()
        c.post('/api/setup/seen', json={'step': 'models'})
        before = len(server.store.list_audit(limit=200))
        c.post('/api/setup/seen', json={'step': 'models'})
        c.post('/api/setup/seen', json={'step': 'models'})
        self.assertEqual(len(server.store.list_audit(limit=200)), before)


class TheAiRowCanBeTickedFromThePageItSendsYouToTests(unittest.TestCase):
    """The checklist's "Set up an AI" row links to the AI CLI agents page. CliPicker's `asBrain`
    branch was the only thing that ever wrote `triage_ai`, and it lived inside the wizard - so
    once that duplicate was deleted, installing and testing a CLI on the real page left the row
    grey with nothing on that page able to tick it. The first CLI that proves it works there
    becomes the brain, and only when none is chosen yet.

    EVERY TEST HERE ASSERTS THE OUTCOME, never the string that was written. The first version of
    this endpoint stored the CLI CONNECTION name (`cli:claude`) where every reader - `setup._ai`,
    `llm._build_llm`, `llm.make_cli_llm` - resolves an agent PROFILE with `get_agent`. Three tests
    that only compared the setting to `'cli:claude'` all passed while the row they exist to tick
    stayed grey and an install with a working API key lost its brain outright."""
    def _was(self):
        return server.store.get_settings().get('triage_ai') or ''

    def _restore(self, was):
        server.store.set_setting('triage_ai', was, 't')

    def _ai_row(self):
        return _step(setup.state(server.store), 'ai')

    def _profile_of(self, cli):
        """The worker the Settings brain picker would offer for this connection - '' if none."""
        from taskuary import agents as hub_agents
        return next((o['value'] for o in hub_agents.cli_agent_options(server.store) if o['cli'] == cli), '')

    def test_a_cli_with_a_profile_behind_it_actually_ticks_the_ai_row(self):
        """The whole point of the endpoint. `claude` is a connection; `coder` is the profile that
        runs it, and only the profile name resolves to anything."""
        was = self._was()
        try:
            server.store.set_setting('triage_ai', '', 't')
            out = c.post('/api/setup/adopt-brain', json={'cli': 'claude'})
            self.assertEqual(out.status_code, 200)
            self.assertTrue(out.json()['adopted'])
            self.assertEqual(self._was(), f'cli:{self._profile_of("claude")}')
            self.assertTrue(server.store.get_agent(self._was()[4:]), 'the stored name resolves')
            self.assertTrue(self._ai_row()['done'])
            self.assertTrue(_step(out.json(), 'ai')['done'], 'and the answer says so on the spot')
        finally:
            self._restore(was)

    def test_a_cli_no_profile_uses_stores_nothing_at_all(self):
        """gemini is a real connection with no seeded worker behind it. A dangling `cli:gemini`
        would be worse than the grey row: nothing resolves it, so it is not a brain, and it stops
        the auto-pick from finding the connector that was working."""
        was = self._was()
        try:
            server.store.set_setting('triage_ai', '', 't')
            self.assertEqual(self._profile_of('gemini'), '', 'this test needs a CLI with no profile')
            before = self._ai_row()['done']
            out = c.post('/api/setup/adopt-brain', json={'cli': 'gemini'})
            self.assertEqual(out.status_code, 200)
            self.assertFalse(out.json()['adopted'])
            self.assertEqual(self._was(), '', 'nothing was written')
            self.assertEqual(self._ai_row()['done'], before)
        finally:
            self._restore(was)

    def test_pressing_test_never_costs_an_install_the_brain_it_already_had(self):
        """The regression this endpoint shipped with: an API key that worked, `triage_ai` unset so
        the auto-pick found it, and one press of Test on the CLI page left `_build_llm` returning
        None - no brain at all. Press it on both kinds of connection; both must still build."""
        from taskuary import llm
        was, had = self._was(), server.store.get_connector_by_type('anthropic')
        try:
            server.store.save_connector({'ConnectorId': had['ConnectorId'], 'Secret': 'sk-x', 'Active': 1}, 't')
            for cli in ('gemini', 'claude'):
                server.store.set_setting('triage_ai', '', 't')
                self.assertIsNotNone(llm._build_llm(server.store), f'before {cli}')
                self.assertTrue(self._ai_row()['done'], f'before {cli}')
                c.post('/api/setup/adopt-brain', json={'cli': cli})
                self.assertIsNotNone(llm._build_llm(server.store), f'after {cli}')
                self.assertTrue(self._ai_row()['done'], f'after {cli}')
        finally:
            server.store.save_connector({'ConnectorId': had['ConnectorId'], 'Secret': '',
                                         'Active': int(had['Active'] or 0)}, 't')
            self._restore(was)

    def test_a_second_clis_test_does_not_steal_the_brain_from_the_first(self):
        was = self._was()
        try:
            server.store.set_setting('triage_ai', '', 't')
            c.post('/api/setup/adopt-brain', json={'cli': 'claude'})
            first = self._was()
            out = c.post('/api/setup/adopt-brain', json={'cli': 'codex'})
            self.assertFalse(out.json()['adopted'])
            self.assertEqual(self._was(), first)             # the first one, untouched
            self.assertTrue(self._ai_row()['done'])
        finally:
            self._restore(was)

    def test_a_brain_the_owner_already_picked_is_never_stomped(self):
        was = self._was()
        try:
            server.store.set_setting('triage_ai', 'connector:anthropic-42', 't')
            out = c.post('/api/setup/adopt-brain', json={'cli': 'claude'})
            self.assertFalse(out.json()['adopted'])
            self.assertEqual(self._was(), 'connector:anthropic-42')
        finally:
            self._restore(was)


if __name__ == '__main__':
    unittest.main()


def test_a_connected_cli_with_no_worker_profile_is_an_ai_that_is_set_up():
    """A tester's install said "Set up an AI" while triage ran on a connected CLI (the owner, 2026-09-24:
    "It says AI not set up but it is"). The brain is found through agents.agent_row - a CLI CONNECTION is a brain
    even with no worker profile - and the checklist has to look it up the same way."""
    from unittest import mock
    from taskuary import config, setup
    from taskuary.store import MemoryStore
    s = MemoryStore()
    s.set_setting('triage_ai', 'cli:codex', 'test')
    assert s.get_agent('codex') is None                                  # no worker profile of that name
    with mock.patch.object(config, 'load', return_value={'cli_connections': {'codex': {'cmd': 'codex'}}}):
        ai = setup._ai(s)
    assert ai and ai.get('Type') == 'cli' and 'codex' in ai.get('Name', '')
