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
        self.continuations, self.sequence = {}, 0

    def __call__(self, tok, upn, since, folder='inbox', cap=500, inclusive=False,
                 through=None, continuation=None, with_continuation=False):
        self.calls.append((folder, since, inclusive, continuation, through))
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError('Graph timed out')
        if continuation:
            keep = self.continuations.pop(continuation)
        else:
            lo = _when(since)
            rows = sorted(self.folders.get(folder, []), key=lambda m: m['receivedDateTime'])
            keep = [m for m in rows if (_when(m['receivedDateTime']) >= lo if inclusive else _when(m['receivedDateTime']) > lo)]
            if through: keep = [m for m in keep if _when(m['receivedDateTime']) <= _when(through)]
        batch, remainder = keep[:cap], keep[cap:]
        next_link = None
        if remainder:
            self.sequence += 1
            next_link = f'fake:{folder}:{self.sequence}'
            self.continuations[next_link] = remainder
        return (batch, next_link) if with_continuation else batch


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


def poll(s, fake, backfill_days=0):
    with mock.patch.object(channels, 'graph_token', return_value='T'), mock.patch.object(channels, '_mail_msgs', fake), \
         mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), mock.patch.object(channels, '_addrs', return_value=[]):
        return channels.poll_channels(s, backfill_days=backfill_days)


def poll_transport(s, get, backfill_days=0):
    with mock.patch.object(channels, 'graph_token', return_value='T'), \
         mock.patch.object(channels.requests, 'get', get), \
         mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), \
         mock.patch.object(channels, '_addrs', return_value=[]):
        return channels.poll_channels(s, backfill_days=backfill_days)


def inbox_rows(s): return s._rows("SELECT * FROM message WHERE Channel='email' AND FromEmail='v@vendor.example' ORDER BY MessageId")


