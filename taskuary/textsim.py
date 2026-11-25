"""Which texts are about the same thing - by MEANING, never by the words they share (the owner, 2026-10-28: "for similarity use
embeddings"). Two shared title words, half a remembered subject's words, a stopword list: each decided what a text meant with a
rule about words, and each was wrong in both directions - "Payworth timeout" and "Pay ... timed out" share none, a greeting and a
weekday share two with anything.

The embedder is the knowledge base's own (kbembed.make): the same server, the same model, the same scrub before a text leaves. The
hub's own short texts - a task's title and summary, a memory line - are embedded once and kept in text_vec, keyed by what they are
("task:12") with a hash of what they said, so a retitled task is embedded again and an unchanged one never. The arrival is embedded
once per call (and remembered for the few calls one triage makes).

What this hands back is a RANKING for the model to read - candidates for triage's same_as, notes in scope - never a verdict. With no
embedder (semantic search off, the server down) `rank` says None, and every caller falls back to STRUCTURE: the same sender, the same
thread, the same conversation, the newest first.
"""
import hashlib, time
from collections import OrderedDict
from loguru import logger

from . import kbembed

DOWN_SECS = 120          # a server that just failed is not asked again inside a triage's few calls: seconds each, not a timeout each
QUERIES = 64             # arrivals whose vector is remembered: one triage asks for the same arrival's neighbours several times
_state = {'down_until': 0.0}
_qcache = OrderedDict()


def _norm(t) -> str: return ' '.join(str(t or '').split())
def _hash(t: str) -> str: return hashlib.sha1(t.encode('utf-8', 'replace')).hexdigest()


def embedder(store):
    """The settings' embedder at an inline timeout, or None: semantic search off, or the server failed a moment ago."""
    if time.time() < _state['down_until']: return None
    try: return kbembed.make(store, kbembed.QUERY_TIMEOUT)
    except Exception as e: logger.debug(f'textsim: no embedder - {e}'); return None


def available(store) -> bool: return embedder(store) is not None
def floor(store) -> float: return kbembed.floor(store)       # the least similarity that counts as alike - the embedder's own setting


def _query(embed, text: str):
    k = (embed.model, _hash(text))
    if k in _qcache: _qcache.move_to_end(k); return _qcache[k]
    v = kbembed.unpack(embed([text])[0])
    _qcache[k] = v
    while len(_qcache) > QUERIES: _qcache.popitem(last=False)
    return v


def vectors(store, embed, items: list) -> dict:
    """{key: packed vector} for [(key, text)] - read from text_vec where the text is unchanged, embedded (and kept) where it is not."""
    items = [(k, _norm(t)) for k, t in items if _norm(t)]
    have = store.text_vecs(embed.model, [k for k, _ in items])
    todo = [(k, t) for k, t in items if have.get(k, ('',))[0] != _hash(t)]
    if todo:
        got = [(k, _hash(t), v) for (k, t), v in zip(todo, embed([t for _, t in todo]))]
        store.text_vec_put(embed.model, got)
        have.update({k: (h, v) for k, h, v in got})
    return {k: have[k][1] for k, _ in items if k in have}


def rank(store, query: str, items: list, k: int = None, least: float = None):
    """[(key, similarity)] best first - at most k, none under `least` (the knowledge base's own floor by default) - for [(key, text)]
    against `query`. None when there is no embedder, or it failed: the caller's structural road then decides what is shown."""
    q = _norm(query)[:kbembed.QUERY_CHARS]
    embed = embedder(store)
    if embed is None: return None
    items = [(key, t) for key, t in items if _norm(t)]
    if not q or not items: return []
    try: qv, vs = _query(embed, q), vectors(store, embed, items)
    except Exception as e:
        _state['down_until'] = time.time() + DOWN_SECS
        logger.warning(f'textsim: the embedder failed, ranking by structure for {DOWN_SECS}s - {e}'); return None
    rows = [(key, len(b) // 4, b) for key, b in vs.items()]
    return kbembed.nearest(qv, rows, k or len(rows), kbembed.floor(store) if least is None else least)


# WHAT BEARS ON THIS, READ BY A MODEL WHERE NO EMBEDDER RUNS (the owner, 2026-11-16: "great example of terrible memory. It should know to
# look in [the app] without spending a bunch of tokens"). Semantic search is off on most computers, and there `rank` says None: the Hub's
# search then found only a post carrying the agent's whole query word for word ("0 Hub posts ... nothing matched in 267 posts" over sixty
# about that very system), and past tasks on the same system reached the agent only from the same sender. A light model reads the
# numbered lists instead - a judgement of meaning, one call for every list, never a count of shared words
PICK_LINE = 160
PICK_SYSTEM = ('An agent is about to work a task. Below are numbered lists of what is already known - each list says what it holds - '
               'and then the task. Pick the entries that bear on THIS task: the same system, the same kind of problem, where its data or code lives. Best '
               'first, at most {k} from each list, none from a list where nothing fits - a shared word alone is not a fit. '
               'Answer JSON {{"picks": ["<id>", ...]}} with the ids as written.')


def pick(store, query: str, groups: dict, k: int = 5, about: dict = None, task_id=None, brain=None):
    """{group: [key, ...]} best first, at most `k` each - for `groups` {name: [(key, text)]} against `query`: ranked by embeddings when an
    embedder runs (`rank`), else one light model call reading every list (`about` {name: what the list holds}), else None (no AI either:
    the caller's structural road decides)."""
    groups = {g: [(key, t) for key, t in items if _norm(t)] for g, items in groups.items()}
    if not _norm(query) or not any(groups.values()): return {g: [] for g in groups}
    if available(store):
        out = {g: rank(store, query, items, k) for g, items in groups.items()}
        if all(v is not None for v in out.values()): return {g: [key for key, _ in v] for g, v in out.items()}
    from . import llm
    try: brain = brain or llm.build_llm(store, job='rank', gear='light', task_id=task_id)
    except Exception as e: logger.debug(f'textsim: no brain to pick with - {e}'); return None
    if not brain: return None
    ids = {f'{g.upper()}{i}': (g, key) for g, items in groups.items() for i, (key, _t) in enumerate(items, 1)}
    lists = '\n\n'.join(f"{g.upper()} - {(about or {}).get(g) or g}:\n" + '\n'.join(f"{g.upper()}{i}. {_norm(t)[:PICK_LINE]}" for i, (_k, t) in enumerate(items, 1))
                        for g, items in groups.items() if items)
    try:
        # ...the lists FIRST and the task last: the same for every task until one closes or a note is added, so the next task's call reads
        # them from the provider's cache (cost, 2026-11-24: ~13K tokens a pick, 8% of them cached with the task in front)
        a = llm.ask_json(brain, PICK_SYSTEM.format(k=k), f'{lists}\n\nTHE TASK:\n{_norm(query)[:kbembed.QUERY_CHARS]}',
                         want={'type': 'object', 'properties': {'picks': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['picks']})
    except Exception as e: logger.info(f'textsim: the model did not pick - {e}'); return None
    got = (a.data or {}).get('picks') if isinstance(a.data, dict) else None
    if not isinstance(got, list): return None
    out = {g: [] for g in groups}
    for i in got:
        g, key = ids.get(str(i).strip().upper().rstrip('.'), (None, None))
        if g and key not in out[g] and len(out[g]) < k: out[g].append(key)
    return out
