"""Taskuary as a SOURCE of an Assistant report (five cards over the sixteen blocks), and a prompt
that names its sources (`[taskuary.messages]`, `[intacct.ap bills due]`) - the owner, 2026-09-20:
"different cards as data sources, the cards should be Taskuary itself... combine them as much as
possible", and "insert into the prompt sections by data source", for every report."""
import json, pathlib, re, unittest

from taskuary import assistant, assistantblocks as B, reports
from taskuary.store import MemoryStore
import tests.test_appfacts as A


class CardTests(unittest.TestCase):
    def test_every_block_but_the_systems_is_on_exactly_one_card(self):
        seen = [b for c in B.CARDS for b in c.blocks]
        self.assertEqual(len(seen), len(set(seen)), 'a block on two cards')
        self.assertEqual(set(seen), {b.id for b in B.CATALOGUE} - {'system_checks'})
        for c in B.CARDS:
            for n, l, d, targets in c.knobs:
                for bid, opt in targets:
                    b = B.by_id(bid)
                    self.assertTrue(b and bid in c.blocks, f'{c.id}.{n} points off the card')
                    self.assertTrue((b.window and b.window[0] == opt) or opt in {k for k, _, _ in b.knobs}, f'{bid} has no {opt}')

    def test_a_present_card_switches_its_blocks_on_and_an_absent_one_off(self):
        s = MemoryStore()
        chosen = B.from_cards(s, [{'type': 'taskuary', 'card': 'memory'}])
        self.assertTrue(all(chosen[b]['on'] for b in B.card('memory').blocks))
        self.assertFalse(any(chosen[b]['on'] for c in B.CARDS if c.id != 'memory' for b in c.blocks))
        self.assertTrue(chosen['system_checks']['on'])            # the systems cards are their own switch

    def test_one_number_on_the_card_lands_on_every_block_it_stands_for(self):
        s = MemoryStore()
        chosen = B.from_cards(s, [{'type': 'taskuary', 'card': 'messages', 'days': 9, 'hours': 'x'}])
        self.assertEqual((chosen['threads']['days'], chosen['arrivals']['days']), (9, 9))
        self.assertEqual((chosen['waiting_on']['hours'], chosen['promised']['hours']), (24, 24))   # a bad number keeps the default

    def test_a_saved_block_choice_shows_as_cards_and_comes_back_the_same(self):
        s = MemoryStore()
        chosen = {b.id: dict(B.defaults(s, b), on=False) for b in B.CATALOGUE}
        chosen['threads'] |= {'on': True, 'days': 5}; chosen['gone_quiet'] |= {'on': True, 'days': 4}
        cards = B.to_cards(chosen)
        self.assertEqual([c['card'] for c in cards], ['messages', 'work'])
        self.assertEqual((cards[0]['days'], cards[1]['quiet_days'], cards[1]['done_days']), (5, 4, 7))
        again = B.from_cards(s, cards)
        self.assertEqual((again['threads']['days'], again['gone_quiet']['days'], again['ooo']['on']), (5, 4, True))

    def test_the_cards_win_over_the_block_dict_and_an_empty_list_reads_nothing(self):
        s = MemoryStore()
        cfg = {'type': 'assistant', 'blocks': {'threads': {'on': True}}, 'taskuary_sources': [{'card': 'work'}]}
        chosen = B.resolve(s, cfg)
        self.assertTrue(chosen['open_work']['on']); self.assertFalse(chosen['threads']['on'])
        none = B.resolve(s, {'type': 'assistant', 'taskuary_sources': []})
        self.assertFalse(B.reads_taskuary(none))
        self.assertIsNone(B.cards_of({'type': 'assistant'}))
        self.assertEqual(B.cards_of({'taskuary_sources': [{'card': 'nope'}, {'card': 'work', 'x': 1}, {'card': 'work'}, 'junk']}),
                         [{'type': 'taskuary', 'card': 'work'}])

    def test_the_cards_are_priced_from_the_blocks(self):
        s = A.store()
        chosen = B.from_cards(s, [{'card': 'memory'}, {'card': 'calendar'}])
        cards = B.price_cards(B.weigh(s, chosen), chosen)
        by = {c['id']: c for c in cards}
        self.assertTrue(by['memory']['on'] and not by['work']['on'])
        self.assertTrue(by['calendar']['live'])                    # the calendar's cost is time
        self.assertEqual(by['work']['tokens'], 0)
        self.assertEqual([k['name'] for k in by['work']['knobs']], ['done_days', 'quiet_days'])

    def test_the_page_and_the_server_name_the_same_cards(self):
        js = pathlib.Path(__file__).resolve().parents[1] / 'website' / 'src' / 'assistantBlocks.js'
        text = js.read_text(encoding='utf-8')
        body = text[text.index('export const TASKUARY_CARDS'):text.index('export const cardsOf')]
        self.assertEqual(re.findall(r'\{ id: "([a-z_]+)", label', body), [c.id for c in B.CARDS])
        self.assertEqual(re.findall(r'label: "([A-Z][^"]+)"', body), [c.label for c in B.CARDS])
        for c in B.CARDS:
            for n, l, d, _ in c.knobs:
                self.assertIn(f'{{ name: "{n}", label: "{l}", default: {d} }}', body, f'{c.id}.{n} differs on the page')


