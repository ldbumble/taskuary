"""Any database by connection string - one card, every engine. Two roads by shape:
a URL ('postgresql://user:pw@host/db', 'mysql+pymysql://...', 'snowflake://...') runs
through SQLAlchemy; anything else ('DRIVER={...};SERVER=...;') is a raw ODBC string via
pyodbc. A {password} placeholder in the string is filled from the card's write-only
secret, so the saved config never carries the password itself.
"""


def conn_str(cfg: dict) -> str:
    cs = (cfg.get('conn_str') or '').strip()
    if not cs:
        from . import words
        raise RuntimeError(f"no connection string set - {words.card('Any database (connection string)')}")
    return cs.replace('{password}', cfg.get('password') or '')


def is_url(cs: str) -> bool: return '://' in cs


# A READ IS ONE SELECT (M3, 2026-11-08). Rollback was the whole of "read": it does not undo MySQL DDL (an implicit commit), anything on
# ClickHouse (no transactions), a mail SQL Server sends (sp_send_dbmail), a shell (xp_cmdshell), a fetch from the DB host (OPENROWSET,
# a linked server) or a BACKUP. So a read-level query must be ONE statement that starts SELECT or WITH and names none of the verbs or
# server routines that act - checked on the SQL with its comments and quoted text taken out. The card's DB user is still the real ceiling.
import re
_QUOTED = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`[^`]*`|\[[^\]]*\]", re.S)
# the statements that act (reserved words, so no plain column carries them), and the routines that reach outside: called, with a '('
_ACTS = re.compile(r'\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke|deny|into|backup|restore|dbcc|bulk)\b'
                   r'|\b(openrowset|opendatasource|openquery|openxml|dblink\w*|pg_read_\w+|pg_write_\w+|pg_ls_dir|lo_import|lo_export|pg_sleep|'
                   r'pg_terminate_backend|pg_cancel_backend|set_config|nextval|setval|load_file|sleep|benchmark|xp_\w+|sp_\w+|'
                   r'url|s3|s3cluster|remote|remotesecure|hdfs|file|mysql|postgresql|jdbc|odbc|azureblobstorage|gcs)\s*\(', re.I)

def read_only(query: str) -> str:
    "The query, when a read-level card may run it; raises ValueError naming why not."
    q = _QUOTED.sub(' ', str(query or '')).strip().rstrip(';').strip()
    if not q: raise ValueError('the query is empty')
    if ';' in q: raise ValueError('a read runs one statement - this query has several')
    if not re.match(r'(select|with)\b', q, re.I): raise ValueError('a read-level card runs only a SELECT (or WITH ... SELECT)')
    if m := _ACTS.search(q): raise ValueError(f"a read-level card does not run {(m[1] or m[2]).upper()} - raise the card to write, or ask for a proposal")
    return query


def _rows_sqlalchemy(cs, query, n, write=False):
    try: import sqlalchemy
    except ImportError:
        # name the package, not the extra: `taskuary[db]` silently no-ops when the install's
        # metadata predates the extra (see aws._boto3)
        raise RuntimeError('sqlalchemy is not installed - run: pip install sqlalchemy, plus the engine '
                           'driver (psycopg2-binary for postgres, pymysql for mysql, snowflake-sqlalchemy…)')
    eng = sqlalchemy.create_engine(cs, pool_pre_ping=True)
    try:
        # an explicit transaction: a 1.4 Connection has no commit()/rollback() of its own, so every query on an
        # install that still had 1.4 failed with "'Connection' object has no attribute 'rollback'" (2026-10-06)
        with eng.connect() as cx, cx.begin() as tx:
            if not write and eng.dialect.name == 'postgresql': cx.execute(sqlalchemy.text('SET TRANSACTION READ ONLY'))   # the server's own word too
            rows = [dict(r._mapping) for r in cx.execute(sqlalchemy.text(query)).fetchmany(n)]
            tx.commit() if write else tx.rollback()      # read is read (mssql.run_query)
            return rows
    finally:
        eng.dispose()


def _rows_odbc(cs, query, n, write=False):
    import pyodbc
    cx = pyodbc.connect(cs, timeout=10)
    try:
        cur = cx.cursor().execute(query)
        cols = [c[0] for c in cur.description or []]
        rows = [dict(zip(cols, r)) for r in cur.fetchmany(n)]
        cx.commit() if write else cx.rollback()          # read is read (mssql.run_query)
        return rows
    finally: cx.close()


def run_query(cfg: dict, limit: int) -> list:
    cs = conn_str(cfg)
    q = cfg['query'] if cfg.get('_write') else read_only(cfg['query'])
    return (_rows_sqlalchemy if is_url(cs) else _rows_odbc)(cs, q, limit, write=bool(cfg.get('_write')))


def test(cfg: dict) -> dict:
    """Connect and run a probe; never raises - errors come back as data. Engines with no
    bare SELECT 1 (Oracle wants FROM DUAL) can set 'test_query' on the card."""
    try:
        cs = conn_str(cfg)
        rows = (_rows_sqlalchemy if is_url(cs) else _rows_odbc)(cs, cfg.get('test_query') or 'SELECT 1', 1)
        eng = cs.split('://', 1)[0] if is_url(cs) else 'odbc'
        return {'ok': True, 'engine': eng, 'detail': f'connected ({eng}) · probe returned {len(rows)} row(s)'}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}


def run_report(cfg: dict):
    """Report executor: (headline, body). One row past the limit is fetched so the
    headline can admit when the result was cut (see reports.rows_out)."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(run_query(cfg, lim + 1), lim, mine=mine)
