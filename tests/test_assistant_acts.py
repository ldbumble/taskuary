"""The assistant runs the app by name (the acts pack, 2026-09-18): a report run, paused, resumed, re-aimed,
edited or deleted; a setting set; a connection tested, paused, resumed; a script started - each proposed
from a CALL the model names, resolved through appfacts, run at once when the tiers say so, and put back
by the undo the receipt carries."""
import json, unittest
from unittest import mock

from taskuary import concierge, operations, server, toolcatalog
import tests.test_appfacts as A


def call(kind, **params):
    """A fake brain that answers with one CALL line."""
    line = 'CALL: ' + json.dumps({'kind': kind, 'params': params})
    return lambda system, user, max_tokens=None: f'On it.\n{line}'


class ActsTests(unittest.TestCase):
    def setUp(self):
        self.s = A.store()
        self.patch = mock.patch.object(server, 'store', self.s); self.patch.start()
        self.sid = A.AR['sid']
    def tearDown(self): self.patch.stop()

    def _turn(self, kind, **params):
        return concierge.say(self.s, 'do it', llm=call(kind, **params))

    def test_the_kinds_are_in_the_registry_and_the_catalogue_with_their_tiers(self):
        b = toolcatalog.block()
        for k in ('report.run', 'report.pause', 'report.resume', 'report.reach', 'report.edit', 'report.delete',
                  'setting.set', 'connection.test', 'connection.pause', 'connection.resume', 'script.start'):
            self.assertIn(k, operations.KINDS); self.assertIn(k, b)
        for k in ('report.run', 'setting.set', 'connection.pause', 'script.start'): self.assertTrue(toolcatalog.is_instant(k), k)
        self.assertFalse(toolcatalog.is_instant('report.delete'))                     # deleting asks first
        self.assertEqual(toolcatalog.valid('setting.set', {'setting': 'poll_minutes'}), 'setting.set needs value')

    def test_a_report_named_by_part_of_its_title_is_proposed_on_its_own_id_and_runs_at_once(self):
        out = self._turn('report.run', title='ar report')
        prop = out['proposal']
        self.assertEqual((prop['kind'], prop['target'], prop.get('auto')), ('report.run', self.sid, True))
        self.assertIn('Monthly AR Report', out['say'])
        with mock.patch.object(server, '_rerun_report', return_value={'queued': True}) as rr:
            done = concierge.run_proposal(self.s, prop)
        self.assertEqual(done['status'], 'done'); rr.assert_called_once()
        self.assertIn('is running', concierge.receipt(self.s, done))

    def test_a_name_that_finds_nothing_proposes_nothing_and_lists_what_exists(self):
        out = self._turn('report.run', title='payroll')
        self.assertIsNone(out.get('proposal')); self.assertIn('Monthly AR Report', out['say'])
        out = self._turn('connection.pause', name='warpdrive')
        self.assertIsNone(out.get('proposal')); self.assertIn('No connection by that name', out['say'])
        # ...while a catalogue card that is OFF is still nameable: resuming it is the whole point
        self.assertEqual(self._turn('connection.resume', name='zoho invoice')['proposal']['kind'], 'connection.resume')

    def test_pause_and_resume_flip_the_clock_and_the_receipt_carries_the_undo(self):
        done = concierge.run_proposal(self.s, self._turn('report.pause', title='ar report')['proposal'])
        self.assertFalse(self.s.get_source(self.sid)['Active'])
        self.assertEqual(done['outcome']['undo']['kind'], 'report.resume')
        line = concierge.receipt(self.s, done)
        self.assertIn('off its clock', line); self.assertIn('Undo: Resume Monthly AR Report', line)
        # ...and "undo" from a phone puts it back, once
        self.assertIn('back on its clock', concierge.undo_last(self.s))
        self.assertTrue(self.s.get_source(self.sid)['Active'])
        self.assertIn('Nothing to undo', concierge.undo_last(self.s))

    def test_reach_and_edit_change_the_config_and_can_be_put_back(self):
        done = concierge.run_proposal(self.s, self._turn('report.reach', title='ar report', reach='wrong')['proposal'])
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual(cfg['reach'], 'wrong'); self.assertEqual(done['outcome']['undo']['params'], {'reach': 'always'})
        self.assertIsNone(self._turn('report.reach', title='ar report', reach='sometimes').get('proposal'))   # not a reach word
        done = concierge.run_proposal(self.s, self._turn('report.edit', title='ar report', config={'daily_at': '08:30'})['proposal'])
        self.assertEqual(json.loads(self.s.get_source(self.sid)['ConfigJson'])['daily_at'], '08:30')
        self.assertEqual(done['outcome']['undo']['params'], {'config': {'daily_at': '07:00'}})

    def test_delete_asks_first_and_then_deletes(self):
        out = self._turn('report.delete', title='ar report')
        self.assertFalse(out['proposal'].get('auto')); self.assertIn('confirm below', out['say'])
        concierge.run_proposal(self.s, out['proposal'])
        self.assertIsNone(self.s.get_source(self.sid))

    def test_a_setting_by_label_is_validated_against_the_schema_and_undone_to_its_old_value(self):
        done = concierge.run_proposal(self.s, self._turn('setting.set', label='intent triage', value='off')['proposal'])
        self.assertEqual(self.s.get_settings()['intent_classify_enabled'], '0')
        self.assertEqual(done['outcome']['undo']['params'], {'setting': 'intent_classify_enabled', 'value': '1'})
        line = concierge.receipt(self.s, done)
        self.assertIn('Intent triage (Triage & routing): off', line); self.assertIn('Undo: Put Intent triage back to on', line)
        bad = concierge.run_proposal(self.s, self._turn('setting.set', setting='poll_minutes', value='often')['proposal'])
        self.assertEqual(bad['status'], 'error'); self.assertIn('takes a number', bad['error'])
        self.assertEqual(self.s.get_settings()['poll_minutes'], '10')
        self.assertIsNone(self._turn('setting.set', label='warp drive', value='on').get('proposal'))

    def test_connections_pause_resume_and_test(self):
        cid = next(c['connector_id'] for c in __import__('taskuary.appfacts', fromlist=['x']).connections(self.s) if c['name'] == 'Uri mailbox')
        done = concierge.run_proposal(self.s, self._turn('connection.pause', name='uri mailbox')['proposal'])
        self.assertFalse(self.s.get_connector(cid)['Active']); self.assertEqual(done['outcome']['undo']['kind'], 'connection.resume')
        concierge.run_proposal(self.s, self._turn('connection.resume', name='uri mailbox')['proposal'])
        self.assertTrue(self.s.get_connector(cid)['Active'])
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True, 'detail': 'signed in as Uri'}):
            done = concierge.run_proposal(self.s, self._turn('connection.test', name='uri mailbox')['proposal'])
        self.assertIn('answered: signed in as Uri', concierge.receipt(self.s, done))

    def test_a_script_is_named_and_the_outcome_says_which(self):
        done = concierge.run_proposal(self.s, self._turn('script.start', name='set up taskuary')['proposal'])
        self.assertEqual(done['outcome']['script'], 'set up Taskuary')
        self.assertIsNone(self._turn('script.start', name='dance').get('proposal'))

    def test_a_run_asked_from_a_chat_reports_back_to_that_chat(self):
        from taskuary import remote_assistant
        sent = []
        with mock.patch.object(remote_assistant, 'send', lambda store, ch, chat, text, connector_id=None: sent.append((ch, chat, text))), \
             mock.patch.object(server, 'run_report_source', return_value={'summary': '3 invoices over 30 days', 'subject': 'Monthly AR Report - 3 rows'}), \
             mock.patch.object(server, '_spawn_rerun', lambda fn: fn()):                       # the work, inline
            remote_assistant._ASKING.chat = {'channel': 'whatsapp', 'chat': '1555@s.whatsapp.net', 'connector_id': 7}
            try: concierge.run_proposal(self.s, self._turn('report.run', title='ar report')['proposal'])
            finally: remote_assistant._ASKING.chat = None
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][:2], ('whatsapp', '1555@s.whatsapp.net'))
        self.assertIn('Monthly AR Report landed: 3 invoices over 30 days', sent[0][2])

    def test_the_regex_settings_table_is_gone(self):
        self.assertFalse(hasattr(concierge, 'SWITCH_ASKS')); self.assertFalse(hasattr(concierge, 'switch_ask'))


