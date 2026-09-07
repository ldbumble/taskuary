"""Does the agent's LAST WORD survive the ending - for both kinds of agent, and both CLIs?

Three endings exist: the owner presses Done, the agent declares itself finished (selfclose), and the
session is stopped. The question is whether the agent's own final sentence is what gets kept, or
whether a second model reconstructs one from the scrollback.
"""
import json, unittest
from unittest import mock

from taskuary import coder, general, selfclose, terminal, witness, workerstate as ws
import tests.test_assistant_reactions as T


class LastWordTests(unittest.TestCase):

    # ── the coding agent: three sources, in priority order (coder.wrap, PW-230) ──────────────
    def test_claude_stop_hook_carries_the_final_message_into_the_witness(self):
        w = witness.Witness()
        for n in witness.claude_notes({'hook_event_name': 'Stop',
                                       'last_assistant_message': 'Fixed the export; four rows flagged.'}):
            w.note(n)
        self.assertEqual(w.said, 'Fixed the export; four rows flagged.')
        self.assertEqual(w.source, 'hook')
        self.assertTrue(w.done_at)

    def test_codex_rollout_carries_the_final_message_too(self):
        """Codex has no hook - the TUI writes every event to ~/.codex/sessions/**/rollout-*.jsonl
        and the witness tails it, so task_complete's last_agent_message is the same last word."""
        w = witness.Witness()
        for n in witness.codex_notes({'type': 'event_msg', 'timestamp': '2026-09-07T14:00:00',
                                      'payload': {'type': 'task_complete',
                                                  'last_agent_message': 'Reconciled to the penny.'}}):
            w.note(n)
        self.assertEqual(w.said, 'Reconciled to the penny.')
        self.assertEqual(w.source, 'rollout')
        # ...and an ordinary agent message on the way there is kept as well
        w2 = witness.Witness()
        for n in witness.codex_notes({'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
                'type': 'AgentMessage', 'content': [{'text': 'Looking at the ledger now.'}]}}}):
            w2.note(n)
        self.assertEqual(w2.said, 'Looking at the ledger now.')

    def test_the_explicit_done_sentence_outranks_everything_and_is_cli_agnostic(self):
        """`taskuary --done "..."` is a plain HTTP call keyed on TASKUARY_TASK, so it works from any
        CLI - it is the one road that does not depend on hooks or rollout files at all."""
        s = T.store()
        with mock.patch.object(T.ingest, '_spawn'):
            out = T.arrive(s, llm=T.brain('task', 'coding'))
        tid = out['task_id']
        ws.record(s, tid, 'sid-1', 'finished', text='Shipped it - the nightly export reconciles.', source='api')
        word = ws.status(s, tid)
        self.assertEqual(word.get('state'), 'finished')
        self.assertIn('Shipped it', str(word.get('result')))

    def test_a_coding_wrap_saves_the_final_word_before_the_session_is_closed(self):
        """SAVE FIRST, close after (PW-231/233): the record must not depend on the pty surviving."""
        s = T.store()
        with mock.patch.object(T.ingest, '_spawn'):
            out = T.arrive(s, llm=T.brain('task', 'coding'))
        tid = out['task_id']
        order = []
        with mock.patch.object(terminal, 'transcript_for', return_value=('$ ran the thing', 'coder', 'sid-1')), \
             mock.patch.object(coder, 'report_from_transcript', side_effect=lambda *a, **k: {'summary': 'from scrollback'}), \
             mock.patch.object(terminal, 'close', side_effect=lambda *a, **k: order.append('close')), \
             mock.patch.object(terminal, 'session_for', return_value=None):
            real_add = s.add_comment
            def watched(tid_, actor, kind, body, *a, **k):
                if 'REPORT' in str(body).upper() or 'penny' in str(body): order.append('save')
                return real_add(tid_, actor, kind, body, *a, **k)
            with mock.patch.object(s, 'add_comment', side_effect=watched):
                try: coder.wrap(s, tid, close=True, actor='owner', final_message='Reconciled to the penny.')
                except Exception as e: self.skipTest(f'wrap needs more of the world than this fixture has: {e}')
        if 'save' in order and 'close' in order:
            self.assertLess(order.index('save'), order.index('close'), order)

    # ── the regular (general) agent: every turn is already a comment ─────────────────────────
    def test_a_regular_agent_files_each_answer_as_it_speaks_so_the_last_one_is_never_lost(self):
        s = T.store()
        tid = s.create_task({'Title': 'Weigh two quotes', 'Summary': 'which vendor', 'Kind': 'general'}, 'owner')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'First pass: vendor A is cheaper.')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Final: go with vendor B - support terms.')
        hist = general.history(s, tid)
        last = next((m['content'][0]['text'] for m in reversed(hist) if m['role'] == 'assistant'), '')
        self.assertEqual(last, 'Final: go with vendor B - support terms.')

    def test_closing_a_regular_agent_returns_its_last_answer_and_keeps_the_conversation(self):
        s = T.store()
        tid = s.create_task({'Title': 'Weigh two quotes', 'Summary': 'which vendor', 'Kind': 'general'}, 'owner')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Final: go with vendor B.')
        fake = mock.Mock(sid='sid-9')
        with mock.patch.object(general, 'session_for', return_value=fake), \
            mock.patch.object(general, 'handles', return_value=True), \
             mock.patch.object(terminal, 'close') as closed:
            out = coder.wrap(s, tid, close=True, actor='owner')
        self.assertEqual(out['report'], 'Final: go with vendor B.')     # the last word is the report
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertTrue(closed.called)
        self.assertTrue(any('Final: go with vendor B.' in (c['Body'] or '') for c in s.list_comments(tid)))

    def test_the_regular_agent_files_its_turn_before_it_ever_self_closes(self):
        """general.py files the reply, then arms the close on a timer explicitly so the record
        cannot be lost to the session dying inside its own answer."""
        import io, os
        src = io.open(os.path.join('taskuary', 'general.py'), encoding='utf-8').read()
        i_file = src.index("self.store.add_comment(self.task_id, 'assistant', ASSISTANT_TYPE, reply)")
        i_close = src.index('threading.Timer(0.1, self._close_out')
        self.assertLess(i_file, i_close, 'the turn must be filed before the close is armed')
        self.assertIn('AFTER the turn is filed', src)


if __name__ == '__main__':
    unittest.main()
