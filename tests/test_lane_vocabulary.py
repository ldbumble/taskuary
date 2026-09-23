"""One lane vocabulary, in one file, for both languages.

The words a lane wears were kept by hand in two tables - `funnel.LANE_WORDS`/`LANE_MARKS` here and
`LANE_META` in website/src/funnelPile.js - plus a third copy of the counting words written out inline
in AssistantView. Nothing checked them against each other, so they drifted: the server said a report
lane reads "landed" while the page said "report", and there was no way to tell which was the mistake
(the owner, 2026-09-15: "we built one idea and then it was changed... it's in a bunch of places").

Both sides now build their tables from taskuary/lanes.json. These tests keep it that way: a word
added to one language and not the other is not possible, because there is only one place to add it.
"""
import json
import re
from pathlib import Path

import pytest

from taskuary import funnel

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / 'taskuary' / 'lanes.json').read_text(encoding='utf-8'))
PILE_JS = (ROOT / 'website' / 'src' / 'funnelPile.js').read_text(encoding='utf-8')


def test_the_python_tables_are_the_file():
    assert funnel.LANES == tuple(l['key'] for l in VOCAB['lanes'])
    for lane in VOCAB['lanes']:
        assert funnel.LANE_WORDS[lane['key']] == (lane['word'], lane['role'])
        assert funnel.LANE_MARKS[lane['key']] == lane['mark']
    assert set(funnel.KIND_MARKS) == {k['key'] for k in VOCAB['kinds']}


def test_the_desktop_builds_its_table_from_the_same_file_rather_than_its_own():
    assert 'import vocab from "../../taskuary/lanes.json"' in PILE_JS
    assert 'export const LANE_META = byKey(vocab.lanes);' in PILE_JS
    assert 'export const KIND_META = byKey(vocab.kinds);' in PILE_JS
    # ...and no hand-written lane table grew back beside it
    assert not re.search(r'LANE_META\s*=\s*\{', PILE_JS), 'the lane table is the file, not a literal'


@pytest.mark.parametrize('lane', VOCAB['lanes'], ids=lambda l: l['key'])
def test_every_lane_carries_a_full_entry(lane):
    assert lane['word'] and lane['mark'] and lane['hint']
    assert 'role' in lane, 'a lane with no colour says so with null, it does not omit the key'
    assert lane['role'] is None or lane['role'] in {'you', 'working', 'info', 'done', 'muted', 'bad'}


def test_only_the_lane_that_needs_a_counting_form_has_one():
    """"3 landed" is English; "3 report" is not - the one reason a lane ever carried two words.
    Every other lane counts under the word it wears, and `counted` defaults to it."""
    counted = {l['key']: l.get('counted') for l in VOCAB['lanes'] if l.get('counted')}
    assert counted == {'report': 'landed'}
    for lane in VOCAB['lanes']:
        assert funnel.LANE_COUNTED[lane['key']] == (lane.get('counted') or lane['word'])


def test_the_pipe_summary_counts_in_the_counting_word():
    items = [{'lane': 'report'}, {'lane': 'report'}, {'lane': 'fyi'}]
    line = funnel.summary(items, coming=False)
    assert '2 landed' in line and '1 fyi' in line
    assert '2 report' not in line


def test_a_lane_label_still_reads_as_the_row_does():
    """The label on a card, and the `lanes` array the rail is sent, use the row's own word."""
    assert funnel.LANE_WORDS['report'][0] == 'report'


def test_the_walk_line_reads_its_counting_words_from_the_vocabulary():
    # the walk opens with who wants what now (walkSummary.js, 2026-09-23); each row's word is the lane's
    # own word from the one vocabulary, never a copy written into the page
    view = (ROOT / 'website' / 'src' / 'AssistantView.jsx').read_text(encoding='utf-8')
    cards = (ROOT / 'website' / 'src' / 'assistantCards.jsx').read_text(encoding='utf-8')
    walk = (ROOT / 'website' / 'src' / 'walkSummary.js').read_text(encoding='utf-8')
    assert 'summarize(items).lead' in view
    assert 'stateOf(i, laneMeta(i.lane).word)' in cards
    assert '["landed", "report"]' not in view + walk, 'the third copy of the counting words is gone'
    assert 'agent waving' not in walk and 'asked you' not in walk