if __name__ == '__main__':
    unittest.main()


class AuditAndPhoneTests(unittest.TestCase):
    def setUp(self):
        self.s = A.store()
        self.patch = mock.patch.object(server, 'store', self.s); self.patch.start()
    def tearDown(self): self.patch.stop()

    def test_what_the_assistant_changed_is_listed_with_the_undo_still_on_offer(self):
        from fastapi.testclient import TestClient
        done = concierge.run_proposal(self.s, concierge.say(self.s, 'x', llm=call('setting.set', label='intent triage', value='off'))['proposal'])
        concierge.receipt(self.s, done)
        c = TestClient(server.app)
        j = c.get('/api/audit/assistant').json()
        self.assertEqual(j['data'][0]['entity'], 'setting'); self.assertEqual(j['data'][0]['detail']['to'], '0')
        self.assertTrue(j['undo'] and j['undo']['id'])
        r = c.post(f"/api/operations/{j['undo']['id']}/execute", json={'version': j['undo']['version']}).json()
        self.assertEqual(r['status'], 'done'); self.assertEqual(self.s.get_settings()['intent_classify_enabled'], '1')
        self.assertIsNone(c.get('/api/audit/assistant').json()['undo'])            # once

    def test_set_up_from_a_phone_opens_on_the_connections(self):
        from taskuary import remote_assistant
        words = remote_assistant.script_words(self.s, 'set up Taskuary')
        self.assertIn('what is connected', words); self.assertIn('Uri mailbox (outlook)', words); self.assertIn('catalogue, off', words)
        self.assertIn('sentence', remote_assistant.script_words(self.s, 'set up a report'))
