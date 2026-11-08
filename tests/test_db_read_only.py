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