class MailMsgsTests(unittest.TestCase):
    def test_repeated_internal_nextlink_fails_after_two_responses_instead_of_looping(self):
        calls = []
        pages = iter([
            {'value': [graph_mail(1, T0)], '@odata.nextLink': 'https://graph/stuck'},
            {'value': [graph_mail(2, T0 + timedelta(seconds=1))],
             '@odata.nextLink': 'https://graph/stuck'},
        ])
        def get(url, headers=None, timeout=None, params=None):
            calls.append(url)
            r = mock.Mock(); r.raise_for_status = lambda: None; r.json.return_value = next(pages); return r
        with mock.patch.object(channels.requests, 'get', get):
            with self.assertRaisesRegex(RuntimeError, 'repeated mail continuation'):
                channels._mail_msgs('tok', 'me@x.com', _iso(T0 - timedelta(hours=1)), cap=100)
        self.assertEqual(len(calls), 2)

    def test_opaque_nextlink_is_followed_verbatim_when_skip_is_not_returned_row_count(self):
        asked = []
        pages = {
            'initial': {'value': [graph_mail(1, T0), graph_mail(2, T0)],
                        '@odata.nextLink': 'https://graph/messages?$skip=173'},
            'https://graph/messages?$skip=173': {'value': [graph_mail(3, T0)]},
        }
        def get(url, headers=None, timeout=None, params=None):
            asked.append((url, params))
            r = mock.Mock(); r.raise_for_status = lambda: None
            r.json.return_value = pages['initial' if params is not None else url]
            return r
        with mock.patch.object(channels.requests, 'get', get):
            got = channels._mail_msgs('tok', 'me@x.com', _iso(T0 - timedelta(hours=1)), cap=3)
        self.assertEqual([m['id'] for m in got], ['inbox-1', 'inbox-2', 'inbox-3'])
        self.assertEqual(asked[1], ('https://graph/messages?$skip=173', None))

    def test_irregular_graph_pages_cross_batch_cap_without_losing_a_provider_page(self):
        asked = []
        pages = iter([
            {'value': [graph_mail(i, T0) for i in range(49)],
             '@odata.nextLink': 'https://graph/page-two'},
            {'value': [graph_mail(i, T0) for i in range(49, 99)],
             '@odata.nextLink': 'https://graph/page-three'},
        ])
        def get(url, headers=None, timeout=None, params=None):
            asked.append(url)
            response = mock.Mock(); response.raise_for_status = lambda: None
            response.json.return_value = next(pages)
            return response
        with mock.patch.object(channels.requests, 'get', get):
            batch, continuation = channels._mail_msgs(
                'tok', 'me@x.com', _iso(T0 - timedelta(hours=1)), cap=50,
                with_continuation=True)
        self.assertEqual(len(batch), 99, 'a complete provider page must never be truncated')
        self.assertEqual(continuation, 'https://graph/page-three')
        self.assertEqual(asked[-1], 'https://graph/page-two')

    def test_alternating_continuations_fail_across_folder_batches(self):
        asked = []
        pages = {
            'initial': {'value': [graph_mail(1, T0)], '@odata.nextLink': 'https://graph/A'},
            'https://graph/A': {'value': [graph_mail(2, T0)], '@odata.nextLink': 'https://graph/B'},
            'https://graph/B': {'value': [graph_mail(3, T0)], '@odata.nextLink': 'https://graph/A'},
        }
        def get(url, headers=None, timeout=None, params=None):
            asked.append(url)
            response = mock.Mock(); response.raise_for_status = lambda: None
            response.json.return_value = pages['initial' if params is not None else url]
            return response
        handled, cursor = [], {}
        with mock.patch.object(channels.requests, 'get', get), mock.patch.object(channels, 'MAIL_BATCH', 1):
            with self.assertRaisesRegex(RuntimeError, 'repeated mail continuation'):
                channels._mail_folder(
                    'tok', {'Address': 'me@x.com'}, 'inbox', _iso(T0 - timedelta(hours=1)),
                    _iso(T0 + timedelta(hours=1)), cursor, lambda row: handled.append(row['id']) or 1,
                    lambda: None)
        self.assertEqual(asked, [
            f'{channels.GRAPH}/users/me@x.com/mailFolders/inbox/messages',
            'https://graph/A', 'https://graph/B'])
        self.assertEqual(handled, ['inbox-1', 'inbox-2', 'inbox-3'])

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

    def test_every_internal_graph_page_keeps_the_frozen_upper_bound_and_failure_is_atomic(self):
        calls = []
        def broken(url, headers=None, timeout=None, params=None):
            calls.append((url, params))
            if len(calls) == 2: raise RuntimeError('page two failed')
            r = mock.Mock(); r.raise_for_status = lambda: None
            r.json.return_value = {'value': [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(50)],
                                   '@odata.nextLink': 'https://graph/next'}
            return r
        through = _iso(T0 + timedelta(hours=1))
        with mock.patch.object(channels.requests, 'get', broken):
            with self.assertRaisesRegex(RuntimeError, 'page two failed'):
                channels._mail_msgs('tok', 'me@x.com', _iso(T0 - timedelta(hours=1)),
                                    cap=100, through=through)
        self.assertIn(f'receivedDateTime le {through}', calls[0][1]['$filter'])
        self.assertIsNone(calls[1][1], 'Graph nextLink must carry the original bounded filter')
        retry_pages = iter([
            {'value': [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(50)],
             '@odata.nextLink': 'https://graph/retry-next'},
            {'value': [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(50, 100)]},
        ])
        def healthy(url, headers=None, timeout=None, params=None):
            r = mock.Mock(); r.raise_for_status = lambda: None; r.json.return_value = next(retry_pages); return r
        with mock.patch.object(channels.requests, 'get', healthy):
            got = channels._mail_msgs('tok', 'me@x.com', _iso(T0 - timedelta(hours=1)),
                                      cap=100, through=through)
        self.assertEqual([m['id'] for m in got], [f'inbox-{i}' for i in range(100)])


