"""The desk Assistant walked through on a CLI brain (tests/assistant_walk.py): every step does what the words asked, says what it
did, and answers inside its time on the stand-in claude's realistic timings (tests/fake_claude.py) - the owner, 2026-10-20: "even
using the Claude CLI backend (headless) it should respond to things quickly"."""
import pytest

from tests import assistant_walk as W


@pytest.fixture(scope='module')
def rows():
    rows = W.run()
    print('\n' + W.table(rows).encode('ascii', 'replace').decode())     # a cp1252 console cannot print the step's arrow
    return rows


def test_every_step_does_what_it_was_asked(rows):
    bad = [(r['step'].text, r['step'].expect, r['got'], r['say'][:160]) for r in rows if not r['ok']]
    assert not bad, bad


def test_every_answer_says_what_it_did(rows):
    bad = [(r['step'].text, r['say'][:160]) for r in rows if not r['said_ok']]
    assert not bad, bad


def test_every_step_answers_inside_its_budget(rows):
    over = [(r['step'].text, round(r['first_word'], 2), round(r['action'], 2), r['step'].budget) for r in rows
            if r['first_word'] > r['step'].budget[0] or r['action'] > r['step'].budget[1]]
    assert not over, over


def test_one_process_serves_the_whole_walk_and_it_was_started_before_the_first_ask(rows):
    assert [r['spawns'] for r in rows] == [0] * len(rows)          # warmed when the page opened; never restarted under a turn
    assert rows[0]['warm'] > 0


def test_the_words_come_before_the_answer_is_whole(rows):
    worded = [r for r in rows if r['first_word'] < r['action'] - 0.1]
    assert len(worded) >= len(rows) - 1, [(r['step'].text, r['first_word'], r['action']) for r in rows]
