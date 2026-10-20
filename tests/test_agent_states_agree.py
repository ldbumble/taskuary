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
        cls.s.cx.close()

    def test_every_surface_says_the_same_state(self):
        self.maxDiff = None; got = {}
        for kind in ('coding', 'general'):
            for st, want in AGREE.items():
                tid = self.w[f'{kind}-{st}']
                got[f'{kind}-{st}'] = (self.tasks[tid]['State'], self.pile.get(tid, {}).get('lane'))
        self.assertEqual(got, {f'{k}-{st}': want for k in ('coding', 'general') for st, want in AGREE.items()})

    def test_an_asking_agent_carries_its_question_and_answer_it_everywhere(self):
        for kind in ('coding', 'general'):
            tid = self.w[f'{kind}-asking']
            sess, item = self.live[tid], self.pile[tid]
            self.assertEqual((sess['waiting'], sess['state']), (True, 'asking'), kind)
            self.assertIn('inter-company rows', sess['request']['text'])
            self.assertEqual(item['request_kind'], 'input_needed')
            self.assertEqual(concierge.chips_for(self.s, item)[0]['verb'], 'answer_agent')
            self.assertEqual(workerstate.status(self.s, tid)['state'], 'input_needed')

    def test_a_stopped_run_offers_no_stop(self):
        """Nothing is live on a stopped run: no Stop and save on its rail row, and its own word says it was stopped (the task page reads
        runEnded to leave the button off - taskLifecycle.endedByStop)."""
        for kind in ('coding', 'general'):
            tid = self.w[f'{kind}-stopped-saved']
            self.assertNotIn('stop_agent', [c['verb'] for c in concierge.chips_for(self.s, self.pile[tid])])
            self.assertEqual(workerstate.ended(self.s, tid), 'stopped')


if __name__ == '__main__': unittest.main()
