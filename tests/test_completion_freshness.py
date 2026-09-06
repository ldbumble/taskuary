"""Finished work refreshes its conversation before it drafts the reply (PW-235 to PW-238).

The agent's result was turned into a reply the moment the session closed, from the ask as it stood
when the work began. Now `coder.finish` refreshes the source conversation first (through the
`coder.REFRESH` hook the server installs), reassesses whether a reply is still owed - an answer
the owner already sent from the mail client means none is, a changed ask means the draft answers
the thread as it is now - drafts from the saved result and the verified current conversation,
recording the context revision it used, and shows an unresolved freshness state when the refresh
failed instead of pretending the ask is unchanged. A channel that cannot carry the reply no longer
suppresses the draft (the always-draft rule): Send is hidden and the reason said, the owner's exit
is Close without sending. Repeated completion events reuse the one review and never send.
"""
import unittest
from unittest import mock

from taskuary import coder, outbound
from taskuary.store import MemoryStore

REP = {'summary': 'fixed the export', 'outcome': 'did_work', 'determination': '', 'actions': ''}


def task_with(s, channel='email', body='Could you fix the August export?'):
    tid = s.create_task({'Title': 'August export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'x-{channel}', 'ConversationId': 'AAQk-x', 'Channel': channel,
                         'SourceName': 'me@northwind.example', 'Subject': 'August export', 'FromName': 'Dana',
                         'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00', 'BodyText': body, 'Status': 'routed'})
    return tid, mid


def refresh_that(**out):
    """A stand-in for the server's context refresh: returns what the poll found, or raises."""
    def f(store, tid, mid):
        f.calls.append((tid, mid))
        if 'error' in out: raise RuntimeError(out['error'])
        return {'polled': True, 'newer': out.get('newer', False), 'added': int(out.get('newer', False))}
    f.calls = []
    return f


class NoHook(unittest.TestCase):
    """Each case installs the refresh it wants; the server's own hook (set at import) never leaks in."""
    def setUp(self): self._prev, coder.REFRESH = coder.REFRESH, None
    def tearDown(self): coder.REFRESH = self._prev


class FreshnessTests(NoHook):

    def test_the_conversation_is_refreshed_before_the_reply_is_drafted_and_an_unchanged_chain_drafts_as_before(self):
        s = MemoryStore(); tid, mid = task_with(s)
        coder.REFRESH = refresh_that(newer=False)
        order = []
        coder.REFRESH.calls = order
        with mock.patch('taskuary.responder.write_draft', side_effect=lambda *a, **k: order.append('draft') or 'Fixed.'):
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual(order, [(tid, mid), 'draft'])                                   # refresh, then the draft
        self.assertEqual((out['drafting'], out['message_id'], out['freshness']), (True, mid, 'fresh'))
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['Stale'], 0); self.assertEqual(s.get_task(tid)['Status'], 'waiting')

    def test_an_answer_the_owner_already_sent_from_the_mail_client_means_no_reply_is_drafted(self):
        s = MemoryStore(); tid, mid = task_with(s)
        def poll(store, t, m):
            store.add_message({'TaskId': tid, 'ExternalId': 'sent-1', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                               'Subject': 'RE: August export', 'FromEmail': 'me@northwind.example', 'FromName': 'You', 'SentAt': '2026-09-06 11:00:00',
                               'BodyText': 'Done - the export is fixed.', 'Status': 'context', 'Direction': 'out'})
            return {'polled': True, 'newer': False, 'added': 1}
        coder.REFRESH = poll
        with mock.patch('taskuary.responder.write_draft') as wd, mock.patch.object(outbound, 'reply_to_message') as send:
            out = coder.finish(s, tid, REP, None, 'coder')
        wd.assert_not_called(); send.assert_not_called()
        self.assertEqual((out['drafting'], out['freshness']), (False, 'answered'))
        self.assertEqual(s.list_reviews('pending'), []); self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertTrue(any('already answered' in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_a_changed_ask_is_answered_as_the_thread_stands_now(self):
        s = MemoryStore(); tid, mid = task_with(s)
        newer = {}
        def poll(store, t, m):
            newer['mid'] = store.add_message({'TaskId': tid, 'ExternalId': 'x2', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                                              'Subject': 'RE: August export', 'FromEmail': 'dana@vendor.example', 'FromName': 'Dana', 'SentAt': '2026-09-06 10:30:00',
                                              'BodyText': 'Actually - September too, please.', 'Status': 'routed'})
            return {'polled': True, 'newer': True, 'added': 1}
        coder.REFRESH = poll
        with mock.patch('taskuary.responder.write_draft', return_value='Both months are done.') as wd:
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual((out['drafting'], out['message_id'], out['freshness']), (True, newer['mid'], 'changed'))
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['MessageId'], newer['mid'])                                  # the draft answers the newest ask
        self.assertIn('thread moved on', rv['Reason'])
        self.assertIn('September too', wd.call_args.args[3])                            # the result is drafted against the current ask

    def test_a_refresh_that_fails_leaves_the_draft_visibly_unresolved(self):
        s = MemoryStore(); tid, mid = task_with(s)
        coder.REFRESH = refresh_that(error='I could not refresh email: token expired')
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual((out['drafting'], out['freshness']), (True, 'unresolved'))
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['Stale'], 1)                                                   # Send waits for a refresh
        self.assertIn('could not be refreshed', rv['Reason']); self.assertIn('token expired', rv['Reason'])
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')

    def test_no_refresh_hook_means_the_freshness_is_unchecked_not_fresh(self):
        s = MemoryStore(); tid, mid = task_with(s)
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual(out['freshness'], 'unchecked'); self.assertEqual(s.list_reviews('pending')[0]['Stale'], 0)


