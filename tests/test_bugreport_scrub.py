"""Nothing private reaches the public tracker. Every person, address, task and message here is
invented; the store is seeded the way a real inbox fills it, and the report text quotes all of it."""
import json, time, unittest
from unittest import mock

from taskuary import bugreport
from taskuary.store import MemoryStore

KEY = 'sk-' + 'proj9fK2abcdefghijklmnopqrstuvwx'
BODY_LINE = 'The renewal terms for the Payworth contract are attached for your review'


def seeded():
    s = MemoryStore()
    s.set_setting('owner_name', 'Alex Doyle', 'test'); s.set_setting('owner_email', 'alex.doyle@northwind.example', 'test')
    s.create_task({'Title': 'Renew the Payworth contract', 'Summary': 'Erin wants the signed copy back before the quarter closes'}, 'test')
    s.add_message({'Subject': 'Q4 vendor review with Payworth', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                   'BodyText': f'Hi Alex,\n{BODY_LINE}. Please sign by Friday.\nThanks', 'OwnText': 'Sending it over tonight, promise',
                   'RecipientsJson': json.dumps({'to': ['Gail Moreno <gail@northwind.example>'], 'cc': []})})
    s.save_connector({'Type': 'imap', 'Name': 'alex@northwind.example', 'Active': 1,
                      'ConfigJson': json.dumps({'username': 'adoyle-mail', 'host': 'mail.northwind.example', 'port': 993, 'ssl': 'true'})}, 'test')
    s.save_source({'Channel': 'email', 'Address': 'inbox@northwind.example', 'Active': 1}, 'test')
    s.upsert_agent('coding', 'cli', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:\\Users\\alexd\\src\\ledger'}}))
    return s


PRIVATE = ['erin@northwind.example', 'Erin Blake', 'Renew the Payworth contract', 'Q4 vendor review with Payworth', BODY_LINE,
           'Sending it over tonight', 'Gail Moreno', 'gail@northwind.example', 'alex@northwind.example', 'inbox@northwind.example',
           'Alex Doyle', 'alex.doyle@northwind.example', 'adoyle-mail', 'mail.northwind.example', 'northwind/ledger', 'alexd',
           'src\\ledger', 'intranet.northwind.example', '192.168.1.20', '10.0.0.7', KEY, 'Erin wants the signed copy back',
           'other/thing', 'northwind']
KEEP = ['https://github.com/ldbumble/taskuary/issues/12', 'https://taskuary.com/docs/x', 'localhost:7787', '127.0.0.1',
        '~\\AppData\\x.log', '~/x', 'Taskuary 0.3.8.2', 'taskuary.server:123', 'assets/index-BH9t30KP.js:10:5', 'TypeError']

TEXT = f"""TypeError: cannot read 'Renew the Payworth contract' while opening RENEW THE PAYWORTH CONTRACT
Taskuary 0.3.8.2 (source) on Windows
2026-10-14 10:00:50 INFO    taskuary.server:123 mail from Erin Blake <erin@northwind.example> - Q4 vendor review with Payworth
2026-10-14 10:00:50 DEBUG   taskuary.ingest:9 body: {BODY_LINE}. own: Sending it over tonight, promise
cc Gail Moreno, account alex@northwind.example, inbox@northwind.example, Alex Doyle <alex.doyle@northwind.example>, adoyle-mail
imap mail.northwind.example:993 failed; see https://intranet.northwind.example/x and https://github.com/other/thing
repo northwind/ledger at C:\\Users\\alexd\\src\\ledger, log C:\\Users\\alexd\\AppData\\x.log and /home/alexd/x
summary: Erin wants the signed copy back before the quarter closes
peer 192.168.1.20 and 10.0.0.7, local 127.0.0.1 and localhost:7787, key {KEY}
at openTask (assets/index-BH9t30KP.js:10:5) - https://github.com/ldbumble/taskuary/issues/12 https://taskuary.com/docs/x
"""


class ScrubTests(unittest.TestCase):
    def setUp(self): self.s = seeded()

    def test_nothing_private_survives(self):
        out = bugreport.scrub(TEXT, self.s)
        for p in PRIVATE: self.assertNotIn(p.lower(), out.lower(), p)
        self.assertIn('[removed]', out)

    def test_taskuarys_own_addresses_loopback_and_the_code_survive(self):
        out = bugreport.scrub(TEXT, self.s)
        for k in KEEP: self.assertIn(k, out, k)

    def test_a_user_folder_becomes_home(self):
        self.assertEqual('see ~\\AppData\\x.log', bugreport.scrub('see C:\\Users\\alexd\\AppData\\x.log', MemoryStore()))
        self.assertEqual('see ~/x', bugreport.scrub('see /home/alexd/x', MemoryStore()))
        self.assertEqual('see ~/Library/y', bugreport.scrub('see /Users/alexd/Library/y', MemoryStore()))

    def test_overlapping_strings_leave_no_tail(self):
        s = MemoryStore(); s.create_task({'Title': 'Renew the Payworth contract'}, 'test')
        s.add_message({'Subject': 'Payworth contract signed by Friday', 'FromEmail': 'erin@northwind.example'})
        self.assertEqual('x [removed] y', bugreport.scrub('x Renew the Payworth contract signed by Friday y', s))

    def test_a_store_string_of_punctuation_alone_removes_nothing(self):
        # issue #270: a blank or punctuation-only string made an empty pattern - "[removed]" after every comma, dot and "·"
        text = 'In Taskuary 0.3.9.77, a report ran (exe) · Windows 11 · connectors: gmail, outlook'
        self.assertEqual(text, bugreport._clean(text, ['-', '·', ' ', '']))

    def test_short_store_strings_are_left_alone(self):
        s = MemoryStore(); s.create_task({'Title': 'Fix'}, 'test')
        self.assertEqual('Fix the build', bugreport.scrub('Fix the build', s))

    def test_a_failing_lookup_fails_closed(self):
        with mock.patch.object(self.s, 'people', side_effect=RuntimeError('db locked')):
            with self.assertRaises(bugreport.Unsafe) as e: bugreport.scrub(TEXT, self.s)
        self.assertIn('could not prepare a safe report', str(e.exception))
        with mock.patch('taskuary.redact.scrub', side_effect=ValueError('bad')), self.assertRaises(bugreport.Unsafe):
            bugreport.scrub(TEXT, self.s)

    def test_a_large_mailbox_scrubs_quickly(self):
        s = seeded()
        rows = [(f'Subject number {i} about the budget', f'Sender {i} Person', f's{i}@vendor.example',
                 '\n'.join(f'Line {j} of message {i} says something rather ordinary. Then another sentence {j}.' for j in range(12)),
                 f'Own reply {i} text here, kept short', json.dumps({'to': [f'r{i}@vendor.example']})) for i in range(10000)]
        with s.lock:
            s.cx.executemany('INSERT INTO message (Subject, FromName, FromEmail, BodyText, OwnText, RecipientsJson, Status) '
                             "VALUES (?,?,?,?,?,?,'routed')", rows)
            s.cx.executemany('INSERT INTO task (Title, Summary) VALUES (?,?)', [(f'Task title {i} for review', f'Summary {i}.') for i in range(3000)])
            s.cx.commit()
        text = TEXT * 20 + 'Line 3 of message 4512 says something rather ordinary.'
        t = time.perf_counter(); out = bugreport.scrub(text, s); took = time.perf_counter() - t
        self.assertNotIn('message 4512', out)
        self.assertLess(took, 5, f'{took:.2f}s')


class SlipThroughTests(unittest.TestCase):
    """The shapes a first review got past the scrub: encodings, other home folders, bare repos, hosts outside a
    TLD list, IPv6, shares, and store strings glued to code."""
    def setUp(self):
        self.s = seeded()
        p = mock.patch.object(bugreport, '_machine', return_value=['alexd', 'ALEXD-LAPTOP', 'D:\\profiles\\alexd']); p.start(); self.addCleanup(p.stop)
    def S(self, t): return bugreport.scrub(t, self.s)

    def test_encoded_text_is_scrubbed(self):
        for t in ['GET /api/people/Erin%20Blake 500', 'q=Erin+Blake', 'to erin%40northwind.example', 'to erin\\u0040northwind.example',
                  'to erin\\x40northwind.example']:
            out = self.S(t)
            self.assertNotIn('erin', out.lower(), t); self.assertNotIn('northwind', out.lower(), t)
        out = self.S('http://localhost:7787/api/search?q=Erin%20Blake&who=Payworth%20renewal done')
        self.assertIn('http://localhost:7787/api/search', out); self.assertNotIn('Payworth', out); self.assertNotIn('Erin', out)
        self.assertIn('C++ and a+b', self.S('C++ and a+b'))                       # a plus is only a space between letters

    def test_other_home_folders(self):
        self.assertEqual('~/src/x', self.S('/c/Users/alexd/src/x'))
        self.assertEqual('~/src/x', self.S('/mnt/c/Users/alexd/src/x'))
        self.assertEqual('~\\AppData\\y', self.S('C:\\Users\\Jordan Smith\\AppData\\y'))
        for t in ['D:\\profiles\\alexd\\x.log', 'host ALEXD-LAPTOP user alexd']:
            self.assertNotIn('alexd', self.S(t).lower(), t)

    def test_scheme_less_github_repos(self):
        for t in ['git@github.com:northwind/internal-billing.git', 'see github.com/northwind/internal-billing',
                  'https://github.com/ldbumble/taskuary/../../northwind/x']:
            out = self.S(t)
            self.assertNotIn('internal-billing', out, t); self.assertNotIn('northwind', out, t)
        self.assertIn('github.com/ldbumble/taskuary/issues/3', self.S('github.com/ldbumble/taskuary/issues/3'))

    def test_hosts_ipv6_and_shares(self):
        for t, gone in [('imap.payworth.xq:993 refused', 'payworth'), ('via smtp.northwind.corp', 'northwind'),
                        ('[2a02:1210:5c4b:9f00::12]:51234', '2a02'), ('peer fe80::1c2b:3dff:fe4e:5f6a', 'fe80'),
                        ('open \\\\fileserver01\\finance\\payroll.xlsx', 'fileserver01')]:
            self.assertNotIn(gone, self.S(t).lower(), t)
        for keep in ['2026-10-14 10:00:50 INFO', 'taskuary.ingest:9', 'index-BH9t30KP.js', 'README.md', 'config.toml', 'Node.js']:
            self.assertIn(keep, self.S(keep), keep)

    def test_short_strings_need_word_boundaries(self):
        s = MemoryStore(); s.set_setting('owner_name', 'Mark Doyle', 'test'); s.add_message({'Subject': 'Error', 'FromEmail': 'x@vendor.example'})
        self.assertEqual('markdown bookmark TypeError', bugreport.scrub('markdown bookmark TypeError', s))
        self.assertEqual('[removed] said: [removed]', bugreport.scrub('Mark said: Error', s))

    def test_underscores_and_dashes_separate_words_and_first_names_count(self):
        for t in ['Payworth_Q4_terms_Erin.pdf', 'Renew_the_Payworth_contract.pdf', 'Hi Erin, ok', 'Gail-Moreno-notes.txt']:
            out = self.S(t)
            for w in ('Erin', 'Renew_the', 'Gail'): self.assertNotIn(w, out, t)

    def test_secret_shaped_connector_keys(self):
        self.s.save_connector({'Type': 'jira', 'Name': 'x', 'Active': 1, 'ConfigJson': json.dumps({'api_token': 'plainvalue77'})}, 'test')
        self.assertNotIn('plainvalue77', self.S('sent plainvalue77'))


class RoundTwoTests(unittest.TestCase):
    """A second review: layered encodings, a home folder with a space, GitHub's other hosts, and stack traces that
    the any-suffix host rule had started to eat."""
    def setUp(self):
        self.s = seeded()
        for n, v in [('_machine', ['Jordan Smith', 'JS-DESK']), ('_home_dirs', ['C:\\Users\\Jordan Smith'])]:
            p = mock.patch.object(bugreport, n, return_value=v); p.start(); self.addCleanup(p.stop)
    def S(self, t): return bugreport.scrub(t, self.s)

    def test_layered_encodings(self):
        for t in ['Erin%2520Blake', 'Renew%2520the%2520Payworth%2520contract', 'Erin%252520Blake', 'erin%2540northwind.example',
                  'Erin\\\\u0020Blake', 'Erin&#32;Blake', 'Erin\u200bBlake', 'Erin\u00a0Blake']:
            out = self.S(t)
            for w in ('erin', 'payworth', 'blake'): self.assertNotIn(w, out.lower(), t)

    def test_the_machines_own_home_goes_whole(self):
        self.assertEqual("Permission denied: '~'", self.S("Permission denied: 'C:\\Users\\Jordan Smith'"))
        self.assertEqual('~ said hi', self.S('C:\\Users\\Jordan Smith said hi'))
        self.assertEqual('~/x', self.S('/c/Users/Jordan Smith/x'))
        self.assertEqual("open '~'", self.S("open 'C:\\Users\\Pat Lee'"))          # anyone's folder, closed by a quote

    def test_githubs_other_hosts(self):
        for t in ['api.github.com/repos/northwind/internal-billing', 'gist.github.com/northwind/abc',
                  'https://raw.githubusercontent.com/northwind/internal-billing/main/x', 'https://github.com/ldbumble/taskuary-private/x']:
            out = self.S(t)
            self.assertNotIn('northwind', out, t); self.assertNotIn('private', out, t)
        for keep in ['https://github.com/LDBUMBLE/taskuary.git', 'api.github.com/repos/ldbumble/taskuary/issues']:
            self.assertIn(keep, self.S(keep), keep)

    def test_stack_traces_survive(self):
        for keep in ['sqlalchemy.exc.OperationalError', 'requests.exceptions.ConnectionError', 'at HTMLButtonElement.onClick (x)',
                     'at t.render', 'floor.check(cmd)', 'Object.keys', 'Promise.all', 'props.task.title', 'cfg.store',
                     'assets/index-BH9t30KP.js:10:5', 'taskuary.ingest:9', 'File server.py:12']:
            self.assertIn(keep, self.S(keep), keep)
        for t, gone in [('imap.payworth.xq:993', 'payworth'), ('smtp.northwind.corp', 'northwind'), ('fileserver01.corp', 'fileserver01'),
                        ('files.northwind.example', 'northwind'), ('host=build7.lab', 'build7'), ('user@build7.lab', 'build7')]:
            self.assertNotIn(gone, self.S(t), t)

    def test_loopback_v6_stays(self):
        self.assertEqual('[::1]:7787', self.S('[::1]:7787'))

    def test_catalogue_words_are_not_accounts(self):
        self.s.save_connector({'Type': 'jira', 'Name': 'jira', 'Active': 1}, 'test')
        self.assertIn('connectors: imap, jira', self.S('connectors: imap, jira'))

    def test_a_host_goes_whole_before_store_strings(self):
        self.s.save_connector({'Type': 'imap', 'Name': 'ledgerline', 'Active': 1}, 'test')
        self.assertEqual('see [removed]', self.S('see northwind.ledgerline.example'))


class RoundThreeTests(unittest.TestCase):
    def setUp(self):
        self.s = seeded()
        p = mock.patch.object(bugreport, '_machine', return_value=[]); p.start(); self.addCleanup(p.stop)
    def S(self, t): return bugreport.scrub(t, self.s)

    def test_hosts_in_any_case(self):
        for t in ['JS-DESK.CORP.NORTHWIND.EXAMPLE', 'MAIL.NORTHWIND.COM rejected', 'Mail.Northwind.com', 'Server.Northwind.Com',
                  'foo.Example.com', 'see Northwind.co.uk', 'Northwind.LedgerLine.com', 'NORTHWIND.LEDGERLINE.COM']:
            self.assertNotIn('northwind', self.S(t).lower(), t)
        self.assertNotIn('foo', self.S('foo.Example.com'))
        for keep in ['sqlalchemy.exc.OperationalError', 'requests.exceptions.ConnectionError', 'at HTMLButtonElement.onClick (x)',
                     'at t.render', 'floor.check(cmd)', 'Object.keys', 'Promise.all', 'props.task.title', 'cfg.store', 'window.location.host']:
            self.assertIn(keep, self.S(keep), keep)

    def test_a_quote_closes_a_home_only_when_a_quote_opened_it(self):
        self.assertEqual("PermissionError: ~ while reading 'config.toml'", self.S("PermissionError: C:\\Users\\bob while reading 'config.toml'"))
        self.assertEqual("open '~'", self.S("open 'C:\\Users\\Pat Lee'"))

    def test_joiners_vanish_and_a_zero_width_space_is_a_space(self):
        self.assertNotIn('in', self.S('Er\u200din Blake').replace('[removed]', ''))
        self.assertNotIn('Erin', self.S('Erin\u200bBlake'))
        self.assertEqual('[removed]', self.S('Erin\u00a0Blake'))


class SmallTests(unittest.TestCase):
    def test_the_machine_names_itself(self):
        with mock.patch('getpass.getuser', return_value='jordanq'), mock.patch('socket.gethostname', return_value='JQ-DESK-7'):
            m = bugreport._machine()
        self.assertIn('jordanq', m); self.assertIn('JQ-DESK-7', m)
        self.assertNotIn('user', [x.lower() for x in bugreport.private_strings(MemoryStore())])   # a generic login is no one

    def test_a_bad_time_is_no_time(self):
        for at in ['9999-12-31T23:59:59+14:00', '0001-01-01T00:00:00-12:00', 'nonsense']: bugreport._when(at)

    def test_a_cut_title_never_splits_a_marker(self):
        t = bugreport._cut('x' * 75 + ' [removed] tail', 80)
        self.assertNotIn('[rem', t.replace('[removed]', '')); self.assertLessEqual(len(t), 80)


if __name__ == '__main__':
    unittest.main()
