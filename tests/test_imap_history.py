"""An IMAP install is a first-class install.

Three things assumed Outlook was the only mailbox that could exist, and each one failed silently
on a perfectly connected IMAP card (owner, 2026-09-02, two machines):

- the Sent folder was never read, so "Generate my reply style" answered "connect the Outlook
  card" - advice the owner cannot act on when Outlook is not their mail;
- a card saved without pressing Test had no source row, so it polled nothing while looking
  connected, and the setup checklist called it unconnected;
- and a child process started from the windowed exe opens its own console, which is why one
  machine kept flashing terminal windows and the dev machine never did.
"""
import unittest
from unittest import mock

from taskuary import histgen, imapmail, spawn
from taskuary.store import MemoryStore

CARD = {'ConnectorId': 1, 'Type': 'imap', 'Name': 'Work mail', 'Active': 1, 'Secret': 'pw',
        'ConfigJson': '{"address": "uri@example.com", "imap_host": "imap.example.com"}'}


class FakeImap:
    """Just enough imaplib: LIST, SELECT, UID SEARCH, UID FETCH."""

    def __init__(self, folders, messages=(), select_ok=True):
        self.folders, self.messages, self.select_ok = folders, list(messages), select_ok
        self.selected, self.readonly = None, None
        self.logged_out = False

    def list(self): return 'OK', list(self.folders)
    def select(self, box, readonly=False):
        self.selected, self.readonly = box, readonly
        return ('OK', [b'1']) if self.select_ok else ('NO', [b'nope'])

    def uid(self, cmd, *args):
        if cmd == 'search': return 'OK', [b' '.join(str(i + 1).encode() for i in range(len(self.messages)))]
        n = int(args[0])
        return 'OK', [(b'x', self.messages[n - 1])]

    def logout(self): self.logged_out = True


def raw(subject, body, date='Mon, 01 Sep 2026 09:15:00 +0000', mid='<a@b>'):
    return ('Subject: %s\r\nFrom: uri@example.com\r\nTo: dana@vendor.com\r\n'
            'Date: %s\r\nMessage-ID: %s\r\nContent-Type: text/plain\r\n\r\n%s'
            % (subject, date, mid, body)).encode()


LIST_SPECIAL = [br'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"',
                br'(\HasNoChildren) "/" "INBOX"']
LIST_PLAIN = [br'(\HasNoChildren) "." INBOX',
              br'(\HasNoChildren) "." INBOX.Sent']
LIST_NONE = [br'(\HasNoChildren) "/" "INBOX"']


class FindingTheSentFolder(unittest.TestCase):
    def test_the_server_flag_wins_over_a_name_guess(self):
        self.assertEqual(imapmail.sent_folder(FakeImap(LIST_SPECIAL)), '[Gmail]/Sent Mail')

    def test_a_familiar_name_is_the_fallback(self):
        self.assertEqual(imapmail.sent_folder(FakeImap(LIST_PLAIN)), 'INBOX.Sent')

    def test_no_sent_folder_is_not_an_error(self):
        self.assertEqual(imapmail.sent_folder(FakeImap(LIST_NONE)), '')

    def test_a_server_that_refuses_list_is_not_an_error(self):
        boom = mock.Mock()
        boom.list.side_effect = OSError('connection reset')
        self.assertEqual(imapmail.sent_folder(boom), '')

    def test_a_folder_with_a_space_reaches_select_quoted(self):
        M = FakeImap(LIST_SPECIAL, [raw('hi', 'there')])
        with mock.patch.object(imapmail, '_login', return_value=(M, 'uri@example.com')):
            imapmail.sent_window(dict(CARD), 90)
        self.assertEqual(M.selected, '"[Gmail]/Sent Mail"')
        self.assertTrue(M.readonly)                       # the owner's outbox is never written to
        self.assertTrue(M.logged_out)


