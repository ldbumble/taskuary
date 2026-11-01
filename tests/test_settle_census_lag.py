"""A settle the membership census refused is the worker's lag, not a refusal: reconciled and tried again while mail keeps landing
(TQ-1251: on a busy mailbox one retry was not enough, and a morning digest already written was logged as failed)."""
import unittest
from unittest import mock

from taskuary import funnel, processing_all

LAG = 'processing membership must be reconciled before settlement'


class Lagging:
    "A store whose settle the census refuses `refusals` times - mail landed between each reconcile and the next try."
    def __init__(self, refusals):
        self.refusals, self.tries, self.reconciled = refusals, 0, 0
    def set_funnel_state(self, *a, **k):
        self.tries += 1
        if self.tries <= self.refusals: raise ValueError(LAG)
    def reconcile_processing_membership(self): self.reconciled += 1


class SettleThroughTheLag(unittest.TestCase):
    def settle(self, s):
        with mock.patch.object(processing_all, 'wait_settled'), mock.patch.object(funnel, '_idea_done'), \
             mock.patch.object(funnel, 'thread_of', return_value=[]), mock.patch.object(funnel, 'invalidate', create=True):
            return funnel.settle(s, 'report:7', 'done', 'report')

    def test_mail_landing_twice_mid_settle_still_settles(self):
        s = Lagging(refusals=2)
        self.settle(s)
        self.assertEqual((s.tries, s.reconciled), (3, 2))

    def test_a_census_that_never_settles_still_says_so(self):
        s = Lagging(refusals=funnel.SETTLE_TRIES)
        with self.assertRaisesRegex(ValueError, 'reconciled before settlement'): self.settle(s)
        self.assertEqual(s.tries, funnel.SETTLE_TRIES)

    def test_any_other_refusal_is_not_retried(self):
        s = Lagging(refusals=0)
        s.set_funnel_state = mock.Mock(side_effect=ValueError('processing context changed since confirmation was proposed'))
        with self.assertRaisesRegex(ValueError, 'context changed'): self.settle(s)
        self.assertEqual(s.set_funnel_state.call_count, 1)
