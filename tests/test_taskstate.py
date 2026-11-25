"""One state per task for the Tasks list and the Board (T1-T9, the owner, 2026-09-25): the rail's rules and words,
decided once on the server."""
import unittest

from taskuary import buttons, taskstate, terminal
from taskuary.store import MemoryStore


def task(s, **kw):
    tid = s.create_task({'Title': 'Fix the export', 'Kind': kw.pop('Kind', 'coding'), 'Status': kw.pop('Status', 'open')}, 'o')
    if kw: s.update_task(tid, kw, kw.pop('by', 'o') if 'by' in kw else 'o')
    return tid


def row(s, tid, **extra): return {**s.get_task(tid), **extra}


class StateTests(unittest.TestCase):
    def test_the_list_says_what_the_rail_says(self):
        s = MemoryStore()
        t = task(s, Assignee='agent:coding')
        self.assertEqual(taskstate.state(s, row(s, t)), 'queued')                      # handed on, nothing started
        s.tag_task(t, terminal.SAVED, True, 'owner')
        self.assertEqual(taskstate.state(s, row(s, t)), 'saved')                       # you ended its session
        s.tag_task(t, terminal.SAVED, False, 'owner'); s.tag_task(t, terminal.INTERRUPTED, True, 'shutdown')
        self.assertEqual(taskstate.state(s, row(s, t)), 'stopped')                     # it ended without finishing
        self.assertEqual(taskstate.state(s, row(s, task(s))), 'yours')                 # nobody was handed it

    def test_a_live_session_is_working_or_waiting_on_you(self):
        s = MemoryStore(); t = task(s)
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'waiting': False}), 'working')
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'waiting': True}), 'blocked')

    def test_a_parked_agent_over_its_drafted_reply_is_the_reply_waiting(self):
        # the email walk, 2026-10-29: one Board card said "agent waiting on you" and "ready to send" - the rail said the reply
        s = MemoryStore(); t = task(s, Kind='general')
        parked, asking = {'alive': True, 'waiting': True, 'state': 'parked'}, {'alive': True, 'waiting': True, 'state': 'asking', 'request': {'text': 'Which date?'}}
        self.assertEqual(taskstate.state(s, row(s, t, ReviewStatus='pending'), parked), 'approve')
        self.assertEqual(taskstate.column('approve'), 'agentdone')
        self.assertEqual(taskstate.state(s, row(s, t, ReviewStatus='pending'), asking), 'blocked')      # a question still outranks it
        # ...A CHAT SESSION THAT NEVER BEGAN A TURN IS NO AGENT AT REST (recorded on the real CLI, 2026-11-13: a start refused behind Trust left
        # its session open, parked - "agent done", Mark done lit, over a chat holding only the sender's message): it reads as with no session
        self.assertEqual(taskstate.state(s, row(s, t), parked), 'yours')
        # ...and a chat turn that drafted nothing and asked nothing is done for now, never waiting on you (the owner, 2026-11-07)
        from taskuary import general
        s.add_comment(t, 'assistant', general.ASSISTANT_TYPE, 'Nothing to do here - it is already booked.')
        self.assertEqual(taskstate.state(s, row(s, t), parked), 'agentdone')
        self.assertEqual(taskstate.state(s, row(s, task(s)), parked), 'blocked')                         # a coding agent parked still waits on you

    def test_a_coding_agent_parked_over_its_reply_reads_as_a_chat_s_does_to_every_reader(self):
        # the audit, 2026-11-10: read with no session in hand (the rail, the story), a coding agent parked over the reply it set up read "stopped -
        # ran on this and left without finishing it" off the transcript an earlier session filed, where its page and a chat read approve
        from unittest import mock
        from taskuary import funnel
        s = MemoryStore(); t = task(s, Assignee='agent:coding')
        s.add_transcript(t, 'old', 'Agent: looked at it', 'coding', '.', 'ext-1', brain='claude')
        class Parked:
            task_id, alive, sid, started, store = t, True, 'live-1', '2026-11-10 09:00:00', s
            def waiting(self): return True
            def info(self, details=True): return {'sid': self.sid, 'alive': True, 'waiting': True, 'state': 'parked', 'request': None, 'mode': 'full'}
        with mock.patch.dict(terminal.SESSIONS, {'live-1': Parked()}, clear=True):
            s.add_review({'TaskId': t, 'Kind': 'draft_reply', 'DraftText': 'Hi Ray - fixed.', 'Status': 'pending'})
            st = taskstate.task_state(s, tid=t)
            self.assertEqual((st.key, st.left), ('approve', ''))
            self.assertEqual(funnel.idle_state(s, t)['kind'], 'live', funnel.idle_state(s, t))       # ...never "left without finishing it"

    def test_a_coding_agent_that_answered_and_idled_out_never_left_without_finishing(self):
        """Recorded on the real CLI, 2026-11-16: a coding agent answered, its session idled out (quiet when idle), and its chat's last line
        and its row said "The coding agent ran on this and left without finishing it" - over the answer it had just finished. An agent at rest
        by its own last word (a turn's end) waits on you, as it did live; only one whose record says it stopped is "left"."""
        from unittest import mock
        from taskuary import funnel, workerstate
        s = MemoryStore(); t = task(s, Assignee='agent:coding')
        s.add_transcript(t, 'acp-1', 'Agent: total() adds tax as an amount', 'coding', '.', 'ext-1', brain='claude')
        workerstate.record(s, t, 'acp-1', 'turn_end', text='total() adds tax as an amount')
        workerstate.idled(s, t, 'acp-1')                     # ...its process closed quietly, as ACPCoding.idle_out closes it
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            got = funnel.idle_state(s, t)
            self.assertNotEqual(got['kind'], 'left', got)
            self.assertNotIn('without finishing', got['line'])
            self.assertIn('finished its turn', got['line'])

    def test_a_done_task_continued_is_live_work_but_a_stale_terminal_is_not(self):
        s = MemoryStore(); t = task(s); s.update_task(t, {'Status': 'done'}, 'owner')
        closed = s.get_task(t)['ClosedAt']
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'started': '2999-01-01 00:00:00'}), 'working')
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'started': '2000-01-01 00:00:00'}), 'closed')
        self.assertTrue(closed)

    def test_a_reply_ready_and_a_task_waiting_on_them_are_different_things(self):
        s = MemoryStore(); t = task(s, Status='waiting')
        self.assertEqual(taskstate.state(s, row(s, t)), 'theirs')
        self.assertEqual(taskstate.state(s, row(s, t, ReviewStatus='pending')), 'approve')

    def test_a_queued_start_stays_waiting_to_start_even_when_it_failed(self):
        s = MemoryStore(); t = task(s, Assignee='agent:coding')
        self.assertEqual(taskstate.state(s, row(s, t), queued={'State': 'failed'}), 'queued')

    def test_a_new_sender_s_held_task_reads_held_never_waiting_to_start(self):
        # 2026-11-17: a stranger's task read "waiting to start" on the chip, the list and the Board - as if it would start by itself -
        # while only the phone said it was held; nothing starts on it until the owner trusts the sender
        from taskuary.ingest import HOLD_TAG
        s = MemoryStore(); t = task(s, Kind='general', Assignee='agent:general')
        s.tag_task(t, HOLD_TAG, True, 'router')
        self.assertEqual(taskstate.state(s, row(s, t), queued={'State': 'waiting'}), 'held')
        self.assertEqual(taskstate.state(s, row(s, t)), 'held')
        self.assertEqual(taskstate.column('held'), 'queued')                          # the Board keeps it where it stood
        from taskuary import funnel, lanes                                             # ...and the rail's row, which the phone reads, says it too
        self.assertEqual((funnel.lane_word({'lane': 'queued', 'hold': True}), funnel.mark_for({'lane': 'queued', 'hold': True})),
                         (lanes.word('held'), '🔒'))
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'waiting': False}), 'working')    # ...an agent at work is at work
        s.tag_task(t, HOLD_TAG, False, 'owner')                                        # Trust lifts it: a plain wait again
        self.assertEqual(taskstate.state(s, row(s, t), queued={'State': 'waiting'}), 'queued')

    def test_who_closed_it_decides_agent_finished(self):
        s = MemoryStore(); t = task(s)
        s.add_comment(t, 'coding', 'agent', 'The agent closed this itself: fixed.')
        s.update_task(t, {'Status': 'done'}, 'coding')
        self.assertEqual(taskstate.state(s, row(s, t)), 'agentdone')
        s.update_task(t, {'Status': 'done'}, 'owner')                                  # you edited it last
        self.assertEqual(taskstate.state(s, row(s, t)), 'closed')

    def test_board_columns(self):
        self.assertEqual([taskstate.column(k) for k in ('queued', 'working', 'blocked', 'saved', 'stopped', 'agentdone', 'approve')],
                         ['queued', 'working', 'blocked', 'left', 'left', 'agentdone', 'agentdone'])
        self.assertIsNone(taskstate.column('yours')); self.assertIsNone(taskstate.column('theirs'))

    def test_how_the_last_run_ended_is_the_state_when_nothing_is_live(self):
        """The run's own word about how it ended (workerstate.ended) - the list and the Board said "on you" over a run that failed or
        was stopped, and "waiting to start" over one that finished (G7, 2026-10-20)."""
        from taskuary import workerstate as ws
        s = MemoryStore()
        def ran(*kinds, **kw):
            t = task(s, **kw)
            for k in kinds: ws.record(s, t, 'r1', k, text='the test database was not reachable' if k == 'failed' else '')
            return t
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'failed'))), 'stopped')
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'stopped'))), 'stopped')
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'finished'))), 'agentdone')
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'finished', Assignee='agent:coding'))), 'agentdone')
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'finished', 'working', 'turn_end'))), 'yours')   # asked for more since
        self.assertEqual(taskstate.state(s, row(s, ran('working', 'turn_end'))), 'yours')                          # silence is not an ending
        t = ran('working', 'stopped'); s.tag_task(t, terminal.SAVED, True, 'owner')
        self.assertEqual(taskstate.state(s, row(s, t)), 'saved')
        self.assertEqual((ws.ended(s, ran('working', 'failed')), ws.ended(s, ran('working', 'turn_end'))), ('failed', None))



