"""Optional semantic search for the knowledge base (kbembed.py). Off by default and then invisible;
on, a tiny fake embedder proves "different words, same meaning". No network: the embedder is a fake
and the one HTTP test mocks requests.post."""
import json, os, time, unittest
from pathlib import Path
from unittest import mock
from taskuary import kbembed, knowledge as kb
from taskuary.store import MemoryStore, DEFAULT_SETTINGS

# a three-word "language model": every word sits on one of these meaning axes, so two passages that share a
# MEANING but no word are near each other - which is the whole point, and which keywords cannot do
AXES = {'leave': 0, 'absence': 0, 'time': 0, 'off': 0, 'vacation': 0, 'holiday': 0,
        'parking': 1, 'permit': 1, 'car': 1, 'refund': 2, 'payment': 2, 'money': 2}

def fake_vec(text):
    v = [0.0, 0.0, 0.0, 0.01]
    for w in text.lower().replace('.', ' ').replace('?', ' ').split():
        if w in AXES: v[AXES[w]] += 1.0
    return v

class FakeEmbedder:
    def __init__(self, model='fake-1'): self.model, self.calls, self.texts = model, 0, []
    def __call__(self, texts):
        self.calls += 1; self.texts += list(texts)
        return [kbembed.pack(fake_vec(t)) for t in texts]

def _put(s, name, *chunks, cid=1):
    return s.kb_put({'ConnectorId': cid, 'Source': 'folder:/docs', 'Path': name, 'Name': name, 'Modified': 'm', 'Size': 1, 'Chars': 1}, list(chunks))

def _on(s, **kw):
    s.set_setting('kb_semantic', '1', 't')
    for k, v in kw.items(): s.set_setting(k, v, 't')


class OffByDefaultTests(unittest.TestCase):
    def test_the_switch_ships_off_and_off_is_exactly_todays_search(self):
        self.assertEqual(DEFAULT_SETTINGS['kb_semantic'], '0')
        s = MemoryStore()
        _put(s, 'leave.md', 'Leave of absence is granted for up to twelve weeks.')
        _put(s, 'parking.md', 'Parking permits are issued at the front desk.')
        today = lambda q: [{k: h[k] for k in ('name', 'path', 'source', 'modified', 'seq', 'score', 'snippet')}
                           for h in kb.search(s, q)]
        # what the keyword path alone returns - the thing the setting must not change
        direct = lambda q: [{**h, 'snippet': kb.passage(h.pop('text', '') or '', h.get('snippet') or '')}
                            for h in s.kb_search(kb._query(q), 8)]
        for q in ('leave of absence policy', 'parking permits', 'time off', 'zebra'):
            self.assertEqual(today(q), [{k: h[k] for k in ('name', 'path', 'source', 'modified', 'seq', 'score', 'snippet')} for h in direct(q)], q)
        # ...and no embedder is built, no vector written, even when one is available
        with mock.patch.object(kbembed, 'make', side_effect=AssertionError('the embedder must not be built while the switch is off')):
            kb.search(s, 'time off'); kb.block(s, 'time off')
            self.assertEqual(kb.reindex(s)['errors'], [])
        self.assertEqual(s.kb_vectors('fake-1'), [])

    def test_the_knobs_are_in_the_schema_with_a_group(self):
        from taskuary import settings_schema
        k = settings_schema.knobs()
        for key in ('kb_semantic', 'kb_embed_url', 'kb_embed_model', 'kb_semantic_min'):
            self.assertIn(key, k); self.assertIn(k[key]['group'], settings_schema.GROUPS); self.assertIn(key, DEFAULT_SETTINGS)
        self.assertEqual(k['kb_semantic']['type'], 'switch')


class DifferentWordsSameMeaningTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.emb = FakeEmbedder()
        _put(self.s, 'leave.md', 'Leave of absence is granted for up to twelve weeks.')
        _put(self.s, 'parking.md', 'Parking permits are issued at the front desk.')
        _put(self.s, 'refunds.md', 'Refund payment arrives within thirty days.')

    def test_time_off_finds_the_leave_policy_only_with_it_on(self):
        self.assertEqual(kb.search(self.s, 'time off'), [])                       # keywords: no shared word
        _on(self.s)
        with mock.patch.object(kbembed, 'make', return_value=self.emb):
            self.assertEqual(kbembed.backfill(self.s, self.emb), 3)
            hits = kb.search(self.s, 'time off')
            self.assertEqual([h['name'] for h in hits], ['leave.md'])             # unrelated passages fall under the floor
            self.assertEqual(set(hits[0]) - {'seq'}, {'doc_id', 'name', 'path', 'source', 'modified', 'score', 'snippet', 'text'})   # the shape kb_search gives today
            self.assertIn('twelve weeks', hits[0]['snippet'])
            self.assertIn('FROM THE KNOWLEDGE BASE', kb.block(self.s, 'How much time off do I get?'))
            self.assertEqual(kb.block(self.s, 'zebra giraffe'), '')                # nothing near: still no block

    def test_a_document_found_both_ways_ranks_first_and_keeps_its_keyword_snippet(self):
        _on(self.s)
        _put(self.s, 'holiday.md', 'Holiday time is booked through the portal.')
        with mock.patch.object(kbembed, 'make', return_value=self.emb):
            kbembed.backfill(self.s, self.emb)
            hits = kb.search(self.s, 'leave of absence')
        self.assertEqual(hits[0]['name'], 'leave.md')
        self.assertIn('absence', hits[0]['snippet'])
        self.assertIn('holiday.md', [h['name'] for h in hits])                    # meaning-only neighbour joins in

    def test_search_falls_back_to_keywords_when_the_embedder_fails_or_nothing_is_embedded(self):
        _on(self.s)
        with mock.patch.object(kbembed, 'make', side_effect=RuntimeError('connection refused')):
            self.assertEqual([h['name'] for h in kb.search(self.s, 'parking permits')], ['parking.md'])
        with mock.patch.object(kbembed, 'make', return_value=self.emb):           # on, but never indexed with vectors
            self.assertEqual([h['name'] for h in kb.search(self.s, 'parking permits')], ['parking.md'])
            self.assertEqual(kb.search(self.s, 'time off'), [])


class IndexingTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tmp = Path(os.environ['TASKUARY_HOME']) / f'kbsem-{time.time_ns()}'; self.tmp.mkdir(parents=True)
        (self.tmp / 'leave.md').write_text('Leave of absence is granted for up to twelve weeks.', encoding='utf-8')
        (self.tmp / 'parking.md').write_text('Parking permits come from the front desk.', encoding='utf-8')
        cid = self.s.get_connector_by_type('knowledge')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps({'folders': str(self.tmp)})}, 't')
        self.cid, self.emb = cid, FakeEmbedder()

    def test_embeddings_are_built_during_reindex_and_only_for_what_changed(self):
        _on(self.s)
        with mock.patch.object(kbembed, 'make', return_value=self.emb):
            r = kb.reindex(self.s, self.cid)
            self.assertEqual((r['indexed'], r['errors']), (2, [])); self.assertEqual(len(self.s.kb_vectors('fake-1')), 2)
            self.assertEqual(self.emb.calls, 2)                                   # one call per new document
            r2 = kb.reindex(self.s, self.cid); self.assertEqual((r2['unchanged'], self.emb.calls), (2, 2))   # nothing re-embedded
            (self.tmp / 'parking.md').write_text('Parking permits are renewed yearly at the desk.', encoding='utf-8')
            kb.reindex(self.s, self.cid)
            self.assertEqual((self.emb.calls, len(self.s.kb_vectors('fake-1'))), (3, 2))   # the changed file only; the old vector is gone
            (self.tmp / 'parking.md').unlink(); kb.reindex(self.s, self.cid)
            self.assertEqual(len(self.s.kb_vectors('fake-1')), 1)                 # pruned documents take their vectors along
        self.assertEqual([h['name'] for h in kb.search(self.s, 'time off')], [])  # off the mock the embedder is unreachable: keywords only

    def test_switching_it_on_after_indexing_is_filled_in_by_the_next_reindex(self):
        kb.reindex(self.s, self.cid)                                              # indexed with it off
        self.assertEqual(self.s.kb_vectors('fake-1'), [])
        _on(self.s)
        with mock.patch.object(kbembed, 'make', return_value=self.emb):
            r = kb.reindex(self.s, self.cid)
            self.assertEqual((r['indexed'], r['unchanged'], r['embedded']), (0, 2, 2))
            self.assertEqual([h['name'] for h in kb.search(self.s, 'time off')], ['leave.md'])
        self.emb.model = 'fake-2'                                                 # another model: the old vectors are ignored, then replaced
        with mock.patch.object(kbembed, 'make', return_value=self.emb):
            self.assertEqual(kb.search(self.s, 'time off'), [])
            self.assertEqual(kb.reindex(self.s, self.cid)['embedded'], 2)
            self.assertEqual([h['name'] for h in kb.search(self.s, 'time off')], ['leave.md'])

    def test_a_dead_embedder_does_not_stop_indexing(self):
        _on(self.s)
        dead = mock.Mock(side_effect=ConnectionError('refused'), model='fake-1')
        with mock.patch.object(kbembed, 'make', return_value=dead):
            r = kb.reindex(self.s, self.cid)
        self.assertEqual((r['indexed'], r['docs']), (2, 2)); self.assertEqual(dead.call_count, 1)   # not hammered once per file
        self.assertTrue(any('semantic search' in e for e in r['errors']))
        self.assertEqual([h['name'] for h in kb.search(self.s, 'parking permits')], ['parking.md'])


