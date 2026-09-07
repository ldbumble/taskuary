"""Coordination context refreshes as peers start and stop (PW-173): one line lands in each live peer's waiting room on
the same checkout, typed when that peer parks. A briefing, never a lock, never a claim of isolation."""
from unittest import mock

from taskuary import blackboard as bb, terminal as term, waitroom
from tests.test_worker_events import Base, live


class PeerUpdates(Base):
    def test_one_note_per_live_peer_on_the_same_checkout_and_none_to_the_speaker(self):
        other = self.fx.task(title='Other job', kind='coding'); elsewhere = self.fx.task(title='Elsewhere', kind='coding')
        term.SESSIONS['a'] = live(self.tid, 'a'); term.SESSIONS['b'] = live(other, 'b'); term.SESSIONS['c'] = live(elsewhere, 'c', cwd=r'C:\code\else')
        with mock.patch.object(waitroom, 'deliver', return_value={'delivered': 0, 'state': 'working'}):
            n = bb.peer_update(self.s, r'C:\code\repo', 'PEER UPDATE: TQ-0002 (coder) started here', exclude_sid='a')
        self.assertEqual(n, 1)
        self.assertEqual([w['Note'] for w in self.s.waiting_notes(other)], ['PEER UPDATE: TQ-0002 (coder) started here'])
        self.assertEqual(self.s.waiting_notes(elsewhere), []); self.assertEqual(self.s.waiting_notes(self.tid), [])

    def test_a_dead_or_taskless_session_is_not_a_peer(self):
        other = self.fx.task(title='Other job', kind='coding')
        dead = live(other, 'b'); dead.alive = False; term.SESSIONS['b'] = dead; term.SESSIONS['c'] = live(None, 'c')
        self.assertEqual(bb.peer_update(self.s, r'C:\code\repo', 'PEER UPDATE: x', exclude_sid='a'), 0)

    def test_the_text_says_briefing_not_lock(self):
        for text in (bb.PEER_STARTED.format(ref='TQ-0002', agent='coder'), bb.PEER_STOPPED.format(ref='TQ-0002', agent='coder')):
            self.assertTrue(text.startswith('PEER UPDATE:')); self.assertNotIn('lock', text.lower()); self.assertNotIn('worktree', text.lower())
        self.assertIn('history', bb.PEER_STOPPED)
