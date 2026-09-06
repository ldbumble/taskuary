"""Freshness on the walk: select first, then validate; say when the thread moved, once; supersede what is behind (PW-050 to PW-053, PW-056, PW-057).

Next without a key surfaced whatever the pile held without asking the source whether the item
had moved; an FYI batch was never checked at all; a new line on a task with a drafted reply left
the draft sitting as if current; the "new message" notice repeated on every render. Now the walk
picks its item, refreshes that item's source (every channel in an FYI batch, once), re-picks when
the refresh changed the pile, and tells the owner once per new revision - before the assistant's
answer - that new messages came in and went through triage; a new inbound line on a task with a
pending draft marks the draft behind and, when triage says a reply is still owed, redrafts that
same review; the owner's own external answer retires the draft and the notice says it was answered.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import channels, funnel, ingest, responder, server
from taskuary.store import MemoryStore


def stamp(seconds=0): return (datetime.now() + timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')


def teams_task(s, title='Teams chat with Mindy', conv='teams:mindy', ext='teams:first', body='can you reset my account?', with_review=True):
    tid = s.create_task({'Title': title, 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': 'teams'}, 'router')
    first = s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': conv, 'Channel': 'teams', 'SourceName': 'Mindy', 'Subject': title,
                           'FromName': 'Mindy', 'SentAt': stamp(-20), 'BodyText': body, 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'ok give me 5 mins', 'Reason': 'needs a reply'}) if with_review else None
    return tid, first, rid


def later(s, tid, conv='teams:mindy', text='Actually it works now.'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'teams:{text[:10]}', 'ConversationId': conv, 'Channel': 'teams', 'SourceName': 'Mindy',
                          'Subject': 'Teams chat with Mindy', 'FromName': 'Mindy', 'SentAt': stamp(), 'BodyText': text, 'Status': 'routed'})


def activate(s, *types):
    for t in types:
        c = s.get_connector_by_type(t)
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': '{}'}, 'test')


class Base(unittest.TestCase):
    def setUp(self):
        funnel.invalidate(); server._NOTICED.clear()
        self.s = MemoryStore(); activate(self.s, 'teams', 'slack')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)


class SelectThenValidateTests(Base):
    def test_next_without_a_key_refreshes_the_picked_items_source_and_repicks_when_it_moved(self):
        tid, first, rid = teams_task(self.s)
        polls = []
        def poll(*a, **k):
            polls.append(k.get('only'))
            later(self.s, tid); return 1                                          # the refresh brings a newer line
        with mock.patch.object(server, '_poll_reports', side_effect=poll):
            fresh = server._refresh_next_selection(server.SurfaceBody())
        self.assertEqual(polls, [['teams']])
        self.assertTrue(fresh['newer']); self.assertEqual(fresh['item']['key'], f'review:{rid}')
        self.assertEqual(fresh['item']['mid'], self.s.last_inbound_on_task(tid)['MessageId'])   # the pick speaks with the newest line

    def test_an_fyi_batch_is_validated_once_per_channel(self):
        for i, ch in enumerate(('teams', 'slack', 'teams')):
            self.s.add_message({'ExternalId': f'fyi{i}', 'ConversationId': f'c{i}', 'Channel': ch, 'SourceName': 'x', 'Subject': f'note {i}',
                                'FromName': 'Sam', 'SentAt': stamp(-10 - i), 'BodyText': 'fyi only', 'Status': 'filed'})
            self.s.add_route(i + 1, None, 'file', None, 'triage: fyi - nothing to do', [], 'triage')
        polls = []
        with mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: polls.append(k.get('only')) or 0):
            fresh = server._refresh_next_selection(server.SurfaceBody())
        self.assertEqual(sorted(p[0] for p in polls), ['slack', 'teams'])
        self.assertFalse(fresh['newer'])

    def test_a_quiet_source_is_a_no_op(self):
        tid, first, rid = teams_task(self.s)
        with mock.patch.object(server, '_poll_reports', return_value=0):
            fresh = server._refresh_next_selection(server.SurfaceBody())
        self.assertFalse(fresh['newer']); self.assertEqual(fresh['item']['key'], f'review:{rid}')


class NoticeTests(Base):
    def stream(self, c, **body):
        with c.stream('POST', '/api/concierge/stream', json={'mode': 'next', **body}) as r:
            # the sync_messages tool event is the poll's own receipt; the notice and the answer are what is asserted
            return [e for e in (json.loads(l) for l in r.iter_lines() if l.strip()) if e.get('type') != 'tool_call']

    def test_the_notice_comes_before_the_answer_once_per_revision_and_says_triage_ran(self):
        tid, first, rid = teams_task(self.s)
        c = TestClient(server.app)
        arrivals = [lambda: later(self.s, tid)]
        def poll(*a, **k):
            if arrivals: arrivals.pop()(); return 1
            return 0
        with mock.patch.object(server, '_poll_reports', side_effect=poll), mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True):
            lines = self.stream(c)
            self.assertEqual([l['type'] for l in lines], ['context_update', 'done'])
            self.assertIn('New message', lines[0]['say']); self.assertIn('triage', lines[0]['say'].lower())
            self.assertIn('works now', lines[0]['say'])
            again = self.stream(c, include_surfaced=True)                         # nothing new: no second notice
            self.assertEqual([l['type'] for l in again], ['done'])
            arrivals.append(lambda: later(self.s, tid, text='One more thing: the VPN too.'))
            third = self.stream(c, include_surfaced=True)
            self.assertEqual([l['type'] for l in third], ['context_update', 'done'])
            self.assertIn('VPN', third[0]['say'])

    def test_a_refresh_that_fails_is_an_error_not_a_fresh_answer(self):
        tid, first, rid = teams_task(self.s)
        c = TestClient(server.app)
        with mock.patch.object(server, '_poll_reports', return_value=False), mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True):
            lines = self.stream(c)
        self.assertEqual([l['type'] for l in lines], ['error'])
        self.assertIn('stale', lines[0]['error'].lower())


def mail_task(s):
    """An email thread with a drafted reply - a later mail is judged by the follow-up verdict (chat lines take chat_route)."""
    tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': 'email'}, 'router')
    first = s.add_message({'TaskId': tid, 'ExternalId': 'm:first', 'ConversationId': 'AAQk-m', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                           'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': stamp(-60),
                           'BodyText': 'Could you send me the August export?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Here it is.', 'Reason': 'needs a reply: asked'})
    return tid, first, rid


def mail(text, ext):
    return {'external_id': ext, 'channel': 'email', 'conversation_id': 'AAQk-m', 'from_email': 'dana@vendor.example', 'from_name': 'Dana',
            'subject': 'Re: August export', 'body': text, 'sent_at': stamp(), 'source_name': 'me@northwind.example'}


class SupersedeTests(Base):
    def test_a_new_ask_on_a_task_with_a_pending_draft_marks_it_behind_and_redrafts_that_same_review(self):
        tid, first, rid = mail_task(self.s)
        spawned = []
        llm = lambda *a, **k: json.dumps({'intent': 'reply_only', 'why': 'another question'})
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append((f.__name__, a[2] if len(a) > 2 else None))):
            out = ingest.ingest_message(self.s, mail('And could you add the July file too?', 'm:second'), llm=llm)
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))
        self.assertEqual(self.s.get_review(rid)['Stale'], 1)
        self.assertEqual(spawned, [('_auto_draft', rid)])                          # the SAME review, redrafted - never a second one
        self.assertEqual(len(self.s.list_reviews('pending')), 1)

    def test_an_fyi_line_leaves_the_draft_alone(self):
        tid, first, rid = mail_task(self.s)
        llm = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'thanks'})
        with mock.patch.object(ingest, '_spawn') as spawn:
            ingest.ingest_message(self.s, mail('Thanks so much!', 'm:thanks'), llm=llm)
        self.assertEqual(self.s.get_review(rid)['Stale'], 0); spawn.assert_not_called()

    def test_the_owners_external_answer_retires_the_draft_and_the_notice_says_so(self):
        tid, first, rid = teams_task(self.s)
        sent = {'ConversationId': 'teams:mindy', 'SentAt': stamp(), 'Channel': 'teams'}
        channels.retire_draft_answered_elsewhere(self.s, tid, sent)
        rv = self.s.get_review(rid)
        self.assertEqual(rv['Status'], 'superseded')
        line = server._context_update_line({'after': {'FromName': 'You', 'BodyText': 'done, reset it'}, 'item': {'ref': 'TQ-0001', 'rid': rid, 'tid': tid}})
        self.assertIn('answered', line.lower()); self.assertIn('nothing to send', line.lower())
        self.assertNotIn('redraft', line.lower())


if __name__ == '__main__':
    unittest.main()
