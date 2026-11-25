"""textsim: which texts are about the same thing, by embeddings - a ranking for the model, None when there is no embedder, so the
caller's structural road decides. The embedder is a stand-in; nothing here reaches a server."""
from unittest import mock

from taskuary import kbembed, textsim
from taskuary.store import MemoryStore
from tests import fake_embed


def test_no_embedder_is_none_never_an_empty_ranking():
    s = MemoryStore()
    assert textsim.rank(s, 'anything', [('task:1', 'Reconcile the Payworth invoice')]) is None, 'semantic search is off by default'


def test_the_nearest_come_first_and_none_under_the_floor():
    s = MemoryStore()
    with fake_embed.meaning({'refund': ['refund'], 'printer': ['printer']}):
        got = textsim.rank(s, 'Can you approve the refund for Gail?', [('task:1', 'Approve the Q3 refund'), ('task:2', 'Printer jammed'),
                                                                       ('task:3', '')])
    assert [k for k, _ in got] == ['task:1'] and got[0][1] > 0.99


def test_a_failing_embedder_falls_back_and_is_not_asked_again_at_once():
    s = MemoryStore(); calls = []
    def broken(texts): calls.append(texts); raise RuntimeError('server down')
    broken.model = 'broken'
    with mock.patch.object(kbembed, 'make', lambda store, timeout=None: broken), mock.patch.dict(textsim._state, {'down_until': 0.0}):
        assert textsim.rank(s, 'a question', [('task:1', 'a task')]) is None
        assert textsim.rank(s, 'a question', [('task:1', 'a task')]) is None
        assert len(calls) == 1, 'a server that just failed is not asked again inside the back-off'


def test_vectors_are_kept_by_key_and_redone_when_the_text_changes():
    s = MemoryStore(); e = fake_embed.embedder({'a': ['alpha']})
    textsim.vectors(s, e, [('task:1', 'alpha one'), ('task:2', 'beta')])
    textsim.vectors(s, e, [('task:1', 'alpha one'), ('task:2', 'beta')])
    textsim.vectors(s, e, [('task:1', 'alpha two'), ('task:2', 'beta')])
    assert e.calls == [['alpha one', 'beta'], ['alpha two']]


def test_two_tasks_picked_over_the_same_lists_share_the_lists_as_one_cached_head():
    """The light model's pick reads ~400 closed titles and the Hub's posts - the same for every task until one closes. With the task in
    front, every pick was a new prompt from its first line (8% of a week's 'rank' tokens cached); the task now comes last."""
    seen = []
    def brain(system, user, **kw): seen.append(system + user); return '{"picks": []}'
    groups = {'repo': [('repo:northwind/ledger', 'northwind/ledger: the GL')], 'hub': [(f'lore:{i}', f'[ops] note {i} on the import') for i in range(60)],
              'past': [(f'task:{i}', f'Closed task {i}: reconcile the Payworth invoice batch') for i in range(200)]}
    with fake_embed.no_embedder():
        for q in ('Reconcile the October Payworth invoice', 'Set up the Trainly seats for the new starter'):
            textsim.pick(MemoryStore(), q, groups, brain=brain)
    a, b = seen
    common = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
    assert common >= 0.9 * len(a) and a.endswith('Reconcile the October Payworth invoice'), 'the lists are the head, the task its own tail'
