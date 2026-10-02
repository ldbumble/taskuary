"""An act the owner confirmed that did NOT happen is never told as done, and never a dead end (2026-09-29).

A Close out on a pull request came back from GitHub with a 403 - the token could not merge - and the chat
said "Not done - 403 Client Error: Forbidden for url: ..." with nothing under it: no Retry, no Mark done,
no way on. Its mirror was worse: a reply whose send threw was receipted "Done" and the walk settled it,
because the verdict came back ok with the error tucked in `send_error`.
"""
import json, unittest
from unittest import mock

from tests.test_chat_proposals import arrive, brain, pile, run, say, store


def drafted(s):
    out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=brain('reply_only', None))
    rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached - sorry for the wait.')
    item = pile(s)[0]
    from taskuary import concierge, general
    concierge.set_current(s, general.dock_task(s)[0]['TaskId'], item['key'])      # on the table, as the walk puts it
    p = say(s, 'approve', key=item['key'], model='Sending it.\nCALL: {"kind": "approve", "params": {}}')['proposal']
    return out['task_id'], rv['ReviewId'], item, p


class AFailedSendIsNotDoneTests(unittest.TestCase):
    def test_a_send_that_threw_is_an_error_the_review_waits_and_the_task_stays_open(self):
        s = store(); tid, rid, item, p = drafted(s)
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('SMTP 550 mailbox unavailable')):
            got = run(s, p).json()
        self.assertEqual(got['status'], 'error')
        self.assertIn('SMTP 550', got['error'])
        self.assertTrue(got['receipt'].startswith('Not sent'), got['receipt'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_a_send_nobody_answered_is_not_done_either(self):
        import requests
        s = store(); tid, rid, item, p = drafted(s)
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=requests.exceptions.ReadTimeout("read timed out")), \
             mock.patch('taskuary.outbound.reconcile_sent', return_value=None):
            got = run(s, p).json()
        self.assertEqual(got['status'], 'error')
        self.assertIn('delivery unknown', got['error'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')


def failed_send(s, tid, rid, item, p, model=None):
    """Confirm the reply with the send throwing, the model (when given) answering about it."""
    from taskuary import concierge
    with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('SMTP 550 mailbox unavailable')), \
         mock.patch.object(concierge, 'brain', return_value=(lambda *a, **k: model) if model else None):
        return run(s, p).json()


class AFailureCarriesItsWayOnTests(unittest.TestCase):
    """The choices are code's; the model only says why and picks one of them."""
    def test_the_failure_offers_try_again_the_items_other_verbs_and_next_never_the_act_that_failed(self):
        s = store(); got = failed_send(s, *drafted(s))
        verbs = [c['verb'] for c in got['chips']]
        self.assertEqual(verbs[0], 'retry'); self.assertIn('next', verbs); self.assertNotIn('approve', verbs)
        self.assertIn('close', verbs)                                              # Mark done: the way out that always works

    def test_the_models_pick_leads_and_its_sentence_follows_the_fact(self):
        s = store(); tid, rid, item, p = drafted(s)
        got = failed_send(s, tid, rid, item, p, model='Their mail server bounced it - the address may be wrong. Mark it done and ring them.\nPICK: 3')   # Try again, Redraft it, Mark done
        self.assertIn('bounced', got['receipt']); self.assertNotIn('PICK', got['receipt'])
        self.assertTrue(got['receipt'].startswith('Not sent'))
        self.assertEqual(got['chips'][0]['verb'], 'close')

    def test_a_pick_the_model_made_up_changes_nothing(self):
        s = store(); tid, rid, item, p = drafted(s)
        got = failed_send(s, tid, rid, item, p, model='Something went wrong.\nPICK: 99')
        self.assertEqual(got['chips'][0]['verb'], 'retry')

    def test_try_again_runs_the_same_confirmation_and_lands_it(self):
        s = store(); tid, rid, item, p = drafted(s)
        retry = failed_send(s, tid, rid, item, p)['chips'][0]
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['craig@vendor.com'], 'cc': []}):
            again = run(s, {'id': retry['op'], 'version': retry['version']}).json()
        self.assertEqual(again['status'], 'done'); self.assertIn(s.get_review(rid)['Status'], ('approved', 'edited'))

    def test_a_grant_github_named_as_missing_is_never_offered_as_try_again(self):
        from taskuary import concierge, operations
        s = store(); tid, rid, item, p = drafted(s)
        s.update_operation(p['id'], {'Status': 'error', 'Error': 'the GitHub token may not merge #7 - it needs Contents: write',
                                     'OutcomeJson': json.dumps({'needs': 'Contents: write', 'rid': rid})})
        way = concierge.recover(s, operations.get(s, p['id']), llm=False)
        self.assertNotIn('retry', [c['verb'] for c in way['chips']])


class ThePhoneNumbersTheWayOnTests(unittest.TestCase):
    def test_a_failed_pick_answers_with_numbered_choices_and_try_again_runs_by_number(self):
        from taskuary import concierge, operations, remote_assistant as ra, server, terminal
        s = store(); tid, rid, item, p = drafted(s)
        for pt in (mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[])):
            pt.start(); self.addCleanup(pt.stop)
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('SMTP 550 mailbox unavailable')), \
             mock.patch.object(concierge, 'brain', return_value=None):
            text = ra._ran(s, p, concierge.run_proposal(s, operations.get(s, p['id'])), item, 'owner')
        self.assertIn('Not sent', text); self.assertIn('Reply with one of:', text); self.assertIn('1 · Try again', text)
        rows = dict(ra.recovery_rows(s, concierge.recover(s, operations.get(s, p['id']), llm=False)['chips']))
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['craig@vendor.com'], 'cc': []}):
            said = ra.run_act(s, rows['Try again'], item)
        self.assertTrue(said.startswith('Done'), said); self.assertIn(s.get_review(rid)['Status'], ('approved', 'edited'))


