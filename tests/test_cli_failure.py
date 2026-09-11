"""Why a CLI run failed, in the CLI's own words.

From the owner's task page, 2026-09-11 (TQ-0496): a set-up walk that had been asked to log into
ADP sat on "Agent is working" for thirteen hours. codex had exited 1 two seconds in, refusing the
model pinned in ~/.codex/config.toml, and said so on STDOUT as JSONL. The reason was read off
STDERR instead, where the only line was the progress notice `Reading prompt from stdin...` - so
the one thing that explained everything never reached the owner, the log, or the trace.
"""
import unittest

from taskuary import agents

# stdout and stderr exactly as codex 0.148.0 split them on the owner's machine
OUT = [
    '{"type":"thread.started","thread_id":"01a09048-2fe8-7752-b5d3-83c4d80ad383"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"error","message":"Model metadata for '
    '`gpt-6-astra` not found. Defaulting to fallback metadata; this can degrade performance."}}',
    '{"type":"turn.started"}',
    '{"type":"error","message":"{\\"type\\":\\"error\\",\\"status\\":400,\\"error\\":{\\"type\\":'
    '\\"invalid_request_error\\",\\"message\\":\\"The \'gpt-6-astra\' model requires a newer version '
    'of Codex. Please upgrade to the latest app or CLI and try again.\\"}}"}',
]
ERR = 'Reading prompt from stdin...\n'


class TheReasonTests(unittest.TestCase):
    def test_the_stdout_event_beats_the_stderr_progress_notice(self):
        said = agents.cli_failure(OUT, ERR)
        self.assertIn('requires a newer version of Codex', said)
        self.assertNotIn('Reading prompt from stdin', said)

    def test_the_owner_reads_a_sentence_and_never_the_envelope(self):
        """codex passes the provider's 400 through as a JSON string inside a JSON event."""
        self.assertNotIn('{', agents.cli_failure(OUT, ERR))
        self.assertNotIn('invalid_request_error', agents.cli_failure(OUT, ERR))

    def test_the_newest_word_wins(self):
        """The metadata warning is real and earlier; the refusal is what stopped the run."""
        self.assertNotIn('Model metadata', agents.cli_failure(OUT, ERR))

    def test_turn_failed_carries_the_reason_when_it_is_the_only_event(self):
        fail = ('{"type":"turn.failed","error":{"message":"{\\"error\\":{\\"message\\":'
                '\\"that model is not supported on this account\\"}}"}}')
        self.assertEqual(agents.cli_failure([fail]), 'that model is not supported on this account')

    def test_stderr_is_still_the_answer_when_stdout_reported_nothing(self):
        self.assertEqual(agents.cli_failure([], 'Access is denied.\n'), 'Access is denied.')
        self.assertEqual(agents.cli_failure(['plain prose output'], ERR), 'plain prose output')

    def test_a_run_that_said_nothing_at_all_says_so(self):
        self.assertEqual(agents.cli_failure([], ''), 'no output')
        self.assertEqual(agents.cli_failure([], ERR), 'no output')      # noise alone is not a reason

    def test_a_successful_looking_stream_offers_no_failure(self):
        """It must not read an ordinary event as a fault - only a real crash is a crash."""
        ok = ['{"type":"item.completed","item":{"id":"i1","type":"agent_message","text":"done"}}']
        self.assertEqual(agents.cli_failure(ok, ''), ok[0])             # falls through to the tail
