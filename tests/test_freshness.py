"""Mandatory freshness: a draft knows what it read, a send rechecks it, and email is refreshed like chat (PW-048, PW-049, PW-054, PW-055).

A draft used to be labelled with the newest message queried AFTER the model finished - a line
that landed during generation was called "seen"; the source-refresh gate before an answer, a
draft or a send skipped email altogether; the reply writer read the last six messages cut at
4,000 characters each. Now the draft is pinned to the exact inbound message and message-set
revision it was written against, before the model runs, and is marked stale when the thread moves
during generation; a verdict rechecks that revision wherever it lands (the Review button or the
phone road) and refuses a stale draft instead of sending yesterday's wording; the refresh gate
covers email through its connector; and the writer reads the assembled, budgeted conversation.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import operations, responder, server, verdicts
from taskuary.store import MemoryStore


def stamp(seconds=0): return (datetime.now() + timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')


def thread(channel='email', source='me@northwind.example'):
    s = MemoryStore()
    tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': channel}, 'router')
    first = s.add_message({'TaskId': tid, 'ExternalId': 'm:first', 'ConversationId': 'AAQk-exp', 'Channel': channel, 'SourceName': source,
                           'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': stamp(-60),
                           'BodyText': 'Could you send me the August export? The earlier note mentioned the marmoset figure.', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
    return s, tid, first, rid


def later(s, tid, text='Never mind - Priya sent it.', channel='email', source='me@northwind.example'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'm:{text[:8]}', 'ConversationId': 'AAQk-exp', 'Channel': channel, 'SourceName': source,
                          'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': stamp(), 'BodyText': text, 'Status': 'routed'})


class DraftPinsWhatItReadTests(unittest.TestCase):
    def test_the_draft_is_pinned_to_the_message_and_revision_it_saw_not_to_what_landed_meanwhile(self):
        s, tid, first, rid = thread()
        arrived = []
        def llm(system, user, **k):
            arrived.append(later(s, tid))                                       # a line lands while the model is writing
            return 'Here is the August export.'
        responder.draft_for_review(s, tid, rid, llm=llm)
        rv = s.get_review(rid)
        self.assertEqual(rv['MessageId'], first)                                 # what the wording actually answered
        self.assertEqual(rv['Stale'], 1)                                         # ...and it is said to be behind the thread
        self.assertTrue(rv['ContextRevision'])

    def test_a_quiet_thread_pins_clean(self):
        s, tid, first, rid = thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        rv = s.get_review(rid)
        self.assertEqual((rv['MessageId'], rv['Stale']), (first, 0))
        self.assertEqual(rv['ContextRevision'], operations.message_revision(s, tid))


class SendRechecksTests(unittest.TestCase):
    def test_a_stale_draft_is_refused_wherever_the_verdict_lands(self):
        s, tid, first, rid = thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        later(s, tid)                                                            # the thread moved after the draft
        with mock.patch('taskuary.outbound.reply_to_message') as send:
            out = verdicts.decide(s, s.get_review(rid), 'approve')               # the phone road: no HTTP gate in front of it
        self.assertEqual((out['ok'], out.get('stale'), send.called), (False, True, False))
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertIn('redraft', out['send_error'].lower())

    def test_a_redraft_repins_and_the_next_yes_sends(self):
        s, tid, first, rid = thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        new = later(s, tid)
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Glad Priya sent it.')
        rv = s.get_review(rid)
        self.assertEqual((rv['MessageId'], rv['Stale']), (new, 0))
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'ok': True, 'channel': 'email', 'to': ['dana@vendor.example']}) as send:
            out = verdicts.decide(s, rv, 'approve')
        self.assertTrue(out['ok']); self.assertTrue(send.called)

    def test_a_marked_stale_draft_is_refused_even_before_a_recheck(self):
        s, tid, first, rid = thread()
        s.update_review_draft(rid, 'old words', None); s.pin_review_context(rid, first, operations.message_revision(s, tid)); s.mark_review_stale(rid)
        with mock.patch('taskuary.outbound.reply_to_message') as send:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((out['ok'], out.get('stale'), send.called), (False, True, False))

    def test_the_review_button_reports_the_stale_verdict_the_same_way(self):
        from fastapi.testclient import TestClient
        s, tid, first, rid = thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        s.mark_review_stale(rid)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.outbound.reply_to_message') as send:
            data = TestClient(server.app).post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': 'Here it is.'}).json()
        self.assertEqual((data['ok'], data['stale'], send.called), (False, True, False))


class EmailRefreshTests(unittest.TestCase):
    def test_the_refresh_gate_reads_the_mailbox_through_its_connector_before_acting(self):
        s, tid, first, _rid = thread()
        o = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'}), 'Secret': 'S'}, 't')
        s.save_source({'Channel': 'email', 'Address': 'me@northwind.example', 'ConnectorId': o['ConnectorId'], 'Active': 1, 'ConfigJson': '{}'}, 't')
        with mock.patch.object(server, 'store', s), \
             mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: (later(s, tid) and 1)) as poll:
            got = server._refresh_chat_context(task_id=tid, message_id=first)
        self.assertTrue(got['polled']); self.assertTrue(got['newer']); self.assertEqual(got['channel'], 'email')
        self.assertEqual(poll.call_args.kwargs['only'], ['outlook']); self.assertTrue(poll.call_args.kwargs['wait'])

    def test_a_mailbox_with_no_active_connector_is_left_alone_and_said_so(self):
        s, tid, first, _rid = thread()
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_poll_reports') as poll:
            got = server._refresh_chat_context(task_id=tid, message_id=first)
        poll.assert_not_called(); self.assertFalse(got['polled']); self.assertFalse(got['newer'])


class WriterReadsTheChainTests(unittest.TestCase):
    def test_the_writer_gets_the_assembled_conversation_including_history(self):
        s, tid, first, rid = thread()
        s.add_message({'TaskId': None, 'ExternalId': 'h:0', 'ConversationId': 'AAQk-exp', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                       'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': stamp(-3600),
                       'BodyText': 'Earlier in this thread: the July file had the capybara total wrong.', 'Status': 'history'})
        seen = {}
        responder.draft_for_review(s, tid, rid, llm=lambda system, user, **k: (seen.update(u=user), 'Here it is.')[1])
        self.assertIn('capybara', seen['u']); self.assertIn('marmoset', seen['u'])

    def test_a_long_thread_is_budgeted_and_the_cut_is_disclosed_not_silent(self):
        s, tid, first, rid = thread()
        for i in range(40):
            s.add_message({'TaskId': tid, 'ExternalId': f'm:{i}', 'ConversationId': 'AAQk-exp', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                           'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': stamp(-3000 + i * 60),
                           'BodyText': f'Message {i}: ' + ('detail ' * 120), 'Status': 'routed'})
        seen = {}
        responder.draft_for_review(s, tid, rid, llm=lambda system, user, **k: (seen.update(u=user), 'Here it is.')[1])
        self.assertLess(len(seen['u']), 40_000)
        self.assertRegex(seen['u'], r'earlier message|older message|dropped|not shown')


if __name__ == '__main__':
    unittest.main()
