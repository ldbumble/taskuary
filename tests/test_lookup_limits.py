"""Model-supplied lookup limits must not crash a turn or return unbounded results."""
from unittest import mock
import pytest
from taskuary import asks, concierge, lookups

@pytest.mark.parametrize('value', ['all', [], {}, float('inf'), float('nan')])
def test_invalid_limit_falls_back(value):
    assert lookups._limit({'limit': value}, 25, 60) == 25

@pytest.mark.parametrize('value, expected', [('-5', 1), ('1000', 60), ('3', 3), (None, 25)])
def test_limit_is_bounded(value, expected):
    assert lookups._limit({'limit': value}, 25, 60) == expected

@pytest.mark.parametrize('value, expected', [('all', 25), ('-5', 1), ('1000', 60)])
def test_tasks_list_applies_limit(value, expected):
    store = mock.Mock()
    store.list_tasks.return_value = [dict(TaskId=i, Status='open', Kind='general', Title='Synthetic task') for i in range(1, 71)]
    out = lookups.tasks_list(store, {'limit': value})
    assert sum(line.startswith('TQ-') for line in out.splitlines()) == expected

@pytest.mark.parametrize('value, expected', [('all', 20), ('-5', 1), ('1000', 60)])
def test_asks_list_applies_limit(value, expected):
    with mock.patch.object(asks, '_asked', return_value=[]) as asked:
        assert asks.listing(mock.Mock(), {'limit': value}) == 'No asks yet.'
    assert asked.call_args.args[2] == expected

@pytest.mark.parametrize('value, expected', [('all', 12), ('-5', 1), ('1000', 40)])
def test_timeline_search_applies_limit(value, expected):
    with mock.patch.object(concierge, 'search_timeline', return_value=[]) as search:
        assert concierge.read_op(mock.Mock(), 'timeline.search', {'limit': value}) == 'Nothing in the history matches that.'
    assert search.call_args.args[2] == expected + 1      # one more than shown, to tell a cut list from a whole one

def test_timeline_search_says_when_it_cut_the_list():
    # "anything from Gail this week?" read 12 of her 18 and was answered "twelve times ... nothing else from her" (2026-11-03)
    hit = lambda i: dict(mid=i, ref=f'TQ-{i:04d}', when='2026-11-03 09:00', who='Gail Moreno', title=f'Ask {i}')
    with mock.patch.object(concierge, 'search_timeline', side_effect=lambda st, sel, n: [hit(i) for i in range(1, min(n, 18) + 1)]):
        cut, whole = (concierge.read_op(mock.Mock(), 'timeline.search', {'sender': 'gail', 'limit': n}) for n in (12, 40))
    assert sum(l.startswith('m') for l in cut.splitlines()) == 12 and 'more match than these 12' in cut
    assert sum(l.startswith('m') for l in whole.splitlines()) == 18 and 'more match' not in whole
