"""What the model is OFFERED must be what the selector can FIND.

2026-09-10. The owner asked to clear the assistant's fyi rows and was told "Nothing in the pipe
matches category: assistant, kind: fyi, so there is nothing to clear" - about eleven rows they were
looking at. The model had not guessed: `toolcatalog.selector` advertised `assistant` as a category,
because `vocabularies` read funnel.build(keep_surfaced=True) - the whole timeline, all-time - while
`concierge.select_items` only ever filtered the live pipe. Five categories were offered that could
not possibly match: assistant, automated, error, filed, yours.

select_items already carried this lesson for itself ("it offered to clear 72 when seven were
actually waiting", 2026-09-07). The menu was left reading the wide set.
"""
import json, unittest
from datetime import datetime, timedelta

from taskuary import concierge, funnel, toolcatalog
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def fyi(s, subject, hours=3, category='info'):
    mid = s.add_message({'ExternalId': f'f:{subject}', 'ConversationId': f'fc:{subject}', 'Channel': 'email',
                         'Subject': subject, 'FromName': 'A List', 'FromEmail': 'list@vendor.com',
                         'SentAt': ago(hours), 'BodyText': 'for your information', 'Status': 'filed',
                         'Category': category})
    return mid


def findable(s, cat):
    return bool(concierge.select_items(s, {"category": cat}))


def read_already(s, key):
    """Shown and settled - off the pipe, still on the timeline. keep_surfaced=True sees these."""
    s.set_funnel_state(key, 'done', 'owner')
    funnel.invalidate(); funnel.forget_states()


class TheMenuMatchesTheSearchTests(unittest.TestCase):
    def test_every_offered_category_can_actually_be_found(self):
        """The invariant. A value in the menu that matches nothing is a dead end the owner is
        invited to walk into, and the answer blames the pipe rather than the menu."""
        s = store()
        for n in range(3): fyi(s, f'live {n}', category='info')
        gone = fyi(s, 'settled long ago', hours=5, category='promo')
        read_already(s, f'msg:{gone}')
        v = toolcatalog.vocabularies(s)
        for cat in v['category']:
            self.assertTrue(concierge.select_items(s, {'category': cat}),
                            f'category {cat!r} is offered but matches nothing in the pipe')
        for kind in v['kind']:
            self.assertTrue(concierge.select_items(s, {'kind': kind}),
                            f'kind {kind!r} is offered but matches nothing in the pipe')

    def test_what_is_offered_never_exceeds_what_is_in_the_pipe(self):
        """The exact shape of the bug: a settled row keeps its category on the timeline, and the menu
        read from there. Stated as a subset rather than a named value, because the categories are
        DERIVED - naming one in a fixture only tests the derivation."""
        s = store()
        fyi(s, 'still waiting')
        gone = fyi(s, 'dealt with', hours=6)
        read_already(s, f'msg:{gone}')
        pipe = {str(i.get('category') or '') for i in funnel.build(s)['items']} - {''}
        wide = {str(i.get('category') or '') for i in funnel.build(s, keep_surfaced=True)['items']} - {''}
        offered = set(toolcatalog.vocabularies(s)['category'])
        self.assertTrue(offered <= pipe, f'offered but not in the pipe: {sorted(offered - pipe)}')
        self.assertTrue(pipe <= wide, 'the pipe is a subset of the timeline, by definition')

    def test_the_block_the_model_reads_names_only_findable_values(self):
        """Through selector() as the model actually receives it, not just the dict behind it."""
        s = store()
        for n in range(2): fyi(s, f'live {n}')
        block = toolcatalog.selector(s)
        line = next(l for l in block.splitlines() if l.strip().startswith('category'))
        for cat in [c.strip() for c in line.split(':', 1)[1].split(',') if c.strip()]:
            self.assertTrue(findable(s, cat), f'{cat} is advertised in the block but matches nothing')


class AMissSaysWhatIsThereTests(unittest.TestCase):
    def test_a_miss_reports_what_the_pipe_actually_holds(self):
        s = store()
        for n in range(3): fyi(s, f'newsletter {n}')
        held = concierge.pipe_holds(s)
        self.assertIn('The pipe holds 3', held)
        self.assertIn('fyi', held)

    def test_an_empty_pipe_says_so_rather_than_listing_nothing(self):
        self.assertEqual(concierge.pipe_holds(store()), 'The pipe is empty.')

    def test_the_clear_turn_tells_the_owner_what_is_there_on_a_miss(self):
        s = store()
        for n in range(2): fyi(s, f'newsletter {n}')
        out = concierge.call_turn(s, 1, {'kind': 'pipe.clear', 'params': {'select': {'category': 'assistant'}}},
                                  None, 'clear the assistant fyi')
        self.assertIn('Nothing in the pipe matches', out['say'])
        self.assertIn('The pipe holds 2', out['say'])          # ...and what IS there
        self.assertIn('nothing has been touched', out['say'])


if __name__ == '__main__':
    unittest.main()
