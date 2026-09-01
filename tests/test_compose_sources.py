"""Point a check at the systems it should read - without knowing what they are called.

"I don't know what fields off hand Intacct has set up" is the Assistant's Pipeline step in one
sentence: the form asks for an object name and a list of UPPERCASE field ids belonging to
somebody else's finance system. compose_sources answers that part. Same fence as the report
composer - a connected type, real keys, a question rather than a guess - minus the report:
no title, no schedule, nothing the card would ignore.
"""
import json
import unittest

from taskuary import compose
from taskuary.store import MemoryStore


def llm_saying(*answers):
    """A model that returns each answer in turn, recording what it was asked. test_compose has
    its own copy: a test module that imports a sibling only runs where the repo root happens to
    be on sys.path, which `python -m pytest` arranges and CI's bare `pytest` does not."""
    seen, it = [], iter(answers)
    def fn(system, user, max_tokens=None):
        seen.append({'system': system, 'user': json.loads(user)})
        return next(it)
    fn.seen = seen
    return fn


def src_answer(*sources, prompt=None, explain='because you asked', confidence='high'):
    out = {'sources': list(sources), 'explain': explain, 'confidence': confidence}
    if prompt: out['ai_prompt'] = prompt
    return json.dumps(out)


def with_intacct(store):
    c = next(x for x in store.list_connectors() if x['Type'] == 'intacct')
    store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'pw',
                          'ConfigJson': json.dumps({'sender_id': 'a', 'sender_password': 'b',
                                                    'user_id': 'c', 'company_id': 'd'})}, 'test')
    return store


class CardsNotReportsTests(unittest.TestCase):
    def setUp(self): self.s = with_intacct(MemoryStore())

    def test_an_ask_becomes_source_cards(self):
        llm = llm_saying(src_answer({'type': 'intacct', 'label': 'AP due', 'object': 'APBILL',
                                     'fields': ['VENDORID', 'TOTALDUE', 'WHENDUE'],
                                     'filters': [['WHENDUE', '<=', '09/30/2026']]},
                                    prompt='Flag anything over 10k or newly overdue.'))
        out = compose.compose_sources(self.s, 'AP bills due in the next 30 days', llm)
        self.assertEqual(out['sources'][0]['object'], 'APBILL')
        self.assertIn('VENDORID', out['sources'][0]['fields'])
        self.assertIn('10k', out['ai_prompt'])

    def test_report_level_keys_are_dropped_not_written_onto_a_card(self):
        """A card has no title and no schedule. Saving them there would put settings on a source
        that nothing reads, and the owner would believe they were scheduled."""
        llm = llm_saying(src_answer({'type': 'intacct', 'object': 'VENDOR', 'title': 'Vendors',
                                     'daily_at': '08:00', 'ai_prompt': 'summarize', 'max_rows': 50}))
        card = compose.compose_sources(self.s, 'the vendor list', llm)['sources'][0]
        self.assertEqual(card['object'], 'VENDOR')
        self.assertEqual(card['max_rows'], 50)
        for gone in ('title', 'daily_at', 'ai_prompt'): self.assertNotIn(gone, card)

    def test_the_card_the_owner_is_standing_on_is_told_to_the_model_and_caps_it_at_one(self):
        llm = llm_saying(src_answer({'type': 'intacct', 'object': 'GLENTRY'},
                                    {'type': 'intacct', 'object': 'APBILL'}))
        out = compose.compose_sources(self.s, 'journal detail for August', llm, one_type='intacct')
        self.assertEqual(len(out['sources']), 1)
        self.assertEqual(llm.seen[0]['user']['the_card_you_are_filling_in'], 'intacct')
        self.assertEqual(llm.seen[0]['user']['max_sources'], 1)

    def test_a_single_object_answer_is_read_as_one_card(self):
        """Asked for one card, models answer with one object about as often as a list of one."""
        llm = llm_saying(json.dumps({'source': {'type': 'intacct', 'object': 'VENDOR'}, 'explain': 'x'}))
        self.assertEqual(compose.compose_sources(self.s, 'vendors', llm, one_type='intacct')['sources'][0]['object'], 'VENDOR')

    def test_several_systems_come_back_as_several_cards(self):
        llm = llm_saying(src_answer({'type': 'intacct', 'label': 'AP due', 'object': 'APBILL'},
                                    {'type': 'local_file', 'label': 'census', 'path': 'C:/exports/census.csv'},
                                    prompt='Say what needs attention.'))
        out = compose.compose_sources(self.s, 'AP bills and the census file', llm)
        self.assertEqual([s['type'] for s in out['sources']], ['intacct', 'local_file'])

    def test_it_will_not_add_more_than_the_cap(self):
        many = [{'type': 'local_file', 'path': f'C:/x{i}.csv'} for i in range(12)]
        out = compose.compose_sources(self.s, 'everything', llm_saying(src_answer(*many)))
        self.assertEqual(len(out['sources']), compose.MAX_SOURCES)


class SameFenceTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def test_a_system_nobody_connected_is_refused(self):
        out = compose.compose_sources(self.s, 'our leads', llm_saying(src_answer({'type': 'salesforce'})))
        self.assertIn('unknown report type', out['error'])

    def test_a_card_that_cannot_run_is_refused_and_handed_back(self):
        out = compose.compose_sources(with_intacct(self.s), 'ap bills',
                                      llm_saying(src_answer({'type': 'intacct'})))
        self.assertIn('no object', out['error'])
        self.assertTrue(out['sources'])          # so the owner can see what it wanted

    def test_standing_on_a_disconnected_card_says_so_without_spending_a_call(self):
        llm = llm_saying(src_answer({'type': 'intacct', 'object': 'APBILL'}))
        out = compose.compose_sources(self.s, 'ap bills', llm, one_type='intacct')
        self.assertIn('intacct', out['error'])
        self.assertEqual(llm.seen, [])

    def test_questions_come_back_as_questions(self):
        llm = llm_saying(json.dumps({'questions': ['Which site?', 'Posted or entered date?']}))
        out = compose.compose_sources(self.s, 'bills for the facility', llm)
        self.assertEqual(len(out['questions']), 2)
        self.assertNotIn('sources', out)

    def test_the_answers_go_back_to_the_model(self):
        llm = llm_saying(src_answer({'type': 'local_file', 'path': 'C:/x.csv'}))
        compose.compose_sources(self.s, 'the census', llm, answers={'Which site?': 'Adelphi'})
        self.assertIn('answers_to_your_questions', llm.seen[0]['user'])

    def test_no_ai_configured_says_where_to_go(self):
        self.assertIn('Connections', compose.compose_sources(self.s, 'x', None)['error'])

    def test_an_empty_ask_is_not_a_source(self):
        self.assertTrue(compose.compose_sources(self.s, '  ', llm_saying(src_answer({'type': 'digest'})))['error'])

    def test_the_check_cannot_be_its_own_source(self):
        """The Assistant reading the Assistant is a loop. It is a real report type, so the model
        can see it in the catalog - it just may not be a card of a check."""
        out = compose.compose_sources(self.s, 'watch everything',
                                      llm_saying(src_answer({'type': 'assistant'},
                                                            {'type': 'local_file', 'path': 'C:/x.csv'})))
        self.assertEqual([s['type'] for s in out['sources']], ['local_file'])

    def test_the_check_alone_is_not_an_answer(self):
        out = compose.compose_sources(self.s, 'watch everything', llm_saying(src_answer({'type': 'assistant'})))
        self.assertIn('the check itself', out['error'])

    def test_an_answer_with_no_sources_says_so(self):
        out = compose.compose_sources(self.s, 'x', llm_saying(json.dumps({'explain': 'sure!'})))
        self.assertIn('without a data source', out['error'])


class LookAtTheRealSchemaTests(unittest.TestCase):
    """The whole point. A field id nobody remembers is read off the system, not guessed - which is
    what makes "AP bills due in 30 days" a card and not a plausible one."""
    def setUp(self): self.s = with_intacct(MemoryStore())

    def test_it_may_peek_before_writing_the_card(self):
        llm = llm_saying(json.dumps({'peek': {'type': 'automate', 'days': 1}}),
                         src_answer({'type': 'local_file', 'path': 'C:/x.csv'}))
        out = compose.compose_sources(self.s, 'what repeats?', llm)
        self.assertEqual(out['looked_at'], [{'type': 'automate', 'days': 1}])
        self.assertTrue(llm.seen[1]['user']['what_you_looked_at'][0]['result'])

    def test_intacct_field_ids_are_in_the_briefing_when_intacct_is_connected(self):
        llm = llm_saying(src_answer({'type': 'intacct', 'object': 'APBILL'}))
        compose.compose_sources(self.s, 'ap bills', llm)
        self.assertIn('intacct_fields', llm.seen[0]['system'])      # how to go and look
        self.assertIn('TOTALENTERED', llm.seen[0]['system'])

    def test_the_briefing_stays_home_where_intacct_is_not_connected(self):
        llm = llm_saying(src_answer({'type': 'local_file', 'path': 'C:/x.csv'}))
        compose.compose_sources(MemoryStore(), 'the census', llm)
        self.assertNotIn('SAGE INTACCT', llm.seen[0]['system'])

    def test_the_source_briefing_is_not_the_report_briefing(self):
        """It must not ask for a schedule or a title - the card has nowhere to put them."""
        llm = llm_saying(src_answer({'type': 'local_file', 'path': 'C:/x.csv'}))
        compose.compose_sources(self.s, 'the census', llm)
        sysmsg = llm.seen[0]['system']
        self.assertIn('DATA SOURCES', sysmsg)
        self.assertNotIn('"daily_at"', sysmsg)
        self.assertIn('Never invent a table, column, object or field name', sysmsg)   # the shared judgement


if __name__ == '__main__':
    unittest.main()
