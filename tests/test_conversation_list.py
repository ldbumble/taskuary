"""A TASK'S CHAT IS ONE LIST THE SERVER OWNS (taskuary/conversation.py) - the corpus of its rules, on a chat agent with a stand-in brain:
the heard rule (an input stands where the agent heard it; what waits is apart, by the box), one hand-over for a flood (every input once, in
the ledger and in what the agent is told), a turn's cards last, a live action kept right above the box, and the agent's markers cleaned.
Invented people only."""
import threading, time, unittest
from unittest import mock

from taskuary import conversation, general, selfclose
from taskuary.store import MemoryStore


class Brain:
    "The model: answers `Answer n.` after `delay` (or `said[n]`), and keeps what each turn was handed - system and user."
    def __init__(self, delay=0.0): self.delay, self.calls, self.said = delay, [], {}
    def __call__(self, system, user, **k):
        self.calls.append(f'{system}\n{user}'); n = len(self.calls); time.sleep(self.delay)
        return self.said.get(n, f'Answer {n}.')


def until(ok, secs=15):
    end = time.time() + secs
    while not ok() and time.time() < end: time.sleep(0.02)
    return ok()


class TheList(unittest.TestCase):
    def setUp(self):
        self.s = s = MemoryStore()
        s.set_setting('owner_name', 'Alex Doyle', 'owner'); s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        self.tid = s.create_task({'Title': 'Offsite venues', 'Kind': 'general', 'Status': 'open'}, 'o')
        self.mail('Can you suggest two venues for the March offsite?')
        self.brain = Brain()
        for p in [mock.patch.object(general.llm_mod, 'build_llm', side_effect=lambda *a, **k: self.brain),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch('taskuary.hooks.judge_ended', lambda *a, **k: None)]:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.end)

    def end(self):
        if (g := general.session_for(self.tid)): g.close(learn=False, report=False)
        general.drop_session(self.tid); general.IDLED.pop(self.tid, None); general.answered(self.tid, every=True)

    def mail(self, body, own=False):
        n = len(self.s.list_messages(self.tid))
        return self.s.add_message({'TaskId': self.tid, 'ExternalId': f'm{n}', 'ConversationId': 'conv-1', 'Channel': 'email', 'Subject': 'Offsite venue',
                                   'BodyText': body, **({'FromName': 'You', 'Status': 'context', 'Direction': 'out'} if own else
                                                        {'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'Status': 'routed'})})

    def say(self, w, name=None, wait=True): return general.take_line(self.s, self.tid, w, line_id=name, wait=wait)
    def list(self): return conversation.items(self.s, self.tid)
    def kinds(self, got=None): return [(x['kind'], x.get('state', '')) for x in (got or self.list())['items']]
    def rest(self): self.assertTrue(until(lambda: not self.list()['working'] and not general.waiting_lines(self.s, self.tid)), self.kinds())

    def test_a_line_at_rest_is_heard_at_the_press_with_its_turn_under_it_and_keeps_its_names(self):
        self.brain.delay = 0.6
        self.say('Suggest two.', 'l-one', wait=False)
        got = self.list()
        self.assertEqual(self.kinds(got)[-2:], [('line', ''), ('turn', got['items'][-1]['state'])])
        self.assertIn(got['items'][-1]['state'], ('starting', 'working')); self.assertEqual(got['pending'], [])
        self.assertEqual(got['items'][-2]['id'], 'l-one'); live = got['items'][-1]['id']
        self.rest()
        got = self.list()
        self.assertEqual([(x['id'], x.get('state')) for x in got['items'][-2:]], [('l-one', None), (live, 'done')])      # the turn that ends redraws in place
        self.assertEqual(got['items'][-1]['text'], 'Answer 1.')

    def test_a_line_sent_mid_turn_waits_by_the_box_and_enters_once_when_the_next_turn_takes_it(self):
        self.brain.delay = 0.8
        self.say('Suggest two.', 'l-one', wait=False)
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        self.say('Near a station.', 'l-two', wait=False); self.say('Under 3000.', 'l-three', wait=False)
        got = self.list()
        self.assertEqual([x['id'] for x in got['pending']], ['l-two', 'l-three'])                 # accepted, not yet heard: by the box...
        self.assertFalse({'l-two', 'l-three'} & {x['id'] for x in got['items']})                 # ...never in the conversation too
        before = [x['id'] for x in got['items'] if x['kind'] != 'turn']
        self.rest()
        got = self.list(); ids = [x['id'] for x in got['items']]
        self.assertEqual([i for i in ids if not i.startswith('t:')], [*before, 'l-two', 'l-three'])      # nothing entered above what was drawn
        self.assertEqual(self.kinds(got)[-4:], [('turn', 'done'), ('line', ''), ('line', ''), ('turn', 'done')])    # both, ONE turn
        self.assertEqual(len(self.brain.calls), 2)

    def test_a_flood_is_one_hand_over_and_every_input_is_heard_once_and_told_once(self):
        self.brain.delay = 1.0
        self.say('Suggest two.', 'l0', wait=False)
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        n = 30
        for i in range(n):
            w = f'flood {i + 1:02d} of {n}'
            if i % 3 == 0: self.mail(w)
            elif i % 3 == 1: self.mail(w, own=True)
            else: self.say(w, f'f{i}', wait=False)
        self.rest()
        got = self.list()
        words = [str(x.get('text') or x.get('words') or '') for x in got['items'] if x['kind'] in ('line', 'arrival')]
        for i in range(n): self.assertEqual(sum(f'flood {i + 1:02d} of' in w for w in words), 1, f'input {i + 1} on the canvas once')
        c = conversation.counts(self.s, self.tid)
        self.assertEqual((c['line'], c['mail'], c['pending']), (11, 21, 0))                      # the ledger: each once (its key is unique)
        self.assertLessEqual(len(self.brain.calls), 3, 'a flood costs a turn or two, never one per input')
        told = '\n'.join(self.brain.calls[1:])
        for i in range(n): self.assertIn(f'flood {i + 1:02d} of', told, f'input {i + 1} was heard and never told')

    def test_what_one_hand_over_takes_stands_in_the_order_it_came(self):
        """The recorded flood, 2026-11-11: fifty inputs heard together stood as his sixteen lines, then his own replies, then the sender's
        mail - "34, 31, 46". One hand-over, written once: each stands where it came, a line and a message of one second too."""
        self.brain.delay = 1.0
        self.say('Suggest two.', 'l0', wait=False)
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        n = 18
        for i in range(n):
            w = f'flood {i + 1:02d} of {n}'
            if i % 3 == 0: self.mail(w)
            elif i % 3 == 1: self.mail(w, own=True)
            else: self.say(w, f'f{i}', wait=False)
        self.rest()
        words = [str(x.get('text') or x.get('words') or '') for x in self.list()['items'] if x['kind'] in ('line', 'arrival')]
        self.assertEqual([w[:8] for w in words if w.startswith('flood ')], [f'flood {i + 1:02d}' for i in range(n)])

    def test_a_kept_line_is_heard_and_taken_in_one_step(self):
        "The recorded flood, 2026-11-11: read between its take and its hear, a line stood for a frame at the time it was typed, above what came in since."
        self.brain.delay = 0.5
        self.say('Suggest two.', 'l-one', wait=False)
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        self.say('Near a station.', 'l-two', wait=False)
        real, at_take = self.s.take_lines, []
        def take(*a, **k): at_take.append(conversation.heard(self.s, self.tid, 'line', ['l-two'])); return real(*a, **k)
        with mock.patch.object(self.s, 'take_lines', side_effect=take): self.rest()
        self.assertEqual(at_take, [True])

    def test_a_message_that_lands_after_the_hand_over_is_the_next_turns_to_hear(self):
        """The recorded flood, 2026-11-11: his own reply on the thread came in while the session started - after the turn's hand-over, before
        its prompt was built - and was named in that prompt as the newest message, then told again by the turn that heard it."""
        real, late = general.prompt_parts, []
        def parts(*a, **k):
            if not late: late.append(self.mail('I booked the Harbour Room myself.', own=True))
            return real(*a, **k)
        with mock.patch.object(general, 'prompt_parts', side_effect=parts): self.say('Suggest two.', 'l-one'); self.rest()
        self.assertEqual(conversation.heard(self.s, self.tid, 'mail', late), False)
        self.assertNotIn('Harbour Room', self.brain.calls[0])                                    # not heard, so not told
        self.say('And now?', 'l-two'); self.rest()
        self.assertTrue(conversation.heard(self.s, self.tid, 'mail', late)); self.assertIn('Harbour Room', self.brain.calls[1])

    def test_two_messages_said_in_one_turn_over_acp_are_two_steps(self):
        said = lambda mid, t: {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': t}, **({'messageId': mid} if mid else {})}
        steps = conversation.acp_steps([said('m1', 'It returns the sum '), said('m1', 'plus tax.'), said('m2', 'The reply to Gail went out.')])
        self.assertEqual([s['text'] for s in steps], ['It returns the sum plus tax.', 'The reply to Gail went out.'])
        self.assertEqual([s['text'] for s in conversation.acp_steps([said('', 'One '), said('', 'message.')])], ['One message.'])     # an adapter that names none
        self.assertFalse([k for s in steps for k in s if k not in ('k', 'text', 'at')])

    def test_a_message_that_came_in_mid_turn_is_pending_then_heard_with_the_next_turn(self):
        self.brain.delay = 3
        self.say('Suggest two.', 'l-one', wait=False)
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        time.sleep(1.1); mid = self.mail('One more thing: near a station.')
        self.assertIn(f'm:{mid}', [x['id'] for x in self.list()['pending']])
        self.rest()
        got = self.list()
        self.assertEqual(got['pending'], []); self.assertEqual(got['items'][-1]['id'], f'm:{mid}')    # nobody took it: it stands after the turn it came in under
        self.say('And that?', 'l-two'); self.rest()
        self.assertEqual([x['id'] for x in self.list()['items'][-3:-1]], [f'm:{mid}', 'l-two'])        # heard with his line, before it: it did not move

    def test_a_turns_cards_stand_last_and_a_live_one_is_kept_under_the_latest_answer(self):
        self.say('Draft it.', 'l-one'); self.rest()
        cid = self.s.list_comments(self.tid, internal=True)[-1]['CommentId']
        rid = self.s.add_review({'TaskId': self.tid, 'MessageId': self.s.list_messages(self.tid)[0]['MessageId'], 'Kind': 'draft_reply', 'Status': 'pending',
                                 'Channel': 'email', 'DraftText': 'Hi Gail, which city? Alex'})
        self.s._exec('UPDATE review SET CreatedAt=(SELECT CreatedAt FROM comment WHERE CommentId=?) WHERE ReviewId=?', (cid, rid))
        t = self.list()['items'][-1]
        self.assertEqual([(c['review'], c['status']) for c in t['cards']], [(rid, 'pending')])
        self.say('Thanks.', 'l-two'); self.rest()
        turns = [x for x in self.list()['items'] if x['kind'] == 'turn']
        self.assertEqual([(c['review'], c['status']) for c in turns[-1]['cards']], [(rid, 'pending')])      # the thing to press: right above the box
        self.assertEqual([(c['review'], c['status'], c['id']) for c in turns[-2]['cards']], [(rid, 'kept', f'r:{rid}:k')])    # where it stood, greyed
        self.s.decide_review(rid, 'approved', 'Hi Gail, which city? Alex', 'owner')
        turns = [x for x in self.list()['items'] if x['kind'] == 'turn']
        self.assertEqual([[c['status'] for c in t['cards']] for t in turns[-2:]], [['kept'], ['approved']])      # pressed, it stays where it stood when he pressed it

    def test_what_taskuary_tells_the_agent_is_never_his_line_and_one_turn_is_at_work_and_last(self):
        """The owner's live task, 2026-11-11: he pressed Approve, and Taskuary's note to the agent ("The owner pressed Approve on what you set
        up ...") stood as his bubble; he typed while that turn worked, and a second head was left spinning under the finished answer."""
        from taskuary import verdicts, waitroom
        self.say('Draft it.', 'l-one'); self.rest()
        self.brain.delay = 1.5
        self.assertEqual(verdicts.in_words({'playbook': 'vendor-review', 'path': '/home/alex/notes/vendor-review.md', 'steps': [1, 2]}),
                         'playbook: vendor-review, path: vendor-review.md')                    # words: no JSON, no folder of his
        self.assertTrue(general.approved(self.s, self.tid, 'Approve', 'write playbook - playbook: vendor-review'))
        self.assertTrue(until(lambda: getattr(general.session_for(self.tid), 'busy', False)))
        self.say('And tell Gail.', 'l-two', wait=False)
        def check():
            got = self.list(); live = [i for i, x in enumerate(got['items']) if x['kind'] == 'turn' and x['state'] in ('working', 'starting')]
            last = max(i for i, x in enumerate(got['items']) if x['kind'] == 'turn')
            self.assertFalse([x for x in [*got['items'], *got['pending']] if 'pressed Approve' in str(x.get('text') or '') and x['kind'] == 'line'])
            self.assertEqual(live, [last] if got['working'] else [], self.kinds(got))
            return got
        for _ in range(12): check(); time.sleep(0.25)
        self.rest(); got = check()
        self.assertEqual(self.kinds(got)[-4:], [('turn', 'done'), ('turn', 'done'), ('line', ''), ('turn', 'done')])
        # ...and a note the waiting room hands a chat agent is filed as Taskuary's, whoever's name the room has it under
        n = len(self.brain.calls); self.brain.delay = 0
        waitroom.to_general(self.s, self.tid, general.session_for(self.tid) or general.start_session(self.s, self.tid), [{'Note': 'The owner pressed Approve on what you set up.', 'CreatedBy': 'router'}])
        self.assertTrue(until(lambda: len(self.brain.calls) > n)); self.rest()
        self.assertFalse([x for x in self.list()['items'] if x['kind'] == 'line' and 'pressed Approve' in x['text']])

    def test_a_thought_is_a_plain_row(self):
        self.assertEqual(conversation._said([{'k': 'thought', 'text': '**Replacing the pending draft**'}])[0]['text'], 'Replacing the pending draft')

    def test_the_agents_markers_never_reach_the_list(self):
        block = f'{selfclose.SUMMARY_OPEN}{{"about": "", "did": "Looked at both.", "on_you": []}}'
        self.assertEqual(conversation.clean(f'Both are free in March.\n\n{block}{selfclose.SUMMARY_CLOSE}'), 'Both are free in March.')
        self.assertEqual(conversation.clean(f'Both are free in March.\n\n{block}'), 'Both are free in March.')       # an opening marker with no close
        self.assertEqual(conversation.clean(block), 'Looked at both.')                                               # only the block: its own sentence, once

    def test_each_duty_is_said_once_at_startup_and_a_turn_carries_only_what_is_new(self):
        self.say('Draft it.', 'l-one'); self.rest()
        self.s.add_review({'TaskId': self.tid, 'MessageId': self.s.list_messages(self.tid)[0]['MessageId'], 'Kind': 'draft_reply', 'Status': 'pending',
                           'Channel': 'email', 'DraftText': 'Hi Gail, which city? Alex'})
        system, _late, _user = general.prompt_parts(self.s, self.tid)
        turn = general.turn_facts(self.s, self.tid, resumed=True, rules=False)
        self.assertEqual(system.count(selfclose.LATEST_LINE), 1); self.assertEqual(system.count(selfclose.WITHDRAW_LINE), 1)
        self.assertNotIn(selfclose.LATEST_LINE, turn); self.assertNotIn(selfclose.WITHDRAW_LINE, turn)
        self.assertIn('THE DRAFT WAITING NOW (to Gail Moreno', turn); self.assertNotIn('rv', turn.split('THE DRAFT WAITING NOW')[1][:40])    # no id for it to say back


if __name__ == '__main__':
    unittest.main()
