"""The assistant reaches the app by name (the acts pack, 2026-09-18): a report run, paused, resumed, re-aimed, edited or deleted; a
setting set; a connection tested, paused, resumed; a script started - each named by a CALL and resolved through appfacts.

On the desk each one opens the page that holds it, its knob or button to press (the owner, 2026-10-19: "the assistant again should just
be a router ... like the assistant surfaces a settings ui"); a phone chat, which has no page, answers a proposal yes or no - and the
handlers it runs are the same ones the pages' buttons run. Nothing carries an undo any more ("no take it back button. hate that")."""
import json, unittest
from unittest import mock

from taskuary import concierge, operations, server, toolcatalog
import tests.test_appfacts as A


def call(kind, **params):
    """A fake brain that answers with one CALL line."""
    line = 'CALL: ' + json.dumps({'kind': kind, 'params': params})
    return lambda system, user, max_tokens=None: f'On it.\n{line}'


class DeskTests(unittest.TestCase):
    """The desk: the page, opened beside the answer - nothing changed on the words."""
    def setUp(self):
        self.s = A.store(); self.sid = A.AR['sid']

    def _turn(self, kind, **params): return concierge.say(self.s, 'do it', llm=call(kind, **params))

    def test_a_report_act_opens_the_report(self):
        # ...Run now and the switch at its row on the shelf, Remove in its builder: a report's builder has neither (2026-11-02)
        for kind, at in (('report.run', '#report=reports'), ('report.pause', '#report=reports'), ('report.delete', f'#report={self.sid}')):
            out = self._turn(kind, title='ar report')
            self.assertNotIn('proposal', out); self.assertEqual(out['open'], at, kind)
            self.assertIn('Monthly AR Report', out['say'])
        self.assertTrue(self.s.get_source(self.sid)['Active'])                         # paused by nobody

    def test_over_its_open_builder_run_and_pause_press_its_own_header(self):
        # the owner, 2026-11-02: a report's builder wears its row's Run now and switch - "run it" there presses them, never the shelf
        sw = 'Monthly AR Report on its clock'
        view = {'area': 'reports', 'item': {'kind': 'report', 'id': self.sid}, 'fields': [{'key': 'sw', 'label': sw, 'kind': 'switch', 'value': 'on'}],
                'buttons': [{'id': 'run_now', 'label': 'Run now'}, {'id': 'remove_report', 'label': 'Remove report'}]}
        say = lambda kind, v=view: concierge.say(self.s, 'do it', llm=call(kind, title='ar report'), view=v)
        out = say('report.run')
        self.assertEqual(out['view_ops'], [{'op': 'press', 'button': 'run_now'}]); self.assertNotIn('open', out); self.assertIn('Run now', out['say'])
        self.assertEqual(say('report.pause')['view_ops'], [{'op': 'set', 'field': 'sw', 'value': 'off'}])
        self.assertIn('already on', say('report.resume')['say'])
        # ...another report's page, or a run already going (Run now greyed), is the road it always was
        self.assertEqual(say('report.run', {**view, 'item': {'kind': 'report', 'id': self.sid + 99}})['open'], '#report=reports')
        self.assertEqual(say('report.run', {**view, 'buttons': [{'id': 'run_now', 'label': 'Run now', 'enabled': False}]})['open'], '#report=reports')
        self.assertTrue(self.s.get_source(self.sid)['Active'])                         # the page's own handlers act, nothing here

    def test_who_gets_it_rides_the_link_into_its_box_and_an_unsure_name_is_one_question(self):
        out = self._turn('report.route', title='ar report', line='send', how='always', to='Gail@Northwind.example')
        self.assertEqual(out['open'], f'#report={self.sid}&line=send&to=gail@northwind.example&how=always')
        self.assertIn('gail@northwind.example in who gets it', out['say'])
        self.assertIsNone(json.loads(self.s.get_source(self.sid)['ConfigJson']).get('deliver'))            # its Save is the owner's
        # two people answer to the name: asked, never guessed - and nothing opened or set
        two = [{'to': 'gmoreno@northwind.example', 'name': 'Gail Moreno'}, {'to': 'gail@vendor.example', 'name': 'Gail Park'}]
        with mock.patch('taskuary.peoplesearch.known', return_value=two):
            self.assertEqual(concierge.route_to(self.s, 'Gail')[0], '')
            self.assertIn('Gail Park (gail@vendor.example)', concierge.route_to(self.s, 'Gail')[1])
            self.assertEqual(concierge.route_to(self.s, 'gail moreno'), ('gmoreno@northwind.example', ''))
            out = self._turn('report.route', title='ar report', line='send', how='always', to='Gail')
        self.assertNotIn('open', out)
        self.assertIn('Nobody called Zed', concierge.route_to(self.s, 'Zed')[1])

    def test_a_draft_with_no_mailbox_to_send_it_says_so(self):
        # the visual audit, 2026-11-13: "Drafted it on TQ-0002 - it waits for your Send" over a card whose only button was Connect email
        tid = self.s.create_task({'Title': 'chat', 'Kind': 'general', 'Status': 'open'}, 'owner')
        made = {'taskId': tid + 1, 'ref': 'TQ-0099', 'draft': 'Hi Gail'}
        params = {'channel': 'email', 'to': 'gail@northwind.example', 'about': 'the Q3 numbers'}
        with mock.patch('taskuary.outbox.compose', return_value=made), mock.patch('taskuary.outbound.send_channels', return_value=[]):
            said = concierge._made_now(self.s, tid, 'outbox', params)['say']
        self.assertIn('Connect email', said); self.assertNotIn('waits for your Send', said)
        with mock.patch('taskuary.outbox.compose', return_value=made), mock.patch('taskuary.outbound.send_channels', return_value=['email']):
            self.assertIn('waits for your Send', concierge._made_now(self.s, tid, 'outbox', params)['say'])

    def test_a_name_with_its_address_is_that_address(self):
        # the visual audit, 2026-11-13: "draft a reminder to Gail Moreno <gail@northwind.example>" - the address was in the ask, and the
        # Assistant said nobody by that name had written here and left To empty
        self.assertEqual(concierge.route_to(self.s, 'Gail Moreno <Gail@Northwind.example>'), ('gail@northwind.example', ''))
        self.assertEqual(concierge.send_to(self.s, 'email', '"Moreno, Gail" <gail@northwind.example>'), ('email', 'gail@northwind.example', ''))
        self.assertIn('Nobody called', concierge.route_to(self.s, 'Gail Moreno <nobody>')[1])

    def test_a_setting_opens_its_group_with_the_knob_named(self):
        out = self._turn('setting.set', label='sort new mail with AI', value='off')
        self.assertTrue(out['open'].startswith('#settings=config&group=How%20mail%20is%20sorted&key=intent_classify_enabled'), out['open'])
        self.assertIn('Sort new mail with AI', out['say']); self.assertNotEqual(self.s.get_settings()['intent_classify_enabled'], '0')

    def test_a_connection_opens_its_card(self):
        out = self._turn('connection.pause', name='alex mailbox')
        self.assertEqual(out['open'], '#connector=outlook'); self.assertIn('switch it off', out['say'])

    def test_a_script_is_a_road_not_a_proposal(self):
        out = self._turn('script.start', name='set up a report')
        self.assertEqual(out['new']['kind'], 'report')
        self.assertIsNone(self._turn('script.start', name='set up taskuary').get('proposal'))   # setup is the Setup button, no script