class TelegramTypesTheNumberTests(unittest.TestCase):
    """Telegram: the way on is the same list - buttons under the message, and a typed "1" runs Try again too."""
    def test_a_failed_send_on_telegram_offers_numbers_and_1_tries_again(self):
        from taskuary import concierge, messengers, operations, remote_assistant as ra, server, terminal
        s = store(); tid, rid, item, p = drafted(s)
        for pt in (mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]),
                   mock.patch.object(concierge, 'brain', return_value=None)):
            pt.start(); self.addCleanup(pt.stop)
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('SMTP 550 mailbox unavailable')):
            text = ra._ran(s, p, concierge.run_proposal(s, operations.get(s, p['id'])), item, 'owner')
        sent = []
        with mock.patch.object(messengers, 'tg_send', side_effect=lambda st, chat, body, connector_id=None, buttons=None: sent.append(buttons)):
            ra.send(s, 'telegram', '4242', text)
        self.assertEqual(sent[-1][0], 'Try again')                       # the bot's own buttons; the number still answers
        self.assertEqual(ra.resolve_index(s, 'telegram', '4242', '1'), ('Try again', True))
        act = ra.acts_for(s, 'telegram', '4242')['Try again']
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['craig@vendor.com'], 'cc': []}):
            self.assertTrue(ra.run_act(s, act, item).startswith('Done'))
        self.assertIn(s.get_review(rid)['Status'], ('approved', 'edited'))

    def test_a_push_waits_on_a_telegram_chat_that_is_talking_whatever_store_handle_sent_it(self):
        from taskuary import remote_assistant as ra
        s = store()
        class Proxy: _store = s                                     # a poll worker's writer proxy (channels._Writer)
        ra.talked(Proxy(), 'telegram', 4242)
        self.assertFalse(ra.quiet(s, 'telegram', '4242'))


class AYesAnswersTheTableTests(unittest.TestCase):
    def test_a_yes_typed_after_walking_on_never_runs_the_proposal_left_behind(self):
        from taskuary import concierge, general, terminal
        s = store(); first = arrive(s, subject='Can you fix the export?')
        second = arrive(s, subject='Is the payroll file in?', body='Payroll closes Thursday.', hours=2)
        items = {i['tid']: i for i in pile(s)}
        say(s, 'close it', key=items[first['task_id']]['key'], model='Closing.\nCALL: {"kind": "close", "params": {}}')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            concierge.surface(s, key=items[second['task_id']]['key'], llm=lambda *a, **k: 'Payroll is asking about the file.')
            got = concierge.confirm_open(s, general.dock_task(s)[0]['TaskId'], items[second['task_id']], False)
        self.assertIn('Nothing is waiting on your yes', got['say'])
        self.assertEqual(s.get_task(first['task_id'])['Status'], 'open')


    def test_the_same_ask_again_is_the_same_proposal_still_waiting_not_a_change(self):
        s = store(); out = arrive(s); item = pile(s)[0]
        first = say(s, 'not ours', key=item['key'], model='Filing it.\nCALL: {"kind": "not_ours", "params": {}}')['proposal']
        again = say(s, 'yes file it', key=item['key'], model='Filing it.\nCALL: {"kind": "not_ours", "params": {}}')['proposal']
        self.assertEqual((again['id'], again['version']), (first['id'], first['version']))
        self.assertTrue(again['say'].startswith('Still waiting for your yes'), again['say'])
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')


class TheWalkResumesTheTableTests(unittest.TestCase):
    """The incident: Close out failed on one pull request, the owner picked "Walk me through my tasks", and the walk
    started afresh - skipping the item it had just shown, still waiting on them - and put up the next one."""
    def test_walk_me_through_brings_back_the_item_whose_act_failed(self):
        from taskuary import concierge, remote_assistant as ra, server, terminal
        s = store(); tid, rid, item, p = drafted(s)
        arrive(s, subject='Is the payroll file in?', body='Payroll closes Thursday.', hours=3)
        for pt in (mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]),
                   mock.patch.object(concierge, 'brain', return_value=None)):
            pt.start(); self.addCleanup(pt.stop)
        concierge.surface(s, key=item['key'])                                        # shown: the walk would skip it for hours
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('SMTP 550 mailbox unavailable')):
            run(s, p)
        card = ra.walk(s).split('\n\n', 2)[-1]                                       # past the opener's who-wants-what
        self.assertIn(f'TQ-{tid:04d}', card); self.assertIn('Can you send it?', card); self.assertNotIn('Payroll closes', card)

    def test_with_nothing_left_on_the_table_the_walk_takes_the_next_thing(self):
        from taskuary import concierge, general, terminal
        s = store(); arrive(s, subject='Is the payroll file in?', body='Payroll closes Thursday.')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, 'brain', return_value=None):
            concierge.set_current(s, general.dock_task(s)[0]['TaskId'], None)
            out = concierge.resume(s)
        self.assertIn('payroll', (out.get('item') or {}).get('title', '').lower())


class PlainFailureWordsTests(unittest.TestCase):
    def test_a_status_prefix_and_a_local_path_never_reach_the_chat(self):
        from fastapi import HTTPException
        from taskuary.operations import plain
        said = plain(HTTPException(422, r'guessing would put an agent in C:\Users\alex\Documents\ledger. Pick one on the card'))
        self.assertEqual(said, 'guessing would put an agent in ledger. Pick one on the card')
        self.assertEqual(plain(RuntimeError('see https://api.github.com/repos/northwind/ledger')), 'see https://api.github.com/repos/northwind/ledger')


if __name__ == '__main__':
    unittest.main()
