"""THE READS THE AGENT VIEW POLLS answer "unchanged" in one small name (speed round, 2026-11-18). The conversation's `rev` was the one road;
the task's own read and the chat's state, each 5-9 KB and re-read every 3-5 s while an agent works, now take it through the same function
(server._revisioned): the page sends the name of what it holds and gets only that name back while it is still the answer. A working
session's idle clock moves on every read and is outside the name; a real change is a new name at once. Invented people only."""
import json, threading, unittest
from fastapi.testclient import TestClient
from taskuary import general, server

c = TestClient(server.app)
store = server.store


def made():
    tid = store.create_task({'Title': 'Vendor review for Erin', 'Kind': 'general', 'Status': 'open', 'Summary': 'Erin Blake asks for a review'}, 'owner')
    store.add_message({'TaskId': tid, 'ExternalId': f'fx-{tid}', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                       'ToEmail': 'alex@northwind.example', 'Subject': 'Your review?', 'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Hi Alex, a review?', 'Status': 'routed'})
    return tid


class PolledReadsAnswerUnchanged(unittest.TestCase):
    def test_the_task_and_the_chat_answer_only_their_name_while_nothing_changed(self):
        tid = made()
        for path in (f'/api/tasks/{tid}', f'/api/tasks/{tid}/assistant', f'/api/tasks/{tid}/conversation'):
            c.get(path)                       # ...the first read settles what a task derives once (its origin)
            full = c.get(path).json()
            self.assertTrue(full.get('rev'), path)
            again = c.get(path, params={'rev': full['rev']})
            self.assertEqual(again.json(), {'rev': full['rev'], 'same': True}, path)
            self.assertLess(len(again.content), 100, f'{path}: N polls with nothing changed move a name, not the answer')
            self.assertGreater(len(c.get(path).content), 400)

    def test_a_real_change_is_a_new_name_at_once(self):
        tid = made()
        for path in (f'/api/tasks/{tid}', f'/api/tasks/{tid}/assistant'):
            c.get(path); before = c.get(path).json()['rev']
            store.add_message({'TaskId': tid, 'ExternalId': f'fx-more-{before}', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                               'ToEmail': 'alex@northwind.example', 'Subject': 'And one more thing', 'SentAt': '2026-11-10 09:00:00', 'BodyText': 'Also the sheet.', 'Status': 'routed'})
            after = c.get(path, params={'rev': before}).json()
            self.assertFalse(after.get('same'), path)
            self.assertNotEqual(after['rev'], before, path)

    def test_a_sessions_idle_clock_is_not_a_change(self):
        got = {'session': {'sid': 's1', 'idle': 3, 'tail': ['a'], 'busy': True}, 'x': 1}
        a = server._revisioned(got)['rev']
        b = server._revisioned({'session': {'sid': 's1', 'idle': 9, 'tail': ['b'], 'busy': True}, 'x': 1})['rev']
        self.assertEqual(a, b)
        self.assertNotEqual(a, server._revisioned({'session': {'sid': 's1', 'idle': 9, 'busy': False}, 'x': 1})['rev'])

