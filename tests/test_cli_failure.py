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
        self.assertEqual(agents.cli_failure(ok, ''), 'no reason given')  # ...and never offers the event's JSON as one either


# ── A ONE-SHOT RUN THAT EXITED NON-ZERO, read as the CLI said it (workstream 6) ──────────────────────────────────────────────────────
import json, sys
from pathlib import Path
from unittest import mock
import pytest
from taskuary import clipool

FAKE = [sys.executable, str(Path(__file__).parent / 'fake_claude.py')]


def one_shot(tmp_path, events, code=1):
    "A one-shot claude (the argv road) that says `events` after its init, then exits `code`: (what run_cli returned, or what it raised)."
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': '.', 'exit': code, 'events': events}]))
    prof = {'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose'], 'cwd': str(Path(__file__).parent)}
    with mock.patch.object(agents, '_resolve_cmd', return_value=FAKE):
        try: return agents.run_cli(prof, 'go', lambda *a: None, extra_env={'FAKE_CLAUDE_SCRIPT': str(rules), 'FAKE_CLAUDE_SPAWN': '0', 'FAKE_CLAUDE_THINK': '0'})
        except Exception as e: return e


@pytest.mark.parametrize('event, words', [
    ({'type': 'turn.failed', 'error': {'message': "The model 'gpt-x' does not exist or you do not have access to it."}}, "The model 'gpt-x' does not exist"),
    ({'type': 'error', 'message': 'The workspace quota for tool calls was used up.'}, 'The workspace quota for tool calls was used up.'),
    ({'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'The request was too large for this model.'}, 'The request was too large'),
], ids=['turn.failed', 'error', 'result is_error'])
def test_a_one_shot_run_that_dies_says_the_reason_its_cli_gave(event, words, tmp_path):
    """A death with only events on stdout was said as the generic "stopped in the middle of its turn", over the CLI's own stated reason - and
    the log lost it too. Where an event says why, those words are the reason (cli_failure, _event_error); the sentence only where none does."""
    got = one_shot(tmp_path, [event])
    assert isinstance(got, RuntimeError) and words in str(got) and clipool.MID_TURN not in str(got), got
    assert '"type"' not in str(got), got                 # ...its words, never the event's JSON (a tail line carries the words too)


def test_a_one_shot_claude_that_dies_after_only_its_init_says_the_one_sentence_with_its_conversation(tmp_path):
    """It showed the owner "claude exit 3: {"type": "system", ...}" - the events' JSON - for a CLI that died before a word, where the kept road
    and ACP say clipool.MID_TURN. It says that sentence, as an end part-way that keeps its conversation."""
    got = one_shot(tmp_path, [], code=3)
    assert isinstance(got, clipool.PartWay) and str(got) == clipool.MID_TURN and got.session_id, got


def test_a_finished_answer_followed_by_a_non_zero_exit_is_kept_as_the_answer(tmp_path):
    """Decided on purpose: claude printed its words and a successful result, then exited non-zero. It was told "stopped in the middle" (untrue)
    and the answer thrown away; the answer is the turn's, the exit the log's."""
    got = one_shot(tmp_path, [{'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'The ledger is reconciled.'}]}},
                              {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'The ledger is reconciled.'}])
    assert isinstance(got, tuple) and got[0] == 'The ledger is reconciled.' and got[1], got


@pytest.mark.parametrize('final', [{'result': 'partial', 'error': 'crashed'},
                                   {'type': 'result', 'subtype': 'error_during_execution', 'result': 'Half of the ledger.'}],
                         ids=['a bare result', 'an error subtype'])
def test_only_a_successful_result_event_keeps_an_answer_past_a_non_zero_exit(final, tmp_path):
    """The keep took any dict with a `result` as the finished answer: {"result": "partial", "error": "crashed"} and exit 1 came back as a
    success, to triage and drafts alike. Only claude's own result event, said as a success, is a finished answer."""
    got = one_shot(tmp_path, [final])
    assert isinstance(got, RuntimeError), got


def test_a_stream_cut_mid_line_is_a_death_part_way_never_its_events_json(tmp_path):
    """Killed while writing (exit 137): init, its words, then `{"type": "res` cut off. The cut line was no event, so the run fell to the
    stand-in reason - its last lines, the events' JSON ("claude exit 137: {"type": "system", ...}") - and lost its conversation. A line that
    opens as an event is a cut event (agents._is_event), and no reason is ever the events themselves (cli_failure)."""
    got = one_shot(tmp_path, [{'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Half of the ledger.'}]}},
                              '{"type": "res'], code=137)
    assert isinstance(got, clipool.PartWay) and str(got) == clipool.MID_TURN and got.session_id, got
    assert agents.cli_failure(['{"type": "system", "subtype": "init"}', '{"type": "res'], '') == 'no reason given'


