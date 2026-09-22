"""Named database cards: Postgres, MySQL, ClickHouse, Snowflake, BigQuery.

WHY THESE EXIST WHEN "Any database (connection string)" ALREADY WORKS. That card asks you to know
the SQLAlchemy URL shape and which driver to install, which is fine if you already do and a dead
end if you do not - and "is Postgres supported?" is a question the Connections page should answer
by having a card called Postgres on it. So these are the same executor with the dialect filled in,
the default port known, and the driver named in the error you actually get.

ONE EXECUTOR, FIVE TYPES. Each card either takes the pieces (host, database, user, and the
password from its write-only secret) and this builds the URL, or takes a full `conn_str` and this
gets out of the way. Everything downstream - the query, the row cap, the ODBC fallback - is
db.run_report, unchanged.

THEY ARE ALL READS. scopes puts every one at `read` and none of them ships a write verb: a report
or an agent runs SELECTs. Changing data in a production database is not something this card can
be talked into, whatever the query says, because the engine's own user is the ceiling - so point
these at a read-only account and the ladder holds even if everything above it fails.
"""
from urllib.parse import quote_plus

# dialect, default port, the pip package whose absence you will otherwise learn about cryptically
ENGINES = {
    'postgresql': ('postgresql+psycopg2', 5432, 'psycopg2-binary'),
    'mysql': ('mysql+pymysql', 3306, 'pymysql'),
    'clickhouse': ('clickhouse+http', 8123, 'clickhouse-sqlalchemy'),
    'snowflake': ('snowflake', None, 'snowflake-sqlalchemy'),
    'bigquery': ('bigquery', None, 'sqlalchemy-bigquery'),
}


def url_for(engine: str, cfg: dict) -> str:
    """The SQLAlchemy URL for one card. `conn_str` always wins - somebody who has one should not
    have to take it apart into fields to use it."""
    if (cfg.get('conn_str') or '').strip():
        return cfg['conn_str'].strip()
    dialect, port, _pkg = ENGINES[engine]
    user, pw = cfg.get('user') or '', cfg.get('password') or ''
    db = (cfg.get('database') or '').strip()
    host = (cfg.get('host') or '').strip()

    if engine == 'bigquery':
        # no host, no password: the project is the authority and credentials come from the
        # environment (GOOGLE_APPLICATION_CREDENTIALS or the gcloud login), like every other
        # Google client. A dataset is optional and scopes unqualified table names.
        project = (cfg.get('project') or db).strip()
        if not project: raise RuntimeError('BigQuery needs a project')
        return f"bigquery://{project}" + (f"/{cfg['dataset'].strip()}" if cfg.get('dataset') else '')

    if engine == 'snowflake':
        # snowflake://user:pw@account/database/schema?warehouse=&role= - the account identifier
        # goes where a host would, and warehouse is usually required for a query to run at all.
        account = (cfg.get('account') or host).strip()
        if not (account and user): raise RuntimeError('Snowflake needs an account identifier and a user')
        tail = f"/{db}" + (f"/{cfg['schema'].strip()}" if cfg.get('schema') else '') if db else ''
        opts = [f'{k}={quote_plus(str(cfg[k]))}' for k in ('warehouse', 'role') if cfg.get(k)]
        return (f"snowflake://{quote_plus(user)}:{quote_plus(pw)}@{account}{tail}"
                + (f"?{'&'.join(opts)}" if opts else ''))

    if not host: raise RuntimeError(f'{engine} needs a host')
    if not db: raise RuntimeError(f'{engine} needs a database name')
    at = f"{quote_plus(user)}:{quote_plus(pw)}@" if user else ''
    where = f"{host}:{int(cfg.get('port') or port)}"
    return f'{dialect}://{at}{where}/{db}'


def runner(engine: str):
    """One executor per card, all the same code with the dialect bound."""
    def run(cfg):
        from . import db
        try:
            return db.run_report({**cfg, 'conn_str': url_for(engine, cfg)})
        except ImportError as e:
            _d, _p, pkg = ENGINES[engine]
            raise RuntimeError(f'{engine} needs its driver - run: pip install sqlalchemy {pkg}  ({e})')
    run.__doc__ = (f'{{"query"}} - run a read-only SQL query against {engine} through SQLAlchemy. '
                   f'Give the card host/database/user (password is its secret), or a full conn_str.')
    return run
