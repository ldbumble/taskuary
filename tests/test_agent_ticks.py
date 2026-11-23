"""An agent ticks the to-dos it finishes (the owner, 2026-10-22): `taskuary --tick <id>` / `--untick <id>` from its own session.
Only the box moves, only on its own task, and never an email box or a goal's step - those tick themselves."""
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import agents, config, general, selfclose, server, terminal
from taskuary.store import MemoryStore, agent_tick


def _task(s):
    tid = s.create_task({'Title': 'Renew the Trainly licence', 'Kind': 'general', 'Status': 'open'}, 't')
    s.set_task_checklist(tid, ['Check the seat count', 'Ask Gail Moreno for the PO'], 't')
    s.add_checklist_items(tid, [{'text': 'Confirm the renewal with the vendor', 'out': {'to': 'sales@vendor.example'}}], 't')
    return tid, {i['text']: i['id'] for i in s.task_checklist(tid)}


class TickTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid, self.ids = _task(self.s)

    def test_the_agents_checklist_carries_the_ids_it_may_tick_and_the_owners_does_not(self):
        md = self.s.checklist_markdown(self.tid, ids=True)
        self.assertIn(f"- [ ] Check the seat count [{self.ids['Check the seat count']}]", md)
        self.assertNotIn(f"[{self.ids['Confirm the renewal with the vendor']}]", md)        # the email box: its --slot line says how
        self.assertNotIn(self.ids['Check the seat count'], self.s.checklist_markdown(self.tid))   # the Assistant's and the page's copy


    def _post(self, item, done=True):
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, '_own_task_only', return_value=None):
            return TestClient(server.app).post('/api/agent/tick', json={'task_id': self.tid, 'item': item, 'done': done})

    def test_tick_and_untick_move_only_the_box(self):
        i = self.ids['Ask Gail Moreno for the PO']
        r = self._post(i)
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json()['done'])
        box = {x['id']: x for x in self.s.task_checklist(self.tid)}[i]
        self.assertTrue(box['done']); self.assertEqual(box['text'], 'Ask Gail Moreno for the PO')
        self._post(i, done=False)
        self.assertFalse({x['id']: x for x in self.s.task_checklist(self.tid)}[i]['done'])

    def test_an_unknown_id_and_an_email_box_are_refused(self):
        self.assertEqual(self._post('nope1234').status_code, 404)
        self.assertEqual(self._post(self.ids['Confirm the renewal with the vendor']).status_code, 422)
        self.assertFalse(any(x['done'] for x in self.s.task_checklist(self.tid)))


    def test_the_checklist_heading_says_only_the_tick(self):
        head = lambda cli: next(l for l in terminal.seed_text(self.s, self.tid, cli=cli).splitlines() if 'CHECKLIST' in l)
        for cli in ('claude', 'codex', 'gemini', ''): self.assertIn(terminal.TICK_HEAD, head(cli)); self.assertNotIn('subagent', head(cli))
        self.assertFalse(hasattr(terminal, 'SUBAGENT_HEAD'))

    def test_the_one_road_refuses_what_the_door_refuses(self):
        self.assertEqual(agent_tick(self.s, self.tid, 'nope1234')[1][0], 404)
        # ...and an id that is gone is the agent's to drop, never the owner's to hear of: "I could not tick the checklist item: Taskuary
        # does not recognise the to-do id" stood in his chat (the real CLI, 2026-11-15) - a step of an earlier turn's summary, rewritten since
        why = agent_tick(self.s, self.tid, 'nope1234')[1][1]
        self.assertIn('needs no tick', why); self.assertIn('do not mention this to the owner', why)
        self.assertEqual(agent_tick(self.s, self.tid, self.ids['Confirm the renewal with the vendor'])[1][0], 422)
        box, err = agent_tick(self.s, self.tid, f" {self.ids['Check the seat count']} ")
        self.assertIsNone(err); self.assertTrue({x['id']: x for x in self.s.task_checklist(self.tid)}[box['id']]['done'])

    def test_a_session_ticks_only_its_own_task(self):
        agent = {'X-Taskuary-Token': config.load()['server']['agent_token']}
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).post('/api/agent/tick', json={'task_id': self.tid, 'item': self.ids['Check the seat count']}, headers=agent)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(any(x['done'] for x in self.s.task_checklist(self.tid)))


