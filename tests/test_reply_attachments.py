"""A reply that says "attached" carries the files.

TQ-0526's draft read "Attached are the PTO accrual files for the 8/31 payroll" and the envelope
carried nothing at all - because nothing in Taskuary could attach a file to an outgoing mail. The
send path took to, subject, body, cc and stopped there, so approving that card would have sent an
external recipient a promise of two workbooks and no workbooks (the owner, 2026-09-14).

Pinned here: a file joins the reply and is kept where the send can still find it; Graph composes a
DRAFT when there are files, because its one-shot reply takes a body and nothing else; a file too big
for the inline road goes up in chunks; a chat refuses rather than dropping what the words promise.
"""
import json
import unittest
from unittest import mock

from taskuary import outbound, verdicts
from taskuary.store import MemoryStore


def pending_reply(store, deliver=None):
    tid = store.create_task({'Title': 'Send PTO file', 'Kind': 'task', 'Status': 'open'}, 'owner')
    return store.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'DraftText': 'Attached are the files.',
                             'Status': 'pending',
                             'Deliver': json.dumps(deliver or {'kind': 'reply', 'to': ['gitty@example.test']})})


class AttachingTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.rid = pending_reply(self.store)

    def test_a_file_joins_the_envelope_and_is_kept_where_the_send_can_find_it(self):
        out = verdicts.attach(self.store, self.rid, 'PTO_Raw_Files.zip', b'PK\x03\x04payload')
        f = out['attachments'][0]
        self.assertEqual((f['name'], f['size']), ('PTO_Raw_Files.zip', 11))
        env = json.loads(self.store.get_review(self.rid)['Deliver'])
        self.assertEqual(env['attachments'][0]['name'], 'PTO_Raw_Files.zip')
        self.assertEqual(env['to'], ['gitty@example.test'])          # the rest of the envelope is untouched
        from pathlib import Path
        self.assertEqual(Path(f['path']).read_bytes(), b'PK\x03\x04payload')

    def test_it_is_a_COPY_because_the_folder_it_came_from_is_the_owners_to_tidy(self):
        verdicts.attach(self.store, self.rid, 'book.xlsx', b'xl')
        path = json.loads(self.store.get_review(self.rid)['Deliver'])['attachments'][0]['path']
        self.assertNotIn('Downloads', path)
        self.assertIn('outbox', path)

    def test_attaching_the_same_name_twice_replaces_it_rather_than_sending_it_twice(self):
        verdicts.attach(self.store, self.rid, 'book.xlsx', b'one')
        out = verdicts.attach(self.store, self.rid, 'book.xlsx', b'two-bytes')
        self.assertEqual(len(out['attachments']), 1)
        self.assertEqual(out['attachments'][0]['size'], 9)

    def test_taking_one_off_removes_the_copy_too(self):
        path = verdicts.attach(self.store, self.rid, 'book.xlsx', b'xl')['attachments'][0]['path']
        from pathlib import Path
        self.assertTrue(Path(path).exists())
        self.assertEqual(verdicts.detach(self.store, self.rid, 'book.xlsx')['attachments'], [])
        self.assertFalse(Path(path).exists())

    def test_a_decided_reply_takes_no_more_files(self):
        self.store.decide_review(self.rid, 'approved', 'sent text', 'owner')
        with self.assertRaises(ValueError): verdicts.attach(self.store, self.rid, 'late.xlsx', b'x')

    def test_an_empty_or_enormous_file_is_refused_before_it_is_kept(self):
        with self.assertRaises(ValueError): verdicts.attach(self.store, self.rid, 'nothing.txt', b'')
        with self.assertRaises(ValueError):
            verdicts.attach(self.store, self.rid, 'huge.zip', b'x' * (outbound.ATTACH_MAX + 1))


