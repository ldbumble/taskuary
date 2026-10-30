"""Close keeps Taskuary running, Quit stops it, and live work holds both the computer and an update (the owner, 2026-10-25).

- the desktop's X hides the window to the tray and the tray says the goodbye; only Quit stops (desktop.closing_handler, welcome.tray_goodbye)
- Quit on the browser's top line stops the server through POST /api/quit (workerstate.SERVER)
- the computer is held awake only while an agent or a workflow run is live (awake.Watch)
- Update now with work live waits for it, and says so (update.when_idle)
- the Assistant's Updates line says what is known about a newer release and that its button is lit, never pressed (update.status_line)
Invented people only.
"""
import threading, time, unittest
from unittest import mock

from taskuary import awake, desktop, update, welcome, workflows, workerstate
from taskuary.store import MemoryStore, task_ref


def working_store():
    from taskuary import terminal
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Reconcile the Northwind ledger', 'Summary': 'x'}, 'owner')
    s.update_task(tid, {'Status': 'in_progress'}, 'agent:coding')
    return s, tid, mock.patch.dict(terminal.SESSIONS, {'s1': mock.Mock(task_id=tid, alive=True)}, clear=True)


class LiveWorkIsCountedOnce(unittest.TestCase):
    def test_agents_and_workflow_runs_in_words(self):
        self.assertEqual(awake.said(0, 0), '')
        self.assertEqual(awake.said(1, 0), '1 running agent')
        self.assertEqual(awake.said(2, 1), '2 running agents and 1 routine run')
        self.assertEqual(awake.said(0, 3), '3 routine runs')

    def test_a_workflow_run_whose_worker_is_live_counts_once_as_the_agent(self):
        s, tid, sessions = working_store()
        with sessions, mock.patch.object(workflows, '_STARTING', {tid, 999}):
            self.assertEqual(awake.live(s), (1, 1))
            self.assertEqual(awake.running(s), '1 running agent and 1 routine run')
        self.assertEqual(awake.live(MemoryStore()), (0, 0))


class TheComputerStaysAwakeOnlyWhileWorkRuns(unittest.TestCase):
    def test_the_hold_moves_only_when_live_work_comes_or_goes(self):
        calls = []; w = awake.Watch(calls.append)
        w.tick(False); self.assertEqual(calls, [])                                   # nothing live: nothing held, nothing called
        w.tick(True); w.tick(True)
        self.assertEqual(calls, [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED])     # held once, not once a poll
        w.tick(False); self.assertEqual(calls[-1], awake.ES_CONTINUOUS); self.assertFalse(w.held)
        w.tick(True); w.release(); self.assertEqual(calls[-1], awake.ES_CONTINUOUS)  # and let go when the app stops

    def test_the_watcher_thread_holds_while_live_and_lets_go_when_stopped(self):
        calls = []
        with mock.patch.object(awake, 'live', return_value=(1, 0)):
            t = awake.start(MemoryStore(), poll=0.01, setter=calls.append)
            for _ in range(100):
                if calls: break
                time.sleep(0.01)
            awake.stop(); t.join(2)
        self.assertEqual(calls, [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED, awake.ES_CONTINUOUS])


