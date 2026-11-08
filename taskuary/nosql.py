"""MONGODB, REDIS AND NEO4J - THE NAMED DATABASES THAT DO NOT SPEAK SQL (the owner, 2026-11-08: "hurry finish it all.. do all of it").

The same promise as the SQL cards (databases.py): a report or an agent READS, and nothing a query says can change the data.
Each engine keeps it its own way, in this code and not only in the account:
  MongoDB  find / aggregate / count only, and a pipeline carrying $out or $merge (the two stages that WRITE) is refused before it is sent.
  Redis    one command from a closed list of reads (GET, HGETALL, SCAN, ...) - anything else is refused, KEYS too (it blocks the server).
  Neo4j    every query runs in a READ transaction (session.execute_read), which the server itself refuses to write in.
The driver is an optional extra (pip install taskuary[mongodb] / [redis] / [neo4j]), imported only when a card is used; missing, the card
says which one and offers Install (deps.Missing). Point each card at a read-only user and the ladder holds twice.
"""
import json
from .deps import Missing

TYPES = ('mongodb', 'redis', 'neo4j')
DRIVER = {'mongodb': ('pymongo', 'mongodb'), 'redis': ('redis', 'redis'), 'neo4j': ('neo4j', 'neo4j')}     # import name, pyproject extra
WRITES = ('$out', '$merge')
REDIS_READS = frozenset('''GET MGET STRLEN GETRANGE EXISTS TYPE TTL PTTL HGET HMGET HGETALL HKEYS HVALS HLEN HEXISTS HSCAN LRANGE LLEN LINDEX
SMEMBERS SISMEMBER SCARD SSCAN ZRANGE ZREVRANGE ZRANGEBYSCORE ZREVRANGEBYSCORE ZSCORE ZCARD ZCOUNT ZRANK ZSCAN XRANGE XREVRANGE XLEN XINFO
SCAN DBSIZE INFO PING TIME'''.split())


def _driver(t: str):
    mod, extra = DRIVER[t]
    try: return __import__(mod)
    except ImportError: raise Missing(mod, f'the {t} card needs its driver - install it from the card, or run: pip install taskuary[{extra}]') from None


def _writes(o) -> list:
    "Every write stage anywhere in a pipeline - $lookup / $facet / $unionWith carry pipelines of their own."
    if isinstance(o, dict): return [k for k in o if k in WRITES] + [w for v in o.values() for w in _writes(v)]
    return [w for v in o for w in _writes(v)] if isinstance(o, list) else []


def _rows(rows, cfg, unit):
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(list(rows), lim, unit, mine)        # each read already stops one past the limit, so the cap can be said


def run_mongodb(cfg: dict):
    """{"collection": "orders", "filter": {...}, "projection": {...}, "sort": {"total": -1}} finds; {"collection", "pipeline": [...]} aggregates
    ($out / $merge refused); {"collection", "count": true} counts; {} lists the collections. Reads only."""
    pm = _driver('mongodb')
    url = (cfg.get('conn_str') or '').replace('{password}', cfg.get('password') or '') or f"mongodb://{cfg.get('host') or 'localhost'}:{cfg.get('port') or 27017}"
    kw = {'username': cfg['user'], 'password': cfg.get('password') or ''} if cfg.get('user') and not cfg.get('conn_str') else {}
    cli = pm.MongoClient(url, serverSelectionTimeoutMS=10000, **kw)
    try:
        db = cli[cfg['database']] if cfg.get('database') else cli.get_default_database(default='admin')
        if not cfg.get('collection'): return _rows([{'collection': n} for n in sorted(db.list_collection_names())], cfg, 'collections')
        col, lim = db[cfg['collection']], int(cfg.get('max_rows') or 200) + 1
        if cfg.get('pipeline') is not None:
            p = cfg['pipeline'] if isinstance(cfg['pipeline'], list) else json.loads(cfg['pipeline'])
            if (w := _writes(p)): raise PermissionError(f"MongoDB: {', '.join(sorted(set(w)))} writes - this card only reads")
            return _rows(col.aggregate(p + [{'$limit': lim}]), cfg, 'documents')
        f = cfg.get('filter') or {}
        f = json.loads(f) if isinstance(f, str) else f
        if cfg.get('count'): return f"{cfg['collection']}: {col.count_documents(f)} documents", ''
        cur = col.find(f, cfg.get('projection') or None).limit(lim)
        if cfg.get('sort'): cur = cur.sort(list(cfg['sort'].items()))
        return _rows(cur, cfg, 'documents')
    finally: cli.close()


def redis_argv(cfg: dict) -> list:
    "The one command, split and checked against the reads."
    c = cfg.get('command') or 'PING'
    argv = (c.split() if isinstance(c, str) else list(c)) + [str(a) for a in cfg.get('args') or []]
    if argv[0].upper() not in REDIS_READS: raise PermissionError(f'Redis: {argv[0].upper()} is not one of the reads this card sends')
    return [argv[0].upper(), *argv[1:]]


def run_redis(cfg: dict):
    """{"command": "HGETALL", "args": ["order:1"]} - one read command (GET, HGETALL, LRANGE, ZRANGE, SCAN, INFO, ...). Nothing that writes."""
    rd, argv = _driver('redis'), redis_argv(cfg)
    kw = dict(socket_timeout=15, decode_responses=True)
    r = (rd.Redis.from_url(cfg['url'], password=cfg.get('password') or None, **kw) if cfg.get('url') else
         rd.Redis(host=cfg.get('host') or 'localhost', port=int(cfg.get('port') or 6379), db=int(cfg.get('db') or 0), username=cfg.get('user') or None,
                  password=cfg.get('password') or None, ssl=str(cfg.get('tls') or '').lower() in ('1', 'true', 'yes', 'on'), **kw))
    try: out = r.execute_command(*argv)
    finally: r.close()
    if isinstance(out, (list, tuple)) and not (argv[0].endswith('SCAN') and len(out) == 2): return _rows([{'value': v} for v in out], cfg, 'values')
    return f'Redis {argv[0]}: answered', json.dumps(out, default=str)[:20000]


def run_neo4j(cfg: dict):
    """{"cypher": "MATCH (c:Customer) RETURN c.name LIMIT 20", "params": {}} - in a READ transaction, which the server refuses to write in."""
    nj = _driver('neo4j')
    drv = nj.GraphDatabase.driver(cfg.get('uri') or cfg.get('host') or 'neo4j://localhost:7687', auth=(cfg.get('user') or 'neo4j', cfg.get('password') or ''))
    try:
        with drv.session(database=cfg.get('database') or None, default_access_mode=nj.READ_ACCESS) as s:
            rows = s.execute_read(lambda tx: [r.data() for r in tx.run(cfg.get('cypher') or 'RETURN 1 AS ok', cfg.get('params') or {})])
    finally: drv.close()
    return _rows(rows, cfg, 'rows')


RUN = {'mongodb': run_mongodb, 'redis': run_redis, 'neo4j': run_neo4j}
PROBE = {'mongodb': {}, 'redis': {'command': 'DBSIZE'}, 'neo4j': {'cypher': 'RETURN 1 AS ok'}}
TITLES = {'mongodb': 'MongoDB', 'redis': 'Redis', 'neo4j': 'Neo4j'}


def test(store, c) -> str:
    "The card's Test: its cheapest read - MongoDB lists the collections, Redis counts the keys, Neo4j returns 1."
    from .reports import _card
    head, _ = RUN[c['Type']]({**_card(store, c['Type'], 'password', c['ConnectorId']), **PROBE[c['Type']], 'max_rows': 50})
    return f"{TITLES[c['Type']]} answered: {head}"
