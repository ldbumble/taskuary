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
    s.upsert_agent('coder', 'cli', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:\\Users\\alexd\\src\\ledger'}}))
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
        self.assertLess(took, 1.5, f'{took:.2f}s')


if __name__ == '__main__':
    unittest.main()
