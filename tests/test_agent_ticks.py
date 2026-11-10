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

    def test_both_prompts_carry_the_ids_and_the_rule(self):
        system, user = general._prompt(self.s, self.tid)
        self.assertIn(f"[{self.ids['Check the seat count']}]", user); self.assertIn('taskuary --tick <id>', system)
        seed = terminal.seed_text(self.s, self.tid, repo=None, cwd=None)
        self.assertIn(f"[{self.ids['Check the seat count']}]", seed); self.assertIn('taskuary --tick <id>', seed)

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

    def test_the_prompts_say_to_tick_beside_the_checklist_itself(self):
        # 2026-11-02: told once deep in the rules, a CLI session ticked about a quarter of its boxes and a general chat one in thirty
        head = lambda text: next(l for l in text.splitlines() if 'CHECKLIST' in l)
        self.assertIn(terminal.TICK_HEAD, head(general._prompt(self.s, self.tid)[1]))
        seed = head(terminal.seed_text(self.s, self.tid, repo=None, cwd=None))
        self.assertIn(terminal.TICK_HEAD, seed); self.assertIn('taskuary --tick <id>', seed)
        for i in self.ids.values(): self.s.tick_checklist_item(self.tid, i, True, 't')      # nothing left to tick: nothing said
        self.assertNotIn(terminal.TICK_HEAD, head(general._prompt(self.s, self.tid)[1]))

    def test_the_checklist_heading_says_only_the_tick_and_the_subagent_rule_rides_in_coding_md(self):
        # 2026-11-02: the subagent rule began as a line of code on this heading; it is CODING.md's now, where the owner can reword it
        head = lambda cli: next(l for l in terminal.seed_text(self.s, self.tid, cli=cli).splitlines() if 'CHECKLIST' in l)
        for cli in ('claude', 'codex', 'gemini', ''): self.assertIn(terminal.TICK_HEAD, head(cli)); self.assertNotIn('subagent', head(cli))
        self.assertFalse(hasattr(terminal, 'SUBAGENT_HEAD'))
        self.assertIn('hand each to its own subagent in parallel', terminal.rules_text(self.s, profile='coding'))

    def test_the_one_road_refuses_what_the_door_refuses(self):
        self.assertEqual(agent_tick(self.s, self.tid, 'nope1234')[1][0], 404)
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
        self.assertIn('propose_reply / propose_email', tooled); self.assertIn(selfclose.DRAFT_TOOL_LINE, tooled)
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


if __name__ == '__main__':
    unittest.main()
