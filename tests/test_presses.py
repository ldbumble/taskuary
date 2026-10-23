"""EVERY PRESS, KEPT (the Advisor and memory design, phase B, 2026-10-23): a press on any surface - the desk, the Tasks tab, the phone -
is one advice_press row whether or not anything was lit: the surface, what it had lit, the other live buttons (a press with none is no
choice), and what the item was and whom it was from. A personal mailbox's mail is never kept, and the owner's words for a draft are."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import advisor, learn, presses, remote_assistant, server
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail


def _row(s, i): return s._one('SELECT * FROM advice_press WHERE Id=?', (i,))


class PressTests(_Rail):
    def test_a_press_with_nothing_lit_is_kept_with_its_surface_and_what_else_was_live(self):
        s = MemoryStore(); t = self._stopped_task(s)
        i = advisor.press(s, f'task:{t}', None, 'done', surface='desk', lit='', live=['continue', 'next', 'done'])
        r = _row(s, i)
        self.assertEqual((r['Surface'], r['Pressed'], r['Lit'], r['Advised'], r['Match'], r['Choice']), ('desk', 'close', '', None, 0, 1))
        self.assertEqual(json.loads(r['Live']), ['continue', 'next'])          # the pressed one is not its own alternative
        self.assertEqual((r['SenderDomain'], r['Scope'], r['Repo']), ('northwind.example', 'northwind.example', ''))
        self.assertIsNone(s.get_setting('learn_pending'), 'no line was shown, so nothing was corrected')

    def test_a_press_with_no_other_button_is_no_choice_and_teaches_no_move(self):
        s = MemoryStore(); t = self._stopped_task(s)
        i = advisor.press(s, f'task:{t}', None, 'next', lit='next', live=['next'])
        self.assertEqual((_row(s, i)['Choice'], _row(s, i)['Match']), (0, 1))
        self.assertEqual(learn.move_rows(s), {}, 'a press with nothing else to press says nothing about what the owner would pick')
        self.assertEqual(presses.rows(s, choice=True), [])
        self.assertEqual([r['pressed'] for r in presses.rows(s, choice=False)], ['next'])

    def test_the_same_press_told_twice_is_one_row(self):
        # the row's press and the card's handler it runs both say so (actionRow.announce): one press, one row, one correction
        s = MemoryStore(); t = self._stopped_task(s)
        a = advisor.press(s, f'task:{t}', 'continue', 'done', live=['continue'])
        b = advisor.press(s, f'task:{t}', 'continue', '12:done', live=['continue'])
        self.assertEqual(a, b)
        self.assertEqual(s._one('SELECT COUNT(*) n FROM advice_press')['n'], 1)
        self.assertFalse(s.get_setting('learn_pending'), 'a press teaches the Advisor, never the reflection that writes what triage reads (2026-10-23)')
        self.assertNotEqual(advisor.press(s, f'task:{t}', None, 'done', surface='task', live=['continue']), a, 'another surface is another press')

    def test_the_tasks_tab_left_to_say_what_it_drew_is_read_off_the_row_without_next(self):
        s = MemoryStore(); t = self._stopped_task(s)
        r = _row(s, advisor.press(s, f'task:{t}', None, 'done', surface='task', lit='done'))
        live = json.loads(r['Live'])
        self.assertTrue(live and 'next' not in live, live)
        self.assertEqual((r['Surface'], r['Lit'], r['Match'], r['Choice']), ('task', 'close', 1, 1))

    def test_an_unknown_surface_is_the_desk_and_a_key_with_nothing_behind_it_keeps_nothing(self):
        s = MemoryStore(); t = self._stopped_task(s)
        self.assertEqual(_row(s, advisor.press(s, f'task:{t}', None, 'done', surface='tablet', live=['next']))['Surface'], 'desk')
        self.assertEqual(advisor.press(s, 'meeting:3', None, 'next', surface='phone'), 0)

    def test_without_a_lit_verb_the_advisors_own_standing_line_is_what_was_lit(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rev = advisor.revision(s, 'task', t)
        s._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,CountJson,EvidenceJson,CreatedAt) VALUES '
                "('task',?,?,'shown',?,1,'x','continue','Continue','[0,0]','[]','2026-10-23 09:00:00')", (t, f'task:{t}', rev))
        r = _row(s, presses.record(s, f'task:{t}', 'continue', 'desk', live=['next']))
        self.assertEqual((r['Advised'], r['Lit'], r['Match']), ('continue', 'continue', 1))

    def test_personal_mail_is_never_kept(self):
        # the owner, 2026-10-23: "nothing learned from personal mail" - a mailbox marked personal on its source
        s = MemoryStore(); t = self._stopped_task(s)
        s.save_source({'Channel': 'email', 'Address': 'alex@home.example', 'ConfigJson': json.dumps({'personal': True}), 'Active': 1}, 'test')
        s._exec("UPDATE message SET SourceName='alex@home.example' WHERE TaskId=?", (t,))
        self.assertEqual(advisor.press(s, f'task:{t}', None, 'done', live=['next']), 0)
        self.assertEqual(s._one('SELECT COUNT(*) n FROM advice_press')['n'], 0)
        s._exec("UPDATE message SET SourceName='alex@northwind.example' WHERE TaskId=?", (t,))     # a work mailbox, unmarked: kept
        self.assertTrue(advisor.press(s, f'task:{t}', None, 'done', live=['next']))

    def test_the_log_reads_back_by_surface_and_moment(self):
        s = MemoryStore(); t = self._stopped_task(s)
        advisor.press(s, f'task:{t}', None, 'done', surface='desk', lit='', live=['next'])
        advisor.press(s, f'task:{t}', None, 'continue', surface='phone', lit='continue', live=['next'])
        got = presses.rows(s, domain='northwind.example')
        self.assertEqual([(r['surface'], r['pressed'], r['lit'], r['choice']) for r in got], [('desk', 'close', '', True), ('phone', 'continue', 'continue', True)])
        self.assertEqual([r['pressed'] for r in presses.rows(s, surface='phone')], ['continue'])
        self.assertEqual(presses.rows(s, days=1, kind=got[0]['kind'], surface='desk')[0]['live'], ['next'])
        with self.assertRaises(ValueError): presses.rows(s, colour='blue')

    def test_the_endpoint_takes_the_surface_what_was_lit_and_what_was_live(self):
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(server, 'store', s):
            got = TestClient(server.app).post('/api/advice/press', json={'key': f'task:{t}', 'pressed': 'remind', 'surface': 'task',
                                                                         'lit': 'done', 'live': ['done', 'nat']}).json()
        r = _row(s, got['id'])
        self.assertEqual((r['Surface'], r['Pressed'], r['Lit'], json.loads(r['Live'])), ('task', 'defer', 'close', ['close', 'remove']))


class PhonePickTests(_Rail):
    def test_a_pick_is_a_press_with_button_one_lit(self):
        s = MemoryStore(); t = self._stopped_task(s)
        key = f'task:{t}'
        acts = {'Continue': {'t': 'verb', 'verb': 'continue', 'key': key}, 'Next': {'t': 'next'}, 'Mark done': {'t': 'verb', 'verb': 'close', 'key': key},
                'More': {'t': 'page', 'at': 1}}
        offered = ['Continue', 'Next', 'Mark done', 'More']
        i = remote_assistant.note_pick(s, acts['Mark done'], {'key': key, 'tid': t}, offered, acts)
        r = _row(s, i)
        self.assertEqual((r['Surface'], r['Pressed'], r['Lit'], r['Match']), ('phone', 'close', 'continue', 0))
        self.assertEqual(json.loads(r['Live']), ['continue', 'next'])
        self.assertTrue(remote_assistant.note_pick(s, acts['Next'], {'key': key, 'tid': t}, offered, acts))

    def test_a_page_a_cancel_or_the_second_step_of_a_question_is_not_a_press(self):
        s = MemoryStore(); t = self._stopped_task(s)
        for act in ({'t': 'page', 'at': 1}, {'t': 'menu'}, {'t': 'stay', 'key': f'task:{t}'}, {'t': 'remind', 'tid': t, 'until': 'tomorrow'},
                    {'t': 'redraft', 'key': f'task:{t}', 'how': 'shorter'}, {'t': 'confirm', 'id': 'op1'}):
            self.assertEqual(remote_assistant.note_pick(s, act, {'key': f'task:{t}'}, [], {}), 0, act)
        self.assertEqual(s._one('SELECT COUNT(*) n FROM advice_press')['n'], 0)

    def test_the_phone_records_the_pick_before_it_runs(self):
        s = MemoryStore(); t = self._stopped_task(s)
        key = f'task:{t}'
        s.set_setting('remote_acts:whatsapp:me', json.dumps({'Next': {'t': 'next'}}), 'test')
        seen = []
        with mock.patch.object(remote_assistant, 'acts_for', lambda *_a: {'Next': {'t': 'next'}}), \
             mock.patch.object(remote_assistant, 'resolve_index', lambda *_a, **_k: ('Next', True)), \
             mock.patch('taskuary.concierge.restore_current', lambda *_a: {'key': key, 'tid': t}), \
             mock.patch.object(remote_assistant, 'run_act', lambda *_a, **_k: seen.append(s._one('SELECT Pressed FROM advice_press')) or 'ok'), \
             mock.patch.object(remote_assistant, 'send', lambda *a, **k: None):
            s.set_setting(f'{remote_assistant.OFFERED_KEY}:whatsapp:me', json.dumps(['Next']), 'test')
            remote_assistant.respond(s, 'whatsapp', 'me', '1', 1)
        self.assertEqual(seen, [{'Pressed': 'next'}])


class InstructionTests(_Rail):
    def _mail(self, s):
        t = s.create_task({'Title': 'Invoice question', 'Status': 'open', 'Kind': 'reply'}, 'owner')
        mid = s.add_message({'ConversationId': 'c-inv', 'Channel': 'email', 'Subject': 'Invoice', 'FromEmail': 'erin@vendor.example',
                             'FromName': 'Erin Blake', 'BodyText': 'When do you pay?', 'Status': 'routed', 'TaskId': t})
        return t, mid

    def test_the_owners_words_for_a_draft_are_kept_on_the_review_and_read_back_by_person(self):
        s = MemoryStore(); t, mid = self._mail(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
             mock.patch('taskuary.responder.write_draft', lambda *a, **k: 'Hi Erin, Friday.'):
            c = TestClient(server.app)
            rid = c.post(f'/api/messages/{mid}/reply', json={'instruction': 'say we pay on Friday'}).json()['reviewId']
            c.post(f'/api/reviews/{rid}/draft', json={'instruction': 'say we pay on Friday'})     # the same words handed on: kept once
            c.post(f'/api/reviews/{rid}/draft', json={'instruction': 'shorter'})
            c.post(f'/api/messages/{mid}/reply', json={'redraft': True})                         # a redraft with no words keeps what was said
        said = json.loads(s.get_review(rid)['Instructions'])
        self.assertEqual([x['text'] for x in said], ['say we pay on Friday', 'shorter'])
        got = presses.instructions(s, to='erin@vendor.example')
        self.assertEqual([(x['rid'], x['domain'], x['text']) for x in got], [(rid, 'vendor.example', 'say we pay on Friday'), (rid, 'vendor.example', 'shorter')])
        self.assertEqual(presses.instructions(s, domain='northwind.example'), [])

    def test_a_chases_brief_is_the_apps_words_not_the_owners(self):
        s = MemoryStore(); t, mid = self._mail(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
             mock.patch('taskuary.responder.write_draft', lambda *a, **k: 'Hi Erin'):
            rid = server.open_reply(mid, server.OpenReplyBody(instruction='a short chase to erin', app_words=True))['reviewId']
        self.assertFalse(s.get_review(rid).get('Instructions'))

    def test_an_outbound_redraft_follows_the_instruction(self):
        from taskuary import outbox
        s = MemoryStore()
        t = s.create_task({'Title': 'Results to Ray', 'Status': 'open'}, 'owner')
        rid = s.add_review({'TaskId': t, 'Kind': 'draft', 'Status': 'pending', 'Deliver': json.dumps({'channel': 'email', 'to': ['ray@northwind.example']})})
        with mock.patch.object(outbox, 'draft_message', lambda store, ch, to, about, **k: about) as _d:
            got = outbox.redraft_review(s, s.get_review(rid), resolution='', instruction="THE OWNER'S INSTRUCTION: warmer")
        self.assertIn('warmer', got)
