"""Microsoft SQL Server connector - local-first via pyodbc. Structured config (no DSN
strings to hand-craft): {"server", "database", "auth": "windows"|"sql", "username",
"password", "driver", "query"}. Windows auth is the default because local SQL Server is
the primary use case; `driver` auto-picks the newest installed 'ODBC Driver NN for SQL
Server'. TrustServerCertificate=yes because Driver 18 mandates encryption and local
instances rarely have real certs. A raw "conn_str" overrides everything built.
"""


def drivers() -> list:
    """Installed SQL Server ODBC drivers, best (newest) first."""
    import pyodbc
    ds = [d for d in pyodbc.drivers() if 'SQL Server' in d]
    return sorted(ds, key=lambda d: ('ODBC Driver' in d, d), reverse=True)


def conn_str(cfg: dict) -> str:
    if cfg.get('conn_str'): return cfg['conn_str']
    drv = cfg.get('driver') or (drivers() or ['ODBC Driver 17 for SQL Server'])[0]
    parts = [f'DRIVER={{{drv}}}', f"SERVER={cfg.get('server') or 'localhost'}"]
    if cfg.get('database'): parts.append(f"DATABASE={cfg['database']}")
    if (cfg.get('auth') or 'windows') == 'windows': parts.append('Trusted_Connection=yes')
    else: parts += [f"UID={cfg.get('username', '')}", f"PWD={cfg.get('password', '')}"]
    parts.append('TrustServerCertificate=yes')
    return ';'.join(parts)


def _connect(cs: str):
    import pyodbc
    return pyodbc.connect(cs, timeout=int(10))


def run_query(cfg: dict, limit: int = None) -> list:
    """Execute cfg['query'], return up to `limit` rows as dicts (cfg['max_rows'] wins)."""
    from .reports import row_limit
    limit = limit or row_limit(cfg)[0]
    with _connect(conn_str(cfg)) as cx:
        cur = cx.cursor().execute(cfg['query'])
        cols = [c[0] for c in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchmany(limit)]


def test(cfg: dict) -> dict:
    """Connect and report server version + current db; never raises - errors come back as data."""
    try:
        with _connect(conn_str(cfg)) as cx:
            ver, db = cx.cursor().execute('SELECT @@VERSION, DB_NAME()').fetchone()
        return {'ok': True, 'version': str(ver).split('\n')[0][:200], 'database': db}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}


def run_report(cfg: dict):
    """Report executor: (headline, summary) for the timeline. One row past the limit is
    fetched so the headline can admit when the result was cut (see reports.rows_out)."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    if cfg.get('dsn'):  # back-compat: sqlalchemy-style dsn from old configs
        import sqlalchemy
        with sqlalchemy.create_engine(cfg['dsn']).connect() as cx:
            rows = [dict(r._mapping) for r in cx.execute(sqlalchemy.text(cfg['query'])).fetchmany(lim + 1)]
    else:
        rows = run_query(cfg, lim + 1)
    return rows_out(rows, lim, mine=mine)
