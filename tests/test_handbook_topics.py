"""One system, one shelf - or the handbook becomes a filing cabinet nobody can search.

topic_of only slugifies, so "Intacct", "intacct " and "Sage Intacct" produced two shelves for one
subject - the sprawl its own docstring promised to prevent. It compounds fast: a single afternoon
on this install left `viventium-api` and `viventium-reimbursements`, one system on two shelves,
and an agent looking up either would read half of what is known.

snap_topic is deliberately conservative. A WRONG merge is worse than a duplicate: it files a fact
where nobody looking for it will read it.
"""
import unittest

from taskuary.handbook import post, snap_topic
from taskuary.store import MemoryStore


def E(*pairs):
    return [{'Topic': t, 'n': n} for t, n in pairs]


class SnappingToAnExistingShelf(unittest.TestCase):
    def test_a_narrower_topic_joins_the_shelf_that_exists(self):
        self.assertEqual(snap_topic('viventium-api', E(('viventium', 5))), 'viventium')

    def test_the_case_the_docstring_always_promised(self):
        self.assertEqual(snap_topic('sage-intacct', E(('intacct', 3))), 'intacct')

    def test_singular_and_plural_are_one_shelf(self):
        self.assertEqual(snap_topic('invoices', E(('invoice', 2))), 'invoice')
        self.assertEqual(snap_topic('invoice', E(('invoices', 2))), 'invoices')

    def test_ties_go_to_the_shelf_carrying_more(self):
        self.assertEqual(snap_topic('acme-payroll-api', E(('payroll', 1), ('acme-payroll', 9))),
                         'acme-payroll')


class WhenItMustNotMerge(unittest.TestCase):
    def test_a_generic_word_is_not_enough_to_merge_on(self):
        """Every system has an api. Filing viventium's api notes under `api` is worse than sprawl."""
        self.assertEqual(snap_topic('viventium-api', E(('api', 9))), 'viventium-api')
        self.assertEqual(snap_topic('billing-data', E(('data', 4))), 'billing-data')

    def test_a_broad_topic_never_files_under_a_narrow_one(self):
        """`viventium` arriving while only `viventium-api` exists makes the broad shelf - and the
        NEXT specific topic snaps onto it. The sprawl unwinds instead of deepening."""
        self.assertEqual(snap_topic('viventium', E(('viventium-api', 1))), 'viventium')
        after = E(('viventium-api', 1), ('viventium', 1))
        self.assertEqual(snap_topic('viventium-reimbursements', after), 'viventium')

    def test_an_unrelated_topic_gets_its_own_shelf(self):
        self.assertEqual(snap_topic('brand-new', E(('payroll', 4))), 'brand-new')

    def test_a_shelf_that_already_exists_is_used_as_typed(self):
        self.assertEqual(snap_topic('payroll', E(('payroll', 4))), 'payroll')

    def test_no_shelves_yet_means_take_what_you_were_given(self):
        self.assertEqual(snap_topic('payroll', []), 'payroll')
        self.assertEqual(snap_topic('payroll', None), 'payroll')


class ThroughTheRealWriter(unittest.TestCase):
    def test_the_second_agent_lands_on_the_first_ones_shelf(self):
        s = MemoryStore()
        post(s, 'Deductions are per-division', topic='Viventium', author='coder')
        second = post(s, 'The import endpoint rejects blank cost centres',
                      topic='Viventium API', author='coder')
        self.assertEqual(second['Topic'], 'viventium')
        self.assertEqual([r['Topic'] for r in s.lore_topics()], ['viventium'])

    def test_it_still_falls_back_to_the_checkout_when_nothing_was_named(self):
        s = MemoryStore()
        self.assertEqual(post(s, 'the tests need pyodbc', cwd='C:/src/taskuary')['Topic'], 'taskuary')


if __name__ == '__main__':
    unittest.main()
