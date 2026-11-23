"""THE READS THE AGENT VIEW POLLS answer "unchanged" in one small name (speed round, 2026-11-18). The conversation's `rev` was the one road;
the task's own read and the chat's state, each 5-9 KB and re-read every 3-5 s while an agent works, now take it through the same function
(server._revisioned): the page sends the name of what it holds and gets only that name back while it is still the answer. A working
session's idle clock moves on every read and is outside the name; a real change is a new name at once. Invented people only."""
import json, threading, time, unittest
from fastapi.testclient import TestClient
from taskuary import chatlog, general, server

c = TestClient(server.app)
store = server.store


def made():
    # ...after the one copy before the log is made (chatlog.backed_up, its own thread): until then a chat reads as the old build drew it and
    # its name moves once when it is frozen - the macOS shard read across that moment (CI, 2026-11-23)
    for _ in range(100):
        if chatlog.backed_up(store): break
        time.sleep(0.1)
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

    def test_only_a_task_page_opened_starts_what_its_chats_first_turn_will_read(self):
        """The first turn's prompt waited seconds on the judgement of what is known about its task (context.recall). The task page's own first
        read (`opened`) starts it (general.warm); a prefetch, a rail card's read and a poll - none of them an open - start nothing."""
        from unittest import mock
        from taskuary import context
        tid, warmed = made(), []
        with mock.patch.object(context, 'warm', lambda st, t: warmed.append(t)):
            rev = c.get(f'/api/tasks/{tid}').json()['rev']                     # ...a prefetch under the pointer, a rail card
            c.get(f'/api/tasks/{tid}', params={'rev': rev})                     # ...a poll
            self.assertEqual(warmed, [], 'a read that is not an open asked for a judgement')
            c.get(f'/api/tasks/{tid}', params={'opened': 1})
            self.assertEqual(warmed, [tid])

    def own(self):
        "A task the owner opened himself - not a stranger's, whose agent is told nothing known (context.recall)."
        tid = store.create_task({'Title': 'Plan the vendor review with Erin', 'Kind': 'general', 'Status': 'open', 'Summary': 'Erin Blake and the sheet'}, 'owner')
        store._exec('UPDATE task SET OriginBase=? WHERE TaskId=?', ('owner', tid))
        store.create_task({'Title': 'Vendor sheet for Paula, closed', 'Kind': 'general', 'Status': 'done'}, 'owner')
        from taskuary import origin
        self.assertNotEqual(origin.of_task(store, tid)[0], 'stranger')
        return tid

    def judged(self, tid, **params):
        "One read, and whatever judgement it started, to its end: claimed as the read runs (context._judging), so nothing is left to time."
        from taskuary import context
        c.get(f'/api/tasks/{tid}', params=params)
        for f in list(context._judging.values()): f.result(10)

    def test_a_task_opened_with_no_ai_connected_writes_nothing(self):
        from unittest import mock
        from taskuary import capabilities, context, textsim
        context._recalled.clear(); tid = self.own()
        n = lambda: store._one('SELECT COUNT(*) n FROM brainroute')['n']
        with mock.patch.object(textsim, 'embedder', lambda st: None), mock.patch.object(capabilities, 'has_ai', lambda st: False):
            was = n()
            for _ in range(3): self.judged(tid, opened=1)
            self.assertEqual(n() - was, 0, 'a read recorded the route of a brain that was never going to answer')

    def test_a_ranking_that_failed_is_not_asked_again_on_every_open(self):
        from unittest import mock
        from taskuary import capabilities, context, llm, textsim
        context._recalled.clear(); tid = self.own()
        asked = []
        def failing(system, user, **k): asked.append(1); raise RuntimeError('the model is down')
        with mock.patch.object(textsim, 'embedder', lambda st: None), mock.patch.object(capabilities, 'has_ai', lambda st: True), \
             mock.patch.object(llm, 'build_llm', lambda *a, **k: failing):
            for _ in range(3): self.judged(tid, opened=1)
            self.assertEqual(len(asked), 1, f'a failing model was asked {len(asked)} times by 3 opens of one task')

    def test_an_open_whose_ranking_failed_does_not_leave_the_turn_without_what_is_known(self):
        """The failure an open met is held against the NEXT OPENS only: the model came back, the owner typed, and his turn's own recall asks
        again - it never reads the open's failure as its answer (the turn's prompt would lead with nothing known and no model asked)."""
        from unittest import mock
        from taskuary import capabilities, context, llm, textsim
        context._recalled.clear(); tid = self.own()
        up, asked = [False], []
        def flaky(system, user, **k):
            asked.append(up[0])
            if not up[0]: raise RuntimeError('rate limited')
            return json.dumps({'picks': ['PAST1']})
        with mock.patch.object(textsim, 'embedder', lambda st: None), mock.patch.object(capabilities, 'has_ai', lambda st: True), \
             mock.patch.object(llm, 'build_llm', lambda *a, **k: flaky):
            self.judged(tid, opened=1)
            self.judged(tid, opened=1)
            self.assertEqual(asked, [False], 'a second open asked the failing model again')
            up[0] = True
            got = context.recall(store, tid, context.brief_messages(store, tid))
        self.assertEqual(asked, [False, True], 'the turn read the open\'s failure instead of asking')
        self.assertTrue(got['past'], got)

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
        # ...as warm as the first: making forty tasks takes long enough on a slow runner that a cache of a second had gone cold, and the read
        # asked once more for that, not for the store's size (Windows CI, 2026-11-18: 123 against 122)
        c.get(f'/api/tasks/{tid}')
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
