"""ONE AGENT STATE, EVERY SURFACE (G7, 2026-10-20). The faults world (taskuary/faults.world) holds an agent of each kind working,
asking, finished, failed and stopped with its conversation saved; for each, the task list and the Board (taskstate), the rail
(funnel.pile), the session row the header reads (terminal.live_sessions) and the row's verbs (concierge.chips_for) must say the same
thing. They did not: the finished, failed and stopped ones read "on you" everywhere but the worker, and a replay asking carried no
question to answer."""
import os, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import advisor, concierge, demo, faults, server, terminal, workerstate
from taskuary.store import SQLiteStore

# world state -> (the task list's and Board's key, the rail's lane)
AGREE = {'working': ('working', 'working'), 'asking': ('blocked', 'blocked'), 'finished': ('agentdone', 'yours'),
         'failed': ('stopped', 'stopped'), 'stopped-saved': ('stopped', 'stopped')}


class AgentStatesAgreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = dict(terminal.SESSIONS)
        cls.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 'world.db'))   # a file: the rail reads it on its own connection
        with mock.patch.dict(os.environ, {faults.ENV: '1', 'TASKUARY_HOME': tempfile.mkdtemp()}), mock.patch.object(advisor, 'notice'):
            demo.seed(cls.s); cls.w = faults.world(cls.s)
        from taskuary import processing_startup
        processing_startup.initialize(cls.s)             # the rail reads the processing inventory, as the app's startup turns it on
        import time; time.sleep(0.6)                     # the asking replays finish typing and park
        # what the pages read: the session rows (the header), the task list (its chip and the Board's column), the rail
        with mock.patch.object(server, 'store', cls.s):
            c = TestClient(server.app, base_url='http://127.0.0.1')
            cls.live = {x['taskId']: x for x in c.get('/api/terminals', params={'details': False}).json()['data']}
            cls.tasks = {t['TaskId']: t for t in c.get('/api/tasks', params={'active': 1}).json()['data']}
            cls.pile = {i['tid']: i for i in c.get('/api/funnel/pile', params={'force': 1}).json()['items'] if i.get('tid')}

    @classmethod
    def tearDownClass(cls):
        from taskuary import assistant
        assistant._AGENDA.clear()
        for k in set(terminal.SESSIONS) - set(cls.before): terminal.SESSIONS.pop(k).close()
        cls.s.close()

    def test_every_surface_says_the_same_state(self):
        self.maxDiff = None; got = {}
        for kind in ('coding', 'general'):
            for st, want in AGREE.items():
                tid = self.w[f'{kind}-{st}']
                got[f'{kind}-{st}'] = (self.tasks[tid]['State'], self.pile.get(tid, {}).get('lane'))
        self.assertEqual(got, {f'{k}-{st}': want for k in ('coding', 'general') for st, want in AGREE.items()})

    def test_every_agent_is_on_the_board_in_its_column(self):
        """The Board draws agent work only (HadAgent): a general agent that finished or failed leaves only its worker events, and
        was off the Board while its state named a column (G7)."""
        from taskuary import taskstate
        for kind in ('coding', 'general'):
            for st in AGREE:
                t = self.tasks[self.w[f'{kind}-{st}']]
                self.assertTrue(t['HadAgent'], f'{kind}-{st}')
                self.assertIsNotNone(taskstate.column(t['State']), f'{kind}-{st}')

    def test_an_asking_agent_carries_its_question_everywhere(self):
        for kind in ('coding', 'general'):
            tid = self.w[f'{kind}-asking']
            sess, item = self.live[tid], self.pile[tid]
            self.assertEqual((sess['waiting'], sess['state']), (True, 'asking'), kind)
            self.assertIn('inter-company rows', sess['request']['text'])
            self.assertEqual(item['request_kind'], 'input_needed')
            # ...answered in its own pane: its row leads with Stop and save, and has no Answer it (owner-approved, 2026-10-20)
            self.assertEqual(concierge.chips_for(self.s, item)[0]['verb'], 'stop_agent')
            self.assertNotIn('answer_agent', [c['verb'] for c in concierge.row_buttons(self.s, item)])
            self.assertEqual(workerstate.status(self.s, tid)['state'], 'input_needed')

    def test_the_agent_step_tells_how_the_run_ended(self):
        """The task page's agent step (funnel.agent_story): a finished run read "not started" over "finished its work" (G7)."""
        from taskuary import funnel
        story = lambda k: (funnel.agent_story(self.s, self.w[k]) or {}).get('kind')
        # ...and a run that failed reads failed, never "stopped" over its own reason (owner-approved, 2026-10-21)
        self.assertEqual((story('coding-finished'), story('coding-failed'), story('coding-stopped-saved')), ('finished', 'failed', 'left'))

    def test_a_stopped_run_offers_no_stop(self):
        """Nothing is live on a stopped run: no Stop and save on its rail row, and its own word says it was stopped (the task page reads
        no session alive, and offers Stop and save only on a live one)."""
        for kind in ('coding', 'general'):
            tid = self.w[f'{kind}-stopped-saved']
            self.assertNotIn('stop_agent', [c['verb'] for c in concierge.chips_for(self.s, self.pile[tid])])
            self.assertEqual(workerstate.ended(self.s, tid), 'stopped')

    def test_an_ended_session_offers_no_stop_only_a_live_one_does(self):
        """Failed, finished or cut off by a restart, a session that has ENDED has nothing to stop (owner-approved, 2026-10-20): its
        chips, its row's buttons (what the Advisor may light) and a pick of it carry no Stop and save. A working one still does."""
        verbs = lambda item, f: [c['verb'] for c in f(self.s, item)]
        for kind in ('coding', 'general'):
            for st in ('finished', 'failed', 'stopped-saved'):
                item = self.pile[self.w[f'{kind}-{st}']]
                self.assertNotIn('stop_agent', verbs(item, concierge.chips_for), f'{kind}-{st}')
                self.assertNotIn('stop_agent', verbs(item, concierge.row_buttons), f'{kind}-{st}')
                if item.get('lane') == 'stopped': self.assertIn('nothing to stop', concierge.cannot(item, 'stop_agent', self.s), f'{kind}-{st}')
            working = self.pile[self.w[f'{kind}-working']]
            self.assertEqual(concierge.cannot(working, 'stop_agent', self.s), '', f'{kind}-working')
            self.assertIn('stop_agent', verbs(working, concierge.row_buttons), f'{kind}-working')


if __name__ == '__main__': unittest.main()
