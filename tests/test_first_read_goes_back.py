"""A connection read for the first time goes back the catch-up window, whatever started the read.

The owner, 2026-11-10: "when you hit sync now after a new connection is connected ... it says connected but it's not going back
whatever the period is to sync it." Only the startup catch-up passed a window; Sync now - and the read a new card's sign-in
starts - passed none, so a source with no watermark yet fell to a fixed day (_since) and an IMAP mailbox with no UID cursor to
SINCE yesterday (_uids). A new mailbox holding ten days of mail brought in one of them, and the card said "Connected".

The shape here: a mailbox with one mail a day for ten days, connected, then Sync now pressed - through the route behind the
button, for a Graph mailbox and an IMAP one. Everything inside the window (3 days, the setting's default) arrives and nothing
older; a second press is an ordinary read from the watermark and brings nothing again.
"""
import json, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import channels, imapmail, server
from taskuary.store import MemoryStore
from tests.test_imap_catchup import FakeBox, mime
from tests.test_mail_catchup import FakeGraph, graph_mail

AGES = [12 + 24 * d for d in range(10)]             # hours: one mail at midday of each of the last ten days


class FirstReadTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.set_setting('startup_sync_days', '3', 't')
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'run_due_reports'),
                  mock.patch.object(server, '_llm', return_value=None)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: server._close_drain_workers(10))
        self.client = TestClient(server.app)

    def press(self):
        self.assertEqual(self.client.post('/api/ingest/poll').json(), {'report': 'running'})

    def subjects(self): return sorted(r['Subject'] for r in self.s._rows("SELECT Subject FROM message WHERE Channel='email' AND Direction IS NOT 'out'"))

    def test_a_new_outlook_mailbox_brings_in_the_whole_window_on_sync_now(self):
        o = self.s.get_connector_by_type('outlook')
        self.s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'Secret': 'S', 'Roles': 'feed',
                               'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'})}, 't')
        self.s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': o['ConnectorId'], 'Active': 1}, 't')
        now = datetime.now(timezone.utc)
        fake = FakeGraph({'inbox': [graph_mail(h, now - timedelta(hours=h)) for h in AGES]})
        with mock.patch.object(channels, 'graph_token', return_value='T'), mock.patch.object(channels, '_mail_msgs', fake), \
             mock.patch.object(channels.requests, 'get', fake.history_get), \
             mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), mock.patch.object(channels, '_addrs', return_value=[]):
            self.press()
            self.assertEqual(self.subjects(), sorted(f'mail {h}' for h in AGES if h < 72))
            self.press()                                                  # an ordinary read now: from the watermark
        self.assertEqual(self.subjects(), sorted(f'mail {h}' for h in AGES if h < 72))

    def test_the_sync_line_hears_how_far_back_and_how_many_over_the_life_of_a_first_sync_and_an_ordinary_one(self):
        """The status the page already polls carries the numbers: `back` from the start of a first read, `landed` as messages land,
        then `brought` once it is over - and an ordinary sync says only a count, and only when it has one."""
        cid = self.s.get_connector_by_type('outlook')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'S', 'Roles': 'feed',
                               'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'})}, 't')
        self.s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Active': 1}, 't')
        now = datetime.now(timezone.utc)
        inbox = [graph_mail(h, now - timedelta(hours=h)) for h in AGES]
        fake, seen, real = FakeGraph({'inbox': inbox}), [], server._visible_status
        def watch(owners):
            st = real(owners); seen.append(st); return st
        with mock.patch.object(channels, 'graph_token', return_value='T'), mock.patch.object(channels, '_mail_msgs', fake), \
             mock.patch.object(channels.requests, 'get', fake.history_get), mock.patch.object(server, '_visible_status', watch), \
             mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), mock.patch.object(channels, '_addrs', return_value=[]):
            self.press()
            running = [s for s in seen if s['state'] == 'running'][1:]                  # after the begin, which knows nothing yet
            self.assertEqual(running[0].get('back'), 72)                                 # starting: how far back, nothing in yet
            self.assertNotIn('landed', running[0])
            self.assertIn(1, [s.get('landed') for s in running])                         # ...N so far, as the first one lands
            self.assertEqual(running[-1].get('landed'), 3)                                # ...and the whole count
            self.assertTrue(all(s.get('back') == 72 for s in running[1:]))
            done = self.client.get('/api/ingest/status').json()
            self.assertEqual(done['status'], {'state': 'idle'})
            self.assertEqual({k: done['brought'][k] for k in ('n', 'hours')}, {'n': 3, 'hours': 72})
            self.assertLess(done['now'] - done['brought']['at'], 30)
            first = json.loads(self.s.get_connector(cid)['ConfigJson'])['first_read']   # ...and the card keeps what its first read did
            self.assertEqual((first['hours'], first['n']), (72, 3))

            seen.clear()                                                                  # an ordinary sync that finds nothing new
            self.press()
            self.assertFalse([s for s in seen if s['state'] == 'running' and (s.get('back') or s.get('landed'))])
            self.assertEqual(self.client.get('/api/ingest/status').json()['brought']['n'], 3)     # the last one's, not a "0"
            self.assertEqual(json.loads(self.s.get_connector(cid)['ConfigJson'])['first_read'], first)

            seen.clear(); inbox.append(graph_mail(0, datetime.now(timezone.utc)))      # ...and one that brings in one
            self.press()
            self.assertEqual(max(s.get('landed', 0) for s in seen if s['state'] == 'running'), 1)
            self.assertFalse([s for s in seen if s.get('back')])
            self.assertEqual({k: v for k, v in self.client.get('/api/ingest/status').json()['brought'].items() if k != 'at'}, {'n': 1, 'hours': 0})

    def test_a_new_imap_mailbox_brings_in_the_whole_window_on_sync_now(self):
        cid = self.s.get_connector_by_type('gmail')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Secret': 'app-password', 'Active': 1, 'Roles': 'feed',
                               'ConfigJson': json.dumps({'address': 'alex@northwind.example'})}, 'o')
        now = datetime.now().astimezone()
        box = FakeBox({u: (mime(u, now - timedelta(hours=h), frm='Erin Blake <erin@vendor.example>'), now - timedelta(hours=h))
                       for u, h in enumerate(reversed(AGES), 1)})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=box):
            self.press()
            got = self.subjects()
            # IMAP's SINCE is a whole day, so the mail of the window's first day may come too - and nothing before it
            day = (now - timedelta(days=3)).date()
            want = {f'mail {u}' for u, h in enumerate(reversed(AGES), 1) if (now - timedelta(hours=h)).date() >= day}
            self.assertEqual(set(got), want)
            self.assertTrue({f'mail {u}' for u, h in enumerate(reversed(AGES), 1) if h < 72} <= set(got))
            self.press()
        self.assertEqual(self.subjects(), got)


if __name__ == '__main__': unittest.main()
