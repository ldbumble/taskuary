"""Say what you want; get a report configuration.

The composer is a model writing a config, so what these cover is the fence around it: it may
only choose types this install can actually run, it may not invent config keys or systems, and
it is allowed - expected - to ask rather than guess.
"""
import json, os, tempfile
import unittest

from taskuary import compose
from taskuary.store import MemoryStore


def llm_saying(*answers):
    """A model that returns each answer in turn, recording what it was asked."""
    seen, it = [], iter(answers)
    def fn(system, user, max_tokens=None):
        seen.append({'system': system, 'user': json.loads(user)})
        return next(it)
    fn.seen = seen
    return fn


def cfg_answer(**cfg):
    return json.dumps({'config': cfg, 'explain': 'because you asked', 'confidence': 'high'})


class CatalogTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def test_it_lists_what_this_install_can_run(self):
        types = {c['type'] for c in compose.catalog(self.s)}
        self.assertIn('local_file', types)
        self.assertIn('intacct', types)
        self.assertNotIn('sharepoint_list', types)      # planned types are not offered as choices

    def test_every_type_carries_its_config_keys(self):
        """Taken from the executors' own docstrings, so the composer cannot believe a type
        takes keys the executor does not read."""
        row = next(c for c in compose.catalog(self.s) if c['type'] == 'sqlite')
        self.assertIn('query', row['takes'])
        self.assertIn('db', row['takes'])

    def test_a_type_with_no_connection_is_ready(self):
        """local_file reads a path on this machine - there is no card to connect."""
        row = next(c for c in compose.catalog(self.s) if c['type'] == 'local_file')
        self.assertTrue(row['ready'])
        self.assertIsNone(row['connection'])

    def test_an_unconnected_type_is_listed_but_not_ready(self):
        """Listed, so the composer can say what you would have to connect - rather than
        silently substituting something else."""
        row = next(c for c in compose.catalog(self.s) if c['type'] == 'intacct')
        self.assertFalse(row['ready'])
        self.assertEqual(row['connection'], 'intacct')
        self.assertTrue(row['why_not'])

    def test_switching_the_card_on_makes_it_ready(self):
        """The card exists from first launch (off), so this is a flip, not a create."""
        c = self.s.get_connector_by_type('intacct')
        self.assertIsNotNone(c, 'the Intacct card should ship in the catalog')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, 'owner')
        row = next(x for x in compose.catalog(self.s) if x['type'] == 'intacct')
        self.assertTrue(row['ready'])


class ComposeTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def test_a_plain_ask_becomes_a_config(self):
        llm = llm_saying(cfg_answer(type='local_file', title='Nightly census',
                                    path='C:/exports/census.csv', daily_at='08:00',
                                    ai_prompt='Total beds by facility; flag anything under 70.'))
        out = compose.compose(self.s, 'read my census csv every morning and flag low facilities', llm)
        self.assertEqual(out['config']['type'], 'local_file')
        self.assertEqual(out['confidence'], 'high')
        self.assertTrue(out['explain'])

    def test_the_catalog_is_what_the_model_sees(self):
        llm = llm_saying(cfg_answer(type='digest', title='Daily digest', daily_at='08:00'))
        compose.compose(self.s, 'daily digest', llm)
        cat = llm.seen[0]['user']['catalog']
        self.assertTrue(any(c['type'] == 'local_file' for c in cat))
        self.assertTrue(all('takes' in c and 'ready' in c for c in cat))

    def test_questions_come_back_as_questions(self):
        llm = llm_saying(json.dumps({'questions': ['Where does the census file live?',
                                                   'Daily, or weekly?']}))
        out = compose.compose(self.s, 'summarize the census', llm)
        self.assertEqual(len(out['questions']), 2)
        self.assertNotIn('config', out)

    def test_the_answers_go_back_to_the_model(self):
        llm = llm_saying(cfg_answer(type='local_file', title='Census', path='C:/x.csv'))
        compose.compose(self.s, 'summarize the census', llm,
                        answers={'Where does the census file live?': 'C:/x.csv'})
        self.assertIn('answers_to_your_questions', llm.seen[0]['user'])

    def test_at_most_three_questions(self):
        llm = llm_saying(json.dumps({'questions': ['a', 'b', 'c', 'd', 'e']}))
        self.assertEqual(len(compose.compose(self.s, 'x', llm)['questions']), 3)


class ItCannotInventTests(unittest.TestCase):
    """A model reading a list is still a model. Everything it picks is checked, because the
    failure it would otherwise produce arrives days later as a scheduled report that has never
    once run."""
    def setUp(self): self.s = MemoryStore()

    def test_a_system_we_do_not_have_is_refused(self):
        out = compose.compose(self.s, 'pull our leads', llm_saying(cfg_answer(type='salesforce', title='Leads')))
        self.assertIn('unknown report type', out['error'])

    def test_a_type_whose_connection_is_off_is_refused_by_name(self):
        out = compose.compose(self.s, 'ap aging', llm_saying(cfg_answer(type='intacct', title='AP aging', object='APBILL')))
        self.assertIn('intacct', out['error'])
        self.assertIn('config', out)          # handed back so the owner can see what it wanted

    def test_a_planned_type_is_refused(self):
        out = compose.compose(self.s, 'sharepoint list', llm_saying(cfg_answer(type='sharepoint_list', title='List')))
        self.assertTrue(out['error'])

    def test_a_config_with_no_title_is_refused(self):
        out = compose.compose(self.s, 'x', llm_saying(cfg_answer(type='digest')))
        self.assertIn('no title', out['error'])

    def test_an_unparseable_answer_says_so_instead_of_crashing(self):
        out = compose.compose(self.s, 'x', llm_saying('I would love to help with that!'))
        self.assertIn('did not answer', out['error'])

    def test_json_in_a_code_fence_still_parses(self):
        fenced = '```json\n' + cfg_answer(type='digest', title='Digest') + '\n```'
        self.assertEqual(compose.compose(self.s, 'x', llm_saying(fenced))['config']['type'], 'digest')

    def test_no_ai_configured_says_where_to_go(self):
        self.assertIn('Connectors', compose.compose(self.s, 'x', None)['error'])

    def test_an_empty_ask_is_not_a_report(self):
        self.assertTrue(compose.compose(self.s, '   ', llm_saying(cfg_answer(type='digest', title='x')))['error'])


