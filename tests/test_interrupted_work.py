"""Work that Taskuary interrupted stays open and says so; only the owner's click starts a worker again (PW-262)."""
import asyncio, unittest
from taskuary import terminal
from taskuary.store import MemoryStore


class InterruptedWork(unittest.TestCase):
    def working(self, s):
        tid = s.create_task({'Title': 'Half done'}, 'owner')
        s.update_task(tid, {'Status': 'in_progress'}, 'owner')
        rid = s.add_run(tid, 'coder', 'do it') if hasattr(s, 'add_run') else None
        return tid

    def test_a_restart_leaves_the_task_open_marked_interrupted_not_working_or_done(self):
        s = MemoryStore(); tid = self.working(s)
        terminal.recover_after_restart(s)
        t = s.get_task(tid)
        self.assertEqual(t['Status'], 'open')
        self.assertTrue(s.task_has_tag(tid, terminal.INTERRUPTED))
        self.assertIn('nobody is working it', s.list_comments(tid)[-1]['Body'])

    def test_an_ordinary_session_end_is_not_an_interruption(self):
        s = MemoryStore(); tid = self.working(s)
        self.assertTrue(terminal.release_task(s, tid, 'terminal'))
        self.assertFalse(s.task_has_tag(tid, terminal.INTERRUPTED))

    def test_starting_a_worker_again_clears_the_mark_and_reopening_alone_does_not(self):
        s = MemoryStore(); tid = self.working(s)
        terminal.release_task(s, tid, 'shutdown')
        s.update_task(tid, {'Status': 'open'}, 'owner')            # Reopen task: status only
        self.assertTrue(s.task_has_tag(tid, terminal.INTERRUPTED))
        self.assertTrue(terminal.resume_task(s, tid, 'owner'))    # the owner chose an agent
        self.assertFalse(s.task_has_tag(tid, terminal.INTERRUPTED))

    def test_a_browser_leaving_the_terminal_releases_nothing(self):
        s = MemoryStore(); tid = self.working(s)
        class Tab: pass
        term = Tab(); term.subs = []
        q = asyncio.Queue()
        terminal.Term.subscribe(term, asyncio.new_event_loop(), q)
        terminal.Term.unsubscribe(term, q)                         # the tab navigated away
        self.assertEqual(term.subs, [])
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')


if __name__ == '__main__': unittest.main()
