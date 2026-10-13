"""Optional semantic search for the knowledge base (knowledge.py).

Off by default, and while it is off nothing here runs: no embedder is built and no vector is written.
Nothing it needs is a required dependency (numpy, when installed, is only imported to speed up the scan). Switched on (Settings -> Assistant) a passage is
embedded as it is indexed, and `knowledge.search` merges the nearest passages with the keyword hits.

- The embedder speaks the OpenAI embeddings surface (`POST {url}/v1/embeddings`), the same standard
  llm.py already uses for the Ollama brain. The default is a small model on Ollama at 127.0.0.1, so a
  passage never leaves the machine; LM Studio, llama.cpp and vLLM answer the same call. Pointing the URL
  at a remote server sends your documents' text there - that is the owner's call, and the help says so.
  What is sent has been through redact.scrub, the same credential scrub every hosted model call gets.
- The vectors live in the knowledge index's own SQLite database (store.kb_vec), one unit-length
  float32 BLOB per passage, written in the same transaction as the passage. Search is a brute-force dot
  product over all of them: numpy when it is installed (`pip install taskuary[semantic]`), pure Python
  when it is not. For one owner's few thousand documents that is milliseconds to a fraction of a second
  (tools/bench_kb_semantic.py), and a vector database is infrastructure somebody else has to run.
- Keyword and vector hits are merged by reciprocal rank fusion: it needs no score calibration between
  bm25 and cosine, which is why it is the simple, proven choice.
"""
import array, math, time
from loguru import logger

DEFAULT_URL, DEFAULT_MODEL, DEFAULT_MIN = 'http://127.0.0.1:11434', 'nomic-embed-text', 0.5
BATCH = 32                 # passages per request: a local server answers a few dozen at once without a timeout
QUERY_CHARS = 2000         # a thread can be pages long; the start of it is what the question is about
RRF_K = 60                 # the constant from the original paper; it only damps how fast the ranks fall off

try:
    import numpy as _np
except ImportError:
    _np = None


def enabled(store) -> bool:
    return store.get_setting('kb_semantic', '0') == '1'

def floor(store) -> float:
    """The least cosine similarity a passage needs to count as a hit. A nearest-neighbour search always has
    NEAREST neighbours, even when nothing is close - without a floor `block()` would quote the least
    unrelated paragraph into every prompt. It depends on the model, so it is a setting."""
    try: return max(0.0, min(1.0, float(store.get_setting('kb_semantic_min') or DEFAULT_MIN)))
    except (TypeError, ValueError): return DEFAULT_MIN


# ── vectors ───────────────────────────────────────────────────────────────────────────────────
def unit(v) -> list:
    """The vector scaled to length 1, so a dot product IS the cosine. Refuses what is not a usable vector."""
    n = math.sqrt(sum(x * x for x in v))
    if not v or not n or not math.isfinite(n): raise ValueError('the embedder returned an empty or zero vector')
    return [x / n for x in v]

def pack(v) -> bytes:
    return array.array('f', unit(v)).tobytes()

def unpack(b: bytes) -> array.array:
    a = array.array('f'); a.frombytes(b); return a


def nearest(qv, rows: list, k: int, least: float = 0.0) -> list:
    """[(ChunkId, similarity)] best first, at most k, none below `least`. `rows` is store.kb_vectors:
    [(ChunkId, Dim, blob)]; a row of another dimension cannot be compared and is skipped."""
    q = list(unit(qv))
    rows = [r for r in rows if r[1] == len(q)]
    if not rows: return []
    if _np is not None:
        m = _np.frombuffer(b''.join(r[2] for r in rows), dtype=_np.float32).reshape(len(rows), len(q))
        sims = m @ _np.asarray(q, dtype=_np.float32)
        top = _np.argpartition(-sims, min(k, len(rows)) - 1)[:k]
        scored = [(rows[i][0], float(sims[i])) for i in top]
    else:
        scored = [(cid, sum(map(float.__mul__, unpack(b), q))) for cid, _, b in rows]
    return sorted((s for s in scored if s[1] >= least), key=lambda s: -s[1])[:k]


def fuse(*ranked: list, k: int = RRF_K) -> list:
    """Reciprocal rank fusion: each list casts 1/(k+rank) for every key it holds, best first.
    [['a','b'], ['b','c']] -> b (in both lists) first. [(key, score)], best first."""
    score = {}
    for lst in ranked:
        for rank, key in enumerate(lst, 1): score[key] = score.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(score.items(), key=lambda kv: -kv[1])


# ── the embedder ──────────────────────────────────────────────────────────────────────────────
def make(store):
    """The embedder the settings name - a callable `embed(texts) -> [packed vector bytes]` carrying `.model` -
    or None when semantic search is off. It raises on a server that is down or answers badly; callers
    (knowledge.reindex, knowledge.search) catch that and fall back to keyword search."""
    if not enabled(store): return None
    base = (store.get_setting('kb_embed_url') or DEFAULT_URL).strip().rstrip('/')
    model = (store.get_setting('kb_embed_model') or DEFAULT_MODEL).strip()

    def embed(texts: list) -> list:
        import requests
        from . import redact
        out = []
        for i in range(0, len(texts), BATCH):
            part = [redact.scrub(t) for t in texts[i:i + BATCH]]      # a credential in a document never reaches a remote embedder
            r = requests.post(f'{base}/v1/embeddings', json={'model': model, 'input': part}, timeout=180)   # the first call loads weights
            if r.status_code != 200: raise RuntimeError(f'embeddings at {base} answered {r.status_code}: {r.text[:200]}')
            data = sorted(r.json().get('data') or [], key=lambda d: d.get('index', 0))
            if len(data) != len(part): raise RuntimeError(f'asked for {len(part)} embeddings, got {len(data)}')
            out += [pack(d['embedding']) for d in data]
        return out
    embed.model = model
    return embed


def backfill(store, embed, cid=None, per_call: int = BATCH) -> int:
    """Embed every passage that has no vector from this model yet; how many were done. Incremental - a run
    that dies halfway resumes where it stopped - and it is what makes switching the setting on after the
    library was indexed work: the next reindex fills in the rest."""
    done = 0
    while True:
        rows = store.kb_unembedded(embed.model, cid, per_call)
        if not rows: return done
        vecs = embed([r['Text'] for r in rows])
        store.kb_vec_put(embed.model, [(r['ChunkId'], v) for r, v in zip(rows, vecs)])
        done += len(rows)


def semantic_hits(store, embed, text: str, limit: int, cid=None) -> list:
    """The passages nearest the question, best first, one per document, in the shape store.kb_search returns."""
    t0 = time.time()
    qv = unpack(embed([text[:QUERY_CHARS]])[0])
    near = nearest(qv, store.kb_vectors(embed.model, cid), limit * 4, floor(store))
    hits, seen = [], set()
    for h in store.kb_chunk_hits([c for c, _ in near]):
        if h['doc_id'] not in seen: seen.add(h['doc_id']); hits.append(h)
        if len(hits) >= limit: break
    logger.debug(f'knowledge: semantic search over {len(near)} near passages in {int((time.time() - t0) * 1000)}ms')
    return hits