class ActsTests(unittest.TestCase):
    """The phone's road: the proposal and the handler it runs on the yes."""
    def setUp(self):
        self.s = A.store()
        self.patch = mock.patch.object(server, 'store', self.s); self.patch.start()
        self.sid = A.AR['sid']
    def tearDown(self): self.patch.stop()

    def _turn(self, kind, **params):
        with concierge.delivering(concierge.PHONE): return concierge.say(self.s, 'do it', llm=call(kind, **params))

    def test_the_kinds_are_in_the_registry_and_the_catalogue(self):
        b = toolcatalog.block()
        for k in ('report.run', 'report.pause', 'report.resume', 'report.route', 'report.edit', 'report.delete',
                  'setting.set', 'connection.test', 'connection.pause', 'connection.resume', 'script.start'):
            self.assertIn(k, operations.KINDS); self.assertIn(k, b)
        self.assertEqual(toolcatalog.valid('setting.set', {'setting': 'poll_minutes'}), 'setting.set needs value')

    def test_a_report_named_by_part_of_its_title_is_proposed_on_its_own_id_and_waits_for_the_yes(self):
        out = self._turn('report.run', title='ar report')
        prop = out['proposal']
        self.assertEqual((prop['kind'], prop['target'], prop.get('auto')), ('report.run', self.sid, None))
        self.assertIn('Monthly AR Report', out['say'])
        lands = 'Its result shows under Reports when it is done. If it fails, the bell says why.'
        with mock.patch.object(server, '_rerun_report', return_value={'queued': True, 'lands': lands}) as rr:
            done = concierge.run_proposal(self.s, prop)
        self.assertEqual(done['status'], 'done'); rr.assert_called_once()
        # where it shows is the report's own route (reports.run_lands), never "it comes back here"
        self.assertIn('is running', concierge.receipt(self.s, done)); self.assertIn(lands, concierge.receipt(self.s, done))
        self.assertNotIn('comes back here', concierge.receipt(self.s, done))

    def test_a_name_that_finds_nothing_proposes_nothing_and_lists_what_exists(self):
        # ...the miss goes to the model, which says it in its own words (7683dad09): the reports that exist are in what it is handed
        seen = []
        def brain(system, user, max_tokens=None): seen.append(user); return call('report.run', title='payroll')(system, user)
        with concierge.delivering(concierge.PHONE): out = concierge.say(self.s, 'do it', llm=brain)
        self.assertIsNone(out.get('proposal')); self.assertTrue(any('Monthly AR Report' in u for u in seen[1:]), seen[1:])
        seen.clear()
        def brain(system, user, max_tokens=None): seen.append(user); return call('connection.pause', name='warpdrive')(system, user)
        with concierge.delivering(concierge.PHONE): out = concierge.say(self.s, 'do it', llm=brain)
        self.assertIsNone(out.get('proposal')); self.assertTrue(any('No connection by that name' in u for u in seen[1:]), seen[1:])
        # ...while a catalogue card that is OFF is still nameable: resuming it is the whole point
        self.assertEqual(self._turn('connection.resume', name='zoho invoice')['proposal']['kind'], 'connection.resume')

    def test_a_miss_goes_back_to_the_model_which_looks_the_name_up_and_calls_again(self):
        """"No report by that name - ..." is written for the model; it reached the owner word for word (2026-09-24)."""
        turns, seen = iter(['CALL: ' + json.dumps({'kind': 'report.pause', 'params': {'title': 'the morning money one'}}),
                            'CALL: ' + json.dumps({'kind': 'reports.list', 'params': {}}),
                            'Pausing it.\nCALL: ' + json.dumps({'kind': 'report.pause', 'params': {'title': 'Monthly AR Report'}})]), []
        def brain(system, user, max_tokens=None): seen.append(user); return next(turns)
        with concierge.delivering(concierge.PHONE): out = concierge.say(self.s, 'stop the morning money report', llm=brain)
        self.assertEqual(out['proposal']['kind'], 'report.pause')
        self.assertIn('No report by that name', seen[1])                   # the model was told...
        self.assertNotIn('No report by that name', out['say'])             # ...the owner was not

    def test_pause_and_resume_flip_the_clock_and_the_receipt_says_so_with_no_undo(self):
        done = concierge.run_proposal(self.s, self._turn('report.pause', title='ar report')['proposal'])
        self.assertFalse(self.s.get_source(self.sid)['Active'])
        line = concierge.receipt(self.s, done)
        self.assertIn('off its clock', line); self.assertNotIn('Undo', line); self.assertNotIn('undo', done['outcome'])
        concierge.run_proposal(self.s, self._turn('report.resume', title='ar report')['proposal'])
        self.assertTrue(self.s.get_source(self.sid)['Active'])
        self.assertFalse(hasattr(concierge, 'undo_last'))

    def test_route_and_edit_change_the_config(self):
        """The Assistant edits the same route card the Reports page does - one line at a time (2026-09-27)."""
        concierge.run_proposal(self.s, self._turn('report.route', title='ar report', line='timeline', how='ai', when='an invoice is over 90 days')['proposal'])
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual(cfg['route']['timeline'], {'how': 'ai', 'when': 'an invoice is over 90 days'})
        self.assertIsNone(self._turn('report.route', title='ar report', line='timeline', how='sometimes').get('proposal'))   # not a way a line goes
        concierge.run_proposal(self.s, self._turn('report.edit', title='ar report', config={'daily_at': '08:30'})['proposal'])
        self.assertEqual(json.loads(self.s.get_source(self.sid)['ConfigJson'])['daily_at'], '08:30')

    def test_route_with_who_fills_the_cards_to_box(self):
        done = concierge.run_proposal(self.s, self._turn('report.route', title='ar report', line='send', how='always', to='gail@northwind.example')['proposal'])
        cfg = json.loads(self.s.get_source(self.sid)['ConfigJson'])
        self.assertEqual(cfg['deliver'], {'gate': 'review', 'channel': 'email', 'to': 'gail@northwind.example'})
        self.assertEqual(cfg['route']['send'], {'how': 'always'})
        self.assertIn('to gail@northwind.example', concierge.receipt(self.s, done))

    def test_delete_waits_for_the_yes_and_then_deletes(self):
        out = self._turn('report.delete', title='ar report')
        self.assertFalse(out['proposal'].get('auto')); self.assertIn(concierge.WAITS, out['say'])
        concierge.run_proposal(self.s, out['proposal'])
        self.assertIsNone(self.s.get_source(self.sid))

    def test_a_setting_by_label_is_validated_against_the_schema(self):
        done = concierge.run_proposal(self.s, self._turn('setting.set', label='sort new mail with AI', value='off')['proposal'])
        self.assertEqual(self.s.get_settings()['intent_classify_enabled'], '0')
        self.assertIn('Sort new mail with AI (How mail is sorted): off', concierge.receipt(self.s, done))
        bad = concierge.run_proposal(self.s, self._turn('setting.set', setting='poll_minutes', value='often')['proposal'])
        self.assertEqual(bad['status'], 'error'); self.assertIn('takes a number', bad['error'])
        self.assertEqual(self.s.get_settings()['poll_minutes'], '10')
        for odd in ('--5', 'nan', 'inf', '-5'):
            bad = concierge.run_proposal(self.s, self._turn('setting.set', setting='poll_minutes', value=odd)['proposal'])
            self.assertEqual(bad['status'], 'error'); self.assertIn('takes a number', bad['error'])
        self.assertEqual(self.s.get_settings()['poll_minutes'], '10')
        self.assertIsNone(self._turn('setting.set', label='warp drive', value='on').get('proposal'))

    def test_a_decimal_setting_keeps_its_decimals(self):
        concierge.run_proposal(self.s, self._turn('setting.set', setting='kb_semantic_min', value='0.6')['proposal'])
        self.assertEqual(self.s.get_settings()['kb_semantic_min'], '0.6')
        concierge.run_proposal(self.s, self._turn('setting.set', setting='poll_minutes', value='15.0')['proposal'])
        self.assertEqual(self.s.get_settings()['poll_minutes'], '15')

    def test_connections_pause_resume_and_test(self):
        cid = next(c['connector_id'] for c in __import__('taskuary.appfacts', fromlist=['x']).connections(self.s) if c['name'] == 'Alex mailbox')
        concierge.run_proposal(self.s, self._turn('connection.pause', name='alex mailbox')['proposal'])
        self.assertFalse(self.s.get_connector(cid)['Active'])
        concierge.run_proposal(self.s, self._turn('connection.resume', name='alex mailbox')['proposal'])
        self.assertTrue(self.s.get_connector(cid)['Active'])
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True, 'detail': 'signed in as Alex'}):
            done = concierge.run_proposal(self.s, self._turn('connection.test', name='alex mailbox')['proposal'])
        self.assertIn('answered: signed in as Alex', concierge.receipt(self.s, done))

    def test_a_script_is_named_and_the_outcome_says_which(self):
        done = concierge.run_proposal(self.s, self._turn('script.start', name='set up a report')['proposal'])
        self.assertEqual(done['outcome']['script'], 'set up a report')
        self.assertIsNone(self._turn('script.start', name='dance').get('proposal'))
        self.assertIsNone(self._turn('script.start', name='set up taskuary').get('proposal'))     # setup is the Setup button now

    def test_a_run_asked_from_a_chat_reports_back_to_that_chat(self):
        from taskuary import remote_assistant
        sent = []
        with mock.patch.object(remote_assistant, 'send', lambda store, ch, chat, text, connector_id=None: sent.append((ch, chat, text))), \
             mock.patch('taskuary.reports.run_report_source', return_value={'summary': '3 invoices over 30 days', 'subject': 'Monthly AR Report - 3 rows'}), \
             mock.patch.object(server, '_spawn_rerun', lambda fn: fn()):                       # the work, inline
            remote_assistant._ASKING.chat = {'channel': 'whatsapp', 'chat': '1555@s.whatsapp.net', 'connector_id': 7}
            try: concierge.run_proposal(self.s, self._turn('report.run', title='ar report')['proposal'])
            finally: remote_assistant._ASKING.chat = None
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][:2], ('whatsapp', '1555@s.whatsapp.net'))
        self.assertIn('Monthly AR Report landed: 3 invoices over 30 days', sent[0][2])

    def test_the_regex_settings_table_is_gone(self):
        self.assertFalse(hasattr(concierge, 'SWITCH_ASKS')); self.assertFalse(hasattr(concierge, 'switch_ask'))


