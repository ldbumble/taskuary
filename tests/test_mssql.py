"""MSSQL connector tests - pure string/logic tests plus a faked pyodbc connection; no
actual SQL Server needed, so these run anywhere (CI included).
"""
import unittest
from unittest import mock
from taskuary import mssql


class FakeCursor:
    description = [('Id',), ('Name',)]
    def execute(self, q): self.q = q; return self
    def fetchmany(self, n): return [(1, 'a'), (2, 'b')][:n]
    def fetchone(self): return ('Microsoft SQL Server 2022\nmore', 'master')

class FakeConn:
    def cursor(self): return FakeCursor()
    def __enter__(self): return self
    def __exit__(self, *a): pass


class ConnStrTests(unittest.TestCase):
    def test_windows_auth_default(self):
        cs = mssql.conn_str({'driver': 'ODBC Driver 18 for SQL Server'})
        self.assertIn('DRIVER={ODBC Driver 18 for SQL Server}', cs)
        self.assertIn('SERVER=localhost', cs)
        self.assertIn('Trusted_Connection=yes', cs)
        self.assertIn('TrustServerCertificate=yes', cs)
        self.assertNotIn('UID=', cs)

    def test_sql_auth(self):
        cs = mssql.conn_str({'server': r'HOST\INST', 'database': 'db1', 'auth': 'sql',
                             'username': 'u', 'password': 'p', 'driver': 'D'})
        for part in (r'SERVER=HOST\INST', 'DATABASE=db1', 'UID=u', 'PWD=p'): self.assertIn(part, cs)
        self.assertNotIn('Trusted_Connection', cs)

    def test_conn_str_override(self):
        self.assertEqual(mssql.conn_str({'conn_str': 'DSN=x', 'server': 'ignored'}), 'DSN=x')

    def test_driver_autopick_newest(self):
        with mock.patch.object(mssql, 'drivers', return_value=['ODBC Driver 18 for SQL Server', 'SQL Server']):
            self.assertIn('{ODBC Driver 18 for SQL Server}', mssql.conn_str({}))

    def test_driver_ordering(self):
        try: import pyodbc
        except ImportError: self.skipTest('pyodbc not installed')
        fake = ['SQL Server', 'ODBC Driver 17 for SQL Server', 'ODBC Driver 18 for SQL Server',
                'SQL Server Native Client 11.0']
        with mock.patch.object(pyodbc, 'drivers', return_value=fake):
            got = mssql.drivers()
        self.assertEqual(got[0], 'ODBC Driver 18 for SQL Server')
        self.assertEqual(got[1], 'ODBC Driver 17 for SQL Server')


class QueryTests(unittest.TestCase):
    def test_run_query_rows_as_dicts(self):
        with mock.patch.object(mssql, '_connect', return_value=FakeConn()):
            rows = mssql.run_query({'driver': 'D', 'query': 'SELECT 1'})
        self.assertEqual(rows, [{'Id': 1, 'Name': 'a'}, {'Id': 2, 'Name': 'b'}])

    def test_test_ok_and_error(self):
        with mock.patch.object(mssql, '_connect', return_value=FakeConn()):
            r = mssql.test({'driver': 'D'})
        self.assertTrue(r['ok']); self.assertIn('SQL Server 2022', r['version']); self.assertEqual(r['database'], 'master')
        with mock.patch.object(mssql, '_connect', side_effect=RuntimeError('login failed')):
            r = mssql.test({'driver': 'D'})
        self.assertFalse(r['ok']); self.assertIn('login failed', r['error'])

    def test_report_executor_registered(self):
        from taskuary.reports import REGISTRY
        self.assertIn('mssql', REGISTRY); self.assertIn('mcp', REGISTRY)
        with mock.patch.object(mssql, '_connect', return_value=FakeConn()):
            head, body = REGISTRY['mssql']({'driver': 'D', 'query': 'SELECT 1'})
        self.assertEqual(head, '2 rows'); self.assertIn('"Name": "a"', body)


if __name__ == '__main__':
    unittest.main()
