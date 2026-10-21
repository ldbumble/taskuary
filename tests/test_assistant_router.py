"""The Assistant on the desk is a router (the owner, 2026-10-19: "no take it back button. hate that. the assistant again should just be
a router to actions or answer quick questions about things ... all work goes to agents, it brings up tasks/settings/action buttons" and
"it should just surface the correct button").

A typed ask that means an act brings its item up with the row's OWN button for it lit (`light`), or opens the page that holds it
(`open`), or writes a new job into New (`new`) - and changes nothing until the owner presses. No proposal card is drawn from a typed
ask on the desk; a phone chat, which has no buttons, keeps its text yes/no.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import buttons, concierge, funnel, ingest, operations, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('team_domains', 'northwind.example', 't'); s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.set_setting('poll_minutes', '5', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    return s


def triage(system, user, **kw): return json.dumps({'intent': 'task', 'why': 'she asked', 'kind': 'task'})


def arrive(s, subject='Can you send the May close numbers?', who='Erin Blake', email='erin@vendor.example'):
    msg = {'external_id': f'x:{subject}', 'channel': 'email', 'conversation_id': f'c:{subject}', 'subject': subject, 'from_name': who,
           'from_email': email, 'sent_at': ago(1), 'body': 'Could you send me the May close numbers by Friday?',
           'to': ['alex@northwind.example'], 'source_name': 'alex@northwind.example'}
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, msg, llm=triage)


def on_table(s):
    out = arrive(s)
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        item = funnel.build(s, keep_surfaced=True)['items'][0]
    return out['task_id'], item


def say(s, text, key, model):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(ingest, '_spawn') as spawn:
        out = concierge.say(s, text, key=key, llm=lambda *a, **k: model)
    return out, spawn


def proposals(s): return [r for r in s._rows("SELECT * FROM operation")] if hasattr(s, '_rows') else []


class DeskRoutes(unittest.TestCase):
    def test_mark_this_done_lights_mark_done_and_changes_nothing_until_pressed(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'mark this done', item['key'], 'Sure.\nCALL: {"kind": "close", "params": {}}')
        self.assertNotIn('proposal', out)
        self.assertEqual((out['light']['verb'], out['light']['label']), ('close', buttons.label('close')))
        # the strip over the row says to press it while it is lit; the chat keeps the past - after a reload nothing says "press" over a dark row
        self.assertEqual(out['light']['line'], f"Press {buttons.label('close')} when you're sure.")
        self.assertEqual(out['say'], f"Lit {buttons.label('close')} on TQ-{tid:04d}.")
        self.assertEqual(s.get_task(tid)['Status'], 'open')                        # nothing ran on the words
        self.assertEqual(proposals(s), [])                                           # ...and nothing waits on a card either

    def test_the_task_tool_road_lights_the_same_button(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'close it out', item['key'], f'CALL: {{"kind": "task.complete", "params": {{"ref": "TQ-{tid:04d}"}}}}')
        self.assertEqual(out['light']['verb'], 'close')
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_an_act_on_another_task_brings_it_up_with_its_button_lit(self):
        s = store(); tid, item = on_table(s)
        other = s.create_task({'Title': 'Renew the Spendly licence', 'Kind': 'task'}, 't')
        out, _ = say(s, 'remind me about the Spendly one next week', item['key'],
                     f'CALL: {{"kind": "task.defer", "params": {{"ref": "TQ-{other:04d}", "until": "monday"}}}}')
        self.assertEqual((out['light']['verb'], out['light']['tid']), ('defer', other))
        self.assertEqual(out['say'], f"Lit {buttons.label('defer')} on TQ-{other:04d}.")
        self.assertFalse(s.get_task(other).get('RemindAt'))

    def test_send_erin_the_answer_drafts_and_sends_nothing(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'send Erin the answer', item['key'], 'CALL: {"kind": "reply", "params": {"text": "the May numbers are attached"}}')
        self.assertNotIn('proposal', out)
        self.assertEqual(out['decision']['verb'], 'reply')                            # the page drafts it and lights Send (AssistantView)
        self.assertEqual(s._rows("SELECT * FROM review WHERE TaskId=?", (tid,)), [])  # nothing drafted, nothing sent by the words

    def test_turn_off_background_sync_opens_the_setting(self):
        s = store(); _, item = on_table(s)
        out, _ = say(s, 'turn off background sync', item['key'], 'CALL: {"kind": "setting.set", "params": {"setting": "poll_minutes", "value": "0"}}')
        self.assertNotIn('proposal', out)
        self.assertEqual(out['open'], '#settings=config&group=Sync%20%26%20startup&key=poll_minutes')
        self.assertIn('Background sync', out['say'])
        self.assertEqual(s.get_setting('poll_minutes'), '5')                         # changed by the knob, not the words

    def test_hand_it_to_a_coding_agent_lights_the_rows_agent_button_and_starts_nothing(self):
        s = store(); tid, item = on_table(s)
        out, spawn = say(s, 'hand this to a coding agent', item['key'], 'CALL: {"kind": "coding_agent", "params": {}}')
        self.assertEqual(out['light']['verb'], 'regular_agent')                     # the row's one Send to agent; its card asks which agent
        spawn.assert_not_called()
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_a_new_job_is_written_into_new_and_starts_nothing(self):
        s = store()
        out, spawn = say(s, 'research which payroll vendors integrate with Payworth', None,
                         'CALL: {"kind": "task.create_from_text", "params": {"kind": "general", "text": "which payroll vendors integrate with Payworth"}}')
        self.assertEqual(out['new'], {'kind': 'agent', 'how': 'general', 'text': 'which payroll vendors integrate with Payworth'})
        self.assertIn(buttons.label('regular_agent'), out['say']); self.assertNotIn('below', out['say'])
        spawn.assert_not_called()
        self.assertEqual([t for t in s.list_tasks() if 'Payworth' in str(t.get('Title'))], [])

    def test_a_button_the_row_does_not_draw_is_never_named(self):
        # a task's row has no Not ours: "Press Not ours" was said over it, lit nothing, and the model was never told (verify, 2026-10-19)
        s = store(); tid = s.create_task({'Title': 'New starter on Monday', 'Kind': 'task'}, 't')
        item = funnel.item_for_key(s, f'task:{tid}')
        self.assertNotIn('not_ours', [b['verb'] for b in concierge.row_buttons(s, item)])
        said = []
        def llm(system, user, **kw):
            said.append(user)
            return 'CALL: {"kind": "message.file", "params": {}}' if len(said) == 1 else 'That one is a task - Mark done or Remind me are its moves.'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'this is not ours', key=item['key'], llm=llm)
        self.assertNotIn('light', out)
        self.assertNotIn(buttons.label('not_ours'), out['say'])
        self.assertIn(f'"{buttons.label("not_ours")}" is not one of the actions', said[1])
        # ...and whatever road the act comes by, the light itself refuses a button the row does not draw, and says what the row has
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), self.assertRaises(concierge.CallMiss) as miss:
            concierge._lit(s, tid, item, item, 'not_ours')
        self.assertIn(f"has no {buttons.label('not_ours')} button", str(miss.exception)); self.assertIn(buttons.label('close'), str(miss.exception))

    def test_a_page_beside_the_item_keeps_the_item_on_the_table(self):
        # the router's own Settings page, beside the item: the next ask carries both, and "this" is still the item (verify, 2026-10-19)
        s = store(); tid, item = on_table(s)
        seen = []
        def llm(system, user, **kw): seen.append(user); return 'CALL: {"kind": "close", "params": {}}'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'mark this done', key=item['key'], llm=llm, open_card='Settings - Sync & startup')
        self.assertIn('OPEN BESIDE IT: Settings - Sync & startup', seen[0])
        self.assertEqual(out['light']['verb'], 'close')

    def test_a_task_named_to_open_comes_with_the_link_that_opens_it(self):
        # "open TQ-0004" was answered "drafted and waiting under my message" and nothing opened: the model was never told that only its
        # link brings a task up (2026-10-19 UI walk, G4) - the evidence is in the prompt, no code reads "open" out of the words
        s = store(); _, item = on_table(s)
        tid2 = arrive(s, subject='Badge for the new starter', who='Dana Pike', email='dana@vendor.example')['task_id']
        seen = []
        def llm(system, user, **kw): seen.append(user); return f'Here it is: [TQ-{tid2:04d}](#task={tid2}).'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            concierge.say(s, f'open TQ-{tid2:04d}', key=item['key'], llm=llm)
        self.assertIn(f'TO SHOW IT: link it in your answer as [TQ-{tid2:04d}](#task={tid2})', seen[0])
        tok = concierge.DELIVERY.set(concierge.PHONE)
        try: self.assertNotIn('TO SHOW IT', concierge.named_now(s, f'open TQ-{tid2:04d}', item), 'a phone has no canvas to open it on')
        finally: concierge.DELIVERY.reset(tok)

    def test_the_item_under_a_page_comes_with_the_link_that_shows_it_again(self):
        # "show me TQ-0003" over Connections answered about it and left it covered (2026-10-19 UI walk, G5)
        s = store(); tid, item = on_table(s)
        seen = []
        def llm(system, user, **kw): seen.append(user); return 'It is the May close numbers.'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            concierge.say(s, f'show me TQ-{tid:04d}', key=item['key'], llm=llm, open_card='Connections')
        self.assertIn('under that page', seen[0])
        self.assertIn(f'to show the item again, link it as [TQ-{tid:04d}](#task={tid})', seen[0])

    def test_page_lines_say_the_page_never_beside_this(self):
        s = store(); _, item = on_table(s)
        out, _ = say(s, 'turn off background sync', item['key'], 'CALL: {"kind": "setting.set", "params": {"setting": "poll_minutes", "value": "0"}}')
        self.assertNotIn('beside', out['say']); self.assertIn('Settings', out['say'])

    def test_a_tool_with_no_button_goes_back_to_the_model_never_to_a_card(self):
        s = store(); _, item = on_table(s)
        said = []
        def llm(system, user, **kw):
            said.append(user)
            return 'CALL: {"kind": "hub.publish", "params": {"title": "PO limit", "body": "Gail approves above 5k"}}' if len(said) == 1 \
                else 'You can save that to the Hub from its own page.'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'save that to the hub', key=item['key'], llm=llm)
        self.assertNotIn('proposal', out)
        self.assertIn('has no button the owner presses here', said[1])
        self.assertEqual(out['say'], 'You can save that to the Hub from its own page.')

    def test_a_set_up_is_its_own_page(self):
        s = store()
        sorts = iter([{'kind': 'report', 'why': 'a check'}, {'kind': 'connection', 'provider': 'quickbooks', 'why': 'their books'}])
        with mock.patch.object(concierge, '_compose_llm', return_value=lambda *a, **k: json.dumps(next(sorts))):
            out, _ = say(s, 'every Monday send me the overdue invoices', None, 'CALL: {"kind": "setup", "params": {"text": "every Monday send me the overdue invoices"}}')
            self.assertEqual(out['new'], {'kind': 'report', 'how': '', 'text': 'every Monday send me the overdue invoices'})
            out, _ = say(s, 'connect our books', None, 'CALL: {"kind": "setup", "params": {"text": "connect our books"}}')
            self.assertEqual(out['open'], '#connector=quickbooks')
        self.assertNotIn('proposal', out); self.assertEqual(proposals(s), [])

    def test_the_phone_keeps_its_text_yes_or_no(self):
        s = store(); tid, item = on_table(s)
        with concierge.delivering(concierge.PHONE):
            out, _ = say(s, 'mark this done', item['key'], 'CALL: {"kind": "close", "params": {}}')
        self.assertEqual(out['proposal']['kind'], 'task.complete')
        self.assertNotIn('below', out['say'])


def notices(s, n=9):
    for k in range(n):
        m = s.add_message({'ExternalId': f'n{k}', 'ConversationId': f'n{k}', 'Channel': 'email', 'Subject': f'Trainly weekly {k}', 'FromName': 'Trainly',
                           'FromEmail': 'news@vendor.example', 'SentAt': ago(k + 2), 'BodyText': 'this week', 'Status': 'filed'})
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
    funnel.invalidate()


def fyis(s): return [i for i in funnel.build(s)['items'] if i.get('kind') == 'fyi']


class TheModelIsToldTheRow(unittest.TestCase):
    def test_a_task_on_the_table_names_its_rows_buttons_not_the_chips(self):
        # "this is not ours" over a task chose Not ours - the chips said it was an action - and the light refused it: the task's row has
        # Remove - not a task, which the model was never told (the 2026-10-20 query walk)
        s = store(); tid, item = on_table(s)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            said = concierge.table_actions(s, item)
            self.assertIn(f'"{buttons.label("remove")}" = task.not_a_task', said)
            self.assertIn(f'"{buttons.label("priority")}" = task.update', said)
            self.assertNotIn(f'"{buttons.label("not_ours")}"', said)
            self.assertIn(f'"{buttons.label("next")}" = next', said)
            with concierge.delivering(concierge.PHONE): self.assertIn(f'"{buttons.label("not_ours")}"', concierge.table_actions(s, item))


class NotesAndDueDays(unittest.TestCase):
    # neither has a button on the row; both are the task page's own writes, run and said (the owner, 2026-10-20)
    def test_a_note_is_added_and_said(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'file a note on it: waiting on the bank', item['key'], 'CALL: {"kind": "task.comment", "params": {"text": "waiting on the bank"}}')
        self.assertEqual(out['did'], 'task.comment'); self.assertTrue(out['say'].startswith(f'Added a note to TQ-{tid:04d}'), out['say'])
        self.assertIn('waiting on the bank', [c.get('Body') for c in s.list_comments(tid)])

    def test_the_due_day_is_set_and_said(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'set the due date to friday', item['key'], 'CALL: {"kind": "task.update", "params": {"due": "friday"}}')
        self.assertEqual(out['did'], 'task.update'); self.assertIn(f"Set TQ-{tid:04d}'s due day to Fri", out['say'])
        self.assertTrue(str(s.get_task(tid).get('DueAt') or ''))

    def test_priority_still_lights_its_picker(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'make it urgent', item['key'], 'CALL: {"kind": "task.update", "params": {"priority": "urgent"}}')
        self.assertEqual(out['light']['verb'], 'priority')


class SetsFromOneSender(unittest.TestCase):
    # "snooze everything from Gail until Monday" and "close all the tasks from Priya" had no tool (the owner approved both, 2026-10-20)
    def two_from(self, s, who='Paula Vance', email='paula@vendor.example'):
        return [arrive(s, subject=f'Invoice {n} needs a code', who=who, email=email)['task_id'] for n in (1, 2)]

    def test_snooze_everything_from_one_sender(self):
        s = store(); tid, item = on_table(s); mine = self.two_from(s)
        out, _ = say(s, 'snooze everything from Paula until Monday', item['key'],
                     'CALL: {"kind": "pipe.defer", "params": {"select": {"sender": "Paula"}, "until": "monday 9am"}}')
        self.assertTrue(out['say'].startswith('Snoozed 2 items from Paula until '), out['say'])
        self.assertTrue(all(s.get_task(t).get('RemindAt') for t in mine)); self.assertFalse(s.get_task(tid).get('RemindAt'))
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            later = {i.get('tid') for i in funnel.build(s)['items'] if i.get('deferred')}      # under For later, saying their day
        self.assertEqual(later, set(mine))

    def test_close_all_from_one_sender(self):
        s = store(); tid, item = on_table(s); mine = self.two_from(s)
        out, _ = say(s, 'close all the tasks from Paula', item['key'], 'CALL: {"kind": "pipe.close", "params": {"select": {"sender": "Paula"}}}')
        self.assertTrue(out['say'].startswith('Closed 2 items from Paula'), out['say'])
        self.assertEqual({s.get_task(t)['Status'] for t in mine}, {'done'}); self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_the_phone_asks_first(self):
        s = store(); tid, item = on_table(s); self.two_from(s)
        with concierge.delivering(concierge.PHONE):
            out, _ = say(s, 'close all from Paula', item['key'], 'CALL: {"kind": "pipe.close", "params": {"select": {"sender": "Paula"}}}')
        self.assertEqual(out['proposal']['kind'], 'pipe.close')


class DraftsInTurnAndAnyButton(unittest.TestCase):
    def test_approve_all_the_drafts_lights_each_send_in_turn(self):
        from tests.assistant_queries import _world
        s = _world()                                                    # the demo world: five drafts wait for a Send
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            drafts = [i for i in funnel.build(s)['items'] if i.get('kind') == 'review']
        out, _ = say(s, 'approve all the drafts', 'msg:1', 'CALL: {"kind": "review.each", "params": {}}')
        self.assertGreater(len(drafts), 1)
        self.assertEqual(out['light']['verb'], 'approve')
        self.assertRegex(out['say'], rf"^Lit {buttons.label('approve')} on .* - 1 of \d+ drafts? waiting")
        self.assertEqual(proposals(s), [])

    def test_any_row_button_by_name(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'press remove', item['key'], 'CALL: {"kind": "button.light", "params": {"button": "remove"}}')
        self.assertEqual(out['light']['verb'], 'remove'); self.assertTrue(out['say'].startswith('Lit '))


class AConnectorIsItsCard(unittest.TestCase):
    # "add LinkedIn as a connector", "connect Slack", "hook up my second Outlook" (the owner, 2026-10-20): the catalogue's card, brought up
    def test_any_catalogue_card_opens_and_says_what_to_do(self):
        s = store()
        for typ, title in (('linkedin', 'LinkedIn'), ('slack', 'Slack'), ('quickbooks', 'QuickBooks Online')):
            out, _ = say(s, f'add {typ} as a connector', None, f'CALL: {{"kind": "connection.create", "params": {{"type": "{typ}"}}}}')
            self.assertEqual(out['open'], f'#connector={typ}'); self.assertTrue(out['say'].startswith(f'Opened the {title} card'), out['say'])
        out, _ = say(s, 'connect quickbooks online', None, 'CALL: {"kind": "connection.create", "params": {"type": "QuickBooks Online"}}')
        self.assertEqual(out['open'], '#connector=quickbooks')

    def test_a_second_one_names_add_another(self):
        s = store(); s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
        out, _ = say(s, 'hook up my second outlook', None, 'CALL: {"kind": "connection.create", "params": {"type": "outlook"}}')
        self.assertEqual(out['open'], '#connector=outlook'); self.assertIn('Add another', out['say'])

    def test_an_unknown_one_is_said_with_the_closest(self):
        s = store(); seen = []
        def llm(system, user, **kw):
            seen.append(user)
            return 'CALL: {"kind": "connection.create", "params": {"type": "slak"}}' if len(seen) == 1 else 'There is no Slak connector - did you mean Slack?'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'connect slak', llm=llm)
        self.assertIn('the closest are Slack', seen[1]); self.assertNotIn('open', out)


class TheToDos(unittest.TestCase):
    # tick, note and add a to-do from the Assistant, run and said (the owner, 2026-10-20)
    def setUp(self):
        self.s = store(); self.tid, self.item = on_table(self.s)
        self.s.set_task_checklist(self.tid, ['send the W-9', 'book the call'], 'owner')

    def call(self, text, kind, **p):
        return say(self.s, text, self.item['key'], 'CALL: ' + json.dumps({'kind': kind, 'params': p}))[0]

    def test_a_note_on_a_to_do_is_kept_and_said(self):
        out = self.call("note on 'send the W-9' that Paula has it", 'task.check', item='1', note='Paula has it')
        self.assertEqual(out['say'], f"Noted on TQ-{self.tid:04d}'s \u201csend the W-9\u201d: Paula has it.")
        box = self.s.task_checklist(self.tid)[0]
        self.assertEqual((box['note'], box['done']), ('Paula has it', False))
        self.assertIn('(note: Paula has it)', self.s.checklist_markdown(self.tid))
        self.s.set_task_checklist(self.tid, ['send the W-9', 'book the call', 'one more'], 'owner')       # an edit of the list keeps it
        self.assertEqual(self.s.task_checklist(self.tid)[0]['note'], 'Paula has it')

    def test_tick_and_add(self):
        out = self.call('tick 2', 'task.check', item='2')
        self.assertEqual(out['say'], f"Ticked \u201cbook the call\u201d on TQ-{self.tid:04d}.")
        self.assertTrue(self.s.task_checklist(self.tid)[1]['done'])
        out = self.call('add a to-do: call the bank', 'task.checklist', add=['call the bank'])
        self.assertTrue(out['say'].startswith(f'Added 1 to-do to TQ-{self.tid:04d}'), out['say'])
        self.assertEqual(self.s.task_checklist(self.tid)[-1]['text'], 'call the bank')

    def test_the_note_route(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        iid = self.s.task_checklist(self.tid)[0]['id']
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).patch(f'/api/tasks/{self.tid}/checklist/{iid}/note', json={'note': 'with legal'})
            self.assertEqual(r.json()['checklist'][0]['note'], 'with legal')
            r = TestClient(server.app).patch(f'/api/tasks/{self.tid}/checklist/{iid}/note', json={'note': ''})
            self.assertNotIn('note', r.json()['checklist'][0])
            self.assertEqual(TestClient(server.app).patch(f'/api/tasks/{self.tid}/checklist/nope/note', json={'note': 'x'}).status_code, 404)


class RunItAgain(unittest.TestCase):
    def test_run_it_again_over_a_good_report_opens_its_page(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'AP ageing', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps({'type': 'agent', 'title': 'AP ageing'})}, 'o')
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'AP ageing', 'Subject': 'AP ageing - 5 rows', 'FromName': 'AP ageing',
                           'SentAt': ago(1), 'BodyText': 'Five invoices past 30 days.', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            item = next(i for i in funnel.build(s)['items'] if i.get('kind') == 'report')
        out, _ = say(s, 'run it again', item['key'], 'CALL: {"kind": "rerun", "params": {}}')
        self.assertEqual(out['open'], f'#report={item["source_id"]}')
        self.assertIn('Reports', out['say']); self.assertNotIn('light', out)


class ClearingASet(unittest.TestCase):
    """"Clear all the FYI, please." was answered "Next." with a 4-FYI batch on the table and ~90 still on the rail (the owner, 2026-10-20:
    "this is clearly broken"). The desk told the model a set had no button - "the owner puts each one down with Next" - so it pressed Next.
    A named set is the owner's own words naming exactly what to mark read: it is marked read at once and the line says how many."""
    def test_clear_all_the_fyi_marks_every_fyi_read_and_says_how_many(self):
        s = store(); tid, item = on_table(s); notices(s)
        self.assertEqual(len(fyis(s)), 9)
        said = []
        def llm(system, user, **kw):
            said.append(user)
            return 'CALL: {"kind": "pipe.clear", "params": {"select": {"kind": "fyi"}}}' if len(said) == 1 else 'CALL: {"kind": "next", "params": {}}'
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'Clear all the FYI, please.', key=item['key'], llm=llm)
        self.assertEqual(fyis(s), [])
        self.assertEqual([i['tid'] for i in funnel.build(s)['items']], [tid])                 # the task on the table stays
        self.assertIn('9', out['say']); self.assertNotEqual(out['say'], concierge.RECEIPTS['next'])
        self.assertIn('search', out['say'].lower())
        self.assertNotIn('proposal', out); self.assertEqual(proposals(s), [])
        self.assertEqual(len(said), 1, 'the set ran on the first CALL - no miss sent the model to Next')

    def test_a_cleared_table_moves_the_walk_on(self):
        s = store(); notices(s, 3)
        key = fyis(s)[0]['key']
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'mark all the fyi read', key=key, llm=lambda *a, **k: 'CALL: {"kind": "pipe.clear", "params": {"select": {"kind": "fyi"}}}')
        self.assertEqual(fyis(s), [])
        self.assertEqual(out['decision'], {'verb': 'next'})

    def test_a_set_never_sweeps_what_waits_on_the_owner(self):
        # "mark everything read" swept the to-dos and the drafts waiting for a Send with the notices: each of those is put down with its
        # own button. The notices go; what is on the owner stays, and the line says so
        s = store(); tid, item = on_table(s); notices(s, 3)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'mark everything read', key=item['key'], llm=lambda *a, **k: 'CALL: {"kind": "pipe.clear", "params": {"select": {"everything": true}}}')
            self.assertEqual(fyis(s), [])
            self.assertEqual([i['tid'] for i in funnel.build(s)['items']], [tid])
        self.assertIn('Marked 3 items read', out['say']); self.assertIn('1 item waiting on you', out['say'])
        self.assertEqual(out['decision'], {'verb': 'setting'})
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            out = concierge.say(s, 'clear the to-dos', key=item['key'], llm=lambda *a, **k: 'CALL: {"kind": "pipe.clear", "params": {"select": {"lane": "yours"}}}')
            self.assertEqual([i['tid'] for i in funnel.build(s)['items']], [tid])
        self.assertNotIn('cleared', out); self.assertIn('own button', out['say'])

    def test_next_keeps_the_words_the_model_said_with_it(self):
        s = store(); tid, item = on_table(s)
        out, _ = say(s, 'can I see the next one, this can wait', item['key'], 'This one can wait - here is the next.\nCALL: {"kind": "next", "params": {}}')
        self.assertEqual(out['decision'], {'verb': 'next'})
        self.assertEqual(out['say'], 'This one can wait - here is the next.')


class NoTakeItBack(unittest.TestCase):
    def test_no_button_is_called_take_it_back(self):
        self.assertNotIn('take_back', buttons.VERBS)
        self.assertNotIn('Take it back', [v['label'] for v in buttons.VERBS.values()])

    def test_a_receipt_offers_no_undo(self):
        s = store(); tid, item = on_table(s)
        s.set_setting('assistant_dock_task_id', str(concierge.general.dock_task(s, 'owner')[0]['TaskId']), 't')
        op = operations.propose(s, 'task.complete', tid, {}, 'owner')
        turn = concierge.receipt_turn(s, {**op, 'status': 'done', 'outcome': {'undo': {'kind': 'task.reopen', 'target': tid}}}, table=True)
        self.assertNotIn('Undo', turn['say'])
        self.assertEqual([o for o in proposals(s) if o.get('Kind') == 'task.reopen'], [])


if __name__ == '__main__':
    unittest.main()
