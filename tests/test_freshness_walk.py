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


def teams_task(s, title='Teams chat with Robin', conv='teams:robin', ext='teams:first', body='can you reset my account?', with_review=True):
    tid = s.create_task({'Title': title, 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': 'teams'}, 'router')
    first = s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': conv, 'Channel': 'teams', 'SourceName': 'Robin', 'Subject': title,
                           'FromName': 'Robin', 'SentAt': stamp(-20), 'BodyText': body, 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'ok give me 5 mins', 'Reason': 'needs a reply'}) if with_review else None
    return tid, first, rid


def later(s, tid, conv='teams:robin', text='Actually it works now.'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'teams:{text[:10]}', 'ConversationId': conv, 'Channel': 'teams', 'SourceName': 'Robin',
                          'Subject': 'Teams chat with Robin', 'FromName': 'Robin', 'SentAt': stamp(), 'BodyText': text, 'Status': 'routed'})


def activate(s, *types):
    for t in types:
        c = s.get_connector_by_type(t)
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': '{}'}, 'test')


class Base(unittest.TestCase):
    def setUp(self):
        funnel.invalidate(); server._NOTICED.clear()
        self.s = MemoryStore(); activate(self.s, 'teams', 'slack')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)


class TheChangeCheckFollowsTheFourTests(Base):
    """Design C (2026-09-17): Next answers from the rail, then asks the provider about what it put on the
    table - on a thread, after the answer. The check itself is unchanged: every channel of the item(s) once."""

    def test_the_picked_items_source_is_polled_once_after_the_answer_and_the_line_lands(self):
        tid, first, rid = teams_task(self.s)
        polls = []
        def poll(*a, **k):
            polls.append(k.get('only'))
            later(self.s, tid); return 1                                          # the refresh brings a newer line
        item = funnel.next_item(self.s, None)
        self.assertEqual(item['key'], f'review:{rid}')
        with mock.patch.object(server, '_poll_reports', side_effect=poll):
            t = server._refresh_after({'item': item}); t.join(5)
        self.assertEqual(polls, [['teams']])
        # the line is in the store; the page's next read of the item carries it (the strip says so)
        self.assertEqual(self.s.last_inbound_on_task(tid)['BodyText'], 'Actually it works now.')
        self.assertEqual(funnel.next_item(self.s, f'review:{rid}')['mid'], self.s.last_inbound_on_task(tid)['MessageId'])

    def test_an_fyi_batch_is_checked_once_per_channel(self):
        for i, ch in enumerate(('teams', 'slack', 'teams')):
            self.s.add_message({'ExternalId': f'fyi{i}', 'ConversationId': f'c{i}', 'Channel': ch, 'SourceName': 'x', 'Subject': f'note {i}',
                                'FromName': 'Sam', 'SentAt': stamp(-10 - i), 'BodyText': 'fyi only', 'Status': 'filed'})
            self.s.add_route(i + 1, None, 'file', None, 'triage: fyi - nothing to do', [], 'triage')
        polls = []
        first = funnel.next_item(self.s, None)
        card = {'kind': 'fyis', 'key': 'fyis:x', 'items': funnel.fyi_batch(self.s, first)}
        with mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: polls.append(k.get('only')) or 0):
            server._refresh_after({'item': card}).join(5)
        self.assertEqual(sorted(p[0] for p in polls), ['slack', 'teams'])

    def test_a_quiet_source_is_a_no_op(self):
        tid, first, rid = teams_task(self.s)
        with mock.patch.object(server, '_poll_reports', return_value=0):
            f = server._refresh_items([funnel.next_item(self.s, None)])
        self.assertFalse(f['newer'])

    def test_nothing_on_the_table_asks_nothing(self):
        with mock.patch.object(server, '_poll_reports', side_effect=AssertionError('must not poll')):
            self.assertIsNone(server._refresh_after({'item': None}))
            self.assertIsNone(server._refresh_after({}))


