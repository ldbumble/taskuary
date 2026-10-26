"""The owner's reply from Gmail's Sent folder joins the thread - and the task - it answers.

A Gmail install connected over IMAP showed a sender's mail on one task and the owner's own answer,
written in Gmail, nowhere near it: "It isnt connecting my incoming mail to my sent mail ... They should
be combined into one task" (TQ-1214, 2026-10-26). The thread key was read off each mail's own headers
alone, so any reply whose headers did not name the thread's first mail - a client that sends only
In-Reply-To pointing at the owner's last answer, References run together with commas - keyed a thread
of its own. Gmail already knows the thread (X-GM-THRID, both folders); every mail now also remembers
its own Message-ID, so a reply naming any mail already here joins that mail's thread.
"""
import email, email.message, email.utils, imaplib, json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import imapmail, store
from taskuary.store import MemoryStore

ME, RAY = 'alex@northwind.example', 'Ray Colton <ray@vendor.example>'
NOW = datetime.now().astimezone().replace(microsecond=0)


def mime(frm, mid, subj='the ledger export', body='it writes empty files', refs=None, irt=None, ago=60, to=ME):
    m = email.message.EmailMessage()
    m['From'], m['To'], m['Subject'] = frm, to, subj
    m['Date'] = email.utils.format_datetime(NOW - timedelta(minutes=ago))
    m['Message-ID'] = mid
    if irt: m['In-Reply-To'] = irt
    if refs: m['References'] = refs
    m.set_content(body)
    return m.as_bytes()


class GmailBox:
    """Enough of Gmail over IMAP: INBOX and [Gmail]/Sent Mail, UID SEARCH/FETCH, and - when `gm` - the X-GM-EXT-1
    capability with each mail's X-GM-THRID on the FETCH response, the way Gmail answers `(X-GM-THRID RFC822)`."""
    def __init__(self, inbox: dict, sent: dict, gm=True):
        self.boxes, self.gm, self.box, self.fetches = {'INBOX': inbox, '[Gmail]/Sent Mail': sent}, gm, 'INBOX', []
        self.capabilities = ('IMAP4REV1', 'X-GM-EXT-1') if gm else ('IMAP4REV1',)
        self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'the mail host certificate'))
    def login(self, u, p): return 'OK', []
    def list(self): return 'OK', [br'(\HasNoChildren) "/" "INBOX"', br'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"']
    def select(self, box, readonly=False):
        self.box = box.strip('"')
        return 'OK', [str(len(self.boxes[self.box])).encode()]
    def response(self, code): return code, [b'7' if code == 'UIDVALIDITY' else None]
    def uid(self, cmd, *a):
        msgs = self.boxes[self.box]
        if cmd == 'search':
            crit = a[1]
            if m := re.fullmatch(r'\(OR HEADER Message-ID "([^"]+)" HEADER References "([^"]+)"\)', crit):
                hit = lambda raw: m.group(1) in str(email.message_from_bytes(raw)['Message-ID']) or m.group(1) in str(email.message_from_bytes(raw)['References'] or '')
                return 'OK', [' '.join(str(u) for u, (raw, _t) in sorted(msgs.items()) if hit(raw)).encode()]
            return 'OK', [' '.join(str(u) for u in sorted(msgs)).encode()]
        if cmd == 'fetch':
            u, what = int(a[0]), a[1]; self.fetches.append(what)
            raw, thrid = msgs[u]
            head = f'{u} (X-GM-THRID {thrid} UID {u} RFC822 {{{len(raw)}}}' if 'X-GM-THRID' in what else f'{u} (UID {u} RFC822 {{{len(raw)}}}'
            return 'OK', [(head.encode(), raw), b')']
        if cmd == 'store': return 'OK', []
        raise AssertionError(cmd)
    def logout(self): return 'BYE', []


def store_with():
    s = MemoryStore()
    cid = s.get_connector_by_type('gmail')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'app-password', 'Active': 1, 'ConfigJson': json.dumps({'address': ME})}, 'o')
    return s, s.get_connector_by_type('gmail', with_secret=True)


def poll(s, box):
    with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=box):
        return imapmail.poll_imap(s, s.get_connector_by_type('gmail', with_secret=True), [], llm=None)


def task_on_first(s):
    """The task triage would have opened on the first mail - there is no model in these tests to open it."""
    tid = s.create_task({'Title': 'Fix the ledger export', 'Kind': 'coding'}, 'o')
    s.attach_message(rows(s)[0]['MessageId'], tid)
    return tid


def rows(s): return s._rows("SELECT MessageId, ExternalId, ConversationId, TaskId, Status, Direction, MailMetaJson FROM message WHERE Channel='email' ORDER BY MessageId")