class ReadingWhatYouSent(unittest.TestCase):
    def _window(self, folders=LIST_PLAIN, msgs=(), **kw):
        M = FakeImap(folders, msgs, **kw)
        with mock.patch.object(imapmail, '_login', return_value=(M, 'uri@example.com')):
            return imapmail.sent_window(dict(CARD), 90)

    def test_a_sent_mail_comes_back_shaped_for_the_readers(self):
        rows = self._window(msgs=[raw('Re: the ledger', 'Attached, and thanks for the nudge.')])
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r['subject'], 'Re: the ledger')
        self.assertIn('thanks for the nudge', r['body'])
        self.assertEqual(r['from_email'], 'uri@example.com')
        self.assertEqual(r['to'], ['dana@vendor.com'])
        self.assertTrue(r['sent_at'].startswith('2026-09-01'))
        self.assertEqual(r['conversation_id'], '<a@b>')

    def test_no_sent_folder_and_a_refused_select_both_give_nothing(self):
        self.assertEqual(self._window(folders=LIST_NONE, msgs=[raw('x', 'y')]), [])
        self.assertEqual(self._window(msgs=[raw('x', 'y')], select_ok=False), [])

    def test_one_unreadable_message_does_not_lose_the_rest(self):
        M = FakeImap(LIST_PLAIN, [raw('one', 'first'), raw('two', 'second')])
        real = M.uid
        def flaky(cmd, *a):
            if cmd == 'fetch' and a[0] == '1': raise OSError('truncated')
            return real(cmd, *a)
        M.uid = flaky
        with mock.patch.object(imapmail, '_login', return_value=(M, 'uri@example.com')):
            rows = imapmail.sent_window(dict(CARD), 90)
        self.assertEqual([r['subject'] for r in rows], ['two'])

    def test_sent_history_walks_every_mailbox_card_and_survives_one_failing(self):
        s = MemoryStore()
        s.save_connector({'Type': 'imap', 'Name': 'Work', 'Active': 1,
                          'ConfigJson': CARD['ConfigJson'], 'Secret': 'pw'}, 'test')
        s.save_connector({'Type': 'imap', 'Name': 'Broken', 'Active': 1,
                          'ConfigJson': CARD['ConfigJson'], 'Secret': 'pw'}, 'test')
        calls = []
        def window(c, days, cap=300, progress=None):
            calls.append(c['Name'])
            if c['Name'] == 'Broken': raise RuntimeError('login refused')
            return [{'subject': 'from work', 'body': 'b', 'sent_at': '2026-09-01 09:00:00'}]
        with mock.patch.object(imapmail, 'sent_window', window):
            rows = imapmail.sent_history(s, 90)
        self.assertEqual(sorted(calls), ['Broken', 'Work'])
        self.assertEqual([r['subject'] for r in rows], ['from work'])


class TheHistoryGeneratorsUseIt(unittest.TestCase):
    SENT = [{'subject': 'Re: the ledger', 'body': 'Attached - thanks for the nudge, I will confirm Friday.',
             'sent_at': '2026-09-01 09:15:00', 'conversation_id': 'conv-1'}]

    def _store(self):
        s = MemoryStore()
        s.save_connector({'Type': 'imap', 'Name': 'Work', 'Active': 1,
                          'ConfigJson': CARD['ConfigJson'], 'Secret': 'pw'}, 'test')
        return s

    def test_style_is_generated_from_imap_sent_mail(self):
        s = self._store()
        seen = {}
        def llm(system, user, **kw):
            seen['user'] = user
            return '### Tone\n- answer first, two sentences'
        with mock.patch.object(imapmail, 'sent_history', return_value=self.SENT):
            block, src, _ev = histgen.gen_style(s, llm, 90)
        self.assertIn('thanks for the nudge', seen['user'])   # the real words reached the model
        self.assertIn('answer first', block)
        self.assertIn('IMAP', src)

    def test_the_error_no_longer_points_at_a_card_the_owner_does_not_use(self):
        s = MemoryStore()
        with mock.patch.object(imapmail, 'sent_history', return_value=[]):
            with self.assertRaises(RuntimeError) as e:
                histgen.gen_style(s, lambda *a, **k: 'x', 90)
        msg = str(e.exception)
        self.assertIn('IMAP', msg)
        self.assertNotIn('connect the Outlook card', msg)

    def test_answered_comes_from_real_sent_mail_rather_than_a_proxy(self):
        s = self._store()
        # two inbound mails; only the first was written back to
        for i, conv in enumerate(('conv-1', 'conv-2')):
            s.add_message({'ExternalId': f'm{i}', 'Channel': 'email', 'ConversationId': conv,
                           'Subject': f'thread {i}', 'FromEmail': f'p{i}@vendor.com',
                           'BodyText': 'please look', 'Status': 'filed',
                           'SentAt': '2026-09-01 08:00:00'})
        seen = {}
        def llm(system, user, **kw):
            seen['user'] = user
            return '- vendor mail matters'
        with mock.patch.object(imapmail, 'sent_history', return_value=self.SENT):
            _block, src, _ev = histgen.gen_triage(s, llm, 90)
        self.assertIn('answered checked against 1 sent mails', src)
        # the answered thread is marked answered and the unanswered one is not
        rows = [l for l in seen['user'].splitlines() if 'vendor.com' in l]
        self.assertTrue(any('p0@vendor.com' in l and 'answered' in l.lower() for l in rows), rows)


class TheSourceRowHealsItself(unittest.TestCase):
    def _card(self, store):
        cid = store.save_connector({'Type': 'imap', 'Name': 'Work', 'Active': 1,
                                    'ConfigJson': CARD['ConfigJson'], 'Secret': 'pw'}, 'test')
        return store.get_connector(cid)

    def _mail(self, store):
        """Only the mailbox sources: a fresh store already carries the seeded report ones."""
        return [(x['Address'], x['Active']) for x in store.list_sources() if x['Channel'] == 'email']

    def test_a_card_saved_without_pressing_test_still_gets_polled(self):
        s = MemoryStore()
        c = self._card(s)
        self.assertEqual(self._mail(s), [])
        self.assertTrue(imapmail.ensure_source(s, c))
        self.assertEqual(self._mail(s), [('uri@example.com', 1)])
        self.assertFalse(imapmail.ensure_source(s, c))      # idempotent: never a second row

    def test_a_card_with_no_address_yet_is_left_alone(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'imap', 'Name': 'Blank', 'Active': 1, 'ConfigJson': '{}'}, 'test')
        self.assertFalse(imapmail.ensure_source(s, s.get_connector(cid)))
        self.assertEqual(self._mail(s), [])

    def test_the_poller_heals_it_and_the_checklist_then_agrees(self):
        from taskuary import channels, setup
        s = MemoryStore()
        s.save_connector({'Type': 'imap', 'Name': 'Work', 'Active': 1,
                          'ConfigJson': CARD['ConfigJson'], 'Secret': 'pw'}, 'test')
        self.assertEqual(setup._inbound(s), [])             # half-connected: looks done, delivers nothing
        with mock.patch.object(channels, 'wants_read', return_value=False), \
             mock.patch.object(imapmail, 'poll_imap', return_value=0):
            channels.poll_channels(s)
        self.assertEqual(setup._inbound(s), ['Work'])


