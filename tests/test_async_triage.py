"""Show first, judge next.

A sync was one long silence: each message waited for its own AI call before it appeared on
the timeline, so a forty-mail catch-up was minutes of "syncing" and then everything at once.
Inside ingest.deferred() a message is STORED and shown at once, wearing 'triaging'; drain()
then judges the queue in arrival order and each row lands - in place, same MessageId - where
its verdict puts it. Nothing that costs nothing waits: dedupe, feeds and policies still answer
immediately, and outside deferred() nothing changes at all.
"""
import unittest

from taskuary import ingest
from taskuary.store import MemoryStore

OWNER = 'me@corp.example'


def mail(i, **over):
    return {'external_id': f'q{i}', 'channel': 'email', 'conversation_id': f'conv-{i}', 'from_email': f'p{i}@client.example',
            'subject': f'Question {i}', 'body': 'Can you check the ledger for me?', 'to': [OWNER], **over}


def oracle(intent, seen=None):
    def f(sys_, usr_, **kw):
        if seen is not None: seen.append(usr_)
        return '{"intent": "%s", "why": "oracle"}' % intent
    return f


class DeferredIngestTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.save_source({'Channel': 'email', 'Address': OWNER, 'Owner': 'me', 'Active': 1}, 'test')
        ingest._PENDING.clear()

    def test_inside_deferred_the_message_is_shown_at_once_and_judged_by_nobody_yet(self):
        asked = []
        with ingest.deferred():
            out = ingest.ingest_message(self.s, mail(1), llm=oracle('task', asked))
        self.assertEqual((out['status'], out['task_id']), ('queued', None))
        self.assertEqual(asked, [])
        row = next(r for r in self.s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual((row['MsgStatus'], row['NeedsYou'], row['Decision']), ('triaging', 0, 'queued'))
        self.assertIn('triage decides next', row['RouteReason'])

    def test_drain_judges_in_place_and_in_order(self):
        with ingest.deferred():
            a = ingest.ingest_message(self.s, mail(1))['message_id']
            b = ingest.ingest_message(self.s, mail(2, conversation_id='conv-1', external_id='q2'))['message_id']   # same thread
        asked = []
        self.assertEqual(ingest.drain(self.s, llm=oracle('task', asked)), 2)
        ra, rb = self.s.get_message(a), self.s.get_message(b)
        self.assertEqual((ra['Status'], rb['Status']), ('routed', 'routed'))
        self.assertIsNotNone(ra['TaskId']); self.assertEqual(rb['TaskId'], ra['TaskId'])   # the second joined the first's task
        self.assertEqual(len(asked), 1)                                                     # ...without a second AI call
        self.assertEqual(len([m for m in self.s.scan_messages() if m['Subject'].startswith('Question')]), 2)   # no duplicate rows
        self.assertEqual(self.s.pending_triage(), [])

    def test_a_drain_in_a_later_process_rebuilds_the_message_from_its_row(self):
        with ingest.deferred():
            mid = ingest.ingest_message(self.s, mail(1, cc=['dana@corp.example']))['message_id']
        ingest._PENDING.clear()                                                             # the app restarted
        asked = []
        ingest.drain(self.s, llm=oracle('reply_only', asked))
        self.assertEqual(self.s.get_message(mid)['Status'], 'routed')
        self.assertIn('"addressed_to_you": "to"', asked[0])                                 # the To/Cc lines survived the restart
        self.assertEqual(self.s.get_task(self.s.get_message(mid)['TaskId'])['Kind'], 'reply')

    def test_a_duplicate_arriving_while_pending_is_still_a_duplicate(self):
        with ingest.deferred():
            ingest.ingest_message(self.s, mail(1))
            self.assertEqual(ingest.ingest_message(self.s, mail(1))['status'], 'duplicate')

    def test_feeds_and_policies_do_not_wait(self):
        self.s.save_policy({'Name': 'noise', 'Kind': 'sender', 'Pattern': 'noreply@bank.example', 'Action': 'ignore',
                            'Reason': 'statements', 'SortOrder': 10, 'Active': 1}, 'test')
        with ingest.deferred():
            feed = ingest.ingest_message(self.s, mail(1), file_only=True)
            ign = ingest.ingest_message(self.s, mail(2, from_email='noreply@bank.example'))
        self.assertEqual((feed['status'], ign['status']), ('feed', 'ignored'))
        self.assertEqual(self.s.pending_triage(), [])

    def test_a_triage_that_raises_files_the_message_and_the_queue_moves_on(self):
        with ingest.deferred():
            bad = ingest.ingest_message(self.s, mail(1))['message_id']
            good = ingest.ingest_message(self.s, mail(2))['message_id']
        calls = []
        def flaky(sys_, usr_, **kw):
            calls.append(1)
            if len(calls) == 1: raise RuntimeError('model down')
            return '{"intent": "task", "why": "ok"}'
        ingest.drain(self.s, llm=flaky)
        self.assertEqual(self.s.get_message(bad)['Status'], 'filed')
        row = next(r for r in self.s.feed(limit=10) if r['MessageId'] == bad)
        self.assertIn('AI triage failed', row['RouteReason'])
        route = self.s.message_routes(bad)[-1]
        self.assertEqual(route['ParseError'], 'model down')
        self.assertIsNone(route['RawOutput'])
        self.assertEqual(self.s.get_message(good)['Status'], 'routed')

    def test_outside_deferred_nothing_changes(self):
        out = ingest.ingest_message(self.s, mail(1), llm=oracle('task'))
        self.assertEqual(out['status'], 'created')
        self.assertEqual(self.s.pending_triage(), [])

    def test_a_nameless_thread_does_not_inherit_deferred(self):
        """A TestClient poll holds deferred() on its own thread. Unittest's MainThread, and a
        random worker, must still judge - or the rest of the suite queues forever. poll_channels'
        pool inherits on purpose; that is a different test."""
        import threading
        asked, started, mid = [], threading.Event(), {}
        def worker():
            started.wait(1)
            mid['id'] = ingest.ingest_message(self.s, mail(9), llm=oracle('task', asked))['message_id']
        t = threading.Thread(target=worker)
        t.start()
        with ingest.deferred():
            started.set()
            t.join(2)
        self.assertFalse(t.is_alive())
        self.assertNotEqual(self.s.get_message(mid['id'])['Status'], 'triaging')
        self.assertEqual(len(asked), 1)

    def test_inner_deferred_does_not_turn_the_outer_off(self):
        asked = []
        with ingest.deferred():
            with ingest.deferred():
                pass
            ingest.ingest_message(self.s, mail(3), llm=oracle('task', asked))
        self.assertEqual(asked, [])
        self.assertEqual(self.s.pending_triage()[0]['Status'], 'triaging')


if __name__ == '__main__':
    unittest.main()