class LookBeforeWritingTests(unittest.TestCase):
    """It is allowed to go and READ the schema first, which is the difference between a query
    against the real columns and a plausible guess at what they are called."""
    def setUp(self): self.s = MemoryStore()

    def test_a_peek_runs_for_real_and_comes_back(self):
        llm = llm_saying(json.dumps({'peek': {'type': 'automate', 'days': 1}}),
                         cfg_answer(type='digest', title='Digest', daily_at='08:00'))
        out = compose.compose(self.s, 'what repeats around here?', llm)
        self.assertEqual(out['config']['type'], 'digest')
        self.assertEqual(out['looked_at'], [{'type': 'automate', 'days': 1}])
        looked = llm.seen[1]['user']['what_you_looked_at'][0]
        self.assertEqual(looked['you_asked_for']['type'], 'automate')
        self.assertTrue(looked['result'])

    def test_a_failed_peek_is_information_not_a_crash(self):
        """'that object does not exist' is something the model should read and act on."""
        # a db inside a directory that does not exist: sqlite refuses everywhere. 'C:/nope.db' only
        # failed where C: was not a drive - on the Windows runner it is, the runner is an admin,
        # and sqlite quietly CREATED the file at the drive root, so the peek that must fail succeeded
        nowhere = os.path.join(tempfile.gettempdir(), 'taskuary-no-such-dir', 'nope.db')
        llm = llm_saying(json.dumps({'peek': {'type': 'sqlite', 'db': nowhere, 'query': 'SELECT 1'}}),
                         cfg_answer(type='digest', title='Digest'))
        out = compose.compose(self.s, 'x', llm)
        self.assertEqual(out['config']['type'], 'digest')
        self.assertIn('lookup failed', llm.seen[1]['user']['what_you_looked_at'][0]['result'])

    def test_an_unknown_peek_type_says_so(self):
        llm = llm_saying(json.dumps({'peek': {'type': 'oracle_schema'}}),
                         cfg_answer(type='digest', title='Digest'))
        compose.compose(self.s, 'x', llm)
        self.assertIn('no such lookup type', llm.seen[1]['user']['what_you_looked_at'][0]['result'])

    def test_it_cannot_peek_forever(self):
        peek = json.dumps({'peek': {'type': 'automate', 'days': 1}})
        out = compose.compose(self.s, 'x', llm_saying(peek, peek, peek, peek), rounds=2)
        self.assertIn('without answering', out['error'])


if __name__ == '__main__':
    unittest.main()


class FinishedConfigTests(unittest.TestCase):
    """"Adelphi AP bills posted daily, by person" came back as a Sage Intacct source with a title
    and nothing else - no object, no fields, no filter - and the wizard showed exactly that. Two
    faults: the composer accepted a config its type cannot run, and the wizard's source card did
    not know Intacct's keys at all. The first is here; the second is website/test."""
    def setUp(self):
        self.s = MemoryStore()
        c = next(x for x in self.s.list_connectors() if x['Type'] == 'intacct')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'pw',
                               'ConfigJson': json.dumps({'sender_id': 'a', 'sender_password': 'b', 'user_id': 'c', 'company_id': 'd'})}, 'test')

    def test_an_intacct_report_with_no_object_is_not_finished(self):
        ok, why = compose.validate(self.s, {'type': 'intacct', 'title': 'Adelphi AP Bills Posted Daily'})
        self.assertFalse(ok); self.assertIn('no object', why)
        ok, _ = compose.validate(self.s, {'type': 'intacct', 'title': 'x', 'object': 'APBILL'})
        self.assertTrue(ok)

    def test_the_composer_hands_back_the_error_not_the_empty_form(self):
        out = compose.compose(self.s, 'how many bills were posted by person in the Adelphi facility, daily',
                              llm_saying(cfg_answer(type='intacct', title='Adelphi AP Bills Posted Daily')))
        self.assertIn('not finished', out['error'])

    def test_intacct_gets_its_playbook_only_when_it_is_connected(self):
        llm = llm_saying(cfg_answer(type='intacct', title='t', object='APBILL', fields=['CREATEDBY', 'LOCATIONID'],
                                    filters=[['LOCATIONID', '=', 'ADEL']], ai_prompt='count per CREATEDBY'))
        out = compose.compose(self.s, 'bills posted by person at Adelphi', llm)
        self.assertEqual(out['config']['object'], 'APBILL')
        self.assertIn('LOCATION', llm.seen[0]['system']); self.assertIn('intacct_fields', llm.seen[0]['system'])
        bare = llm_saying(cfg_answer(type='digest', title='d'))
        compose.compose(MemoryStore(), 'what repeats?', bare)
        self.assertNotIn('SAGE INTACCT', bare.seen[0]['system'])