class AnUpdateWaitsForRunningWork(unittest.TestCase):
    def setUp(self): update.QUEUED.update(at=None, error=None)

    def test_with_nothing_running_it_goes_at_once(self):
        go = mock.Mock(return_value={'restarting': True})
        self.assertEqual(update.when_idle(lambda: '', go), {'restarting': True}); go.assert_called_once()

    def test_with_an_agent_running_it_waits_says_so_and_goes_when_the_last_one_stops(self):
        live, went = ['1 running agent'], threading.Event()
        out = update.when_idle(lambda: live[0], went.set, poll=0.01)
        self.assertEqual(out, {'waiting': True, 'waits': 'Update waits for 1 running agent', 'restarting': False})
        self.assertIsNotNone(update.QUEUED['at']); self.assertFalse(went.wait(0.05))
        # a second press while it waits is told the same, and queues nothing more
        again = mock.Mock()
        self.assertTrue(update.when_idle(lambda: live[0], again, poll=0.01)['waiting'])
        live[0] = ''
        self.assertTrue(went.wait(2)); again.assert_not_called()
        for _ in range(100):
            if update.QUEUED['at'] is None: break
            time.sleep(0.01)
        self.assertIsNone(update.QUEUED['at'])

    def test_a_waiting_update_that_fails_says_why_on_the_card(self):
        live = ['1 routine run']
        update.when_idle(lambda: live[0], mock.Mock(side_effect=RuntimeError('the download stopped short')), poll=0.01)
        live[0] = ''
        for _ in range(200):
            if update.QUEUED['at'] is None: break
            time.sleep(0.01)
        self.assertEqual(update.QUEUED['error'], 'the download stopped short')

    def test_over_the_api_the_press_waits_and_the_check_says_for_what(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        with mock.patch.object(update, 'ready', return_value={'newer': True, 'url': 'u'}), \
             mock.patch('taskuary.awake.update_waits_for', return_value='1 running agent'), \
             mock.patch.object(update, 'when_idle', wraps=lambda running, go: {'waiting': True, 'waits': update.waits_line(running()), 'restarting': False}), \
             mock.patch.object(update, 'apply') as apply, mock.patch.object(update, 'exit_soon') as bye:
            r = c.post('/api/update', json={})
            self.assertEqual(r.json(), {'waiting': True, 'waits': 'Update waits for 1 running agent', 'restarting': False})
            apply.assert_not_called(); bye.assert_not_called()
            with mock.patch.object(update, 'check', return_value={'current': '1', 'latest': '2', 'newer': True}):
                self.assertEqual(c.get('/api/update').json()['waits'], 'Update waits for 1 running agent')


class AnUpdateWaitsOnlyForWorkInFlight(unittest.TestCase):
    """An agent parked at its prompt is waiting on the owner and never finishes by itself - an update held for one waited an hour and
    a half without saying which task it was (TQ-1237). It waits for agents mid-turn, and names them."""
    def sessions(self, tid, *parked):
        from taskuary import terminal
        ss = {f's{i}': mock.Mock(task_id=tid, alive=True, waiting=mock.Mock(return_value=p)) for i, p in enumerate(parked)}
        return mock.patch.dict(terminal.SESSIONS, ss, clear=True)

    def test_a_working_agent_holds_the_update_and_is_named(self):
        s, tid, _ = working_store()
        with self.sessions(tid, False):
            self.assertEqual(awake.update_waits_for(s), f'1 running agent ({task_ref(tid)})')

    def test_an_agent_parked_at_its_prompt_does_not_hold_it(self):
        s, tid, _ = working_store()
        with self.sessions(tid, True):
            self.assertEqual(awake.update_waits_for(s), '')
            self.assertEqual(awake.running(s), '1 running agent')      # ...though it is still live: Quit says it stops it, sleep stays held

    def test_one_session_still_working_keeps_the_task_in_flight(self):
        s, tid, _ = working_store()
        with self.sessions(tid, True, False): self.assertEqual(awake.holding(s), ([tid], []))

    def test_a_workflow_run_holds_it_too(self):
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True), mock.patch.object(workflows, '_STARTING', {7}):
            self.assertEqual(awake.update_waits_for(MemoryStore()), f'1 routine run ({task_ref(7)})')


class TheAssistantLightsUpdateNeverPressesIt(unittest.TestCase):
    def tearDown(self): update._cache.update({'at': 0.0, 'result': None})

    def test_the_line_beside_updates_says_what_is_known_and_that_nothing_installs_by_itself(self):
        update._cache.update({'at': time.time(), 'result': {'current': '0.3.9.34', 'latest': '0.3.9.35', 'newer': True}})
        said = update.status_line()
        self.assertIn('v0.3.9.35 is out (this is v0.3.9.34)', said); self.assertIn('Update to v0.3.9.35 button is lit', said)
        self.assertIn('Nothing installs unless the owner presses it', said)
        self.assertIn('Update waits for 1 running agent once pressed', update.status_line('1 running agent'))
        self.assertNotIn('lit', update.status_line(lit=False))                    # a phone has no button to light
        update._cache.update({'result': {'current': '0.3.9.35', 'latest': '0.3.9.35', 'newer': False}})
        self.assertIn('is the latest release', update.status_line())
        update._cache.update({'result': None})
        self.assertIn('shows on the page as it opens', update.status_line())     # never a fresh call to GitHub from a chat turn

    def test_app_find_for_an_update_carries_that_line(self):
        from taskuary import concierge, words
        update._cache.update({'at': time.time(), 'result': {'current': '0.3.9.34', 'latest': '0.3.9.35', 'newer': True}})
        out = concierge.read_op(MemoryStore(), 'app.find', {'query': 'is there an update'})
        self.assertIn(f"link it as [{words.name('updates')}]({words.href('updates')})", out)
        self.assertIn(f"{words.name('updates')} now: v0.3.9.35 is out", out)