class CompletionScopeTests(NoHook):
    def test_cross_scope_or_unattributed_reply_cannot_close_the_task_or_held_review(self):
        cases = [
            ('email', 'me@other.example', 'me@northwind.example'),
            ('teams', 'me@northwind.example', 'me@northwind.example'),
            ('email', None, 'me@northwind.example'),
            ('email', 'me@northwind.example', None),
            ('email', None, None),
        ]
        for channel, reply_source, incoming_source in cases:
            with self.subTest(channel=channel, reply_source=reply_source, incoming_source=incoming_source):
                s = MemoryStore(); self.addCleanup(s.cx.close)
                tid, mid = task_with(s)
                s.set_setting('notify_level', 'off', 'test')
                s._exec('UPDATE message SET SourceName=? WHERE MessageId=?', (incoming_source, mid))
                rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                    'Status': 'pending', 'DraftText': 'Retained draft'})
                s.hold_reviews(tid, 'working')
                other = s.add_message({'ExternalId': 'other-answer', 'ConversationId': 'AAQk-x',
                    'Channel': channel, 'SourceName': reply_source, 'FromEmail': 'me@other.example',
                    'FromName': 'You', 'SentAt': '2026-09-06 11:00:00', 'BodyText': 'Done elsewhere.',
                    'Status': 'context', 'Direction': 'out'})
                s.set_funnel_state(f'msg:{mid}', 'done', note='Existing owner read')
                s.save_doc('style', 'Owner text /Data >= 7', 'owner')
                messages = [s.get_message(mid), s.get_message(other)]
                receipts = s.funnel_states()
                coder.REFRESH = refresh_that(newer=False)
                with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as draft, \
                     mock.patch.object(outbound, 'reply_to_message') as send:
                    result = coder.finish(s, tid, REP)
                self.assertTrue(result['drafting'])
                self.assertEqual(result['message_id'], mid)
                self.assertEqual(s.get_task(tid)['Status'], 'waiting')
                self.assertEqual((s.get_review(rid)['Status'], s.get_review(rid)['MessageId']), ('pending', mid))
                self.assertEqual(s.get_review(rid)['DraftText'], 'Retained draft')
                self.assertEqual(draft.call_args.args[2], rid)
                send.assert_not_called()
                self.assertEqual([s.get_message(mid), s.get_message(other)], messages)
                self.assertEqual(s.funnel_states(), receipts)
                self.assertEqual(s.get_doc('style'), 'Owner text /Data >= 7')

    def test_matching_mailbox_reply_still_closes_the_task_and_held_review(self):
        s = MemoryStore(); self.addCleanup(s.cx.close)
        tid, mid = task_with(s)
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                            'Status': 'pending', 'DraftText': 'Earlier draft'})
        s.hold_reviews(tid, 'working')
        s.add_message({'ExternalId': 'same-answer', 'ConversationId': 'AAQk-x',
            'Channel': 'email', 'SourceName': 'ME@NORTHWIND.EXAMPLE', 'FromEmail': 'me@northwind.example',
            'SentAt': '2026-09-06 11:00:00', 'BodyText': 'Done.', 'Status': 'context', 'Direction': 'out'})
        coder.REFRESH = refresh_that(newer=False)
        with mock.patch('taskuary.responder.write_draft') as draft, mock.patch.object(outbound, 'reply_to_message') as send:
            result = coder.finish(s, tid, REP)
        self.assertEqual((result['drafting'], result['freshness']), (False, 'answered'))
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual(s.get_review(rid)['Status'], 'no_reply')
        draft.assert_not_called(); send.assert_not_called()

    def test_foreign_store_refresh_stays_unresolved_without_touching_the_server_store(self):
        from taskuary import server
        owned, foreign = MemoryStore(), MemoryStore()
        self.addCleanup(owned.cx.close); self.addCleanup(foreign.cx.close)
        task_with(owned)  # Deliberately collide the two stores' local task/message IDs.
        tid, mid = task_with(foreign)
        foreign.set_setting('notify_level', 'off', 'test')
        before = list(owned.cx.iterdump())
        coder.REFRESH = server._refresh_for_finish
        with mock.patch.object(server, 'store', owned), \
             mock.patch.object(server, '_refresh_chat_context') as refresh, \
             mock.patch('taskuary.responder.write_draft', return_value='Fixed.'), \
             mock.patch.object(outbound, 'reply_to_message') as send:
            result = coder.finish(foreign, tid, REP)
        refresh.assert_not_called(); send.assert_not_called()
        self.assertEqual(result['freshness'], 'unresolved')
        self.assertEqual(foreign.get_task(tid)['Status'], 'waiting')
        review = foreign.list_reviews('pending')[0]
        self.assertEqual((review['MessageId'], review['Stale']), (mid, 1))
        self.assertIn('different store', review['Reason'])
        self.assertEqual(list(owned.cx.iterdump()), before)

    def test_owned_store_refresh_keeps_the_exact_task_and_message(self):
        from taskuary import server
        s = MemoryStore(); self.addCleanup(s.cx.close)
        tid, mid = task_with(s)
        result = {'polled': True, 'newer': False}
        with mock.patch.object(server, 'store', s), \
             mock.patch.object(server, '_refresh_chat_context', return_value=result) as refresh:
            self.assertIs(server._refresh_for_finish(s, tid, mid), result)
        refresh.assert_called_once_with(task_id=tid, message_id=mid)


