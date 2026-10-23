"""LIT AND PRESSED (the deep dive, 2026-10-20): nothing recorded whether the button the Advisor lit was the one pressed. A press while
its line is shown is one advice_press row - advised and pressed verb, whether they matched, the item's kind and channel, the sender
and their domain, and the scope a move is learned at (a repository for code, else the domain)."""
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import advisor, server
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail


class PressTests(_Rail):
    def test_a_press_is_kept_with_what_was_lit_and_whom_the_item_was_from(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rev = advisor.revision(s, 'task', t)
        i = advisor.press(s, f'task:{t}', 'continue', 'done', rev)
        r = s._one('SELECT * FROM advice_press WHERE Id=?', (i,))
        self.assertEqual((r['Advised'], r['Pressed'], r['Match'], r['Stale']), ('continue', 'close', 0, 0))   # the row's `done` is close
        self.assertEqual((r['Sender'], r['SenderDomain'], r['Scope'], r['Channel']), ('gail@northwind.example', 'northwind.example', 'northwind.example', 'email'))
        self.assertTrue(r['ItemKind'])
        self.assertFalse(s.get_setting('learn_pending'), "a press is the Advisor's to learn, never the reflection's - it writes what triage reads")
        j = advisor.press(s, f'task:{t}', 'continue', 'continue', 'an-older-revision')
        self.assertEqual(s._one('SELECT Match, Stale FROM advice_press WHERE Id=?', (j,)), {'Match': 1, 'Stale': 1})

    def test_a_code_item_is_scoped_to_its_repository(self):
        s = MemoryStore()
        t = s.create_task({'Title': '#12 import fails', 'Status': 'open'}, 'owner')
        mid = s.add_message({'ConversationId': 'github:12', 'Channel': 'github', 'Subject': '#12 import fails', 'FromName': 'Ray Colton',
                             'SourceName': 'northwind/ledger', 'BodyText': 'Traceback', 'Status': 'routed', 'TaskId': t})
        w = advisor.who_of(s, {'tid': t, 'mid': mid, 'channel': 'github'})
        self.assertEqual((w['scope'], w['channel']), ('northwind/ledger', 'github'))

    def test_a_key_with_nothing_to_advise_on_records_nothing(self):
        self.assertEqual(advisor.press(MemoryStore(), 'meeting:3', 'close', 'next'), 0)

    def test_the_endpoint_records_and_never_fails_the_press(self):
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            got = c.post('/api/advice/press', json={'key': f'task:{t}', 'advised': 'continue', 'pressed': 'next'}).json()
            self.assertTrue(got['id'])
            with mock.patch.object(advisor, 'press', side_effect=RuntimeError('disk full')):
                self.assertEqual(c.post('/api/advice/press', json={'key': f'task:{t}', 'pressed': 'next'}).json(), {'id': 0})
        self.assertEqual(s._one('SELECT Pressed FROM advice_press')['Pressed'], 'next')