def test_a_successful_result_with_no_words_and_a_non_zero_exit_is_a_finished_empty_answer(tmp_path):
    """Claude said its turn succeeded, with no words, then exited non-zero: it was told "stopped in the middle of its turn" - it had not. It is
    the finished turn it said it was, empty, as at exit 0."""
    got = one_shot(tmp_path, [{'type': 'result', 'subtype': 'success', 'is_error': False, 'result': ''}])
    assert isinstance(got, tuple) and got[0] == '' and got[1], got


def printed(tmp_path, lines, code=1, err='', cmd='gemini', args=('-p',)):
    "A CLI that prints `lines` as they are (and `err`), then exits `code`: what run_cli returned, or what it raised."
    spec = tmp_path / 'spec.json'; spec.write_text(json.dumps({'lines': lines, 'code': code, 'err': err}))
    with mock.patch.object(agents, '_resolve_cmd', return_value=FAKE):
        try: return agents.run_cli({'cmd': cmd, 'args': list(args), 'cwd': str(Path(__file__).parent)}, 'go', lambda *a: None, extra_env={'FAKE_CLAUDE_PRINTS': str(spec)})
        except Exception as e: return e


@pytest.mark.parametrize('lines, words', [
    (["{'error': 'API key not valid'}"], "{'error': 'API key not valid'}"),
    (['{ Error: ENOSPC: no space left on device, write', '    at Object.writeSync (node:fs:927:3) }'], 'ENOSPC: no space left on device'),
    (['Working...', "{ status: 'RESOURCE_EXHAUSTED' }"], 'RESOURCE_EXHAUSTED'),
    (['{"error": {"code": 401, "message": "API key not valid. Please pass a valid API key."}}'], 'API key not valid. Please pass a valid API key.'),
], ids=['a dict repr', 'a stack dump in braces', 'words then braces', 'a bare error object'])
def test_words_a_cli_printed_in_braces_are_its_reason_never_a_death_part_way(lines, words, tmp_path):
    """Any line opening with a brace was taken for an event: a text CLI's own error words were dropped, and the owner read "the agent stopped in
    the middle of its turn. It may have done part of the work" over a run that did nothing. Only a JSON object is an event (and a stream's last
    line cut off as it was killed); the rest is words, and its reason."""
    got = printed(tmp_path, lines)
    assert isinstance(got, RuntimeError) and not isinstance(got, clipool.PartWay) and words in str(got), got


def test_a_stream_of_events_with_only_the_stdin_notice_on_stderr_is_a_death_part_way(tmp_path):
    """Claude printed its events and died, its stderr holding only its own "Reading prompt from stdin..." notice: that notice counted as a
    reason, and the owner read "claude exit 1: no output" after a stream of events. A CLI's own notice is no reason."""
    got = printed(tmp_path, [json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 's-1'})], err='Reading prompt from stdin...',
                  cmd='claude', args=('-p', '--output-format', 'stream-json', '--verbose'))
    assert isinstance(got, clipool.PartWay) and str(got) == clipool.MID_TURN and got.session_id == 's-1', got


def test_a_one_shot_turn_that_reached_its_limit_reads_the_one_sentence_for_it(tmp_path):
    """claude's error_max_turns on the one-shot road read "Reached max turns (3)" - a third wording of the fact ACP and the kept road say in the
    one sentence for a limit (clipool.ended_early). It is that sentence, as a turn that ended part-way, with its conversation."""
    got = one_shot(tmp_path, [{'type': 'result', 'subtype': 'error_max_turns', 'is_error': True, 'errors': ['Reached max turns (3)']}])
    assert isinstance(got, clipool.PartWay) and str(got) == clipool.ended_early('error_max_turns') and got.session_id, got
