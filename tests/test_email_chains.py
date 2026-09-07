"""The full email chain, fetched once and kept once (PW-009 to PW-015).

A mail arrived alone: triage saw it and whatever earlier messages happened to be stored, and a
reply to a thread that started before the watermark, in another folder, or while the app was
closed had no history at all. Now a conversation newly encountered - or one with gaps - has its
missing history retrieved from the provider: the thread is LISTED first (ids and metadata only),
and only the messages not yet stored have their bodies fetched, once. Fetched history lives on the
conversation as `history` rows (the owner's own sent mail as `context`), never on a task, never in
the feed or Unread, never re-triaged; coverage is recorded per conversation and an incomplete or
failed retrieval is said out loud in the context the model gets. Repeated polls change nothing.
"""
import json, unittest
from unittest import mock

from taskuary import chains, channels, ingest
from taskuary.store import MemoryStore
from tests.test_mail_catchup import FakeGraph, graph_mail, outlook_store, poll, T0
from datetime import timedelta

CONV = 'AAQk-refund'
ME = 'me@x.com'


def gmail(i, when, frm='v@vendor.example', conv=CONV):
    return {**graph_mail(i, when, frm=frm), 'conversationId': conv, 'id': f'g-{i}'}


class FakeThreadGraph:
    """The provider side of a conversation: list ids by conversation, fetch bodies by id."""
    def __init__(self, mails, fail=False):
        self.mails = {m['id']: m for m in mails}; self.listed, self.fetched, self.fail = [], [], fail
    def list_ids(self, tok, upn, conv):
        if self.fail: raise RuntimeError('Graph 503')
        self.listed.append(conv)
        return [{'id': m['id'], 'receivedDateTime': m['receivedDateTime'], 'from': m['from']} for m in self.mails.values() if m['conversationId'] == conv]
    def fetch(self, tok, upn, ids):
        self.fetched += list(ids)
        return [self.mails[i] for i in ids]


def stored(s, i, conv=CONV, status='routed', frm='v@vendor.example', tid=None):
    m = gmail(i, T0 + timedelta(minutes=i), frm=frm, conv=conv)
    return s.add_message({'TaskId': tid, 'ExternalId': f"graph:{m['id']}", 'ConversationId': conv, 'Channel': 'email', 'Subject': m['subject'],
                          'FromName': 'V', 'FromEmail': frm, 'SentAt': channels._local(m['receivedDateTime']), 'BodyText': f"body {i}", 'Status': status})


class RefreshTests(unittest.TestCase):
    def test_a_known_chain_is_listed_not_refetched(self):
        s, sid = outlook_store()
        for i in range(3): stored(s, i)
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(3)])
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            cov = chains.refresh_outlook(s, 'tok', ME, CONV)
        self.assertEqual(fake.fetched, []); self.assertEqual(cov['complete'], True); self.assertEqual(cov['added'], 0)
        self.assertEqual(len(s.thread_messages(CONV)), 3)

    def test_missing_history_is_fetched_once_and_kept_as_history(self):
        s, sid = outlook_store()
        stored(s, 3)                                                              # only D is stored
        mails = [gmail(i, T0 + timedelta(minutes=i)) for i in range(4)]
        mails[1]['from'] = {'emailAddress': {'name': 'Me', 'address': ME}}         # B was the owner's own reply
        fake = FakeThreadGraph(mails)
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            cov = chains.refresh_outlook(s, 'tok', ME, CONV)
            again = chains.refresh_outlook(s, 'tok', ME, CONV)
        self.assertEqual(sorted(fake.fetched), ['g-0', 'g-1', 'g-2']); self.assertEqual(cov['added'], 3); self.assertEqual(again['added'], 0)
        rows = s.thread_messages(CONV)
        self.assertEqual([r['ExternalId'] for r in rows], ['graph:g-0', 'graph:g-1', 'graph:g-2', 'graph:g-3'])
        self.assertEqual([r['Status'] for r in rows[:3]], ['history', 'context', 'history'])
        self.assertTrue(all(r['TaskId'] is None for r in rows[:3]))
        self.assertEqual(s.list_tasks(), [])                                     # history opens no work
        self.assertFalse([r for r in s.feed(limit=50) if r['MessageId'] in {x['MessageId'] for x in rows[:3]}])   # and is not an arrival
        lines = ingest.exchange_lines(s, {'conversation_id': CONV, 'subject': 'mail 3', '_mid': rows[3]['MessageId'], 'sent_at': channels._local(mails[3]['receivedDateTime'])})
        self.assertEqual(len(lines), 3); self.assertTrue(lines[1].startswith('you '))

    def test_same_subject_on_another_conversation_is_never_merged(self):
        s, sid = outlook_store()
        stored(s, 0)
        other = [gmail(9, T0, conv='AAQk-other')]
        fake = FakeThreadGraph([gmail(0, T0)] + other)
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            chains.refresh_outlook(s, 'tok', ME, CONV)
        self.assertEqual(fake.fetched, []); self.assertEqual(len(s.thread_messages('AAQk-other')), 0)

    def test_a_failed_retrieval_is_recorded_and_disclosed_not_presented_as_complete(self):
        s, sid = outlook_store()
        stored(s, 3)
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(4)], fail=True)
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            cov = chains.refresh_outlook(s, 'tok', ME, CONV)
        self.assertFalse(cov['complete']); self.assertIn('Graph 503', cov['error'])
        self.assertEqual(chains.coverage(s, CONV)['complete'], False)
        lines = ingest.exchange_lines(s, {'conversation_id': CONV, 'subject': 'mail 3', 'sent_at': '2026-09-06 12:00:00'})
        self.assertTrue(lines[0].startswith('…') and 'history' in lines[0].lower(), lines)


