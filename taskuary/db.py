"""Any database by connection string - one card, every engine. Two roads by shape:
a URL ('postgresql://user:pw@host/db', 'mysql+pymysql://...', 'snowflake://...') runs
through SQLAlchemy; anything else ('DRIVER={...};SERVER=...;') is a raw ODBC string via
pyodbc. A {password} placeholder in the string is filled from the card's write-only
secret, so the saved config never carries the password itself.
"""


def conn_str(cfg: dict) -> str:
    cs = (cfg.get('conn_str') or '').strip()
    if not cs: raise RuntimeError('no connection string set - Connections → Any database (connection string)')
    return cs.replace('{password}', cfg.get('password') or '')


def is_url(cs: str) -> bool: return '://' in cs


def _rows_sqlalchemy(cs, query, n):
    try: import sqlalchemy
    except ImportError:
        # name the package, not the extra: `taskuary[db]` silently no-ops when the install's
        # metadata predates the extra (see aws._boto3)
        raise RuntimeError('sqlalchemy is not installed - run: pip install sqlalchemy, plus the engine '
                           'driver (psycopg2-binary for postgres, pymysql for mysql, snowflake-sqlalchemy…)')
    eng = sqlalchemy.create_engine(cs, pool_pre_ping=True)
    try:
        with eng.connect() as cx:
            return [dict(r._mapping) for r in cx.execute(sqlalchemy.text(query)).fetchmany(n)]
    finally:
        eng.dispose()


def _rows_odbc(cs, query, n):
    import pyodbc
    with pyodbc.connect(cs, timeout=10) as cx:
        cur = cx.cursor().execute(query)
        cols = [c[0] for c in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchmany(n)]


def run_query(cfg: dict, limit: int) -> list:
    cs = conn_str(cfg)
    return (_rows_sqlalchemy if is_url(cs) else _rows_odbc)(cs, cfg['query'], limit)


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
