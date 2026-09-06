"""Outlook catch-up drains the whole backlog before the watermark moves (PW-006).

`_mail_msgs()` used to read newest-first and stop at 500, and `_poll_one()` then stamped the
source's watermark 'now': in a folder with more than 500 new mails the OLDEST were never asked
for again. Now a folder is read oldest-first in batches until it is exhausted; progress is kept
per folder between batches, so a fetch that dies half-way resumes where it stopped instead of
re-downloading, and the watermark advances only once every folder has been read to the end.
"""
import json, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from taskuary import channels
from taskuary.store import MemoryStore

T0 = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def _iso(dt): return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _when(s: str) -> datetime:
    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(timezone.utc)


def graph_mail(i: int, when: datetime, frm='v@vendor.example', folder='inbox') -> dict:
    return {'id': f'{folder}-{i}', 'subject': f'mail {i}', 'receivedDateTime': _iso(when), 'isRead': True,
            'hasAttachments': False, 'from': {'emailAddress': {'name': 'V', 'address': frm}},
            'body': {'content': f'body {i}', 'contentType': 'text'}, 'conversationId': f'conv-{i}',
            'webLink': f'https://outlook/{i}', 'toRecipients': [], 'ccRecipients': []}


class FakeGraph:
    """Enough of /mailFolders/{folder}/messages to stand in for _mail_msgs: honours the since
    filter (exclusive, or inclusive when asked), returns oldest-first, at most `cap` a call."""
    def __init__(self, folders: dict, fail_on_call: int = None):
        self.folders, self.calls, self.fail_on_call = folders, [], fail_on_call

    def __call__(self, tok, upn, since, folder='inbox', cap=500, inclusive=False, skip=0):
        self.calls.append((folder, since, inclusive))
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError('Graph timed out')
        lo = _when(since)
        rows = sorted(self.folders.get(folder, []), key=lambda m: m['receivedDateTime'])
        keep = [m for m in rows if (_when(m['receivedDateTime']) >= lo if inclusive else _when(m['receivedDateTime']) > lo)]
        return keep[skip:skip + cap]


def outlook_store(folders=('inbox',)):
    s = MemoryStore()
    o = s.get_connector_by_type('outlook')
    s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'Secret': 'S', 'Roles': 'feed',
                      'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'})}, 't')
    sid = s.save_source({'Channel': 'email', 'Address': 'me@x.com', 'ConnectorId': o['ConnectorId'], 'Active': 1,
                         'ConfigJson': json.dumps({'folders': list(folders)})}, 't')
    # an established watermark: the last poll was a while ago and everything since is backlog
    s._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', ((T0 - timedelta(hours=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S'), sid))
    return s, sid


def poll(s, fake):
    with mock.patch.object(channels, 'graph_token', return_value='T'), mock.patch.object(channels, '_mail_msgs', fake), \
         mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), mock.patch.object(channels, '_addrs', return_value=[]):
        return channels.poll_channels(s)


def inbox_rows(s): return s._rows("SELECT * FROM message WHERE Channel='email' AND FromEmail='v@vendor.example' ORDER BY MessageId")


class MailMsgsTests(unittest.TestCase):
    def test_graph_is_asked_oldest_first_and_at_most_cap_come_back(self):
        pages = [{'value': [graph_mail(i, T0 + timedelta(minutes=i)) for i in range(50)], '@odata.nextLink': 'https://graph/next1'},
                 {'value': [graph_mail(i, T0 + timedelta(minutes=i)) for i in range(50, 100)], '@odata.nextLink': 'https://graph/next2'},
                 {'value': [graph_mail(i, T0 + timedelta(minutes=i)) for i in range(100, 120)]}]
        asked = []
        def get(url, headers=None, timeout=None, params=None):
            asked.append((url, params))
            r = mock.Mock(); r.json.return_value = pages[len(asked) - 1]; r.raise_for_status = lambda: None
            return r
        with mock.patch.object(channels.requests, 'get', get):
            got = channels._mail_msgs('tok', 'me@x.com', _iso(T0), folder='inbox', cap=100)
        self.assertEqual(asked[0][1]['$orderby'], 'receivedDateTime asc')
        self.assertIn(f'receivedDateTime gt {_iso(T0)}', asked[0][1]['$filter'])
        self.assertEqual(len(got), 100)                                # the cap is a hard batch size...
        self.assertEqual([m['id'] for m in got[:3]], ['inbox-0', 'inbox-1', 'inbox-2'])   # ...of the OLDEST
        self.assertEqual(len(asked), 2, 'a full batch stops paging')

    def test_inclusive_asks_for_the_boundary_timestamp_too(self):
        asked = []
        def get(url, headers=None, timeout=None, params=None):
            asked.append(params); r = mock.Mock(); r.json.return_value = {'value': []}; r.raise_for_status = lambda: None; return r
        with mock.patch.object(channels.requests, 'get', get):
            channels._mail_msgs('tok', 'me@x.com', _iso(T0), inclusive=True)
        self.assertIn(f'receivedDateTime ge {_iso(T0)}', asked[0]['$filter'])