class PartsTests(unittest.TestCase):
    def test_rank_fusion_rewards_agreement(self):
        order = [k for k, _ in kbembed.fuse(['a', 'b', 'c'], ['b', 'd'])]
        self.assertEqual(order[0], 'b'); self.assertEqual(set(order), {'a', 'b', 'c', 'd'})
        self.assertEqual(kbembed.fuse([], []), [])

    def test_nearest_ranks_by_cosine_and_applies_the_floor_in_both_scan_paths(self):
        rows = [(1, 3, kbembed.pack([1, 0, 0])), (2, 3, kbembed.pack([0.8, 0.6, 0])), (3, 3, kbembed.pack([0, 0, 1])), (4, 2, kbembed.pack([1, 0]))]
        for np_mod in (kbembed._np, None):                                        # numpy when installed, pure Python always
            with mock.patch.object(kbembed, '_np', np_mod):
                got = kbembed.nearest([1, 0, 0], rows, 5, 0.5)
                self.assertEqual([c for c, _ in got], [1, 2]); self.assertAlmostEqual(got[1][1], 0.8, places=5)   # wrong dimension skipped
                self.assertEqual(kbembed.nearest([1, 0, 0], [], 3), [])
        with self.assertRaises(ValueError): kbembed.pack([0, 0, 0])

    def test_the_http_embedder_speaks_the_openai_surface(self):
        s = MemoryStore(); _on(s, kb_embed_url='http://127.0.0.1:9/', kb_embed_model='tiny')
        class R:
            status_code = 200; text = ''
            def json(self): return {'data': [{'index': 1, 'embedding': [0, 1]}, {'index': 0, 'embedding': [1, 0]}]}
        with mock.patch('requests.post', return_value=R()) as post:
            emb = kbembed.make(s)
            vs = emb(['one', 'two'])
        self.assertEqual(emb.model, 'tiny'); self.assertEqual(post.call_args.args[0], 'http://127.0.0.1:9/v1/embeddings')
        self.assertEqual(post.call_args.kwargs['json'], {'model': 'tiny', 'input': ['one', 'two']})
        self.assertEqual([list(kbembed.unpack(v)) for v in vs], [[1.0, 0.0], [0.0, 1.0]])   # reordered by index
        with mock.patch('requests.post', return_value=R()) as post2:
            emb(['the key is AKIAABCDEFGHIJKLMNOP ok', 'fine'])
        sent = post2.call_args.kwargs['json']['input']
        self.assertNotIn('AKIAABCDEFGHIJKLMNOP', sent[0]); self.assertIn('[redacted:', sent[0]); self.assertEqual(sent[1], 'fine')   # scrubbed on the way out
        bad = R(); bad.status_code = 500; bad.text = 'boom'
        with mock.patch('requests.post', return_value=bad), self.assertRaises(RuntimeError): emb(['x'])
        self.assertIsNone(kbembed.make(MemoryStore()))                            # off: no embedder

    def test_a_search_waits_seconds_on_the_embedder_and_a_reindex_minutes(self):
        import requests
        s = MemoryStore(); _on(s)
        _put(s, 'parking.md', 'Parking permits are issued at the front desk.')
        with mock.patch('requests.post', side_effect=requests.Timeout('read timed out')) as post:
            hits = kb.search(s, 'parking permits')
        self.assertEqual(post.call_args.kwargs['timeout'], kbembed.QUERY_TIMEOUT)   # inline, while a triage or a draft waits
        self.assertLess(sum(kbembed.QUERY_TIMEOUT), 30)
        self.assertEqual([h['name'] for h in hits], ['parking.md'])               # a slow embedder leaves the keyword hits
        with mock.patch('requests.post', side_effect=requests.Timeout('read timed out')) as post:
            with self.assertRaises(requests.Timeout): kbembed.make(s)(['x'])
        self.assertEqual(post.call_args.kwargs['timeout'], kbembed.INDEX_TIMEOUT)  # a reindex lets the model load


if __name__ == '__main__': unittest.main()