class MakeATaskTests(unittest.TestCase):
    def test_a_message_that_is_already_a_task_is_not_offered_make_a_task(self):
        # the owner, 2026-09-25: "why am i getting make this a task?? it already is" (desktop and the phone's poll)
        from taskuary import concierge
        s = MemoryStore()
        on = lambda item: [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertIn('mine', on({'key': 'msg:7', 'kind': 'asked', 'mid': 7}))
        t = s.create_task({'Title': 'Send the August reports', 'Kind': 'general', 'Status': 'open'}, 'o')
        mine = {'key': 'msg:7', 'kind': 'asked', 'mid': 7, 'tid': t, 'ref': f'TQ-{t:04d}'}
        self.assertNotIn('mine', on(mine))
        self.assertIn('already a task', concierge.cannot(mine, 'mine', s))
        # ...but on a task an agent holds it takes it back, and says so
        s.update_task(t, {'Assignee': 'agent:coding'}, 'o')
        # ONE name per button (buttons.json): the hover says it takes the work back
        took = [c for c in concierge.chips_for(s, mine) if c['verb'] == 'mine']
        self.assertEqual([c['label'] for c in took], [buttons.label('mine')]); self.assertIn('back', took[0]['hint'])

    def test_an_idea_or_an_fyi_that_already_has_its_task_is_not_offered_make_a_task(self):
        # the owner, 2026-10-01: "no Make a task on an item that already IS a task" - an Advisor idea that triage opened a
        # task for, and an fyi filed under a task, still offered it (and the walk's sentence still said "make it a task")
        from taskuary import concierge
        s = MemoryStore()
        on = lambda item: [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertIn('mine', on({'key': 'idea:3', 'kind': 'idea', 'idea': 3, 'title': 'Chase the invoice'}))
        t = s.create_task({'Title': 'Chase the invoice', 'Kind': 'general', 'Status': 'open'}, 'o')
        idea = {'key': 'idea:3', 'kind': 'idea', 'idea': 3, 'tid': t, 'ref': f'TQ-{t:04d}', 'title': 'Chase the invoice'}
        self.assertNotIn('mine', on(idea))
        self.assertNotIn(buttons.label('mine'), concierge.fallback(idea, True))
        s.update_task(t, {'Status': 'done'}, 'o')
        self.assertIn('mine', on(idea), "a closed task is history - new work on it may be a task again")
        live = s.create_task({'Title': 'Payroll notice', 'Kind': 'task', 'Status': 'open'}, 'o')
        fyi = {'key': 'msg:9', 'kind': 'fyi', 'mid': 9, 'tid': live, 'ref': f'TQ-{live:04d}', 'title': 'Payroll notice', 'who': 'Erin Blake'}
        self.assertNotIn(buttons.label('mine'), concierge.fallback(fyi, True))
        self.assertIn(buttons.label('mine', 'fyi'), concierge.fallback({**fyi, 'tid': None}, True))   # an FYI's own words for it (2026-10-29)

    def test_the_mine_door_on_a_message_with_a_task_returns_that_task_and_makes_no_second(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore()
        t = s.create_task({'Title': 'Send the August reports', 'Kind': 'task', 'Status': 'open', 'Assignee': 'owner'}, 'o')
        mid = s.add_message({'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'August reports', 'FromEmail': 'erin@northwind.example',
                             'BodyText': 'Can you send them?', 'TaskId': t, 'Status': 'routed'})
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/messages/{mid}/mine', json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['taskId'], t)
        self.assertEqual(len(s.list_tasks()), 1)


# WHERE A TASK STANDS, SAID ONCE (the owner, 2026-11-24; walks 11-16): the rail, the header, the phone, the day's brief, the Advisor's input, the
# Assistant's facts, triage's open work and Send and close each told "who moves next" their own way - "agent done" right after the email that
# asked Erin something, a question's buttons live after it was answered, a closed question still "open" to the reopened agent
ERIN = 'erin@northwind.example'


def _chat(s, title):
    "A chat task whose agent answered a turn and rests (its run's events, as an idled-out agent leaves them)"
    import json
    from taskuary import general, workerstate as ws
    tid = s.create_task({'Title': title, 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Get the vendor numbers.')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Done my part.')
    s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Asked for the numbers', 'on_you': [], 'nothing_left': False}))
    ws.record(s, tid, 'sid1', 'working', source='api'); ws.record(s, tid, 'sid1', 'turn_end', text='Done my part.', source='api')
    return tid


class StandingTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting('owner_email', 'alex@northwind.example', 't')

    def surfaces(self, tid) -> dict:
        "What every surface says of task `tid`, each through its own door"
        from taskuary import assistant, card, concierge, context, evening, funnel, remote_assistant
        s, t = self.s, self.s.get_task(tid)
        row = funnel.one_state(s, {'items': [{'tid': tid, 'key': f'task:{tid}', 'kind': 'task', 'lane': 'yours'}]})['items'][0]
        line = lambda txt: next((l for l in txt.splitlines() if f'TQ-{tid:04d}' in l), '')
        return {'key': taskstate.state(s, t), 'header': taskstate.status(s, t)['word'], 'rail': (row['lane'], (row.get('status') or {}).get('word')),
                'phone': remote_assistant.status_word(s, {'tid': tid}), 'brief': evening.owed(s, t, '2000-01-01'),
                'advisor': line(assistant._open(s)), 'assistant': concierge.task_now(s, tid),
                'triage': next((l for l in context.open_items(s) if f'(tid {tid})' in l), ''), 'may_close': card.may_close(s, tid)}

    def test_one_task_in_each_state_reads_the_same_on_every_surface(self):
        from taskuary import waiton, workerstate as ws
        s = self.s
        asks = _chat(s, 'Seat count'); ws.record(s, asks, 'sid1', 'input_needed', text='Is it 25 seats or 250?', source='api')
        erin = _chat(s, 'Vendor spend'); waiton.declare(s, erin, ERIN, 'agent')
        done = _chat(s, 'Old ask')
        mine, theirs, quiet = self.surfaces(asks), self.surfaces(erin), self.surfaces(done)
        # ...his input: the agent's question stands, at rest as live
        self.assertEqual((mine['key'], mine['header'], mine['rail'], mine['phone']),
                         ('blocked', 'waiting for your input', ('blocked', 'waiting for your input'), 'waiting for your input'))
        for k in ('brief', 'advisor', 'assistant', 'triage'): self.assertIn("waiting for your input: the agent's question: Is it 25 seats or 250?", mine[k], k)
        self.assertEqual(mine['may_close'], "the agent's question (Is it 25 seats or 250?)", 'his answer is owed first (J1)')
        # ...somebody else's, by name - never "agent done"
        self.assertEqual((theirs['key'], theirs['header'], theirs['rail'], theirs['phone']),
                         ('theirs', "waiting for Erin's input", ('theirs', "waiting for Erin's input"), "waiting for Erin's input"))
        for k in ('brief', 'advisor', 'assistant', 'triage'): self.assertIn("waiting for Erin's input: an answer from Erin", theirs[k], k)
        self.assertEqual(theirs['may_close'], 'an answer from Erin')
        for k in ('header', 'brief', 'advisor', 'phone'): self.assertNotIn('agent done', theirs[k], k)
        # ...nobody's: the agent is done for now, and nothing holds the close
        self.assertEqual((quiet['key'], quiet['header'], quiet['phone'], quiet['may_close']), ('agentdone', 'agent done', 'agent done', ''))
        for k in ('brief', 'advisor', 'assistant'): self.assertIn('no input awaited from anyone', quiet[k], k)
        self.assertNotIn('waiting for', quiet['triage'])

    def test_steps_its_turn_listed_for_him_wait_on_nobody_a_card_or_its_question_does(self):
        """Walk 21: a turn ended with steps in its summary's `on_you` and asked nothing, set up no card - and every surface read "waiting for
        your input" (the owner, 2026-11-25: only a card waiting for his press or the agent's question to him is waiting for his input)."""
        import json
        from taskuary import general, workerstate as ws
        s = self.s
        tid = _chat(s, 'Rotate the keys')
        s.add_comment(tid, 'agent', general.SUMMARY_TYPE, json.dumps({'did': 'Listed the keys', 'nothing_left': False,
                                                                        'on_you': ['Paste the new key into the vault']}))
        got = self.surfaces(tid)
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], None)
        for k in ('header', 'phone', 'brief', 'advisor', 'assistant'): self.assertNotIn('waiting for your input', got[k], k)
        self.assertNotEqual(got['rail'][1], 'waiting for your input')
        # ...a card set up for his press is
        rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'save the new key',
                           'DraftText': json.dumps({'action': 'browser_act', 'what': 'save the new key'})})
        self.assertEqual((taskstate.standing(s, tid)['waits_on'], self.surfaces(tid)['header']), ('you', 'waiting for your input'))
        # ...and so is its question to him
        s.decide_review(rv, 'rejected', None, 'owner'); ws.record(s, tid, 'sid1', 'input_needed', text='Which vault?', source='api')
        self.assertEqual((taskstate.standing(s, tid)['waits_on'], self.surfaces(tid)['header']), ('you', 'waiting for your input'))

    def test_the_agents_question_stands_until_he_answers_the_task_closes_or_the_agent_takes_it_back(self):
        from taskuary import agenttools, concierge, workerstate as ws
        s = self.s
        tid = _chat(s, 'Seat count'); ws.record(s, tid, 'sid1', 'input_needed', text='Is it 25 seats or 250?', source='api')
        # ...a later turn woken by mail that did not ask it again leaves it standing (it once vanished at the turn's end - walk 16, J1)
        ws.record(s, tid, 'sid1', 'working', text=ws.WAKE, source='api'); ws.record(s, tid, 'sid1', 'turn_end', text='Filed the invoice.', source='api')
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], 'you')
        # ...the agent withdraws it, with the tool it asked with
        self.assertIn('Withdrawn: Is it 25 seats or 250?', agenttools.call(s, tid, 'ask_owner', {'withdraw': True}, {}))
        self.assertEqual((taskstate.standing(s, tid)['waits_on'], taskstate.state(s, s.get_task(tid))), (None, 'agentdone'))
        # ...or the task closes with it unanswered, said so on the close's row for the day's brief
        ws.record(s, tid, 'sid1', 'input_needed', text='Which vendor first?', source='api')
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], 'you')
        concierge.close_task(s, tid)
        self.assertEqual(taskstate.open_question(s, tid), None, 'a reopened agent reads what the page reads')
        row = s._one("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='close_from_assistant'", (tid,))
        self.assertIn('Which vendor first?', row['Detail'])

    def test_send_and_close_is_not_offered_under_the_agents_standing_question(self):
        """Walk 18 (L3, S9): the agent drafted the reply to Erin and asked him which seat count is right; "Send and close" stood first under the
        card, though the question stands until he answers, the task closes or the agent takes it back (J1). Send stays; the close waits."""
        from taskuary import agenttools, card, concierge, workerstate as ws
        s = self.s
        tid = _chat(s, 'Seat count')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'q1', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': ERIN,
                             'Subject': 'Seats', 'BodyText': 'How many seats?', 'Status': 'routed'})
        rv = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi Erin - checking the count.'})
        self.assertEqual(card.may_close(s, tid), '')
        ws.record(s, tid, 'sid1', 'input_needed', text='Is it 25 seats or 250?', source='api')
        self.assertEqual(card.may_close(s, tid), "the agent's question (Is it 25 seats or 250?)")
        item = {'tid': tid, 'rid': rv, 'kind': 'review', 'ref': f'TQ-{tid:04d}', 'draft': True}
        self.assertIn('stays open', concierge.cannot(item, 'send_close', s))
        self.assertIn('Withdrawn', agenttools.call(s, tid, 'ask_owner', {'withdraw': True}, {}))
        self.assertEqual(card.may_close(s, tid), '', 'taken back, nothing holds the close')

    def test_their_answer_or_a_check_back_come_due_moves_it_back_to_the_agent(self):
        from taskuary import checkback, waiton
        s = self.s
        tid = _chat(s, 'Vendor spend'); waiton.declare(s, tid, ERIN, 'agent')
        checkback.set_check(s, tid, 'in 2 days', 'Erin sent the numbers')
        st = taskstate.standing(s, tid)
        self.assertEqual((st['waits_on'], st['who'], bool(st['next'])), ('them', 'Erin', True))
        self.assertIn('checks back', taskstate.said(st))
        s._exec("UPDATE task SET WaitingSince='2026-01-01 09:00:00' WHERE TaskId=?", (tid,))
        def erin_writes(at, body):
            m = s.add_message({'TaskId': tid, 'ExternalId': at, 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': ERIN, 'BodyText': body, 'Status': 'routed'})
            s._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (at, m)); waiton.arrived(s, tid, s.get_message(m), m)
        def turn(): ws.record(s, tid, 'sid1', 'working', text=ws.WAKE, source='api'); ws.record(s, tid, 'sid1', 'turn_end', text='Read it.', source='api')
        from taskuary import workerstate as ws
        # ...her holding line moves it to the agent, the wait still standing - triage still sees whose answer it waits for (walk 17, K2)
        erin_writes('2026-01-01 10:00:00', 'Still working on the split - the quote is attached.')
        st = taskstate.standing(s, tid)
        self.assertEqual((st['waits_on'], [x['who'] for x in st['them']]), ('agent', ['Erin Blake']))   # ...named as her line names her (waiton.person)
        self.assertIn("also waiting for Erin's input", taskstate.said(st))
        self.assertNotEqual(taskstate.state(s, s.get_task(tid)), 'theirs')
        # ...the turn that read it still waits on her, and says so again: the wait stands
        ws.record(s, tid, 'sid1', 'working', text=ws.WAKE, source='api'); waiton.declare(s, tid, ERIN, 'agent')
        ws.record(s, tid, 'sid1', 'turn_end', text='Erin is still on the split.', source='api')
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], 'them')
        # ...her real answer moves it to the agent; a turn that reads it and ends leaves the wait standing (walk 19, M2) ...
        s._exec("UPDATE task SET WaitingSince='2026-01-01 11:00:00' WHERE TaskId=?", (tid,))
        erin_writes('2026-01-01 12:00:00', 'More users - we added the sales team.')
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], 'agent')
        turn()
        self.assertEqual((taskstate.standing(s, tid)['waits_on'], s.get_task(tid)['WaitingOn']), ('them', ERIN))
        # ...and only a turn whose end says nothing is left ends it
        erin_writes('2026-01-01 13:00:00', 'That is all of it.')
        ws.record(s, tid, 'sid1', 'working', text=ws.WAKE, source='api'); waiton.settle(s, tid, over=True)
        ws.record(s, tid, 'sid1', 'turn_end', text='Read it.', source='api')
        self.assertEqual((taskstate.standing(s, tid)['them'], s.get_task(tid)['WaitingOn']), ([], None))
        s._exec("UPDATE task SET CheckBackAt='2000-01-01 09:00:00' WHERE TaskId=?", (tid,))
        self.assertEqual(taskstate.standing(s, tid)['waits_on'], 'agent')

    def test_the_brief_reads_where_it_stands_never_an_unticked_opening_ask(self):
        """Walk 17 (K3): "to-dos left: Post the Ask HN question" - the task's seeded to-do the agent never ticked - read as "held for your
        approval" after he had dismissed the post; and a standing check-back was never said."""
        from taskuary import checkback, evening
        s = self.s
        tid = _chat(s, 'Ask HN post'); s.set_task_checklist(tid, ['Post the Ask HN question'], 'agent')
        checkback.set_check(s, tid, 'in 2 days', 'the post got answers')
        row = evening.owed(s, s.get_task(tid), '2000-01-01')
        self.assertNotIn('Post the Ask HN question', row); self.assertIn('checks back', row)

    def test_a_new_mail_that_asked_them_something_waits_for_their_input(self):
        """Walks 14-16 (S2): "email Erin for the monthly spend" - the card sent, and the header read "agent done" with nothing saying it waited
        on her. Whether it asked is the model's to read (sentjudge); the wait is the one the agent's own --waiting-on records."""
        from unittest import mock
        from taskuary import asks, sentjudge
        s = self.s
        tid = _chat(s, 'Vendor spend')
        rv = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'sent', 'Deliver': '{"to": ["Erin Blake <erin@northwind.example>"]}'})
        with mock.patch.object(asks, '_background', lambda f: f()), \
             mock.patch.object(sentjudge, 'judge_text', return_value={'asks_them': True, 'promise': False, 'what': '', 'due': None}):
            asks.watch_reply(s, s.get_review(rv), 'Hi Erin, what was the monthly spend?', to=['Erin Blake <erin@northwind.example>'])
        self.assertEqual(self.surfaces(tid)['header'], "waiting for Erin's input")
        with mock.patch.object(asks, '_background', lambda f: f()), \
             mock.patch.object(sentjudge, 'judge_text', return_value={'asks_them': False, 'promise': False, 'what': '', 'due': None}):
            other = _chat(s, 'FYI sent')
            asks.watch_reply(s, {'TaskId': other}, 'Here is the sheet.', to=[ERIN])
        self.assertEqual(taskstate.standing(s, other)['waits_on'], None, 'a mail that asked nothing awaits nothing')


if __name__ == '__main__': unittest.main()
