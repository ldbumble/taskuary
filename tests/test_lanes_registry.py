"""ONE LANES REGISTRY, server side: every count, section and kind word the server says is built from taskuary/lanes.json - the page
builds the same tables from the same file (website/test/lanesRegistry.test.mjs)."""
import json, unittest
from pathlib import Path

from taskuary import assistant, concierge, funnel, lanes, processing_unread, remote_assistant, welcome

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / 'taskuary' / 'lanes.json').read_text(encoding='utf-8'))
PILE = [{'key': 'a', 'lane': 'asked', 'order_band': 2}, {'key': 'y', 'lane': 'yours', 'order_band': 2},
        {'key': 'b', 'lane': 'blocked', 'order_band': 2}, {'key': 't', 'lane': 'theirs', 'order_band': 2},
        {'key': 'l', 'lane': 'yours', 'order_band': 2, 'put_down': True}, {'key': 'd', 'lane': 'yours', 'order_band': 2, 'deferred': True},
        {'key': 'f', 'lane': 'fyi', 'order_band': 4},
        {'key': 'r', 'lane': 'report', 'order_band': 3}, {'key': 'w', 'lane': 'working', 'order_band': 2},
        {'key': 'm', 'lane': 'time', 'order_band': 1}, {'key': 's', 'lane': 'asked', 'order_band': 2, 'settling': True}]


class SectionTests(unittest.TestCase):
    def test_the_sections_are_lanes_json_s(self):
        self.assertEqual(remote_assistant.LEVEL_ORDER, tuple(s['key'] for s in VOCAB['sections']))
        self.assertEqual(funnel.SECTION_WORDS, {s['key']: s['word'] for s in VOCAB['sections']})
        # no Urgent section (the owner, 2026-10-22): an urgent row is drawn in Tasks, and the meeting's minutes live on `urgent`
        self.assertNotIn('urgent', funnel.SECTION_WORDS)
        self.assertEqual(funnel.ALERT_MIN, VOCAB['urgent']['minutes'])

    def test_a_row_with_no_band_lands_where_its_lane_says_and_the_server_band_agrees(self):
        for l in VOCAB['lanes']:
            self.assertIsInstance(l['on_you'], bool, l['key'])
            self.assertEqual(funnel.level_of({'lane': l['key']}), l['section'], l['key'])
            # the band the server stamps and the band a row without one gets are one function now
            self.assertEqual(funnel.level_of({'lane': l['key'], 'order_band': funnel._band({'lane': l['key']})}), l['section'], l['key'])
        self.assertEqual(funnel.level_of({'lane': 'unjudged', 'held': True}), 'task')
        self.assertEqual(funnel._band({'lane': 'yours', 'urgent_request': True}), 1)

    def test_owner_lanes_and_what_a_new_walk_raises_are_read_off_the_lanes(self):
        self.assertEqual(set(processing_unread.OWNER_LANES), {l['key'] for l in VOCAB['lanes'] if l['section'] == 'task'})
        self.assertEqual(set(processing_unread.RAISED_BY_NEW_WALK), {l['key'] for l in VOCAB['lanes'] if l.get('waits')})


class OnYouTests(unittest.TestCase):
    def test_the_greeting_and_the_opening_card_count_one_set(self):
        you = [i['key'] for i in PILE if lanes.on_you(i)]
        # a task Next walked past is still under Tasks, so still on you (the owner, 2026-10-21); not waiting on them, For later
        # (Remind me), reading, an agent at work - under Tasks, but not on you - nor a settling row
        self.assertEqual(you, ['a', 'y', 'b', 'l', 'm'])
        self.assertEqual(lanes.level_of(PILE[8]), 'task'); self.assertEqual(lanes.level_of(PILE[5]), 'later')
        self.assertEqual([i['key'] for i in welcome.needs_you(PILE)], you)
        self.assertEqual([i['key'] for i in PILE if lanes.to_read(i)], ['f', 'r'])

    def test_the_walk_leads_with_what_waits_on_the_owner(self):
        self.assertTrue(funnel.waits_on_you({'lane': 'approve'})); self.assertFalse(funnel.waits_on_you({'lane': 'yours'}))


class KindTests(unittest.TestCase):
    def test_every_kind_is_counted_in_lanes_json_s_words(self):
        for k, v in VOCAB['item_kinds'].items():
            self.assertEqual(lanes.kind_says(k, 1), f"1 {v['one']}"); self.assertEqual(lanes.kind_says(k, 2), f"2 {v['many']}")
        self.assertEqual(concierge.waiting_line([{'kind': 'goal_slipped'}, {'kind': 'review'}, {'kind': 'review'}]),
                         '3 waiting: 2 drafts to approve, 1 goal that slipped.')
        self.assertEqual(concierge.waiting_line([{'kind': 'nonsense'}]), '1 waiting: 1 other thing.')
        self.assertEqual(set(funnel.MAIL_KINDS), {k for k, v in VOCAB['item_kinds'].items() if v.get('mail')})

    def test_an_advisor_line_is_placed_by_its_kind(self):
        for k, v in VOCAB['idea_kinds'].items(): self.assertEqual(assistant.section_of({'kind': k}), v['section'], k)
        self.assertEqual(assistant.section_of({'kind': 'nonsense'}), 'ideas')
        self.assertEqual(assistant.section_of({'kind': 'followup', 'section': 'people'}), 'people')   # the model's own choice wins

    def test_no_copy_of_a_table_is_left_on_the_server(self):
        read = lambda f: (ROOT / 'taskuary' / f).read_text(encoding='utf-8')
        self.assertNotIn('_BAND_FALLBACK', read('funnel.py')); self.assertNotIn("ON_YOU = ('blocked'", read('funnel.py'))
        self.assertNotIn('KIND_SAYS', read('concierge.py')); self.assertNotIn('KIND_SECTION', read('assistant.py'))
        self.assertNotIn("('urgent', 'task', 'later')", read('welcome.py'))
        self.assertNotIn("OWNER_LANES = ('", read('processing_unread.py'))


class StateWordsAreWrittenOnce(unittest.TestCase):
    """A state's word lives in lanes.json and nowhere else (the cleanup round, 2026-10-18): the phone typed "stopped and saved" and
    "agent finished" beside the json that already said them. Multi-word ones only - "done" and "report" are ordinary English too."""
    def test_word_reads_the_json(self):
        for g in ('lanes', 'kinds', 'states'):
            for r in VOCAB[g]: self.assertEqual(lanes.word(r['key']), r['word'], r['key'])
        self.assertEqual(lanes.word('no-such-state'), '')

    def test_no_module_retypes_one(self):
        import ast, io, tokenize
        words, hits = {w for w in lanes.WORD.values() if ' ' in w}, []
        for p in sorted((ROOT / 'taskuary').rglob('*.py')):
            for t in tokenize.generate_tokens(io.StringIO(p.read_text(encoding='utf-8')).readline):
                if t.type != tokenize.STRING: continue
                try: v = ast.literal_eval(t.string)
                except (ValueError, SyntaxError): continue
                if v in words: hits.append(f'{p.relative_to(ROOT)}:{t.start[0]}: {v}')
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