class CatchUpTests(unittest.TestCase):
    def test_deletion_before_provider_cursor_replays_boundary_and_recovers_shifted_item(self):
        mails = [graph_mail(i, T0) for i in range(600)]
        s, sid = outlook_store()
        class Transport:
            def __init__(self, rows, fail_cursor=False):
                self.rows, self.fail_cursor, self.failed = rows, fail_cursor, False
            def __call__(self, url, headers=None, timeout=None, params=None):
                folder = 'sentitems' if 'sentitems' in url else 'inbox'
                offset = 0 if params is not None else int(url.rsplit('/', 1)[-1])
                if folder == 'inbox' and offset == 500 and self.fail_cursor and not self.failed:
                    self.failed = True
                    raise RuntimeError('opaque continuation failed')
                rows = [] if folder == 'sentitems' else self.rows
                page = rows[offset:offset + 50]
                next_link = (f'https://opaque/{folder}/{offset + len(page)}'
                             if offset + len(page) < len(rows) else None)
                response = mock.Mock(); response.raise_for_status = lambda: None
                response.json.return_value = {'value': page, **(
                    {'@odata.nextLink': next_link} if next_link else {})}
                return response
        cutoff = _iso(T0 + timedelta(days=1))
        with mock.patch.object(channels, '_mail_cutoff', return_value=cutoff):
            poll_transport(s, Transport(mails, fail_cursor=True))
            self.assertEqual(len(inbox_rows(s)), 500)
            shifted = mails[1:]                    # deletion shifts provider offsets before retry
            poll_transport(s, Transport(shifted))
        ids = {row['ExternalId'] for row in inbox_rows(s)}
        self.assertIn('graph:inbox-500', ids)
        self.assertEqual(len(ids), 600)

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

    def test_sent_failure_retains_progress_and_retry_creates_each_context_row_once(self):
        sent = [graph_mail(i, T0 + timedelta(seconds=i), frm='me@x.com', folder='sentitems')
                for i in range(520)]
        s, sid = outlook_store()
        before = s.get_source(sid)['LastPolledAt']
        poll(s, FakeGraph({'sentitems': sent}, fail_on_call=2))
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 500)
        cfg = json.loads(s.get_source(sid)['ConfigJson'])
        self.assertIn('sentitems', cfg['mail_cursor'])
        self.assertEqual(s.get_source(sid)['LastPolledAt'], before)
        poll(s, FakeGraph({'sentitems': sent}))
        rows = s._rows("SELECT * FROM message WHERE Status='context'")
        self.assertEqual(len(rows), 520)
        self.assertEqual(len({row['ExternalId'] for row in rows}), 520)
        self.assertEqual(inbox_rows(s), [], 'Sent retry was incorrectly triaged as inbound mail')

    def test_one_frozen_cutoff_prevents_arrival_during_a_slow_folder_from_being_skipped(self):
        first = graph_mail(1, T0 + timedelta(seconds=1))
        arrived = graph_mail(2, T0 + timedelta(minutes=1))
        folders = {'inbox': [first], 'AAMk-vend': []}
        s, sid = outlook_store(folders=('inbox', 'AAMk-vend'))
        class Arrival(FakeGraph):
            def __call__(self, *args, **kwargs):
                if kwargs.get('folder') == 'AAMk-vend' and arrived not in self.folders['inbox']:
                    self.folders['inbox'].append(arrived)
                return super().__call__(*args, **kwargs)
        cut1, cut2 = _iso(T0 + timedelta(seconds=30)), _iso(T0 + timedelta(minutes=2))
        with mock.patch.object(channels, '_mail_cutoff', side_effect=[cut1, cut2]):
            first_cycle = Arrival(folders); poll(s, first_cycle)
            self.assertEqual([row['ExternalId'] for row in inbox_rows(s)], ['graph:inbox-1'])
            self.assertEqual(s.get_source(sid)['LastPolledAt'], channels._local(cut1))
            self.assertTrue(all(call[4] == cut1 for call in first_cycle.calls))
            poll(s, FakeGraph(folders))
        self.assertEqual([row['ExternalId'] for row in inbox_rows(s)],
                         ['graph:inbox-1', 'graph:inbox-2'])

    def test_unrelated_owner_config_edit_survives_progress_checkpoint(self):
        mails = [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(510)]
        s, sid = outlook_store()
        class OwnerEdit(FakeGraph):
            def __call__(self, *args, **kwargs):
                rows = super().__call__(*args, **kwargs)
                if kwargs.get('folder') == 'inbox' and not hasattr(self, 'edited'):
                    self.edited = True
                    src = s.get_source(sid); cfg = json.loads(src['ConfigJson'])
                    cfg['owner_custom'] = {'kept': True}
                    s.save_source({'SourceId': sid, 'ConfigJson': json.dumps(cfg)}, 'owner')
                return rows
        poll(s, OwnerEdit({'inbox': mails}))
        self.assertEqual(json.loads(s.get_source(sid)['ConfigJson'])['owner_custom'], {'kept': True})
        self.assertEqual(len(inbox_rows(s)), 510)

    def test_rewind_during_catchup_blocks_progress_and_makes_old_cursor_incompatible(self):
        mails = [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(520)]
        s, sid = outlook_store()
        class Rewind(FakeGraph):
            def __call__(self, *args, **kwargs):
                rows = super().__call__(*args, **kwargs)
                if kwargs.get('folder') == 'inbox' and len([c for c in self.calls if c[0] == 'inbox']) == 2:
                    s.rewind_source(sid)
                return rows
        poll(s, Rewind({'inbox': mails}))
        src = s.get_source(sid)
        self.assertIsNone(src['LastPolledAt'])
        self.assertIn('source changed', s.get_connector_by_type('outlook')['LastError'])
        self.assertEqual(channels._mail_progress(src), ({}, {}),
                         'a post-rewind cycle must not resume the old watermark cursor')

    def test_widened_startup_backfill_discards_a_narrower_incomplete_cursor(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        recent = [graph_mail(i, now - timedelta(minutes=50) + timedelta(seconds=i))
                  for i in range(510)]
        older = graph_mail(9999, now - timedelta(days=2))
        s, sid = outlook_store()
        s._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?',
                ((now - timedelta(hours=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S'), sid))
        cut1, cut2 = _iso(now + timedelta(minutes=1)), _iso(now + timedelta(minutes=2))
        with mock.patch.object(channels, '_mail_cutoff', side_effect=[cut1, cut2]):
            poll(s, FakeGraph({'inbox': recent}, fail_on_call=3))
            narrow = json.loads(s.get_source(sid)['ConfigJson'])['mail_cursor_basis']['since']
            poll(s, FakeGraph({'inbox': [older, *recent]}), backfill_days=3)
        self.assertIn('graph:inbox-9999', {row['ExternalId'] for row in inbox_rows(s)})
        self.assertEqual(len(inbox_rows(s)), 511)
        self.assertNotIn('mail_cursor_basis', json.loads(s.get_source(sid)['ConfigJson']))
        self.assertGreater(_when(narrow), now - timedelta(days=1))

    def test_folder_scope_edit_during_catchup_is_preserved_and_blocks_completion(self):
        mails = [graph_mail(i, T0 + timedelta(seconds=i)) for i in range(510)]
        s, sid = outlook_store(folders=('inbox', 'AAMk-old'))
        before = s.get_source(sid)['LastPolledAt']
        class FolderEdit(FakeGraph):
            def __call__(self, *args, **kwargs):
                rows = super().__call__(*args, **kwargs)
                if kwargs.get('folder') == 'inbox' and not hasattr(self, 'edited'):
                    self.edited = True
                    src = s.get_source(sid); cfg = json.loads(src['ConfigJson'])
                    cfg['folders'] = ['inbox', 'AAMk-new']
                    s.save_source({'SourceId': sid, 'ConfigJson': json.dumps(cfg)}, 'owner')
                return rows
        fake = FolderEdit({'inbox': mails, 'AAMk-old': [graph_mail(8000, T0, folder='AAMk-old')]})
        poll(s, fake)
        src = s.get_source(sid)
        self.assertEqual(json.loads(src['ConfigJson'])['folders'], ['inbox', 'AAMk-new'])
        self.assertEqual(src['LastPolledAt'], before)
        self.assertIn('source changed', s.get_connector_by_type('outlook')['LastError'])
        self.assertNotIn('AAMk-old', [call[0] for call in fake.calls],
                         'a retargeted source kept making calls from its stale folder snapshot')

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