class CatchUpTests(unittest.TestCase):
    def test_a_backlog_beyond_one_batch_is_read_to_the_end_before_the_watermark_moves(self):
        fake = FakeGraph({'inbox': [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(1050)]})
        s, sid = outlook_store()
        n = poll(s, fake)
        self.assertEqual(n, 1050)
        self.assertEqual(len(inbox_rows(s)), 1050)
        self.assertEqual([c[0] for c in fake.calls].count('inbox'), 3)           # 500 + 500 + 50
        src = s.get_source(sid)
        self.assertGreater(src['LastPolledAt'], (T0 + timedelta(seconds=1050)).astimezone().strftime('%Y-%m-%d %H:%M:%S'))
        self.assertNotIn('mail_cursor', json.loads(src['ConfigJson']))           # nothing left half-read
        self.assertEqual(json.loads(src['ConfigJson'])['folders'], ['inbox'])    # the owner's folder choice survives

    def test_a_fetch_that_dies_half_way_resumes_there_instead_of_starting_over(self):
        mails = [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(1050)]
        s, sid = outlook_store()
        before = s.get_source(sid)['LastPolledAt']
        broken = FakeGraph({'inbox': mails}, fail_on_call=3)                      # sentitems, inbox#1 ok; inbox#2 dies
        poll(s, broken)
        self.assertEqual(len(inbox_rows(s)), 500)
        src = s.get_source(sid)
        self.assertEqual(src['LastPolledAt'], before, 'the watermark must not step over unfetched mail')
        self.assertEqual(json.loads(src['ConfigJson'])['mail_cursor']['inbox'], mails[499]['receivedDateTime'])
        self.assertIn('Graph timed out', s.get_connector_by_type('outlook')['LastError'] or '')
        healthy = FakeGraph({'inbox': mails})
        poll(s, healthy)
        self.assertEqual(len(inbox_rows(s)), 1050)
        inbox_calls = [c for c in healthy.calls if c[0] == 'inbox']
        self.assertEqual(inbox_calls[0][1], mails[499]['receivedDateTime'], 'resume from the cursor, not the watermark')
        self.assertEqual(len(inbox_calls), 2)                                    # 500 (from the boundary) + the last 51
        src = s.get_source(sid)
        self.assertNotIn('mail_cursor', json.loads(src['ConfigJson']))
        self.assertGreater(src['LastPolledAt'], before)

    def test_mails_sharing_the_boundary_timestamp_are_not_skipped(self):
        # 600 mails, all received in the same second: a strict "after the last one" continuation loses the rest
        mails = [graph_mail(i, T0) for i in range(600)]
        s, _sid = outlook_store()
        poll(s, FakeGraph({'inbox': mails}))
        self.assertEqual(len(inbox_rows(s)), 600)
        self.assertEqual(len({r['ExternalId'] for r in inbox_rows(s)}), 600)

    def test_a_batch_of_only_already_seen_mail_ends_the_folder_instead_of_looping(self):
        mails = [graph_mail(i, T0) for i in range(500)]                          # exactly one full batch, one timestamp
        s, sid = outlook_store()
        fake = FakeGraph({'inbox': mails})
        poll(s, fake)
        self.assertEqual(len(inbox_rows(s)), 500)
        self.assertLessEqual([c[0] for c in fake.calls].count('inbox'), 3)   # one to read it, at most two to learn it is over
        self.assertNotIn('mail_cursor', json.loads(s.get_source(sid)['ConfigJson']))

    def test_sent_items_are_drained_the_same_way(self):
        sent = [graph_mail(i, T0 + timedelta(seconds=i), frm='me@x.com', folder='sentitems') for i in range(520)]
        s, _sid = outlook_store()
        fake = FakeGraph({'sentitems': sent})
        poll(s, fake)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 520)
        self.assertEqual([c[0] for c in fake.calls].count('sentitems'), 2)

    def test_every_chosen_folder_is_drained_and_a_dead_folder_holds_only_itself(self):
        s, sid = outlook_store(folders=('inbox', 'AAMk-vend'))
        fake = FakeGraph({'inbox': [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(10)],
                          'AAMk-vend': [graph_mail(i, T0 + timedelta(seconds=i), folder='AAMk-vend') for i in range(10)]}, fail_on_call=2)
        poll(s, fake)                                                            # sentitems ok, inbox dies, the vendor folder still reads
        self.assertEqual(len(inbox_rows(s)), 10)
        cfg = json.loads(s.get_source(sid)['ConfigJson'])
        self.assertNotIn('inbox', cfg.get('mail_cursor', {}))                    # nothing of it was read: no half-way point to keep
        self.assertEqual(s.get_source(sid)['LastPolledAt'], (T0 - timedelta(hours=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S'))


if __name__ == '__main__':
    unittest.main()