class AuditAndPhoneTests(unittest.TestCase):
    def setUp(self):
        self.s = A.store()
        self.patch = mock.patch.object(server, 'store', self.s); self.patch.start()
    def tearDown(self): self.patch.stop()

    def test_what_the_assistant_changed_is_listed_as_a_record(self):
        from fastapi.testclient import TestClient
        with concierge.delivering(concierge.PHONE):
            prop = concierge.say(self.s, 'x', llm=call('setting.set', label='sort new mail with AI', value='off'))['proposal']
        concierge.receipt(self.s, concierge.run_proposal(self.s, prop))
        j = TestClient(server.app).get('/api/audit/assistant').json()
        self.assertEqual(j['data'][0]['entity'], 'setting'); self.assertEqual(j['data'][0]['detail']['to'], '0')
        self.assertNotIn('undo', j)

    def test_setting_taskuary_up_from_a_phone_names_the_setup_button(self):
        from taskuary import remote_assistant
        self.assertIn('Setup button', remote_assistant.script_words(self.s, 'set up Taskuary'))
        with mock.patch('taskuary.capabilities.has_ai', return_value=True):        # with no AI it says so (test_phone_approved)
            self.assertIn('sentence', remote_assistant.script_words(self.s, 'set up a report'))


if __name__ == '__main__':
    unittest.main()
