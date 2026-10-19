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
