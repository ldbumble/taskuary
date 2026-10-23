"""A FINISHED AGENT IS NEVER "AGENT WORKING" (the owner, 2026-10-23: "this shows agent working but it's not working"). A coding agent
ran `taskuary --reply`, then `taskuary --done`; the wrap closed its pty and left the task open on the reply it wrote. The task page's
Result said "finished its work", while the header pill and the rail row said an agent was working. Every server reading of the task -
the task list's and the page's state (taskstate), the rail's lane (the pile), the agent step's story - must name the SAME state for
each way a run ends: finished with its reply waiting, finished with none, failed, stopped, and a CLI that exited with no hook ever
firing (a transcript, no worker events).

They do: the "agent working" came from a rail built while the agent still worked (the server held that build for minutes), which the
header pill reads too - the desktop now lets a newer read of the task take back a stale agent lane (website railStatus.agentGone)."""
import os, tempfile, unittest, uuid
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import funnel, server, terminal, workerstate
from taskuary.store import SQLiteStore
from taskuary.testing import Factory

# case -> (taskstate's key, the rail's lane, the agent step's story)
WANT = {'finished-reply': ('approve', 'approve', 'finished'), 'finished': ('agentdone', 'yours', 'finished'),
        'failed': ('stopped', 'stopped', 'failed'), 'stopped': ('saved', 'saved', 'left'), 'no-hook-exit': ('stopped', 'stopped', 'left')}


class FinishedAgentOneStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = dict(terminal.SESSIONS)
        cls.home = mock.patch.dict(os.environ, {'TASKUARY_HOME': tempfile.mkdtemp()}); cls.home.start()
        cls.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 'w.db'))     # a file: the rail reads it on its own connection
        f, cls.w = Factory(cls.s), {}
        for case in WANT:
            tid = f.task(title=f'Fix the rail order ({case})', status='in_progress', kind='coding', source='whatsapp')
            mid = f.message(task_id=tid, channel='whatsapp', subject='rail order', body='The rail looks out of order - can you check?',
                            from_name='Erin Blake', from_email='erin@northwind.example')
            f.route(mid, tid, 'create', 'a question addressed to you')
            cls.s.update_task(tid, {'Assignee': 'agent:coding'}, 'walk')
            sid = uuid.uuid4().hex[:12]
            if case != 'no-hook-exit':
                workerstate.record(cls.s, tid, sid, 'working')
                end = {'finished-reply': 'finished'}.get(case, case)
                workerstate.record(cls.s, tid, sid, end, text='Rows sort by arrival; the age column now says the same.' if end != 'stopped' else '')
            if case == 'stopped': cls.s.tag_task(tid, terminal.SAVED, True, 'owner')
            # what the pty filed on its way out (Term.keep) - for the no-hook exit, the only proof it ran
            cls.s.add_transcript(tid, sid, 'Reading the rail.', agent='coding', brain='claude')
            if case == 'finished-reply':
                # the session's own reply (`taskuary --reply`), and the wrap's task left open for it: what self-close leaves behind
                f.review(tid, mid, kind='draft_reply', draft='Fixed - the rail sorts by arrival and the ages agree now.')
                cls.s.update_task(tid, {'Status': 'waiting'}, 'coding')
            elif case == 'finished': cls.s.update_task(tid, {'Status': 'open'}, 'coding')
            cls.w[case] = tid
        from taskuary import processing_startup
        processing_startup.initialize(cls.s)
        with mock.patch.object(server, 'store', cls.s):
            c = TestClient(server.app, base_url='http://127.0.0.1')
            cls.tasks = {t['TaskId']: t for t in c.get('/api/tasks', params={'active': 1}).json()['data']}
            cls.detail = {tid: c.get(f'/api/tasks/{tid}').json() for tid in cls.w.values()}
            cls.pile = {i['tid']: i for i in c.get('/api/funnel/pile', params={'force': 1}).json()['items'] if i.get('tid')}

    @classmethod
    def tearDownClass(cls):
        for k in set(terminal.SESSIONS) - set(cls.before): terminal.SESSIONS.pop(k).close()
        cls.s.cx.close(); cls.home.stop()

    def test_every_reader_names_one_state_for_each_ending(self):
        self.maxDiff = None
        got = {case: (self.tasks[tid]['State'], self.pile.get(tid, {}).get('lane'), (funnel.agent_story(self.s, tid) or {}).get('kind'))
               for case, tid in self.w.items()}
        self.assertEqual(got, WANT)

    def test_the_page_reads_the_list_state_and_no_live_session(self):
        for case, tid in self.w.items():
            d = self.detail[tid]
            self.assertEqual(d.get('state'), self.tasks[tid]['State'], case)
            self.assertFalse((d.get('session') or {}).get('alive'), case)

    def test_no_reader_says_an_agent_is_working(self):
        for case, tid in self.w.items():
            item = self.pile.get(tid, {})
            self.assertNotIn(self.tasks[tid]['State'], ('working', 'blocked'), case)
            self.assertNotIn(item.get('lane'), ('working', 'blocked'), case)
            self.assertNotIn('is working on this', str(item.get('why') or ''), case)


if __name__ == '__main__': unittest.main()
