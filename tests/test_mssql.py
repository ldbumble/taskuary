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
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


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


class WhereItConnectsIsTheCards(unittest.TestCase):
    """Security round 5 (C6): an agent's tool call carried its own `dsn`, and the SQL Server executor opened it as it came - a sqlite URL
    of Taskuary's own database, every connector's secret in it. Where a card connects is the saved card's alone, and never a local file."""
    def test_a_tool_call_cannot_name_the_connection(self):
        from taskuary.reports import query_only
        q = query_only({'type': 'mssql', 'query': 'SELECT 1', 'dsn': 'sqlite:///x.db', 'driver': 'D};Database=x;{', 'auth': 'windows', 'conn_str': 'DSN=x'})
        self.assertEqual(q, {'type': 'mssql', 'query': 'SELECT 1'})

    def test_a_local_file_is_never_a_sql_server(self):
        import sqlite3, tempfile
        from pathlib import Path
        p = Path(tempfile.mkdtemp()) / 'ledger.db'
        cx = sqlite3.connect(p); cx.execute('CREATE TABLE secrets (v)'); cx.execute("INSERT INTO secrets VALUES ('northwind-key')"); cx.commit(); cx.close()
        for dsn in (f'sqlite:///{p.as_posix()}', 'sqlite://', f'duckdb:///{p.as_posix()}'):
            with self.assertRaisesRegex(RuntimeError, 'never a database file'): mssql.run_report({'dsn': dsn, 'query': 'SELECT v FROM secrets'})

    def test_a_saved_dsn_runs_on_the_one_road_and_only_reads(self):
        from taskuary import db
        seen = []
        with mock.patch.object(db, '_rows_sqlalchemy', lambda cs, q, n, write=False: seen.append((cs, write)) or [{'A': 1}]):
            head, _ = mssql.run_report({'dsn': 'mssql+pyodbc://erin@sql.northwind.example/ledger', 'query': 'SELECT 1'})
            with self.assertRaises(ValueError): mssql.run_report({'dsn': 'mssql+pyodbc://erin@sql.northwind.example/ledger', 'query': 'DROP TABLE bills'})
        self.assertEqual((head, seen), ('1 row', [('mssql+pyodbc://erin@sql.northwind.example/ledger', False)]))

    def test_no_connection_string_opens_taskuarys_own_database(self):
        from taskuary import config, db
        with self.assertRaisesRegex(RuntimeError, 'not a report source'):
            db.run_query({'conn_str': f"sqlite:///{(config.home() / 'taskuary.db').as_posix()}", 'query': 'SELECT 1'}, 5)


if __name__ == '__main__':
    unittest.main()


class AWriteThatReturnsNoRows(unittest.TestCase):
    """2026-11-16: an approved INSERT ... SELECT said "No results. Previous SQL was not a query." - the fetch raised before the commit, so
    the change the owner approved was rolled back. A batch with no result set is done: it says how many rows it changed, and commits."""
    class Cur:
        def __init__(self): self.description, self.rowcount, self.sets = None, 3, 0
        def execute(self, q): return self
        def nextset(self): self.sets += 1; return False
        def fetchmany(self, n): raise RuntimeError('No results.  Previous SQL was not a query.')

    class Cx:
        def __init__(self, cur): self.cur, self.committed, self.rolled = cur, False, False
        def cursor(self): return self.cur
        def commit(self): self.committed = True
        def rollback(self): self.rolled = True
        def close(self): pass

    def test_an_approved_insert_commits_and_says_its_count(self):
        cx = self.Cx(self.Cur())
        with mock.patch.object(mssql, '_connect', return_value=cx):
            rows = mssql.run_query({'driver': 'D', 'query': 'INSERT INTO t (a) SELECT a FROM s', '_write': True})
        self.assertEqual(rows, [{'rows_affected': 3}])
        self.assertTrue(cx.committed); self.assertFalse(cx.rolled)

    def test_the_odbc_road_of_any_database_does_the_same(self):
        from taskuary import db
        cx = self.Cx(self.Cur())
        fake = mock.MagicMock(); fake.connect.return_value = cx          # no pyodbc on CI's macOS: the driver is stood in
        with mock.patch.dict('sys.modules', {'pyodbc': fake}):
            rows = db._rows_odbc('DRIVER=x', 'UPDATE t SET a=1', 5, write=True)
        self.assertEqual(rows, [{'rows_affected': 3}]); self.assertTrue(cx.committed)
