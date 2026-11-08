"""Every line the owner sends is kept the moment it is sent (the owner, 2026-11-07: "a word typed is a word kept").

The audit's stress run: a first turn ran fourteen minutes, and the five lines typed in its first seconds lived only in the server's memory and
the page's own state - a page opened mid-turn showed none of them, a restart would have lost them, and when they finally drew they were stamped
with the time the next turn took them. And a line held behind a turn that failed came back "reload the page and ask again", red in the box,
where the first line's road started again quietly. One road now: kept at once with its typed time, shown on every screen as waiting for the
agent, taken together when the turn ends, and started again on a fresh session where the old one ended under it.
"""
import json, threading, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server
from taskuary.store import MemoryStore


class Brain:
    "The model: answers after `delay`, fails the turns named in `fail`, keeps what each turn was handed."
    def __init__(self, delay=0.0, fail=()): self.delay, self.fail, self.calls = delay, set(fail), []
    def __call__(self, system, user, **k):
        self.calls.append(user); n = len(self.calls); time.sleep(self.delay)
        if n in self.fail: raise RuntimeError('the model gave up')
        return f'Answer {n}.'


class OwnerLineIsKept(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Compare expense tools for Northwind', 'Kind': 'general'}, 'o')
        self.brain = Brain(delay=1.0)
        for p in [mock.patch.object(general.llm_mod, 'build_llm', side_effect=lambda *a, **k: self.brain),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch('taskuary.hooks.judge_ended', lambda *a, **k: None),
                  mock.patch.object(server, 'store', self.s),
                  mock.patch.object(server, '_refresh_for_turn', return_value=({}, ''))]:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.end)

    def end(self):
        if (g := general.session_for(self.tid)): g.close(learn=False, report=False)
        general.drop_session(self.tid); general.IDLED.pop(self.tid, None)

    def said(self): return [(c['ActorType'], c['Body']) for c in general.chat_rows(self.s, self.tid)]

    def test_a_line_typed_mid_turn_is_kept_at_once_with_its_time_and_taken_with_the_next_turn(self):
        first = threading.Thread(target=lambda: general.say_line(self.s, self.tid, 'Compare three tools.')); first.start()
        time.sleep(0.3)
        held = [threading.Thread(target=lambda w=w: general.say_line(self.s, self.tid, w)) for w in ('Make it cheapest first.', 'And add Trainly.')]
        for t in held: t.start(); time.sleep(0.1)
        time.sleep(0.1)
        kept = general.waiting_lines(self.s, self.tid)
        self.assertEqual([w['text'] for w in kept], ['Make it cheapest first.', 'And add Trainly.'])      # kept the moment they were sent...
        self.assertEqual([w['text'] for w in server._assistant_payload(self.tid)['waiting']], [w['text'] for w in kept])   # ...on every screen
        self.assertNotIn('And add Trainly.', [b for _, b in self.said()])                                # ...waiting, not yet a turn of its own
        typed = {w['text']: w['at'] for w in kept}
        for t in [first, *held]: t.join(15)
        self.assertEqual(self.said(), [(general.USER_TYPE, 'Compare three tools.'), (general.ASSISTANT_TYPE, 'Answer 1.'),
                                       (general.USER_TYPE, 'Make it cheapest first.'), (general.USER_TYPE, 'And add Trainly.'),
                                       (general.ASSISTANT_TYPE, 'Answer 2.')])                         # one turn took both, after the first
        rows = {c['Body']: c['CreatedAt'] for c in self.s.list_comments(self.tid)}
        self.assertEqual({w: rows[w] for w in typed}, typed)                                          # ...each at the time it was typed
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])

    def test_a_line_kept_when_the_server_restarted_goes_to_the_agent(self):
        general.wait_line(self.s, self.tid, 'And copy Erin Blake.')                    # typed mid-turn; then the process went away
        self.brain.delay = 0
        self.assertEqual(server.deliver_waiting(), [self.tid])
        end = time.time() + 10
        while (general.waiting_lines(self.s, self.tid) or general.ASSISTANT_TYPE not in dict(self.said())) and time.time() < end: time.sleep(0.05)
        self.assertEqual(self.said()[-2:], [(general.USER_TYPE, 'And copy Erin Blake.'), (general.ASSISTANT_TYPE, 'Answer 1.')])
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])

    def test_a_held_line_behind_a_turn_that_failed_starts_the_agent_again_quietly(self):
        "Bug 10: the held road had no restart - the line came back 'reload the page and ask again'."
        self.brain.fail = {1}
        c = TestClient(server.app)
        first = threading.Thread(target=lambda: c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.'})); first.start()
        time.sleep(0.3)
        r = c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Cheapest first, please.'})
        first.join(15)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['reply'], 'Answer 2.')                                  # answered on a fresh session...
        self.assertEqual([b for t, b in self.said() if t == general.USER_TYPE].count('Cheapest first, please.'), 1)    # ...the line said once
        self.assertNotIn('reload the page', general.ENDED)

    def test_a_cancelled_line_is_taken_back(self):
        ses = general.start_session(self.s, self.tid)
        threading.Thread(target=lambda: ses.send_prompt('Compare three tools.'), daemon=True).start(); time.sleep(0.2)
        cancel = threading.Event(); threading.Timer(0.2, cancel.set).start()
        with self.assertRaises(RuntimeError): ses.send_prompt('Never mind.', cancel=cancel)
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])


if __name__ == '__main__':
    unittest.main()
