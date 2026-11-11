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
        general.drop_session(self.tid); general.IDLED.pop(self.tid, None); general.answered(self.tid, every=True)

    def said(self): return [(c['ActorType'], c['Body']) for c in general.chat_rows(self.s, self.tid)]

    def test_a_line_typed_mid_turn_is_kept_at_once_with_its_time_and_taken_with_the_next_turn(self):
        # waits for the state, never a fixed sleep: CI's macOS box had not started the first turn 0.3s in, so nothing was held (2026-11-08)
        def until(ok, secs=10):
            end = time.time() + secs
            while not ok() and time.time() < end: time.sleep(0.02)
        first = threading.Thread(target=lambda: general.take_line(self.s, self.tid, 'Compare three tools.')); first.start()
        until(lambda: getattr(general.session_for(self.tid), 'busy', False))
        held = [threading.Thread(target=lambda w=w: general.take_line(self.s, self.tid, w)) for w in ('Make it cheapest first.', 'And add Trainly.')]
        for i, t in enumerate(held): t.start(); until(lambda n=i + 1: len(general.waiting_lines(self.s, self.tid)) >= n)
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

    def test_a_line_kept_when_the_server_restarted_goes_back_into_the_box_never_to_the_agent(self):
        general.wait_line(self.s, self.tid, 'And copy Erin Blake.')                    # typed mid-turn; then the process went away
        self.assertEqual(server.lines_to_box(), [self.tid])
        time.sleep(0.3)
        self.assertEqual(self.said(), [])                                               # nothing started an agent for it
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])
        self.assertEqual(server._assistant_payload(self.tid)['box'], 'And copy Erin Blake.')   # ...it is back in the owner's box
        self.brain.delay = 0
        general.take_line(self.s, self.tid, 'And copy Erin Blake, please.')               # they send it, changed
        self.assertEqual(general.box_text(self.s, self.tid), '')                          # ...offered once, never twice
        self.assertEqual([b for t, b in self.said() if t == general.USER_TYPE], ['And copy Erin Blake, please.'])

    def test_a_held_line_behind_a_turn_that_failed_starts_the_agent_again_quietly(self):
        "Bug 10: the held road had no restart - the line came back 'reload the page and ask again'."
        self.brain.fail = {1}
        c = TestClient(server.app)
        first = threading.Thread(target=lambda: c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.'})); first.start()
        time.sleep(0.3)
        r = c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Cheapest first, please.'})
        first.join(15)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get('kept'))                                             # a line sent while a turn works is kept and answered at once...
        end = time.time() + 15
        while (general.ASSISTANT_TYPE, 'Answer 2.') not in self.said() and time.time() < end: time.sleep(0.05)
        self.assertIn((general.ASSISTANT_TYPE, 'Answer 2.'), self.said())                 # ...and answered on a fresh session
        self.assertEqual([b for t, b in self.said() if t == general.USER_TYPE].count('Cheapest first, please.'), 1)    # ...the line said once
        self.assertNotIn('reload the page', general.ENDED)

    def test_a_cancelled_line_is_taken_back(self):
        ses = general.start_session(self.s, self.tid)
        threading.Thread(target=lambda: ses.send_prompt('Compare three tools.'), daemon=True).start(); time.sleep(0.2)
        cancel = threading.Event(); threading.Timer(0.2, cancel.set).start()
        with self.assertRaises(RuntimeError): ses.send_prompt('Never mind.', cancel=cancel)
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])

    def test_a_line_keeps_the_name_its_page_gave_it_while_it_waits_and_as_the_turn_it_becomes(self):
        """THE SPINE AUDIT, 2026-11-09: the page that sent a line draws it at once and has to know when the conversation has it. It knew by
        the line's words and by counting the owner's lines, so a line from another window retired one the server did not have yet, and "ok"
        sent twice stood once. The page names its line; the name is kept on the waiting row and on the turn it becomes, and comes back on both."""
        def until(ok, secs=10):
            end = time.time() + secs
            while not ok() and time.time() < end: time.sleep(0.02)
        say = lambda w, name: threading.Thread(target=lambda: general.take_line(self.s, self.tid, w, line_id=name))
        first = say('Compare three tools.', 'held-1'); first.start()
        until(lambda: getattr(general.session_for(self.tid), 'busy', False))
        held = [say('ok', 'held-2'), say('ok', None), say('ok', 'held-3')]
        for i, t in enumerate(held): t.start(); until(lambda n=i + 1: len(general.waiting_lines(self.s, self.tid)) >= n)
        # ...and a line the page gave no name gets one here (general.new_line_id): the ledger says by it that the agent heard it
        waits = [(w['text'], w.get('line')) for w in server._assistant_payload(self.tid)['waiting']]
        self.assertEqual([(w, n) for w, n in waits if n in ('held-2', 'held-3')], [('ok', 'held-2'), ('ok', 'held-3')])
        made = waits[1][1]; self.assertTrue(made and made.startswith('s'))
        for t in [first, *held]: t.join(15)
        mine = [(m['content'][0]['text'], m.get('line')) for m in server._assistant_payload(self.tid)['messages'] if m['role'] == 'user']
        self.assertEqual(mine, [('Compare three tools.', 'held-1'), ('ok', 'held-2'), ('ok', made), ('ok', 'held-3')])

    def test_the_chats_door_takes_the_name_and_a_long_one_is_cut(self):
        self.brain.delay = 0
        out = TestClient(server.app).post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.', 'line_id': 'h' * 200}).json()
        self.assertEqual([m.get('line') for m in out['messages'] if m['role'] == 'user'], ['h' * 80])


if __name__ == '__main__':
    unittest.main()