class ClosingHidesToTheTray(unittest.TestCase):
    def test_the_tray_goodbye_says_it_is_still_running_and_where(self):
        s, tid, sessions = working_store()
        with sessions: said = welcome.tray_goodbye(s)
        self.assertIn("I'm still running in the tray", said); self.assertIn(f'the work on {task_ref(tid)} carries on', said)
        self.assertIn('Quit in its menu stops me', said); self.assertNotIn("can't watch", said)
        self.assertNotIn('carries on', welcome.tray_goodbye(MemoryStore()))

    def test_with_a_tray_the_x_hides_the_window_and_stops_nothing(self):
        s, tid, sessions = working_store()
        win, tray = mock.Mock(), mock.Mock()
        shell = {'tray': tray, 'quit': False, 'gone': False}
        with sessions, mock.patch.object(desktop.threading, 'Thread') as th:
            handler = desktop.closing_handler(win, lambda: s, secs=0, shell=shell)
            self.assertFalse(handler())                                          # held: the window stays alive, hidden
            th.call_args.kwargs['target']()
        win.hide.assert_called_once(); win.destroy.assert_not_called(); win.load_html.assert_not_called()
        self.assertIn("still running in the tray", tray.say.call_args.args[0])
        self.assertIsNotNone(welcome.last_here(s))                               # the owner left: the next look counts from here

    def test_quit_from_the_tray_goes_the_way_closing_always_went(self):
        s, tid, sessions = working_store()
        win, tray = mock.Mock(), mock.Mock(); win.get_current_url.return_value = 'http://127.0.0.1:7787/'
        shell = {'tray': tray, 'quit': True, 'gone': False}
        with sessions, mock.patch.object(desktop.threading, 'Thread') as th:
            handler = desktop.closing_handler(win, lambda: s, secs=0, shell=shell)
            keep, anyway = win.expose.call_args.args
            self.assertFalse(handler()); th.call_args.kwargs['target'](*th.call_args.kwargs.get('args', ()))
            self.assertIn('Keep working', win.load_html.call_args.args[0])          # work runs: it asks first
            keep(); self.assertFalse(shell['quit'])                                 # ...Keep working: the next X hides again
        win.hide.assert_not_called(); tray.say.assert_not_called()

    def test_a_server_already_stopped_lets_the_window_go(self):
        self.assertTrue(desktop.closing_handler(mock.Mock(), lambda: MemoryStore(), shell={'tray': mock.Mock(), 'gone': True})())

    def test_off_windows_there_is_no_tray_and_closing_quits(self):
        with mock.patch.object(desktop.sys, 'platform', 'linux'), mock.patch.object(desktop, '_NET', []):
            self.assertIsNone(desktop.tray(mock.Mock(), mock.Mock()))


class QuitInTheBrowser(unittest.TestCase):
    def setUp(self): self.was = workerstate.SERVER[0]
    def tearDown(self): workerstate.SERVER[0] = self.was

    def test_a_server_registers_itself_for_quit(self):
        srv = desktop.Server(desktop.server_config('taskuary.server:app', '127.0.0.1', 1))
        self.assertIs(workerstate.SERVER[0], srv)

    def test_quit_tells_the_server_to_exit_says_what_stopped_and_is_the_owners(self):
        from fastapi.testclient import TestClient
        from taskuary import guard, server
        c, srv = TestClient(server.app), mock.Mock(should_exit=False)
        workerstate.SERVER[0] = srv
        self.assertTrue(guard.denied('POST', '/api/quit')); self.assertFalse(guard.denied('GET', '/api/quit'))
        with mock.patch('taskuary.awake.live', return_value=(1, 0)):
            self.assertEqual(c.get('/api/quit').json(), {'agents': 1, 'workflows': 0, 'running': '1 running agent'})
        with mock.patch.object(server.threading, 'Timer', side_effect=lambda t, f: mock.Mock(start=f)):
            r = c.post('/api/quit', json={})
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json()['quitting']); self.assertTrue(srv.should_exit)
        workerstate.SERVER[0] = None
        self.assertEqual(c.post('/api/quit', json={}).status_code, 409)


if __name__ == '__main__': unittest.main()