class AChatWithNoShellTicksByAMarkTests(unittest.TestCase):
    """A general chat the owner set to look things up only has no shell for `taskuary --tick`: it is told the mark instead, and
    the mark takes the command's own road - the same refusals, the line out of what the owner reads."""
    def setUp(self):
        self.s = MemoryStore(); self.tid, self.ids = _task(self.s)
        real, conns = config.load, {'claude': {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}}
        for p in (mock.patch.object(config, 'load', side_effect=lambda: {**real(), 'cli_connections': conns}),
                  mock.patch.object(agents, 'connection_brains', getattr(agents.connection_brains, 'real', agents.connection_brains))):
            p.start(); self.addCleanup(p.stop)

    def _turn(self, reply, hands):
        self.s.set_setting('general_agent_hands', hands, 't'); seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kw):
            args = list(profile.get('args') or [])
            flag = next((f for f in ('--append-system-prompt-file', '--system-prompt-file') if f in args), None)
            seen['prompt'] = (open(args[args.index(flag) + 1], encoding='utf-8').read() if flag else '') + '\n\n' + prompt
            return reply, None, None
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            general.start_session(self.s, self.tid, pick='cli:claude').send_prompt('Go ahead', pick='cli:claude')
        return seen['prompt']

    def test_only_a_chat_with_no_shell_is_told_the_mark(self):
        self.assertIn(selfclose.TICK_MARKER, self._turn('ok', 'look'))
        self.assertNotIn(selfclose.TICK_MARKER, self._turn('ok', 'cli'))

    def test_a_chat_is_told_one_road_for_an_email_by_the_tools_it_has(self):
        """The agent walk, 2026-11-10: one agent was handed the propose_email tool, the [[TASKUARY-DRAFT]] block and `taskuary --slot ...
        --draft` for the same email, and wrote it as a second email beside the line that asked for it. A session with Taskuary's tools
        hears the tool, one without hears the block - and both read the id of the line the email fills."""
        vendor = self.ids['Confirm the renewal with the vendor']
        self.s.add_message({'TaskId': self.tid, 'Channel': 'email', 'Subject': 'Trainly renewal', 'FromName': 'Gail Moreno',
                            'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you renew Trainly this week?', 'Status': 'routed'})
        with mock.patch('taskuary.origin.of_task', return_value=('trusted', 'a colleague')): tooled, plain = self._turn('ok', 'cli'), self._turn('ok', 'look')
        for said in (tooled, plain):
            self.assertIn(f'-> email to sales@vendor.example, slot {vendor} - to draft', said)
            for shell in ('taskuary --slot', 'taskuary --draft', 'taskuary --reply "'): self.assertNotIn(shell, said)
        for mark in (selfclose.DRAFT_OPEN, selfclose.REPLY_OPEN): self.assertNotIn(mark, tooled)
        self.assertIn(selfclose.DRAFT_LINE, plain); self.assertIn(selfclose.REPLY_LINE, plain)
        for tool in ('propose_email', 'propose_reply'): self.assertNotIn(tool, plain)

    def test_the_mark_ticks_the_box_and_leaves_the_reply(self):
        seats, vendor = self.ids['Check the seat count'], self.ids['Confirm the renewal with the vendor']
        self._turn(f'Twelve seats are in use.\n[[TASKUARY-TICK: {seats}]]\n[[ taskuary_tick {vendor} ]]\n[[TASKUARY-TICK: nope1234]]', 'look')
        boxes = {x['id']: x['done'] for x in self.s.task_checklist(self.tid)}
        self.assertTrue(boxes[seats]); self.assertFalse(boxes[vendor])               # an email box ticks when its email goes
        self.assertFalse(boxes[self.ids['Ask Gail Moreno for the PO']])
        said = [c['Body'] for c in self.s.list_comments(self.tid) if 'Twelve seats' in (c['Body'] or '')]
        self.assertTrue(said); self.assertFalse(any('TASKUARY' in b.upper() for b in said))

    def test_tick_lines_come_out_whole_and_in_order(self):
        self.assertEqual(selfclose.tick_markers('Done.\n[[TASKUARY-TICK: ab12cd34]]\n  [[taskuary tick:ef56]]\n[[TASKUARY-TICK: ab12cd34]]'),
                         ('Done.', ['ab12cd34', 'ef56']))
        self.assertEqual(selfclose.tick_markers('Plain [[link]] text'), ('Plain [[link]] text', []))


class NeverDoneOverAFailedAct(unittest.TestCase):
    """HIPAA walk 6: "Summarise the lease, then set up a meeting with Ray next week" was ticked in the same second set_up_meeting answered
    "No calendar is connected" - the two calls ran side by side - and the phone read "To do - 1 of 1 done". An act that failed in the turn
    undoes the tick made beside it, and refuses one after it."""
    def test_a_tick_beside_a_failed_act_is_undone_and_one_after_it_refused(self):
        import json, time
        from taskuary import agenttools, conversation
        s = MemoryStore(); tid, ids = _task(s); item = ids['Check the seat count']
        conversation.hear(s, tid, turn=True)                                            # ...the turn begins
        doors = {'tick': lambda t, i, done: {'ok': bool(agent_tick(s, t, i, done)[0]), 'item': i, 'done': done},
                 'meeting': lambda t, a: {'ok': False, 'says': 'No calendar is connected - connect one.'}}
        agenttools.call(s, tid, 'tick', {'item': item}, doors)
        self.assertTrue(next(i for i in s.task_checklist(tid) if i['id'] == item)['done'])
        agenttools.call(s, tid, 'set_up_meeting', {'with': ['ray@northwind.example'], 'title': 'Lease review'}, doors)
        self.assertFalse(next(i for i in s.task_checklist(tid) if i['id'] == item)['done'], 'the tick beside the failed act is undone')
        with self.assertRaises(ValueError) as no: agenttools.call(s, tid, 'tick', {'item': item}, doors)
        self.assertIn('set_up_meeting failed in this turn', str(no.exception))
        time.sleep(0.01); conversation.hear(s, tid, turn=True)                         # ...a new turn: the failure is its past
        agenttools.call(s, tid, 'tick', {'item': item}, doors)
        self.assertTrue(next(i for i in s.task_checklist(tid) if i['id'] == item)['done'])


if __name__ == '__main__':
    unittest.main()