class ResultAndReviewTests(NoHook):

    def test_the_saved_result_survives_a_failed_draft_which_stays_retryable(self):
        s = MemoryStore(); tid, mid = task_with(s)
        s.add_comment(tid, 'coder', 'agent', 'REPORT: fixed the export')                 # the result, saved before finish
        with mock.patch('taskuary.responder.write_draft', side_effect=RuntimeError('no AI connector is set up to write replies')):
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertTrue(out['drafting'])
        rv = s.list_reviews('pending')[0]
        self.assertFalse((rv.get('DraftText') or '').strip())                            # empty draft: "Draft with AI" retries it
        self.assertTrue(any('REPORT: fixed' in (c.get('Body') or '') for c in s.list_comments(tid)))
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')

    def test_a_repeated_completion_reuses_the_one_review_and_never_sends(self):
        s = MemoryStore(); tid, mid = task_with(s)
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as wd, mock.patch.object(outbound, 'reply_to_message') as send:
            coder.finish(s, tid, REP, None, 'coder'); coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual(len(s.list_reviews('pending')), 1); send.assert_not_called()
        self.assertEqual(wd.call_count, 2)                                                # rewritten, not duplicated
        self.assertEqual(wd.call_args_list[0].args[2], wd.call_args_list[1].args[2])     # the same review id both times

    def test_a_held_review_is_the_one_reused(self):
        s = MemoryStore(); tid, mid = task_with(s)
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'early guess', 'Reason': 'needs a reply'})
        s.hold_reviews(tid, 'the agent is looking at it')
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as wd:
            coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual(wd.call_args.args[2], rid); self.assertEqual(len(s.list_reviews('pending')), 1)


class UnsupportedSendTests(NoHook):
    """PW-237: the always-draft rule - a channel that cannot carry the reply hides Send, it does not hide the answer."""
    def test_a_channel_that_cannot_send_still_gets_its_draft_and_says_why_send_is_hidden(self):
        s = MemoryStore(); tid, mid = task_with(s, 'github')
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as wd, mock.patch.object(outbound, 'reply_to_message') as send:
            out = coder.finish(s, tid, REP, None, 'coder')
        wd.assert_called_once(); send.assert_not_called()
        self.assertEqual((out['drafting'], out['message_id'], out['can_send']), (True, mid, False))
        self.assertIn('GitHub', out['send_block'])
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['MessageId'], mid); self.assertEqual(s.get_task(tid)['Status'], 'waiting')

    def test_a_channel_switched_off_by_the_owner_drafts_too(self):
        s = MemoryStore(); s.set_setting('reply_channels', 'email', 't'); tid, mid = task_with(s, 'slack')
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            out = coder.finish(s, tid, REP, None, 'coder')
        self.assertEqual((out['drafting'], out['can_send']), (True, False)); self.assertEqual(len(s.list_reviews('pending')), 1)

    def test_a_report_row_still_drafts_nothing_because_nobody_sent_it(self):
        s = MemoryStore(); tid, mid = task_with(s, 'report')
        with mock.patch('taskuary.responder.write_draft') as wd:
            out = coder.finish(s, tid, REP, None, 'coder')
        wd.assert_not_called(); self.assertEqual((out['drafting'], out['can_send']), (False, False)); self.assertEqual(s.get_task(tid)['Status'], 'done')


if __name__ == '__main__':
    unittest.main()
