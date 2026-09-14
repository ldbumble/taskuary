"""A task waiting to start says WHY, and the fyi batch is the owner's to size.

"waiting to start" names the state and not the cause, so it reads as a queue that will clear
itself - and every cause underneath it needs the owner instead (the owner, 2026-09-14: "if the
agent did not start, tell the user why it did not start, or left over from yesterday").
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel, funnel_selection, terminal
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
        self.assertIn('Taskuary closed while codex had this', why)
        self.assertIn('Nothing restarts by itself', why)

    def test_a_run_that_stopped_without_finishing_says_so(self):
        s = MemoryStore(); t = handed(s)
        rid = s.start_run(t, 'codex', 'do the thing', 'owner')
        s.update_run(rid, {'Status': 'stopped'}, finished=True)
        self.assertIn('ran on this and stopped', funnel.not_started_why(s, t))

    def test_triages_own_refusal_to_start_is_quoted_back(self):
        """The first-time-sender gate writes the sentence; a no-reply address never clears it."""
        s = MemoryStore(); t = handed(s)
        mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'no-reply@vendor.example',
                             'Subject': 'Refresh warning', 'BodyText': 'gateway deprecated',
                             'SentAt': ago(0), 'Status': 'routed'})
        s.add_route(mid, t, 'create', 0.0,
                    'triage: task - the gateway is deprecated \u00b7 not auto-worked: first message from '
                    'no-reply@vendor.example - not one of your domains', [], 'router')
        why = funnel.not_started_why(s, t)
        self.assertIn('Triage did not start it:', why)
        self.assertIn('not one of your domains', why)

    def test_auto_start_switched_off_is_named_as_the_reason(self):
        s = MemoryStore(); t = handed(s)
        s.set_setting('coder_auto_enabled', '0', 'owner')
        self.assertIn('Auto-start is off', funnel.not_started_why(s, t))

    def test_with_no_other_reason_it_still_says_nobody_is_on_it(self):
        s = MemoryStore(); t = handed(s)
        self.assertEqual(funnel.not_started_why(s, t), 'It was handed to codex and nothing has started it.')

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

    def test_the_setting_reaches_the_selection_batch_too(self):
        """Two call sites read it; a setting that reached only one would half-work in silence."""
        first = {'key': 'msg:1', 'lane': 'fyi'}
        ready = [first] + [{'key': f'msg:{n}', 'lane': 'fyi'} for n in range(2, 9)]
        for size in (1, 3, 8):
            card, keys = funnel_selection._batch(first, ready, size)
            self.assertEqual(len(keys), size, size)
            self.assertEqual(keys[0], 'msg:1', 'the one it led with stays first')


if __name__ == '__main__':
    unittest.main()
