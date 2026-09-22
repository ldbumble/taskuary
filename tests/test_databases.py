"""Five named database cards over one executor.

What can actually go wrong here is the URL: a password with an @ in it, a Snowflake account that
is not a host, a BigQuery project that has no password at all. So that is what this pins - plus
the one property that matters more than any of it, which is that none of these cards can be
talked into a write.
"""
import unittest
from unittest import mock

from taskuary import databases, scopes
from taskuary.reports import CARD_OF, REGISTRY


class EveryOneIsARead(unittest.TestCase):
    def test_all_five_are_reads_on_cards_that_ship_at_read(self):
        for e in databases.ENGINES:
            self.assertEqual(scopes.ACTIONS[e], 'read', e)
            self.assertEqual(scopes.DEFAULT_SCOPE[e], 'read', e)

    def test_all_five_are_registered_and_map_to_their_own_card(self):
        for e in databases.ENGINES:
            self.assertIn(e, REGISTRY)
            self.assertEqual(CARD_OF[e], e)


class TheUrl(unittest.TestCase):
    def test_a_password_with_punctuation_survives(self):
        """An @ or a / in a password silently breaks a hand-built URL - quote it or lose the host."""
        url = databases.url_for('postgresql', {'host': 'db.internal', 'database': 'app',
                                               'user': 'ro', 'password': 'p@ss/w:rd'})
        self.assertIn('p%40ss%2Fw%3Ard', url)
        self.assertTrue(url.startswith('postgresql+psycopg2://ro:'))
        self.assertIn('@db.internal:5432/app', url)

    def test_the_default_port_is_the_engine_s_own(self):
        self.assertIn(':5432/', databases.url_for('postgresql', {'host': 'h', 'database': 'd'}))
        self.assertIn(':3306/', databases.url_for('mysql', {'host': 'h', 'database': 'd'}))
        self.assertIn(':8123/', databases.url_for('clickhouse', {'host': 'h', 'database': 'd'}))
        self.assertIn(':15432/', databases.url_for('postgresql', {'host': 'h', 'database': 'd', 'port': 15432}))

    def test_snowflake_puts_the_account_where_a_host_would_go(self):
        url = databases.url_for('snowflake', {'account': 'xy12345.eu-west-1', 'user': 'u',
                                              'password': 'p', 'database': 'DB', 'schema': 'PUBLIC',
                                              'warehouse': 'WH', 'role': 'ANALYST'})
        self.assertTrue(url.startswith('snowflake://u:p@xy12345.eu-west-1/DB/PUBLIC?'))
        self.assertIn('warehouse=WH', url)
        self.assertIn('role=ANALYST', url)

    def test_bigquery_has_no_host_and_no_password(self):
        self.assertEqual(databases.url_for('bigquery', {'project': 'p', 'dataset': 'd'}), 'bigquery://p/d')
        self.assertEqual(databases.url_for('bigquery', {'project': 'p'}), 'bigquery://p')

    def test_a_full_connection_string_always_wins(self):
        """Somebody who already has one should not have to take it apart into fields."""
        for e in databases.ENGINES:
            self.assertEqual(databases.url_for(e, {'conn_str': 'postgresql://a:b@c/d', 'host': 'ignored'}),
                             'postgresql://a:b@c/d')

    def test_a_missing_piece_says_which_one(self):
        with self.assertRaises(RuntimeError) as e:
            databases.url_for('postgresql', {'database': 'app'})
        self.assertIn('host', str(e.exception))
        with self.assertRaises(RuntimeError) as e:
            databases.url_for('mysql', {'host': 'h'})
        self.assertIn('database', str(e.exception))
        with self.assertRaises(RuntimeError) as e:
            databases.url_for('snowflake', {'user': 'u'})
        self.assertIn('account', str(e.exception))


class TheDriver(unittest.TestCase):
    def test_a_missing_driver_names_the_package_to_install(self):
        run = databases.runner('postgresql')
        with mock.patch('taskuary.db.run_report', side_effect=ImportError('no module named psycopg2')):
            with self.assertRaises(RuntimeError) as e:
                run({'host': 'h', 'database': 'd', 'query': 'select 1'})
        self.assertIn('psycopg2-binary', str(e.exception))

    def test_the_query_reaches_the_reader_with_the_built_url(self):
        run = databases.runner('mysql')
        with mock.patch('taskuary.db.run_report', return_value={'rows': []}) as rr:
            run({'host': 'h', 'database': 'd', 'user': 'u', 'password': 'p', 'query': 'select 1'})
        self.assertEqual(rr.call_args[0][0]['conn_str'], 'mysql+pymysql://u:p@h:3306/d')
        self.assertEqual(rr.call_args[0][0]['query'], 'select 1')


if __name__ == '__main__':
    unittest.main()
