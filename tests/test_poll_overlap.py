"""A message that arrives moments before a poll must not be lost for good.

The reported case, reconstructed from the log and Graph itself. A Teams message from Richard
Spencer was created at 19:29:11Z. A poll ran at 15:29:19 local - eight seconds later - and
asked getAllMessages/delta for everything newer than its own last watermark. Graph's delta is
eventually consistent and had not surfaced an eight-second-old message yet, so the poll saw
nothing and moved the watermark to 15:29:19 regardless. Every poll after that asked for
"newer than 15:29:19", and the message sat permanently on the wrong side of the line: Sync
now could not find it, because syncing is what buried it.

Every channel here shares that shape - a watermark that jumps to now - so the window reaches
back past it. Dedupe makes the re-read free: ingest_message checks external_id in its first
line, before policies and before any AI call.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import channels, net
from taskuary.channels import POLL_OVERLAP, STARTUP_OVERLAP, _since


class OverlapTests(unittest.TestCase):
    def test_the_window_reaches_back_past_its_own_watermark(self):
        polled = datetime.now() - timedelta(minutes=1)
        got = _since({'LastPolledAt': polled.isoformat(sep=' ', timespec='seconds')})
        self.assertLess(got, polled)
        self.assertAlmostEqual((polled - got).total_seconds(), POLL_OVERLAP.total_seconds(), delta=2)

    def test_the_eight_second_message_is_inside_the_next_window(self):
        """The actual failure, to the second: sent at :11, polled at :19, and the poll after
        that must still be able to see it."""
        sent = datetime(2026, 8, 24, 15, 29, 11)
        watermark = datetime(2026, 8, 24, 15, 29, 19)          # what that poll wrote
        self.assertLess(_since({'LastPolledAt': watermark.isoformat(sep=' ')}), sent)

    def test_a_source_never_polled_still_reaches_back_a_day(self):
        got = _since({})
        self.assertAlmostEqual((datetime.now() - got).total_seconds(), 86400, delta=5)

    def test_a_backfill_still_widens_the_window_rather_than_narrowing_it(self):
        """Startup catch-up asks for hours; the overlap must never make that window smaller."""
        polled = (datetime.now() - timedelta(minutes=1)).isoformat(sep=' ', timespec='seconds')
        got = _since({'LastPolledAt': polled}, backfill_hours=72)
        self.assertAlmostEqual((datetime.now() - got).days, 3, delta=1)

    def test_the_catchup_asks_for_the_gap_and_not_a_rounded_up_day(self):
        """The window must reach back past the watermark by the startup overlap and NO further.

        Closed 8.75h, the day-granular catch-up asked Graph for 24h from now - 15 hours BEHIND
        the watermark, into mail already stored. 272 of the 365 messages one such startup pulled
        were dropped by dedupe (the owner's mailbox, 2026-09-17)."""
        closed_h = 8.75
        polled = datetime.now() - timedelta(hours=closed_h)
        got = _since({'LastPolledAt': polled.isoformat(sep=' ', timespec='seconds')},
                     backfill_hours=closed_h + STARTUP_OVERLAP.total_seconds() / 3600)
        reach = (polled - got).total_seconds()
        self.assertGreater(reach, 0)                                       # still past the watermark
        self.assertAlmostEqual(reach, STARTUP_OVERLAP.total_seconds(), delta=120)

    def test_re_reading_the_overlap_costs_nothing(self):
        """The whole fix rests on this: a message seen twice is dropped on the FIRST line of
        ingest, before any policy is evaluated and before any AI is called."""
        from unittest import mock
        from taskuary.ingest import ingest_message
        from taskuary.store import MemoryStore
        s = MemoryStore()
        m = {'external_id': 'teams:c1:1', 'channel': 'teams', 'subject': 'x', 'body': 'hello',
             'from_name': 'Ray Silva', 'from_email': 'rs@partner.example'}
        ingest_message(s, m, llm=lambda *a, **k: '{"intent": "fyi", "why": "t"}')
        with mock.patch('taskuary.ingest.evaluate') as pol:
            llm = mock.Mock()
            out = ingest_message(s, m, llm=llm)
        self.assertEqual(out['status'], 'duplicate')
        pol.assert_not_called()                                # no policy pass
        llm.assert_not_called()                                # and no AI call


def _iso(dt): return channels._utc(dt)


class _R:
    def __init__(self, code=200, j=None): self.status_code, self._j, self.text = code, j or {}, ''
    def json(self): return self._j
    def raise_for_status(self):
        if self.status_code >= 400: raise net.HTTPError(str(self.status_code))


class _Graph:
    """Microsoft, as the live card saw it on 2026-11-13: getAllMessages reads an EXPORT copy of the chats that lags the chat itself,
    so a message lands in it late, carrying the older lastModifiedDateTime it was written at. A filtered read sees what is in the
    export and modified after its filter; a delta link sees whatever landed in the export after that link was handed out."""
    UPN = 'alex@northwind.example'
    def __init__(self): self.export, self.chats, self.calls = [], [], []
    def land(self, mid, chat, at, text='can you send the deck?'):
        self.export.append({'id': mid, 'chatId': chat, 'messageType': 'message', 'createdDateTime': _iso(at), 'lastModifiedDateTime': _iso(at),
                            'from': {'user': {'id': 'u-erin', 'displayName': 'Erin Blake'}}, 'body': {'content': f'<p>{text}</p>'}})
    def request(self, method, url, **kw):
        self.calls.append(url); p = kw.get('params') or {}
        if 'getAllMessages/delta' in url or 'deltatoken=' in url:
            if 'deltatoken=' in url: got = self.export[int(url.rsplit('=', 1)[1]):]
            else: got = [m for m in self.export if m['lastModifiedDateTime'] > p['$filter'].split(' gt ')[1]]
            return _R(200, {'value': got[::-1], '@odata.deltaLink': f'{channels.GRAPH}/delta?$deltatoken={len(self.export)}'})
        if url.endswith('/chats'): return _R(200, {'value': self.chats})
        return _R(200, {})


class LateTeamsMessageTests(unittest.TestCase):
    """A Teams message that reaches Microsoft's export after its poll, stamped older than the next poll's window, was never asked for
    again: the watermark had moved past it. Delayed became lost, and nothing said so (the owner, 2026-11-13)."""
    def setUp(self):
        from taskuary.store import DEFAULT_ROLES, SQLiteStore
        self.store = s = SQLiteStore(':memory:')
        self.cid = s.get_connector_by_type('teams')['ConnectorId']
        s.save_connector({'ConnectorId': self.cid, 'Active': 1, 'Secret': 'app-secret', 'Roles': DEFAULT_ROLES['teams'],
                          'ConfigJson': json.dumps({'tenant_id': 'tid-1', 'client_id': 'cid-1'})}, 'test')
        s.save_source({'Channel': 'teams', 'Address': _Graph.UPN, 'ConnectorId': self.cid, 'Active': 1}, 'test')
        self.g = _Graph()

    def poll(self):
        with mock.patch.object(net, 'session', lambda: self.g), mock.patch.object(channels, 'graph_token', return_value='tok'):
            channels._poll_one(self.store, self.store.get_connector(self.cid), True, 0, None, False)

    def rows(self, ext): return self.store._one('SELECT COUNT(*) AS n FROM message WHERE ExternalId=?', (ext,))['n']

    def test_a_message_that_lands_late_with_an_old_stamp_is_still_read_once(self):
        now = datetime.now()
        self.g.land('m1', '19:crew', now - timedelta(minutes=30))
        self.poll()                                              # the first read: the window, and Graph's delta link kept
        self.assertEqual(self.rows('teams:19:crew:m1'), 1)
        # an hour old when it finally reaches the export - well behind the next window (the last poll, less five minutes)
        self.g.land('late', '19:crew', now - timedelta(hours=1), text='the contract needs your signature today')
        self.poll()
        self.assertEqual(self.rows('teams:19:crew:late'), 1, 'a message that landed late is read, whatever its stamp')
        self.poll()                                              # and again: still one row
        self.assertEqual(self.rows('teams:19:crew:late'), 1)

    def test_an_expired_delta_link_reads_the_window_again(self):
        self.g.land('m1', '19:crew', datetime.now() - timedelta(minutes=30))
        self.poll()
        real = self.g.request
        self.g.request = lambda method, url, **kw: _R(410) if 'deltatoken=' in url else real(method, url, **kw)
        self.g.land('m2', '19:crew', datetime.now() - timedelta(minutes=1))
        self.poll()
        self.assertEqual(self.rows('teams:19:crew:m2'), 1)
        self.assertFalse(self.store.get_connector(self.cid).get('LastError'))

    def test_chats_ahead_of_what_came_in_are_said_on_the_card_and_the_bell_until_they_arrive(self):
        from taskuary import problems
        now = datetime.now()
        self.g.land('m1', '19:crew', now - timedelta(minutes=50))
        self.poll()
        # Microsoft's chat list already shows a newer message in two chats; the export has handed neither over
        preview = lambda chat, mid, at: {'id': chat, 'lastMessagePreview': {'id': mid, 'createdDateTime': _iso(at), 'messageType': 'message',
                                                                            'from': {'user': {'id': 'u-erin'}}}}
        self.g.chats = [preview('19:crew', 'm2', now - timedelta(minutes=40)), preview('19:ops', 'm3', now - timedelta(minutes=35)),
                        preview('19:new', 'm4', now - timedelta(minutes=2))]          # inside the grace: not behind yet
        self.poll()
        err = self.store.get_connector(self.cid)['LastError']
        self.assertTrue(err.startswith('Teams messages are behind: 2 chats newer than what came in'), err)
        self.assertEqual(channels.card_error(self.store.get_connector(self.cid)), err)
        item = next(x for x in problems.collect(self.store, True) if x['key'] == f'connector:{self.cid}')
        self.assertIn('messages are behind', item['title'])
        # ...they arrive: the line goes
        self.g.land('m2', '19:crew', now - timedelta(minutes=40)); self.g.land('m3', '19:ops', now - timedelta(minutes=35))
        self.poll()
        self.assertFalse(self.store.get_connector(self.cid).get('LastError'))
        self.assertEqual(sum(u.endswith('/chats') for u in self.g.calls), 3, 'one chat list a poll, never a history read')

    def test_a_late_chat_message_is_read_from_the_chat_list_when_the_export_never_hands_it_over(self):
        """The live card, 2026-11-13 (invented people): a colleague asked in a group chat at 10:33 and the export handed over nothing all
        morning - the card said "behind", and the ask never became work. The chat list's preview of the last message is that message."""
        now = datetime.now()
        self.g.land('m1', '19:crew', now - timedelta(minutes=50))
        self.poll()
        self.g.chats = [{'id': '19:sec', 'topic': 'Security app help', 'lastMessagePreview': {'id': 'm9', 'createdDateTime': _iso(now - timedelta(minutes=40)),
                         'messageType': 'message', 'from': {'user': {'id': 'u-gail', 'displayName': 'Gail Moreno'}},
                         'body': {'contentType': 'html', 'content': '<p>Paula starts Monday - can you set up her login in the security app?</p>'}}}]
        self.poll()
        row = self.store._one("SELECT BodyText, FromName FROM message WHERE ExternalId='teams:19:sec:m9'")
        self.assertTrue(row and 'set up her login' in row['BodyText'], row)
        self.assertFalse(self.store.get_connector(self.cid).get('LastError'), 'it came in: nothing is behind')
        self.g.land('m9', '19:sec', now - timedelta(minutes=40)); self.poll()             # the export's copy, at last: the same message
        self.assertEqual(self.rows('teams:19:sec:m9'), 1)


class SignedInChatsTests(unittest.TestCase):
    """The sign-in road reads chat by chat. A chat whose last message showed up after its poll - older than the next window - is
    still read: each chat is asked since its own newest message already in, not only since the poll."""
    def test_a_chat_whose_late_message_is_older_than_the_window_is_still_read(self):
        now = datetime.now()
        since, mark, late = now - timedelta(minutes=10), now - timedelta(hours=2), now - timedelta(hours=1)
        asked = []
        def answer(method, url, **kw):
            if url.endswith('/me/chats'):
                return _R(200, {'value': [{'id': '19:crew', 'lastMessagePreview': {'createdDateTime': _iso(late)}}]})
            asked.append(kw['params']['$filter'])
            lo = kw['params']['$filter'].split(' gt ')[1]
            m = {'id': 'late', 'lastModifiedDateTime': _iso(late), 'createdDateTime': _iso(late), 'messageType': 'message'}
            return _R(200, {'value': [m] if m['lastModifiedDateTime'] > lo else []})
        with mock.patch.object(net, 'session', lambda: type('S', (), {'request': staticmethod(answer)})()):
            got = channels._teams_user_delta('tok', _iso(since), state={'seen': {'19:crew': _iso(mark)}})
        self.assertEqual([m['id'] for m in got], ['late'])
        self.assertEqual(asked, [f'lastModifiedDateTime gt {_iso(mark)}'])


if __name__ == '__main__':
    unittest.main()