class NoticeTests(Base):
    def stream(self, c, **body):
        with c.stream('POST', '/api/concierge/stream', json={'mode': 'next', **body}) as r:
            # the sync_messages tool event is the poll's own receipt; the notice and the answer are what is asserted
            return [e for e in (json.loads(l) for l in r.iter_lines() if l.strip()) if e.get('type') != 'tool_call']

    def test_the_answer_comes_first_and_the_provider_is_asked_after_it(self):
        """Design C: no notice and no wait before the answer - the rail's item is spoken as it stands, the
        provider is polled once the answer is out, and what arrives reaches the page through its own reload
        (the strip's "New message from ... arrived" line, funnelPile.currentItemFromPile)."""
        tid, first, rid = teams_task(self.s)
        c = TestClient(server.app)
        polls = []
        def poll(*a, **k):
            polls.append(k.get('only')); later(self.s, tid); return 1
        with mock.patch.object(server, '_poll_reports', side_effect=poll), mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True):
            lines = self.stream(c)
            self.assertEqual([l['type'] for l in lines], ['done'])
            self.assertEqual(lines[0]['item']['key'], f'review:{rid}')
            self.assertEqual(lines[0]['item']['mid'], first, 'spoken as the rail had it - the check had not run yet')
            server.wait_refresh_after(5)
        self.assertEqual(polls, [['teams']])
        newest = self.s.last_inbound_on_task(tid)['MessageId']
        self.assertNotEqual(newest, first)
        cur = c.get('/api/funnel/pile', params={'force': 1, 'current': f'review:{rid}'}).json()['current']
        self.assertEqual(cur['mid'], newest, "the page's next read carries the line that arrived")

    def test_a_named_pull_still_refreshes_its_item_first(self):
        """Clicking a row is about THAT item: the check stays up front, with its notice (PW-050/052)."""
        tid, first, rid = teams_task(self.s)
        c = TestClient(server.app)
        with mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: later(self.s, tid) and 1), \
             mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True):
            lines = self.stream(c, key=f'review:{rid}')
        self.assertEqual([l['type'] for l in lines], ['context_update', 'done'])
        self.assertIn('works now', lines[0]['say'])

    def test_a_provider_that_cannot_be_reached_does_not_fail_the_answer(self):
        tid, first, rid = teams_task(self.s)
        c = TestClient(server.app)
        with mock.patch.object(server, '_poll_reports', return_value=False), mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True):
            lines = self.stream(c)
            server.wait_refresh_after(5)
        self.assertEqual([l['type'] for l in lines], ['done'])


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

    def test_a_second_line_judged_a_task_still_repoints_and_redrafts_the_pending_reply(self):
        """Ray asked for the budgets link, then wrote again asking for access to the files. Triage
        called the second mail a task, so the draft was ONLY marked behind: still pinned to the
        first mail, warned as stale, with nothing behind the warning but a Refresh link (TQ-0665,
        2026-09-21). What the new line was judged to be does not change that a reply is owed to it."""
        tid, first, rid = mail_task(self.s)
        spawned = []
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'he needs access granted'})
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append((f.__name__, a[2] if len(a) > 2 else None))):
            out = ingest.ingest_message(self.s, mail('I also need access to the census files.', 'm:second'), llm=llm)
        rv = self.s.get_review(rid)
        self.assertEqual(out['task_id'], tid)
        self.assertNotEqual(rv['MessageId'], first)                                # re-pointed at the line it must answer
        self.assertIn(('_auto_draft', rid), spawned)                               # ...and rewritten from it
        self.assertEqual(len(self.s.list_reviews('pending')), 1)

    def test_the_second_message_adds_its_own_boxes_to_the_task_list(self):
        """Re-triaged means re-triaged: what the new line ASKS FOR joins the list, nothing already
        on it moves or unticks, and the addition is said on the task rather than made silently.

        The code was there; on TQ-0665 it did nothing, because the verdict came back with no
        checklist at all - the same field the model dropped along with title and summary. The
        schema now requires it, so this is the link that had never actually run on that thread."""
        tid, first, rid = mail_task(self.s)
        self.s.set_task_checklist(tid, ['Send the August export'], 'triage')
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'he needs access',
                                          'checklist': ['Send the August export', 'Grant access to the census files']})
        with mock.patch.object(ingest, '_spawn'):
            ingest.ingest_message(self.s, mail('I also need access to the census files.', 'm:second'), llm=llm)
        boxes = [i['text'] for i in self.s.task_checklist(tid)]
        self.assertEqual(boxes, ['Send the August export', 'Grant access to the census files'])   # added, not replaced
        said = [c['Body'] for c in self.s.list_comments(tid) if 'New from the latest message' in (c['Body'] or '')]
        self.assertTrue(said and 'Grant access to the census files' in said[0])

    def test_an_fyi_line_leaves_the_draft_alone(self):
        tid, first, rid = mail_task(self.s)
        llm = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'thanks'})
        with mock.patch.object(ingest, '_spawn') as spawn:
            ingest.ingest_message(self.s, mail('Thanks so much!', 'm:thanks'), llm=llm)
        self.assertEqual(self.s.get_review(rid)['Stale'], 0); spawn.assert_not_called()

    def test_the_owners_external_answer_retires_the_draft_and_the_notice_says_so(self):
        tid, first, rid = teams_task(self.s)
        sent = {'ConversationId': 'teams:robin', 'SentAt': stamp(), 'Channel': 'teams'}
        channels.retire_draft_answered_elsewhere(self.s, tid, sent)
        rv = self.s.get_review(rid)
        self.assertEqual(rv['Status'], 'superseded')
        line = server._context_update_line({'after': {'FromName': 'You', 'BodyText': 'done, reset it'}, 'item': {'ref': 'TQ-0001', 'rid': rid, 'tid': tid}})
        self.assertIn('answered', line.lower()); self.assertIn('nothing to send', line.lower())
        self.assertNotIn('redraft', line.lower())


if __name__ == '__main__':
    unittest.main()
