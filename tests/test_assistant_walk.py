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


def test_what_brings_something_up_says_it_in_a_few_words(rows):
    """The owner, 2026-10-21: "free text should almost never be used in the assistant - it should be bringing up UI components"."""
    bad = [(r['step'].text, W.words(r['say']), r['say'][:160]) for r in rows if not r['brief']]
    assert not bad, bad


def test_the_walks_lines_name_what_comes_up_and_repeat_nothing_its_card_shows():
    """Every item Next brings up on the desk - the FYI handful, a report, a draft, a to-do - comes with a few words naming it,
    never its sender, its subject or its gist beside the card that shows them (the walk read the four FYIs out over their card)."""
    from contextlib import ExitStack
    from taskuary import concierge
    s, seen = W.world(), []
    with ExitStack() as st:
        W._guards(st, set())
        for _ in range(30):
            out = concierge.surface(s)
            it = out.get('item')
            if not it or it['key'] in [k for k, _ in seen]: break
            seen.append((it['key'], out['say']))
            shown = [it.get('title'), it.get('who'), it.get('preview')] + [x for e in it.get('items') or [] for x in (e.get('title'), e.get('who'))]
            assert W.words(out['say']) <= W.BRIEF, (it['key'], out['say'])
            assert not [x for x in shown if x and len(str(x)) > 3 and str(x) in out['say']], (it['key'], out['say'])
            concierge.move_on(s, it['key'], 'owner')
    assert {k.split(':')[0] for k, _ in seen} >= {'msg', 'review', 'report', 'fyis'}, seen       # every kind of card the demo has


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


def test_a_typed_turn_builds_the_pipe_once_and_says_the_owners_line_once():
    """The speed pass, 2026-10-27: the owner's line, written first, moved the store's mark, and the Advisor's decision and SELECT's
    values read after it each rebuilt the whole pipe the turn had just built - 150-260 ms of every typed turn before the model was
    asked, more on a real mailbox. And the line itself rode twice: the last row of CONVERSATION SO FAR, then "The owner says"."""
    from contextlib import ExitStack
    from unittest import mock
    from taskuary import concierge, funnel
    s, asked, whole = W.world(), [], []
    build = funnel.build
    def counted(store, *a, **k):
        if not k.get('keys'): whole.append(1)
        return build(store, *a, **k)
    with ExitStack() as st:
        W._guards(st, set())
        st.enter_context(mock.patch.object(funnel, 'build', counted))
        llm = lambda system, user, **k: (asked.append(user), 'Ok.')[1]
        concierge.say(s, 'bring up TQ-12', llm=llm)
        whole.clear(); asked.clear()
        concierge.say(s, "what's this one about", key='msg:17', llm=llm)
    assert len(whole) == 1, f'the pipe was built {len(whole)} times in one typed turn'
    assert 'OWNER: bring up TQ-12' in asked[0] and "OWNER: what's this one about" not in asked[0]
    assert asked[0].count("what's this one about") == 1
