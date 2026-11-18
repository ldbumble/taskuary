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


class TheTasksReadAsksEachSettingOnce(unittest.TestCase):
    """task_detail is the page's hot read (every 3 s while an agent works). Its readers each asked the same settings again - the owner's
    addresses, the AI pick, trusted organisations: ~40 of its ~180 queries. Counted, never timed."""
    def queries(self, tid):
        asked = []
        rows = store._rows                      # ...every read ends here (_one is a _rows)
        def _rows(q, p=()): asked.append((threading.current_thread().name, q, tuple(p))); return rows(q, p)
        store._rows = _rows
        try: c.get(f'/api/tasks/{tid}')
        finally: store._rows = rows
        return [(q, p) for who, q, p in asked if who.startswith('AnyIO')]       # ...the request's own thread, not the background ones

    def test_no_setting_is_read_twice_in_one_read(self):
        tid = made(); c.get(f'/api/tasks/{tid}')
        names = [p[0] for q, p in self.queries(tid) if q.startswith('SELECT Value FROM setting WHERE Name=?')]
        self.assertEqual(sorted(n for n in set(names) if names.count(n) > 1), [], 'a setting asked again within one read')

    def test_the_count_does_not_grow_with_the_store(self):
        tid = made(); c.get(f'/api/tasks/{tid}')
        few = len(self.queries(tid))
        for k in range(40): made()
        self.assertLessEqual(len(self.queries(tid)), few + 2, 'the read of one task asks the same questions whatever else the store holds')

    def test_a_document_is_read_once_and_a_write_inside_the_hold_is_read_fresh(self):
        tid = made(); c.get(f'/api/tasks/{tid}')
        docs = [p for q, p in self.queries(tid) if q.startswith('SELECT Content FROM doc')]
        self.assertEqual([d for d in set(docs) if docs.count(d) > 1], [], 'a document asked again within one read')
        with store.held_settings():
            store.get_doc('soul'); store.save_doc('soul', 'Alex Doyle, Northwind.', 'owner')
            self.assertEqual(store.get_doc('soul'), 'Alex Doyle, Northwind.')

    def test_every_writer_of_a_held_setting_or_document_is_read_fresh_inside_the_hold(self):
        """A WRITE INSIDE THE HOLD WAS READ STALE (robustness review, 2026-11-18): save_doc('learned') reads the old text to diff it line by
        line, after it had dropped its held copy - so it held the OLD text again, and the hold served it after the write. Writers that go
        straight to the table (a setting deleted by name, the task number's mark) dropped nothing at all. Each is read back as written."""
        with store.held_settings():
            store.save_doc('learned', '- Erin Blake prefers a short summary.', 'owner')
            self.assertEqual(store.get_doc('learned'), '- Erin Blake prefers a short summary.')
            store.save_doc('learned', '- Erin Blake prefers a short summary.\n- Gail Moreno signs off on vendors.', 'owner')
            self.assertEqual(store.get_doc('learned'), '- Erin Blake prefers a short summary.\n- Gail Moreno signs off on vendors.')
            store.delete_doc('learned')
            self.assertIsNone(store.get_doc('learned'))
            store.set_setting('owner_name', 'Alex Doyle', 'owner')
            self.assertEqual(store.get_setting('owner_name'), 'Alex Doyle')
            store._exec('UPDATE OR IGNORE setting SET Value=? WHERE Name=?', ('Alex Doyle (Northwind)', 'owner_name'))
            self.assertEqual(store.get_setting('owner_name'), 'Alex Doyle (Northwind)')
            store._exec('DELETE FROM setting WHERE Name=?', ('owner_name',))         # ...as a module that clears its own keys does
            self.assertIsNone(store.get_setting('owner_name'))
            mark = store.get_setting('task_id_mark')
            store.create_task({'Title': 'Vendor sheet for Paula', 'Kind': 'general', 'Status': 'open'}, 'owner')
            self.assertNotEqual(store.get_setting('task_id_mark'), mark, 'the task number mark written under the hold')
