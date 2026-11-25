"""A read-level database card runs one SELECT: rollback cannot take back a sent mail, a shell, MySQL DDL or anything on ClickHouse (M3)."""
import pytest
from unittest import mock
from taskuary import db, mssql

@pytest.mark.parametrize('q', ["SELECT name, url, file FROM pages WHERE note = 'drop table; exec x'", 'with t as (select 1 a) select * from t',
                               'select replace(title, \'a\', \'b\') from t -- update later', 'SELECT last_update FROM t;'])
def test_a_plain_select_reads(q): assert db.read_only(q) == q

@pytest.mark.parametrize('q', ['DROP TABLE t', 'select 1; delete from t', "EXEC msdb..sp_send_dbmail @recipients='x@vendor.example'",
                               'with x as (select 1) delete from t', 'select * into t2 from t', "select * from openrowset('SQLNCLI', 'x', 'y')",
                               "SELECT * FROM url('https://x.example/?d=1', CSV)", "select pg_read_file('/etc/passwd')", 'select 1 into outfile "/tmp/x"',
                               'update t set a=1', '', 'select 1 /* ; */ ; select 2'])
def test_anything_that_acts_is_refused(q):
    with pytest.raises(ValueError): db.read_only(q)

def test_both_roads_check_before_connecting_and_a_write_card_is_untouched():
    with mock.patch.object(mssql, '_connect') as c, pytest.raises(ValueError): mssql.run_query({'query': 'DROP TABLE t'})
    c.assert_not_called()
    with mock.patch.object(db, '_rows_odbc', return_value=[]) as r:
        with pytest.raises(ValueError): db.run_query({'conn_str': 'DRIVER=x', 'query': 'DROP TABLE t'}, 5)
        db.run_query({'conn_str': 'DRIVER=x', 'query': 'DROP TABLE t', '_write': True}, 5); r.assert_called_once()


def test_mysqls_executable_comment_is_read_as_the_sql_it_runs():
    "Round 4: `/*! ... */` was taken out as a comment, and MySQL runs what it holds."
    for q in ('SELECT 1 /*!50000 ; DROP TABLE t */', 'SELECT 1 /*! INTO OUTFILE "/tmp/x" */'):
        with pytest.raises(ValueError): db.read_only(q)
    assert db.read_only('SELECT /*+ MAX_EXECUTION_TIME(1000) */ 1 /* a note */') .startswith('SELECT')


def test_a_read_is_the_databases_own_word_duckdb_reaches_no_file_and_mysql_reads_in_a_read_only_transaction():
    """Round 4: `SELECT * FROM read_csv('C:/...')` read any file on this computer through a DuckDB card - a text check cannot know every table
    function. DuckDB is opened with no reach outside its own file; MySQL, like Postgres, runs the read in a read-only transaction."""
    sqlalchemy = pytest.importorskip('sqlalchemy')
    made, ran = [], []
    class Cx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def begin(self): return self
        def commit(self): pass
        def rollback(self): pass
        def execute(self, q):
            ran.append(str(q)); return mock.Mock(returns_rows=True, fetchmany=lambda n: [])
    def engine(cs, **kw):
        made.append(kw); e = mock.Mock(); e.connect.return_value = Cx(); e.dialect.name = sqlalchemy.engine.make_url(cs).get_backend_name(); return e
    with mock.patch('sqlalchemy.create_engine', engine):
        db._rows_sqlalchemy('duckdb:///C:/data/books.duckdb?access_mode=read_only', 'SELECT 1', 5)
        db._rows_sqlalchemy('duckdb:///C:/data/books.duckdb', 'SELECT 1', 5, write=True)
        db._rows_sqlalchemy('mysql+pymysql://reader@db.northwind.example/books', 'SELECT 1', 5)
    assert made[0]['connect_args']['config']['enable_external_access'] is False and 'connect_args' not in made[1]
    assert ran[-2:] == ['SET TRANSACTION READ ONLY', 'SELECT 1']