class TheReplyFromSentJoinsTheThread(unittest.TestCase):
    def test_an_ordinary_gmail_reply_lands_on_the_inbound_task(self):
        s, _c = store_with()
        poll(s, GmailBox({1: (mime(RAY, '<r1@vendor.example>'), '900')}, {}))
        tid = task_on_first(s)
        reply = mime(ME, '<a1@mail.gmail.example>', 'Re: the ledger export', 'fixed - try again', '<r1@vendor.example>', '<r1@vendor.example>', 30, RAY)
        poll(s, GmailBox({1: (mime(RAY, '<r1@vendor.example>'), '900')}, {1: (reply, '900')}))
        got = rows(s)
        self.assertEqual([r['ConversationId'] for r in got], ['<r1@vendor.example>'] * 2)
        self.assertEqual((got[1]['Direction'], got[1]['TaskId']), ('out', tid))

    def test_a_reply_naming_only_the_owners_answer_still_joins_and_the_next_answer_follows(self):
        # Ray's client threads on In-Reply-To alone, and that names Alex's answer, not Ray's first mail
        s, _c = store_with()
        first = mime(RAY, '<r1@vendor.example>')
        ans = mime(ME, '<a1@mail.gmail.example>', 'Re: the ledger export', 'fixed - try again', '<r1@vendor.example>', '<r1@vendor.example>', 50, RAY)
        again = mime(RAY, '<r2@vendor.example>', 'RE: the ledger export', 'still empty', irt='<a1@mail.gmail.example>', ago=40)
        ans2 = mime(ME, '<a2@mail.gmail.example>', 'Re: the ledger export', 'one more try', '<r1@vendor.example> <a1@mail.gmail.example> <r2@vendor.example>',
                    '<r2@vendor.example>', 30, RAY)
        poll(s, GmailBox({1: (first, '900')}, {}))
        tid = task_on_first(s)
        poll(s, GmailBox({1: (first, '900')}, {1: (ans, '900')}))
        poll(s, GmailBox({1: (first, '900'), 2: (again, '900')}, {1: (ans, '900'), 2: (ans2, '900')}))
        got = rows(s)
        self.assertEqual([r['ConversationId'] for r in got], ['<r1@vendor.example>'] * 4)
        self.assertEqual([r['TaskId'] for r in got], [tid] * 4)          # Ray's second mail and both answers, one task

    def test_without_gmail_the_owners_stored_message_id_carries_the_thread(self):
        s, _c = store_with()
        first = mime(RAY, '<r1@vendor.example>')
        ans = mime(ME, '<a1@mail.gmail.example>', 'Re: the ledger export', 'fixed', '<r1@vendor.example>', '<r1@vendor.example>', 50, RAY)
        again = mime(RAY, '<r2@vendor.example>', 'RE: the ledger export', 'still empty', irt='<a1@mail.gmail.example>', ago=40)
        poll(s, GmailBox({1: (first, '')}, {1: (ans, '')}, gm=False))
        box = GmailBox({1: (first, ''), 2: (again, '')}, {1: (ans, '')}, gm=False)
        poll(s, box)
        self.assertEqual([r['ConversationId'] for r in rows(s)], ['<r1@vendor.example>'] * 3)
        self.assertNotIn('X-GM-THRID', ' '.join(box.fetches))          # a server without the extension is never asked for it

    def test_gmail_alone_knows_a_reply_whose_headers_name_nothing_here(self):
        # a reply from a client that dropped both headers: only Gmail's own thread id says where it goes
        s, _c = store_with()
        first = mime(RAY, '<r1@vendor.example>')
        bare = mime(RAY, '<r3@vendor.example>', 'RE: the ledger export', 'and the import too', ago=20)
        poll(s, GmailBox({1: (first, '900'), 2: (bare, '900')}, {}))
        self.assertEqual([r['ConversationId'] for r in rows(s)], ['<r1@vendor.example>'] * 2)
        self.assertEqual(json.loads(rows(s)[1]['MailMetaJson'])['gm_thread'], '900')

    def test_comma_separated_references_still_key_on_the_root(self):
        msg = email.message_from_bytes(mime(RAY, '<r4@vendor.example>', refs='<r1@vendor.example>,<a1@mail.gmail.example>'))
        self.assertEqual(imapmail.thread_key(msg), '<r1@vendor.example>')
        msg = email.message_from_bytes(mime(RAY, '<r4@vendor.example>', irt="<a1@mail.gmail.example> (Alex's message of Monday)"))
        self.assertEqual(imapmail.thread_key(msg), '<a1@mail.gmail.example>')

    def test_a_thread_stored_before_the_fix_keeps_its_key(self):
        # rows written by an earlier build carry no ids in their meta; the References root still finds them
        s, _c = store_with()
        s.add_message({'ExternalId': 'imap:old:1', 'ConversationId': '<r1@vendor.example>', 'Channel': 'email', 'SourceName': ME,
                       'Subject': 'the ledger export', 'FromEmail': 'ray@vendor.example', 'SentAt': '2026-10-20 09:00:00', 'Status': 'filed'})
        ans = mime(ME, '<a1@mail.gmail.example>', 'Re: the ledger export', 'fixed', '<r1@vendor.example>', '<r1@vendor.example>', 50, RAY)
        poll(s, GmailBox({}, {1: (ans, '900')}))
        self.assertEqual([r['ConversationId'] for r in rows(s)], ['<r1@vendor.example>'] * 2)

    def test_the_lookups_ride_an_index(self):
        s = MemoryStore()
        for col in ('gm_thread', 'mid'):
            plan = ' '.join(str(r[-1]) for r in s.cx.execute(f'EXPLAIN QUERY PLAN SELECT ConversationId FROM message WHERE {store.meta_expr(col)}=?', ('x',)))
            self.assertIn('USING INDEX', plan, col)


if __name__ == '__main__': unittest.main()
