"""Time the semantic knowledge search on a library of a few thousand passages.

    python tools/bench_kb_semantic.py [chunks=5000] [dim=384]

Measures what THIS code adds: writing vectors in the same transaction as the passages, loading them, the
brute-force scan (numpy and pure Python), and a whole hybrid `knowledge.search`. The embedder is a seeded
random-vector fake, so the model's own inference time is NOT in these numbers - that is whatever your
Ollama takes per passage (measure it with `time ollama run`/a request to /v1/embeddings). Invented text only.
"""
import os, random, sys, tempfile, time
os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='taskuary_bench_'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from unittest import mock
from taskuary import kbembed, knowledge as kb
from taskuary.store import MemoryStore

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
DIM = int(sys.argv[2]) if len(sys.argv) > 2 else 384
rnd = random.Random(7)
WORDS = [f'word{i}' for i in range(2000)]

def passage_text(): return ' '.join(rnd.choice(WORDS) for _ in range(150))      # ~1200 chars, like a real chunk

class Fake:
    model = 'bench'
    def __call__(self, texts): return [kbembed.pack([rnd.gauss(0, 1) for _ in range(DIM)]) for _ in texts]

def ms(t0): return f'{(time.perf_counter() - t0) * 1000:8.1f} ms'

s = MemoryStore(); emb = Fake()
s.set_setting('kb_semantic', '1', 'bench'); s.set_setting('kb_semantic_min', '0', 'bench')
docs = N // 5                                                                    # five passages per document
texts = [[passage_text() for _ in range(5)] for _ in range(docs)]
vecs = [emb(t) for t in texts]                                                   # the fake's own cost stays out of the timings

t0 = time.perf_counter()
for i, parts in enumerate(texts): s.kb_put({'ConnectorId': 1, 'Source': 'bench', 'Path': f'd{i}', 'Name': f'd{i}', 'Modified': 'm', 'Size': 1, 'Chars': 1}, parts)
print(f'{N} passages, keywords only          index {ms(t0)}')
s2 = MemoryStore()
t0 = time.perf_counter()
for i, parts in enumerate(texts): s2.kb_put({'ConnectorId': 1, 'Source': 'bench', 'Path': f'd{i}', 'Name': f'd{i}', 'Modified': 'm', 'Size': 1, 'Chars': 1}, parts, vecs[i], 'bench')
print(f'{N} passages, + {DIM}-d vectors        index {ms(t0)}   (storage write only)')
s2.set_setting('kb_semantic', '1', 'bench'); s2.set_setting('kb_semantic_min', '0', 'bench')
print(f'vector bytes in the database: {N * (DIM * 4 + 20) / 1e6:.1f} MB')

q = emb(['query'])[0]
t0 = time.perf_counter(); rows = s2.kb_vectors('bench'); print(f'load all vectors from SQLite        {ms(t0)}')
for label, mod in (('numpy', kbembed._np), ('pure Python', None)):
    if label == 'numpy' and mod is None: print('numpy not installed - skipping that path'); continue
    with mock.patch.object(kbembed, '_np', mod):
        best = min((lambda t: (kbembed.nearest(kbembed.unpack(q), rows, 32), time.perf_counter() - t)[1])(time.perf_counter()) for _ in range(5))
    print(f'brute-force scan, {label:11s}          {best * 1000:8.1f} ms (best of 5)')
text = ' '.join(rnd.choice(WORDS) for _ in range(12))
for label, setting in (('keyword search (today)', '0'), ('hybrid search', '1')):
    s2.set_setting('kb_semantic', setting, 'bench')
    with mock.patch.object(kbembed, 'make', return_value=emb):
        best = min((lambda t: (kb.search(s2, text), time.perf_counter() - t)[1])(time.perf_counter()) for _ in range(5))
    print(f'{label:34s}  {best * 1000:8.1f} ms (best of 5, one query embedding from the fake = ~0)')