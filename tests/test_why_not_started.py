"""A task waiting to start says WHY, and the fyi batch is the owner's to size.

"waiting to start" names the state and not the cause, so it reads as a queue that will clear
itself - and every cause underneath it needs the owner instead (the owner, 2026-09-14: "if the
agent did not start, tell the user why it did not start, or left over from yesterday").
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel, funnel_selection, terminal, wrapup
from taskuary.store import MemoryStore


def ago(days=0):
    return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def handed(s, title='Add skip policy', who='agent:codex', **over):
    return s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'open', 'Assignee': who, **over}, 'triage')


class WhyNotStartedTests(unittest.TestCase):
    def test_taskuary_closed_on_top_of_it_is_the_strongest_reason(self):
        """terminal.release_task tags this when the app itself went down mid-session (PW-262)."""
        s = MemoryStore(); t = handed(s)
        s.tag_task(t, terminal.INTERRUPTED, True, 'shutdown')
        why = funnel.not_started_why(s, t)
        self.assertIn('Taskuary closed while the coding agent had this', why)     # what it IS, never the profile's name
        self.assertIn('Nothing restarts by itself', why)

    def test_a_run_that_stopped_without_finishing_says_so(self):
        s = MemoryStore(); t = handed(s)
        rid = s.start_run(t, 'codex', 'do the thing', 'owner')
        s.update_run(rid, {'Status': 'stopped'}, finished=True)
        self.assertIn('ran on this and stopped', funnel.not_started_why(s, t))

    def test_triages_own_refusal_to_start_is_quoted_back(self):
        """The first-time-sender gate writes the sentence; a no-reply address never clears it. The page reads it whole,
        led by its state and followed by the one thing to do - no "<agent> did not start:" glued to a fragment."""
        s = MemoryStore(); t = handed(s)
        mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'no-reply@vendor.example',
                             'Subject': 'Refresh warning', 'BodyText': 'gateway deprecated',
                             'SentAt': ago(0), 'Status': 'routed'})
        s.add_route(mid, t, 'create', 0.0,
                    'triage: work for the coding agent - the gateway is deprecated \u00b7 held for you: no-reply@vendor.example is not on '
                    'your domain and you have never written to them, so no agent starts on their words by itself.', [], 'router')
        st = funnel.idle_state(s, t)
        self.assertEqual((st['kind'], st['row']), ('held', 'held for you - not started'))
        self.assertEqual(st['line'], 'Waiting for you. no-reply@vendor.example is not on your domain and you have never written to '
                                     'them, so no agent starts on their words by itself.')   # the moves are the item's own buttons

    def test_a_route_written_in_the_old_words_still_reads_as_a_hold(self):
        s = MemoryStore(); t = handed(s)
        mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'no-reply@vendor.example', 'Subject': 'Refresh warning',
                             'BodyText': 'gateway deprecated', 'SentAt': ago(0), 'Status': 'routed'})
        s.add_route(mid, t, 'create', 0.0, 'triage: task - the gateway is deprecated \u00b7 not auto-worked: first message from '
                    'no-reply@vendor.example - not one of your domains', [], 'router')
        why = funnel.not_started_why(s, t)
        self.assertTrue(why.startswith('Waiting for you. First message from no-reply@vendor.example - not one of your domains.'), why)

    def test_a_setup_failure_says_what_is_wrong_and_never_offers_start_as_the_fix(self):
        """The owner, 2026-10-16: "coder could not start: unknown agent: coder. Press Start now to try again." - Start
        fails the same way every time until the agent is fixed."""
        s = MemoryStore(); t = handed(s, who='agent:coder')
        s.enqueue_dispatch(t, None, 'coder', 'x'); s.dispatch_failed(t, 'unknown agent: coder', permanent=True)
        st = funnel.idle_state(s, t)
        self.assertEqual(st['kind'], 'failed'); self.assertEqual(st['row'], "couldn't start: unknown agent: coder")
        self.assertTrue(st['line'].startswith("Couldn't start: unknown agent: coder. This is a setup problem"), st['line'])
        self.assertNotIn('try again', st['line']); self.assertNotIn('coder could not', st['line'])

    def test_a_retrying_start_says_when_and_a_ranked_wait_is_its_turn_not_a_full_house(self):
        s = MemoryStore(); t = handed(s)
        s.enqueue_dispatch(t, None, 'codex', 'x'); s.dispatch_failed(t, 'pty spawn failed', backoff=(30,))
        st = funnel.idle_state(s, t)
        self.assertEqual(st['kind'], 'retrying'); self.assertRegex(st['line'], r"^Couldn't start yet \(pty spawn failed\) - trying again at \d\d:\d\d\.$")
        s2 = MemoryStore(); t2 = handed(s2)
        s2.enqueue_dispatch(t2, None, 'codex', 'ranked'); s2._exec('UPDATE dispatchq SET Value=0.4 WHERE TaskId=?', (t2,))
        st2 = funnel.idle_state(s2, t2)
        self.assertTrue(st2['line'].startswith('Waiting its turn.'), st2['line']); self.assertNotIn('slot is busy', st2['line'])
        self.assertEqual(st2['row'], 'queued - waiting its turn')

    def test_auto_start_switched_off_is_named_as_the_reason(self):
        s = MemoryStore(); t = handed(s)
        s.set_setting('coding_auto_enabled', '0', 'owner')
        self.assertIn('Starting the coding agent by itself is switched off', funnel.not_started_why(s, t))

    def test_with_no_other_reason_it_still_says_nobody_is_on_it(self):
        s = MemoryStore(); t = handed(s)
        self.assertEqual(funnel.not_started_why(s, t), 'Not started yet. Nothing has started the coding agent on this.')

    def test_work_from_before_today_says_it_has_been_waiting(self):
        s = MemoryStore(); t = handed(s)
        s._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(2), t))   # CreatedAt is the store's to set
        self.assertIn('waiting since yesterday', funnel.not_started_why(s, t))

    def test_todays_work_does_not_claim_to_be_old(self):
        s = MemoryStore(); t = handed(s)
        self.assertNotIn('yesterday', funnel.not_started_why(s, t))


class FyiBatchSettingTests(unittest.TestCase):
    def test_the_default_is_four_and_the_range_is_one_to_ten(self):
        s = MemoryStore()
        self.assertEqual(funnel.fyi_batch_size(s), funnel.FYI_BATCH)
        self.assertEqual(funnel.FYI_BATCH_RANGE, (1, 10))

    def test_it_is_clamped_so_no_value_can_empty_or_flood_the_walk(self):
        s = MemoryStore()
        for value, want in (('1', 1), ('7', 7), ('10', 10), ('0', 1), ('-3', 1), ('99', 10)):
            s.set_setting('fyi_batch', value, 'owner')
            self.assertEqual(funnel.fyi_batch_size(s), want, value)

    def test_junk_falls_back_to_the_default_rather_than_breaking_the_walk(self):
        s = MemoryStore()
        for value in ('', '   ', 'four', 'NaN'):
            s.set_setting('fyi_batch', value, 'owner')
            self.assertEqual(funnel.fyi_batch_size(s), funnel.FYI_BATCH, repr(value))

    def test_a_store_that_cannot_answer_gets_the_default_not_an_exception(self):
        """Selection runs against stand-ins that hold no settings; a preference must never fail a walk."""
        class NoSettings: pass
        self.assertEqual(funnel.fyi_batch_size(NoSettings()), funnel.FYI_BATCH)

    def test_the_screen_that_asked_sets_it_unless_the_owner_chose(self):
        """Six on a desktop, four on a small one (the owner, 2026-10-28) - the page says which (SCREEN_BATCH); a number SET wins."""
        s = MemoryStore()
        for screen, want in ((6, 6), (4, 4), (40, 10)):
            tok = funnel.SCREEN_BATCH.set(screen)
            try: self.assertEqual(funnel.fyi_batch_size(s), want, f'the shipped default gives way to a screen of {screen}')
            finally: funnel.SCREEN_BATCH.reset(tok)
        s.set_setting('fyi_batch', '3', 'owner')
        tok = funnel.SCREEN_BATCH.set(6)
        try: self.assertEqual(funnel.fyi_batch_size(s), 3, "the owner's own number holds on any screen")
        finally: funnel.SCREEN_BATCH.reset(tok)

    def test_the_page_header_is_the_screen_for_that_request_only(self):
        """server.fyi_screen reads X-Taskuary-Fyi-Batch (website/src/fyiBatch.js) into SCREEN_BATCH while the request runs - junk is no screen."""
        import asyncio
        from starlette.requests import Request
        from taskuary import server
        def seen(value):
            got = []
            async def call_next(_): got.append(funnel.SCREEN_BATCH.get())
            hdrs = [(b'x-taskuary-fyi-batch', value.encode())] if value is not None else []
            asyncio.run(server.fyi_screen(Request({'type': 'http', 'method': 'GET', 'path': '/api/funnel/pile', 'headers': hdrs}), call_next))
            return got[0]
        for value, want in (('6', 6), ('4', 4), (None, None), ('', None), ('six', None), ('0', None), ('-2', None), ('999', None)):
            self.assertEqual(seen(value), want, repr(value))
        self.assertIsNone(funnel.SCREEN_BATCH.get(), 'reset once the request is done')

    def test_the_setting_reaches_the_selection_batch_too(self):
        """Two call sites read it; a setting that reached only one would half-work in silence."""
        first = {'key': 'msg:1', 'lane': 'fyi'}
        ready = [first] + [{'key': f'msg:{n}', 'lane': 'fyi'} for n in range(2, 9)]
        for size in (1, 3, 8):
            card, keys = funnel_selection._batch(first, ready, size)
            self.assertEqual(len(keys), size, size)
            self.assertEqual(keys[0], 'msg:1', 'the one it led with stays first')


class AgentStoryTests(unittest.TestCase):
    """The agent step tells "never started" from "did half and was cut off" (the owner, 2026-10-11)."""
    def held_pr(self, s):
        t = handed(s, who='agent:coding')
        mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'pat@vendor.example', 'Subject': 'Fix the docs',
                             'BodyText': 'one line', 'SentAt': ago(0), 'Status': 'routed'})
        s.add_route(mid, t, 'create', 0.0, 'triage: task - review it · not auto-worked: first message from '
                    'pat@vendor.example - not one of your domains', [], 'router')
        return t

    def test_a_hold_says_why_once_without_triages_lead_in(self):
        s = MemoryStore(); st = funnel.agent_story(s, self.held_pr(s))
        self.assertEqual(st['kind'], 'held')
        self.assertTrue(st['line'].startswith('Waiting for you. First message from pat@vendor.example'), st['line'])
        self.assertTrue(st['line'].endswith('not one of your domains.'), st['line'])     # a state, never a button it may not show
        self.assertNotIn('did not start', st['line'])

    def test_a_restart_mid_run_says_when_how_far_in_and_what_it_last_said(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = handed(s, who='agent:coding', Status='in_progress')
        ws.record(s, t, 's1', 'working', source='hook')
        ws.record(s, t, 's1', 'turn_end', text='Read the diff.\n- one line changed', source='hook')
        terminal.release_task(s, t, 'startup')
        st = funnel.agent_story(s, t)
        self.assertEqual(st['kind'], 'interrupted')
        self.assertIn('Taskuary restarted at', st['line'])
        self.assertIn('Nothing restarts by itself', st['line'])
        self.assertEqual(st['said'], 'Read the diff.\n- one line changed', 'its own line breaks are kept')
        self.assertEqual([x['text'] for x in st['steps']], ['Started', 'Finished a turn', 'Cut off - Taskuary restarted'])
        self.assertTrue(st['steps'][-1]['cut'])

    def test_only_the_last_session_is_told(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = handed(s, who='agent:coding', Status='in_progress')
        ws.record(s, t, 'old', 'turn_end', text='the first try', source='hook')
        ws.record(s, t, 'old', 'stopped', source='hook')
        ws.record(s, t, 'new', 'working', source='hook')
        ws.record(s, t, 'new', 'turn_end', text='the second try', source='hook')
        terminal.release_task(s, t, 'shutdown')
        st = funnel.agent_story(s, t)
        self.assertEqual(st['said'], 'the second try')
        self.assertNotIn('Stopped', [x['text'] for x in st['steps']])

    def test_nothing_to_tell_when_no_agent_was_meant_to_have_it_or_it_is_finished(self):
        s = MemoryStore()
        self.assertIsNone(funnel.agent_story(s, s.create_task({'Title': 'Mine', 'Status': 'open', 'Assignee': 'owner'}, 'owner')))
        self.assertIsNone(funnel.agent_story(s, handed(s, Status='done')))


if __name__ == '__main__':
    unittest.main()


class FinishedIsNotLeftTests(unittest.TestCase):
    """A coding agent closed its task itself, the reply went out, the sender wrote again and the task reopened - and the step said
    the agent "left without finishing" over its own finished record (2026-10-12)."""

    def ran(self, s, t, finish=True):
        from taskuary import workerstate as ws
        ws.record(s, t, 's1', 'working', source='hook')
        ws.record(s, t, 's1', 'turn_end', text='Found it: the primary address is wrong.', source='hook')
        if finish: ws.record(s, t, 's1', 'finished', source='hook')
        s.add_transcript(t, 's1', 'screen text', agent='coding')

    def test_a_session_that_finished_did_not_leave(self):
        s = MemoryStore(); t = handed(s, who='agent:coding'); self.ran(s, t)
        self.assertFalse(funnel.agent_left(s, t))
        why = funnel.not_started_why(s, t)
        self.assertIn('finished its work', why)
        self.assertNotIn('left without finishing', why)

    def test_a_report_written_after_it_began_is_a_finish_too(self):
        s = MemoryStore(); t = handed(s, who='agent:coding'); self.ran(s, t, finish=False)
        s.add_comment(t, 'agent', 'agent', f'{wrapup.REPORT}\nDetermination: done.')
        self.assertFalse(funnel.agent_left(s, t))

    def test_a_session_that_walked_away_still_left(self):
        s = MemoryStore(); t = handed(s, who='agent:coding'); self.ran(s, t, finish=False)
        self.assertTrue(funnel.agent_left(s, t))
        self.assertIn('left without finishing', funnel.not_started_why(s, t))


class NewsAfterTheAgentTests(unittest.TestCase):
    """A coding agent's session ended, the task closed, and days later the sender wrote again: the task reopened and opened on the
    old session's "You ended the session" (2026-10-12). The message is what the task is about now."""

    def setUp(self):
        self.s = MemoryStore(); self.t = handed(self.s, who='agent:coding')
        self.s.add_transcript(self.t, 's1', 'screen text', agent='coding')
        self.s.tag_task(self.t, terminal.SAVED, True, 'owner')
        self.s._exec("UPDATE transcript SET CreatedAt=? WHERE TaskId=?", (ago(5), self.t))

    def wrote(self, when):
        return self.s.add_message({'TaskId': self.t, 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                                   'Subject': 'Re: access list', 'BodyText': 'looks right except one', 'SentAt': when, 'Status': 'routed'})

    def test_a_message_after_the_session_is_the_news(self):
        self.wrote(ago(0))
        why = funnel.not_started_why(self.s, self.t)
        self.assertIn('Erin Blake wrote again today', why)
        self.assertNotIn('You stopped it', why)
        self.assertFalse(funnel.agent_left(self.s, self.t), 'not "stopped" or "saved" on the rail')
        self.assertEqual(funnel.agent_story(self.s, self.t)['kind'], 'news')

    def test_the_message_that_started_the_work_is_not_news(self):
        self.wrote(ago(6))
        self.assertIsNone(funnel.news_since_agent(self.s, self.t))
        self.assertIn('You stopped it', funnel.not_started_why(self.s, self.t))