def reply_raw(uid_body, ref='<orig@them>', date='Mon, 01 Sep 2026 11:00:00 +0000'):
    return ('Subject: RE: the report\r\nFrom: uri@example.com\r\nTo: dana@vendor.com\r\n'
            'Date: %s\r\nMessage-ID: <r%s@us>\r\nReferences: %s\r\nContent-Type: text/plain\r\n\r\n%s'
            % (date, abs(hash(uid_body)) % 999, ref, uid_body)).encode()


class ReplyingFromOutlookNotFromHere(unittest.TestCase):
    """An IMAP mailbox never had its Sent folder POLLED - only read on demand for the style
    document. So the owner answered a mail in their mail client and the row here went on saying
    nothing had happened, which is the one thing the Timeline must never do."""

    def _inbound(self, s):
        return s.add_message({'ExternalId': 'in1', 'ConversationId': '<orig@them>', 'Channel': 'email',
                              'SourceName': 'uri@example.com', 'Subject': 'the report', 'FromName': 'Dana',
                              'FromEmail': 'dana@vendor.com', 'SentAt': '2026-09-01 06:00:00',
                              'BodyText': 'where is it?', 'Status': 'filed'})

    def test_your_reply_lands_on_the_thread_it_answers(self):
        s = MemoryStore()
        mid = self._inbound(s)
        M = FakeImap(LIST_PLAIN, [reply_raw('going out today.')])
        n, uid = imapmail.poll_sent(s, M, 'uri@example.com', 0, 7)
        self.assertEqual((n, uid), (1, 1))
        self.assertEqual(M.selected, 'INBOX.Sent')
        self.assertTrue(M.readonly)                        # the owner's outbox is never written to
        row = {r['MessageId']: r for r in s.feed(limit=50)}[mid]
        self.assertIsNotNone(row['AnsweredAt'])            # ...and the Timeline says so
        self.assertEqual([m['Status'] for m in s.thread_messages('<orig@them>')], ['filed', 'context'])

    def test_the_watermark_means_a_second_poll_reads_nothing_twice(self):
        s = MemoryStore()
        self._inbound(s)
        M = FakeImap(LIST_PLAIN, [reply_raw('going out today.')])
        _n, uid = imapmail.poll_sent(s, M, 'uri@example.com', 0, 7)
        self.assertEqual(imapmail.poll_sent(s, M, 'uri@example.com', uid, 7), (0, uid))

    def test_a_mailbox_with_no_sent_folder_is_not_an_error(self):
        self.assertEqual(imapmail.poll_sent(MemoryStore(), FakeImap(LIST_NONE), 'uri@example.com', 0, 7), (0, 0))


class ChildProcessesOpenNoWindow(unittest.TestCase):
    """The exe is built with console=False, so on Windows every child it starts gets a brand new
    console - a terminal window that opens by itself. Launched from a terminal the child inherits
    that console instead, which is why it never showed on the dev machine."""

    def test_the_flag_is_added_on_windows_and_nowhere_else(self):
        with mock.patch.object(spawn, 'WINDOWS', True):
            self.assertEqual(spawn.flags(timeout=5),
                             {'timeout': 5, 'creationflags': spawn.CREATE_NO_WINDOW})
        with mock.patch.object(spawn, 'WINDOWS', False):
            self.assertEqual(spawn.flags(timeout=5), {'timeout': 5})

    def test_an_explicit_flag_is_kept_not_replaced(self):
        with mock.patch.object(spawn, 'WINDOWS', True):
            out = spawn.flags(creationflags=0x00000200)     # CREATE_NEW_PROCESS_GROUP
            self.assertEqual(out['creationflags'], 0x00000200 | spawn.CREATE_NO_WINDOW)

    def test_the_modules_that_shell_out_go_through_it(self):
        """A direct subprocess call in any of these is a console window waiting to happen."""
        import inspect
        from taskuary import agents, browserview, channels, mcp, proof, reports
        for mod in (agents, browserview, channels, mcp, proof, reports):
            src = inspect.getsource(mod)
            self.assertNotIn('subprocess.run(', src, mod.__name__)
            self.assertNotIn('subprocess.Popen(', src, mod.__name__)


if __name__ == '__main__':
    unittest.main()