class SubstituteTests(unittest.TestCase):
    def test_a_named_source_is_placed_and_an_unknown_one_stays_visible(self):
        text, used, missing = reports.substitute('Look at [Intacct.AP  bills due] then [taskuary.messages]. Also [x.y].',
                                                 {'intacct.ap bills due': 'ROWS', 'taskuary.messages': 'MSGS'})
        self.assertIn('ROWS', text); self.assertIn('MSGS', text); self.assertIn('[x.y]', text)
        self.assertEqual((used, missing), ({'intacct.ap bills due', 'taskuary.messages'}, ['[x.y]']))

    def test_a_prompt_naming_nothing_is_left_alone(self):
        self.assertEqual(reports.substitute('plain words', {'a.b': 'x'}), ('plain words', set(), []))
        self.assertFalse(reports.names_sources('plain words')); self.assertTrue(reports.names_sources('[a.b]'))

    def test_the_key_is_the_type_and_the_label(self):
        self.assertEqual(reports.source_key({'type': 'intacct', 'label': ' AP  Bills Due '}, 1), 'intacct.ap bills due')
        self.assertEqual(reports.source_key({'type': 'mssql'}, 2), 'mssql.mssql #2')

    def test_a_report_prompt_gets_the_named_source_in_place_and_the_rest_underneath(self):
        s = MemoryStore()
        seen = {}
        def llm(system, user, **kw): seen['user'] = user; return 'fine'
        reports.REGISTRY['_a'] = lambda cfg: ('2 rows', 'A-ROWS')
        reports.REGISTRY['_b'] = lambda cfg: ('1 row', 'B-ROWS')
        try:
            cfg = {'title': 't', 'sources': [{'type': '_a', 'label': 'first'}, {'type': '_b', 'label': 'second'}],
                   'ai_prompt': 'Compare [_a.first] with the rest.'}
            reports.render_report(s, cfg, llm)
            u = seen['user']
            self.assertLess(u.index('A-ROWS'), u.index('Data ('))          # placed in the instruction
            self.assertGreater(u.index('B-ROWS'), u.index('Data ('))       # the rest underneath
            self.assertEqual(u.count('A-ROWS'), 1)
            cfg['ai_prompt'] = 'Summarise.'
            reports.render_report(s, cfg, llm)
            self.assertTrue(seen['user'].startswith('Instruction: Summarise.'))
            self.assertLess(seen['user'].index('Data ('), seen['user'].index('A-ROWS'))
        finally:
            reports.REGISTRY.pop('_a', None); reports.REGISTRY.pop('_b', None)

    def test_the_assistant_places_a_named_card_in_its_instruction_and_not_below(self):
        s = A.store()
        seen = {}
        def llm(system, user, **kw): seen['system'], seen['user'] = system, user; return '{"say": []}'
        chosen = B.from_cards(s, [{'card': 'memory'}, {'card': 'work'}])
        assistant.think(s, [], llm, 'Never repeat these: [taskuary.memory]. Now the rest.', blocks=chosen)
        self.assertIn('ALREADY SAID (never repeat)', seen['system']); self.assertNotIn('ALREADY SAID (never repeat)', seen['user'])
        self.assertIn('OPEN WORK', seen['user']); self.assertNotIn('OPEN WORK', seen['system'])
        assistant.think(s, [], llm, 'Plain.', blocks=chosen)
        self.assertNotIn('ALREADY SAID (never repeat)', seen['system']); self.assertIn('ALREADY SAID (never repeat)', seen['user'])   # the contract's own words mention the head; the section is the head with its rows

    def test_the_preview_is_the_placed_shape(self):
        s = A.store()
        chosen = B.from_cards(s, [{'card': 'memory'}])
        plain = assistant.facts(s, blocks=chosen, instruction='Plain.')
        self.assertTrue(plain.startswith('NOW:'))
        shaped = assistant.facts(s, blocks=chosen, instruction='Read [taskuary.memory] first.')
        self.assertTrue(shaped.startswith('YOUR INSTRUCTION'))
        self.assertEqual(shaped.count('ALREADY SAID (never repeat)'), 1)

    def test_a_card_with_nothing_rendered_still_answers_in_words(self):
        self.assertEqual(B.sections_by_card([('open_work', 'X')])['taskuary.calendar'], '(nothing in Taskuary · Calendar right now)')


if __name__ == '__main__':
    unittest.main()