class PollHookTests(unittest.TestCase):
    def test_a_newly_encountered_thread_is_completed_during_the_poll_and_only_once(self):
        s, sid = outlook_store()
        d = gmail(3, T0 + timedelta(minutes=3))
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(3)] + [d])
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            poll(s, FakeGraph({'inbox': [d]}))
            poll(s, FakeGraph({'inbox': [d]}))
        self.assertEqual(fake.listed, [CONV]); self.assertEqual(sorted(fake.fetched), ['g-0', 'g-1', 'g-2'])
        rows = s.thread_messages(CONV)
        self.assertEqual(len(rows), 4); self.assertEqual(rows[-1]['ExternalId'], 'graph:g-3')
        self.assertEqual(len([r for r in rows if r['Status'] == 'history']), 3)

    def test_a_reply_on_a_known_thread_with_a_gap_retrieves_only_the_gap(self):
        s, sid = outlook_store()
        for i in (0, 1): stored(s, i)                                             # A and B stored before this feature; no coverage row yet
        d = gmail(3, T0 + timedelta(minutes=3))
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(3)] + [d])
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch):
            poll(s, FakeGraph({'inbox': [d]}))
            poll(s, FakeGraph({'inbox': [d]}))
        self.assertEqual(fake.listed, [CONV]); self.assertEqual(fake.fetched, ['g-2'])
        self.assertEqual([r['ExternalId'] for r in s.thread_messages(CONV)], ['graph:g-0', 'graph:g-1', 'graph:g-2', 'graph:g-3'])

    def test_a_failed_completion_is_retried_on_the_next_mail_of_the_thread(self):
        s, sid = outlook_store()
        d, e = gmail(3, T0 + timedelta(minutes=3)), gmail(4, T0 + timedelta(hours=2))
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(4)] + [e], fail=True)
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch), \
             mock.patch.object(channels, '_mail_cutoff', side_effect=[
                 (T0 + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 (T0 + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')]):
            poll(s, FakeGraph({'inbox': [d]}))
            self.assertFalse(chains.coverage(s, CONV)['complete'])
            fake.fail = False
            poll(s, FakeGraph({'inbox': [d, e]}))
        self.assertTrue(chains.coverage(s, CONV)['complete']); self.assertEqual(sorted(fake.fetched), ['g-0', 'g-1', 'g-2'])

    def test_a_later_reply_in_the_listing_is_left_for_the_poll_to_triage(self):
        s, sid = outlook_store()
        d, e = gmail(3, T0 + timedelta(minutes=3)), gmail(4, T0 + timedelta(hours=2))
        fake = FakeThreadGraph([gmail(i, T0 + timedelta(minutes=i)) for i in range(3)] + [d, e])   # E is already at the provider
        with mock.patch.object(chains, 'list_ids_graph', fake.list_ids), mock.patch.object(chains, 'fetch_graph', fake.fetch), \
             mock.patch.object(channels, '_mail_cutoff', side_effect=[
                 (T0 + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 (T0 + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')]):
            poll(s, FakeGraph({'inbox': [d]}))
            self.assertEqual({r['ExternalId']: r['Status'] for r in s.thread_messages(CONV)}.get('graph:g-4'), None)   # not swallowed as history
            poll(s, FakeGraph({'inbox': [d, e]}))
        rows = {r['ExternalId']: r['Status'] for r in s.thread_messages(CONV)}
        self.assertNotIn(rows['graph:g-4'], ('history', 'context'))                    # E arrived through the poll and was judged
        self.assertEqual([rows[f'graph:g-{i}'] for i in range(3)], ['history'] * 3)


class ListingTests(unittest.TestCase):
    def test_listing_follows_pagination_and_never_asks_for_bodies(self):
        pages = {'p1': {'value': [{'id': 'g-0'}], '@odata.nextLink': 'p2'}, 'p2': {'value': [{'id': 'g-1'}]}}
        calls = []
        class R:
            def __init__(self, j): self.j = j
            def raise_for_status(self): pass
            def json(self): return self.j
        def get(url, headers=None, timeout=None, params=None):
            calls.append((url, params)); return R(pages['p2' if url == 'p2' else 'p1'])
        with mock.patch.object(channels.requests, 'get', get):
            ids = chains.list_ids_graph('tok', ME, CONV)
        self.assertEqual([x['id'] for x in ids], ['g-0', 'g-1']); self.assertEqual(len(calls), 2)
        self.assertNotIn('body', calls[0][1]['$select']); self.assertIn(CONV, calls[0][1]['$filter']); self.assertIsNone(calls[1][1])

    def test_a_provider_that_keeps_pointing_at_the_same_page_is_a_stopped_listing(self):
        """It used to return the one page as if the conversation ended there (PW-010): a repeated page is
        the provider misbehaving, and coverage must say the listing stopped."""
        calls = []
        class R:
            def raise_for_status(self): pass
            def json(self): return {'value': [{'id': 'g-0'}], '@odata.nextLink': 'again'}
        def get(url, headers=None, timeout=None, params=None): calls.append(url); return R()
        with mock.patch.object(channels.requests, 'get', get):
            with self.assertRaises(chains.ListingStopped) as cm: chains.list_ids_graph('tok', ME, CONV)
        self.assertEqual([x['id'] for x in cm.exception.ids], ['g-0']); self.assertLessEqual(len(calls), 2)
        self.assertIn('listing', str(cm.exception))                    # the same ids again is an empty continued page

    def test_a_wholesale_mocked_transport_yields_nothing_rather_than_looping(self):
        with mock.patch.object(channels, 'requests') as req:                       # what tests of other features do
            ids = chains.list_ids_graph('tok', ME, CONV)
        self.assertEqual(ids, []); self.assertLessEqual(req.get.call_count, chains.MAX_PAGES)


class ImapChainTests(unittest.TestCase):
    def test_references_pull_the_thread_from_inbox_and_sent(self):
        from tests.test_imap_catchup import FakeBox, mime
        from datetime import datetime
        import email.utils
        from datetime import timedelta
        now = datetime.now().astimezone()
        root = '<root@partner.example>'
        def mail(uid, subject, refs, when, frm='Rita Vole <rita@partner.example>'):
            import email.message
            m = email.message.EmailMessage()
            m['From'], m['To'], m['Subject'] = frm, 'me@myco.example', subject
            m['Date'] = email.utils.format_datetime(when); m['Message-ID'] = f'<{uid}@partner.example>'
            if refs: m['References'] = refs
            m.set_content(f'body {uid}\n'); return (m.as_bytes(), when)
        inbox = {1: mail(1, 'Export', '', now - timedelta(hours=2)), 3: mail(3, 'Re: Export', root, now - timedelta(hours=1)),
                 5: mail(5, 'Re: Export', root, now)}                                   # uid 5 is NEWER than the mail being judged
        inbox[1] = (inbox[1][0].replace(b'<1@partner.example>', root.encode()), inbox[1][1])   # uid 1 IS the root
        sent = {7: mail(7, 'Re: Export', root, now - timedelta(minutes=90), frm='Me <me@myco.example>')}
        box = FakeBox(inbox, sent=sent)
        s = MemoryStore()
        at3 = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        s.add_message({'ExternalId': 'imap:me@myco.example:3', 'ConversationId': root, 'Channel': 'email', 'Subject': 'Re: Export',
                       'FromEmail': 'rita@partner.example', 'BodyText': 'body 3', 'SentAt': at3, 'Status': 'routed'})
        cov = chains.refresh_imap(s, box, 'me@myco.example', root, before=at3)
        self.assertTrue(cov['complete']); self.assertEqual(cov['added'], 2)              # the root and the owner's reply; uid 5 is the poll's
        rows = s.thread_messages(root)
        self.assertEqual(sorted(r['ExternalId'] for r in rows), ['imap-sent:me@myco.example:7', 'imap:me@myco.example:1', 'imap:me@myco.example:3'])
        self.assertEqual({r['ExternalId']: r['Status'] for r in rows}['imap-sent:me@myco.example:7'], 'context')
        self.assertEqual({r['ExternalId']: r['Status'] for r in rows}['imap:me@myco.example:1'], 'history')


class CoverageHonestyTests(unittest.TestCase):
    """PW-010/011: a listing that stopped early or a fetch that failed is INCOMPLETE coverage, said so; and
    coverage belongs to the mailbox that checked it, never to a bare conversation id another account shares."""
    def test_an_empty_continued_page_stops_the_listing_and_coverage_says_so(self):
        s, sid = outlook_store()
        pages = {'p1': {'value': [gmail(0, T0)], '@odata.nextLink': 'p2'}, 'p2': {'value': []}}
        class R:
            def __init__(self, j): self.j = j
            def raise_for_status(self): pass
            def json(self): return self.j
        fetched = []
        get = lambda url, headers=None, timeout=None, params=None: R(pages['p2' if url == 'p2' else 'p1'])
        with mock.patch.object(channels.requests, 'get', get), mock.patch.object(chains, 'fetch_graph', lambda tok, upn, ids: fetched.extend(ids) or []):
            cov = chains.refresh_outlook(s, 'tok', ME, CONV)
        self.assertFalse(cov['complete']); self.assertIn('page', cov['error']); self.assertEqual(cov['listed'], 1)
        self.assertEqual(fetched, ['g-0'], 'what WAS listed is still fetched')
        self.assertTrue(chains.needs_history(s, CONV, ME), 'it is listed again next time')

    def test_a_failed_imap_fetch_leaves_coverage_incomplete_but_keeps_the_rest(self):
        from tests.test_imap_catchup import FakeBox
        import email.message, email.utils
        from datetime import datetime, timedelta
        now, root = datetime.now().astimezone(), '<root@partner.example>'
        def mail(uid, refs, when, mid=None):
            m = email.message.EmailMessage()
            m['From'], m['To'], m['Subject'] = 'Rita <rita@partner.example>', 'me@myco.example', 'Export'
            m['Date'] = email.utils.format_datetime(when); m['Message-ID'] = mid or f'<{uid}@partner.example>'
            if refs: m['References'] = refs
            m.set_content(f'body {uid}\n'); return (m.as_bytes(), when)
        inbox = {1: mail(1, '', now - timedelta(hours=3), mid=root), 2: mail(2, root, now - timedelta(hours=2)), 3: mail(3, root, now - timedelta(hours=1))}
        box = FakeBox(inbox); box.bad = {1}                                             # the root's FETCH answers NO
        s = MemoryStore()
        at3 = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        s.add_message({'ExternalId': 'imap:me@myco.example:3', 'ConversationId': root, 'Channel': 'email', 'Subject': 'Export',
                       'FromEmail': 'rita@partner.example', 'BodyText': 'body 3', 'SentAt': at3, 'Status': 'routed'})
        cov = chains.refresh_imap(s, box, 'me@myco.example', root, before=at3)
        self.assertFalse(cov['complete']); self.assertIn('could not be fetched', cov['error'])
        self.assertEqual(cov['added'], 1, 'uid 2 is kept; only the failed uid is missing')
        self.assertTrue(chains.needs_history(s, root, 'me@myco.example'))

    def test_coverage_belongs_to_the_mailbox_that_checked_it(self):
        s = MemoryStore()
        s.set_chain_coverage(CONV, 'email', 'a@x.com', {'complete': True, 'listed': 2, 'added': 0, 'error': None})
        self.assertFalse(chains.needs_history(s, CONV, 'a@x.com'))
        self.assertTrue(chains.needs_history(s, CONV, 'b@x.com'), "another account's conversation is its own to complete")
        self.assertEqual(chains.coverage(s, CONV)['complete'], True, 'a caller without a mailbox reads the latest row')
        s.set_chain_coverage(CONV, 'email', 'b@x.com', {'complete': False, 'listed': 0, 'added': 0, 'error': 'x'})
        self.assertFalse(chains.needs_history(s, CONV, 'a@x.com'), 'B failing does not touch A')
        self.assertEqual(chains.coverage(s, CONV, 'b@x.com')['error'], 'x')


if __name__ == '__main__':
    unittest.main()