class ReadingThemBackTests(unittest.TestCase):
    def test_a_file_that_moved_stops_the_send_instead_of_half_making_it(self):
        with self.assertRaises(RuntimeError) as e:
            outbound.read_attachments([{'name': 'gone.zip', 'path': 'C:/nowhere/gone.zip'}])
        self.assertIn('no longer where it was put', str(e.exception))

    def test_the_total_is_what_a_mailbox_refuses_over(self):
        store, rid = MemoryStore(), None
        big = b'x' * (outbound.ATTACH_MAX // 2 + 10)
        import tempfile, pathlib
        d = pathlib.Path(tempfile.mkdtemp())
        one, two = d / 'a.bin', d / 'b.bin'
        one.write_bytes(big); two.write_bytes(big)
        with self.assertRaises(RuntimeError) as e:
            outbound.read_attachments([{'name': 'a.bin', 'path': str(one)}, {'name': 'b.bin', 'path': str(two)}])
        self.assertIn('send a link', str(e.exception))


class SendingThemTests(unittest.TestCase):
    """Graph's one-shot /reply takes a comment and nothing else, so a mail with files is composed."""

    def _graph(self, calls, sizes=(10,)):
        def post(url, **kw):
            calls.append(('POST', url, kw))
            r = mock.Mock(status_code=200)
            r.json.return_value = {'id': 'draft-1', 'body': {'content': '<div>quoted original</div>'},
                                   'uploadUrl': 'https://upload.test/session'}
            return r
        def patch(url, **kw):
            calls.append(('PATCH', url, kw)); return mock.Mock(status_code=200)
        def put(url, **kw):
            calls.append(('PUT', url, kw)); return mock.Mock(status_code=201)
        return post, patch, put

    def _send(self, files, calls):
        post, patch, put = self._graph(calls)
        with mock.patch.object(outbound.requests, 'post', side_effect=post), \
             mock.patch.object(outbound.requests, 'patch', side_effect=patch), \
             mock.patch.object(outbound.requests, 'put', side_effect=put):
            return outbound._send_with_files({'Authorization': 'Bearer t'}, 'me@co.test', ['gitty@example.test'],
                                             [], 'Re: PTO', 'Attached are the files.', 'graph-99', files)

    def test_a_reply_with_files_is_composed_as_a_draft_and_keeps_its_thread(self):
        calls = []
        out = self._send([{'name': 'small.xlsx', 'size': 10, 'bytes': b'0123456789', 'type': 'application/x-xls'}], calls)
        urls = [u for _m, u, _k in calls]
        self.assertTrue(any(u.endswith('/messages/graph-99/createReply') for u in urls), urls)
        self.assertTrue(any(u.endswith('/messages/draft-1/attachments') for u in urls), urls)
        self.assertTrue(any(u.endswith('/messages/draft-1/send') for u in urls), urls)
        self.assertEqual(out['attached'], ['small.xlsx'])
        # ...and our words go ABOVE the quoted original the draft already holds
        body = next(json.loads(k['data'])['body']['content'] for m, _u, k in calls if m == 'PATCH')
        self.assertTrue(body.startswith('Attached are the files.'))
        self.assertIn('quoted original', body)

    def test_a_file_too_big_for_one_request_goes_up_in_chunks(self):
        calls = []
        big = b'y' * (outbound.GRAPH_INLINE + 5)
        self._send([{'name': 'PTO_Raw.zip', 'size': len(big), 'bytes': big, 'type': 'application/zip'}], calls)
        self.assertTrue(any(u.endswith('/attachments/createUploadSession') for _m, u, _k in calls))
        puts = [k for m, _u, k in calls if m == 'PUT']
        self.assertTrue(puts, 'the bytes have to actually go somewhere')
        self.assertIn('Content-Range', puts[0]['headers'])
        # the upload url is pre-authorised - our token on it is what makes Graph refuse the chunk
        self.assertNotIn('Authorization', puts[0]['headers'])

    def test_a_chat_says_it_cannot_carry_a_file_rather_than_dropping_it(self):
        store = MemoryStore()
        msg = {'Channel': 'teams', 'ConversationId': 'teams:19:abc', 'ExternalId': 'teams:1'}
        with self.assertRaises(RuntimeError) as e:
            outbound.reply_to_message(store, msg, 'Attached are the files.',
                                      attachments=[{'name': 'a.zip', 'path': 'x'}])
        self.assertIn('cannot carry a file', str(e.exception))


class TheEnvelopeReachesTheSendTests(unittest.TestCase):
    def test_approving_hands_the_cards_files_to_the_send(self):
        """The list the owner saw is the list that goes - decide() reads it off the envelope."""
        store = MemoryStore()
        mid = store.add_message({'Channel': 'email', 'FromEmail': 'gitty@example.test', 'FromName': 'Gitty',
                                 'Subject': 'PTO', 'ExternalId': 'graph:99', 'SourceName': 'me@co.test'})
        tid = store.create_task({'Title': 'Send PTO file', 'Kind': 'task', 'Status': 'open'}, 'owner')
        rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending',
                                'DraftText': 'Attached are the files.',
                                'Deliver': json.dumps({'kind': 'reply', 'to': ['gitty@example.test'],
                                                       'attachments': [{'name': 'book.xlsx', 'path': 'C:/tmp/book.xlsx',
                                                                        'size': 4}]})})
        with mock.patch.object(outbound, 'reply_to_message',
                               return_value={'channel': 'email', 'to': ['gitty@example.test'],
                                             'attached': ['book.xlsx']}) as sent,              mock.patch.object(outbound, 'send_block', return_value=''):
            out = verdicts.decide(store, store.get_review(rid), 'approve', 'Attached are the files.', None, 'owner')
        self.assertTrue(out['ok'])
        self.assertEqual(sent.call_args.kwargs['attachments'], [{'name': 'book.xlsx', 'path': 'C:/tmp/book.xlsx', 'size': 4}])
        # ...and the task's record says what actually went with the words
        said = [c['Body'] for c in store.list_comments(tid)]
        self.assertTrue(any('book.xlsx' in b for b in said), said)


if __name__ == '__main__':
    unittest.main()
