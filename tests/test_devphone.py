"""The phone into the running coding agents (devphone.py): coding_agents, tell_agent and land exist only in the owner's phone chat with
Developer mode on; tell_agent is the owner's words through the agent's own box; land asks back and lands only on the owner's pick; and
nothing here speaks to the phone unasked."""
import os, tempfile, unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())

from taskuary import agents, concierge, devphone, landing, peers, remote_assistant as ra, terminal as term, toolcatalog, waitroom
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory


def pane(tid, cwd=r'C:\code\ledger'):
    return SimpleNamespace(alive=True, task_id=tid, cwd=cwd, argv=['claude'], quick=False, agent='coding', label='coding', draft='',
                           started='2026-11-06 09:00:00', files=lambda: ['ledger/money.py', 'tests/test_money.py'], sid=f's{tid}')


class DevPhoneTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Ledger rounding', kind='coding')
        self._was = dict(term.SESSIONS); term.SESSIONS.clear(); term.SESSIONS[f's{self.tid}'] = pane(self.tid)
        self.p = [mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'),
                  mock.patch.object(landing, 'head_branch', return_value='fix-rounding'),
                  mock.patch.object(term, 'asking_lines', return_value=['Running the money tests…']),
                  mock.patch.object(waitroom, 'state', return_value=('working', None)),
                  mock.patch.object(ra, 'send', side_effect=AssertionError('the phone was spoken to unasked')),
                  # the suite runs in Developer mode (conftest); these tests are about the switch, so they read the real one
                  mock.patch.object(agents, 'developer_mode', getattr(agents.developer_mode, 'real', agents.developer_mode))]
        for p in self.p: p.start()

    def tearDown(self):
        for p in self.p: p.stop()
        term.SESSIONS.clear(); term.SESSIONS.update(self._was)

    def dev(self, on=True): self.s.set_setting('developer_mode', '1' if on else '0', 'owner')

    def test_the_tools_do_not_exist_with_developer_mode_off(self):
        self.dev(False)
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s):
            self.assertFalse(any(toolcatalog.runs_now(k) for k in devphone.KINDS))
            self.assertEqual(devphone.block(), '')
            self.assertIn('not an operation', toolcatalog.valid('coding_agents', {}))
            self.assertNotIn('coding_agents', concierge._system(self.s))

    def test_nor_on_the_desk_with_it_on(self):
        self.dev()
        with devphone.armed(self.s): self.assertFalse(toolcatalog.runs_now('tell_agent'))
        with concierge.delivering(concierge.PHONE): self.assertFalse(toolcatalog.runs_now('tell_agent'))      # not armed: not a phone turn

    def test_on_the_phone_they_are_told_and_run_in_the_turn(self):
        self.dev()
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s):
            self.assertTrue(all(toolcatalog.runs_now(k) for k in devphone.KINDS))
            self.assertIn('tell_agent', concierge._system(self.s))
            self.assertEqual(toolcatalog.valid('tell_agent', {'task': 'TQ-1'}), 'tell_agent needs text')
            said = concierge.read_op(self.s, 'coding_agents', {})
        self.assertIn(task_ref(self.tid), said)
        for bit in ('northwind/ledger', 'fix-rounding', 'working', '2 files changed', 'Running the money tests'): self.assertIn(bit, said)

    def test_tell_agent_is_the_owners_words_through_the_agents_box(self):
        self.dev()
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s), \
             mock.patch.object(waitroom, 'add', return_value={'delivered': 0}) as add:
            said = concierge.read_op(self.s, 'tell_agent', {'task': task_ref(self.tid), 'text': 'use the main branch for the fixture'})
        add.assert_called_once_with(self.s, self.tid, 'use the main branch for the fixture', 'owner')
        mine = [c for c in self.s.list_comments(self.tid) if c['Actor'] == 'owner']
        self.assertEqual(mine[-1]['Body'], 'use the main branch for the fixture')
        self.assertIn('when it stops', said)

    def test_tell_agent_with_no_agent_running_sends_nothing(self):
        self.dev(); other = Factory(self.s).task(title='Portal', kind='coding')
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s), mock.patch.object(waitroom, 'add') as add:
            self.assertIn('nothing was sent', concierge.read_op(self.s, 'tell_agent', {'task': task_ref(other), 'text': 'x'}))
        add.assert_not_called()

    def test_land_asks_back_and_lands_only_on_the_owners_pick(self):
        self.dev()
        st = {'ask': True, 'line': 'fix-rounding is 2 commits ahead of master: 2 files changed, +9 -3. How should it land?', 'proposal': None,
              'answers': [{'how': k, 'label': v} for k, v in landing.HOW.items()]}
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s), mock.patch.object(landing, 'state', return_value=st), \
             mock.patch.object(landing, 'land', return_value={'ok': True, 'says': 'Merged fix-rounding into master.'}) as land:
            said = concierge.read_op(self.s, 'land', {'task': task_ref(self.tid), 'how': 'merge'})
            land.assert_not_called()                                           # the model naming `how` lands nothing
            self.assertIn('How should it land?', said)
            picks = devphone.take()
            self.assertEqual([a['how'] for _, a in picks], ['rebase', 'merge', 'pr', 'discard'])
            labels, acts = [l for l, _ in picks], dict(picks)
            self.assertEqual(devphone.typed('merge commit', labels, acts)['how'], 'merge')       # typed instead of tapped: the same pick
            self.assertIsNone(devphone.typed('just do whatever', labels, acts))
            self.assertEqual(ra._run_act(self.s, acts[labels[1]], None), 'Merged fix-rounding into master.')
        land.assert_called_once_with(self.s, self.tid, 'merge', 'owner')

    def test_a_pick_left_from_developer_mode_on_does_nothing_once_it_is_off(self):
        self.dev(False)
        with concierge.delivering(concierge.PHONE), devphone.armed(self.s), mock.patch.object(landing, 'land') as land:
            self.assertIn('Developer mode is off', ra._run_act(self.s, {'t': 'land', 'tid': self.tid, 'how': 'rebase'}, None))
        land.assert_not_called()

    def test_notes_and_conflicts_never_ring_the_phone(self):
        other = Factory(self.s).task(title='Ledger export', kind='coding'); term.SESSIONS[f's{other}'] = pane(other)
        with mock.patch('taskuary.origin.of_task', return_value=('owner', '')):
            peers.send(self.s, self.tid, task_ref(other), 'money.py is mine for ten minutes')
        landing._conflict(self.s, self.tid, {'branch': 'fix-rounding', 'base': 'master'}, 'merge', ['ledger/money.py'])
