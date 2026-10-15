"""Setup asks a few short questions for SOUL.md and JOB.md, filled from the mail where it can, and ends in a finish the owner
presses (the owner, 2026-10-15: "we need survey like a few short question on setup screen to fill out soul.md and job.md (though you
can generate as much as possible from history) ... we only have repo's in the soul.md not what other corporate system connectors
they have for non technical people ... forgot to ask for their name ... we should be able to dismiss the walk through and then the
morning digest screen will show up")."""
import json, unittest
from unittest import mock

from taskuary import firstrun
from taskuary.store import MemoryStore

ANSWERS = {'name': 'Alex Doyle', 'role': 'Finance systems lead at Northwind', 'owns': 'Month-end close, vendor payments',
           'systems': ['Workday', 'Salesforce', 'Payworth'], 'people': 'Erin Blake, Gail Moreno'}


class AboutTests(unittest.TestCase):
    def test_the_answers_land_in_soul_and_job_and_the_name_everywhere(self):
        s = MemoryStore()
        with mock.patch.object(firstrun, '_learn_in_background'):
            firstrun.save_about(s, ANSWERS)
        soul, job = s.get_doc('soul'), s.get_doc('job')
        self.assertIn('## Systems I work in', soul)
        for x in ('Workday', 'Salesforce', 'Payworth'): self.assertIn(f'- {x}', soul)
        self.assertLess(soul.index('## Systems I work in'), soul.index('## Connected systems'))
        self.assertIn('Finance systems lead at Northwind', job); self.assertIn('Month-end close', job); self.assertIn('Erin Blake', job)
        self.assertEqual(s.owner()['owner'], 'Alex Doyle')
        self.assertTrue(firstrun.state(s)['about_done'])

    def test_saving_again_replaces_the_answers_and_keeps_the_owners_own_lines(self):
        s = MemoryStore()
        with mock.patch.object(firstrun, '_learn_in_background'):
            firstrun.save_about(s, ANSWERS)
            s.save_doc('soul', s.get_doc('soul') + '\n## My notes\n- Never wire money on a Friday.\n', 'owner')
            firstrun.save_about(s, {**ANSWERS, 'systems': ['ADP']})
        soul = s.get_doc('soul')
        self.assertIn('- ADP', soul); self.assertNotIn('- Workday', soul); self.assertEqual(soul.count('## Systems I work in'), 1)
        self.assertIn('Never wire money on a Friday.', soul)
        self.assertEqual(firstrun.about(s)['systems'], ['ADP'])

    def test_suggestions_come_from_the_mail_and_never_overwrite_what_was_typed(self):
        s = MemoryStore()
        def brain(system, user, **kw): return json.dumps({'role': 'Finance lead', 'owns': 'Payroll and vendor payments',
                                                          'systems': ['Workday'], 'people': 'Erin Blake'})
        with mock.patch('taskuary.histgen.job_evidence', return_value=('PEOPLE WHO WRITE TO THE OWNER ...', 'x', [])), \
             mock.patch('taskuary.llm.build_llm', return_value=brain):
            out = firstrun.suggest_about(s)
        self.assertEqual((out['role'], out['systems']), ('Finance lead', ['Workday']))

    def test_a_suggestion_that_fails_says_why_and_the_form_still_works(self):
        s = MemoryStore()
        with mock.patch('taskuary.histgen.job_evidence', side_effect=RuntimeError('no mail history yet')):
            out = firstrun.suggest_about(s)
        self.assertIn('no mail history yet', out['error'])

    def test_the_systems_offered_are_the_catalogues_corporate_ones(self):
        offered = firstrun.about(MemoryStore())['offered']
        self.assertTrue(len(offered) >= 8); self.assertTrue(all(isinstance(x, str) and x for x in offered))


class FinishTests(unittest.TestCase):
    def test_setup_stays_until_the_owner_finishes_it(self):
        s = MemoryStore()
        self.assertFalse(firstrun.state(s)['dismissed'])
        firstrun.finish(s)
        self.assertTrue(firstrun.state(s)['dismissed'])

    def test_an_install_already_working_before_this_is_treated_as_finished(self):
        """The finish button is new: an install that set up before it must not open on setup again."""
        s = MemoryStore()
        with mock.patch.object(firstrun, 'state', return_value={'step': 'done'}):
            firstrun.settle_existing(s)
        self.assertEqual(s.get_setting('first_run_dismissed'), '1')
        t = MemoryStore()
        with mock.patch.object(firstrun, 'state', return_value={'step': 'ai'}):
            firstrun.settle_existing(t)
        self.assertEqual(t.get_setting('first_run_dismissed'), '0')
        with mock.patch.object(firstrun, 'state', return_value={'step': 'done'}):
            firstrun.settle_existing(t)                                  # once decided, never re-decided
        self.assertEqual(t.get_setting('first_run_dismissed'), '0')


if __name__ == '__main__': unittest.main()
