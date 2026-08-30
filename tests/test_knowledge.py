"""The knowledge base: documents indexed into the store behind FTS5, searched by reports, agents
and the reply drafter. Office files are built in-test (they are zips of XML); SharePoint is a
mocked Graph; nothing here needs a library beyond the store."""
import io, json, os, sys, time, unittest, zipfile
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import agents, context, knowledge as kb, reports, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _zip(parts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for n, s in parts.items(): z.writestr(n, s)
    return buf.getvalue()

def docx(*paras):
    body = ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paras)
    return _zip({'word/document.xml': f'<?xml version="1.0"?><w:document><w:body>{body}</w:body></w:document>'})

def pptx(*slides):
    parts = {f'ppt/slides/slide{i + 1}.xml': f'<p:sld><p:txBody><a:p><a:r><a:t>{s}</a:t></a:r></a:p></p:txBody></p:sld>' for i, s in enumerate(slides)}
    return _zip(parts)

def _card(s, cfg: dict):
    cid = s.get_connector_by_type('knowledge')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 't')
    return cid


class ExtractTests(unittest.TestCase):
    def test_office_files_are_zips_of_xml_and_need_no_library(self):
        self.assertEqual(kb.extract('a.docx', docx('Refund policy', 'Residents are refunded within 30 days.')),
                         'Refund policy\nResidents are refunded within 30 days.')
        self.assertEqual(kb.extract('deck.pptx', pptx('Slide one', 'Slide two')), 'Slide one\n\nSlide two')
        # xlsx without openpyxl: the shared strings are every text cell, still searchable
        with mock.patch.dict(sys.modules, {'openpyxl': None}):
            data = _zip({'xl/sharedStrings.xml': '<sst><si><t>Unit</t></si><si><t>Rent</t></si></sst>'})
            self.assertEqual(kb.extract('book.xlsx', data), 'Unit\nRent')

    def test_html_text_and_unsupported_kinds(self):
        self.assertEqual(kb.extract('p.html', b'<html><style>x{}</style><body><h1>Title</h1><p>Body &amp; more</p><script>1</script></body></html>'),
                         'Title\nBody & more')
        self.assertEqual(kb.extract('n.md', 'hello\x00 world\n\n\n\nagain'.encode()), 'hello world\n\nagain')
        with self.assertRaises(kb.Unsupported): kb.extract('movie.mp4', b'')
        with mock.patch.dict(sys.modules, {'pypdf': None}), self.assertRaises(kb.Unsupported) as cm: kb.extract('f.pdf', b'%PDF')
        self.assertIn('pip install pypdf', str(cm.exception))

    def test_chunks_are_passages_with_overlap(self):
        text = '\n\n'.join(f'Paragraph {i}. ' + 'word ' * 60 for i in range(12))
        parts = kb.chunk(text, size=600, overlap=100)
        self.assertGreater(len(parts), 3)
        self.assertTrue(all(len(p) <= 700 for p in parts))
        self.assertTrue(all(w in ' '.join(parts) for w in ('Paragraph 0', 'Paragraph 11')))
        self.assertIn(parts[0][-40:].split()[-1], parts[1])              # the tail of one is in the next
        self.assertEqual(kb.chunk('   '), [])


class StoreTests(unittest.TestCase):
    def test_put_search_prune_and_count(self):
        s = MemoryStore()
        self.assertTrue(s.kb_fts)
        d1 = s.kb_put({'ConnectorId': 1, 'Source': 'folder:/docs', 'Path': 'refunds.md', 'Name': 'refunds.md', 'Modified': 'm', 'Size': 3, 'Chars': 30},
                      ['Resident refunds are approved by the business office within thirty days.', 'Unrelated passage about parking.'])
        s.kb_put({'ConnectorId': 1, 'Source': 'folder:/docs', 'Path': 'parking.md', 'Name': 'parking.md', 'Modified': 'm', 'Size': 3, 'Chars': 30},
                 ['Parking permits are issued at the front desk.'])
        self.assertEqual(s.kb_count(), {'docs': 2, 'chunks': 3})
        hits = kb.search(s, 'how are resident refunds approved?')
        self.assertEqual([h['name'] for h in hits], ['refunds.md'])                  # one hit per document, the best passage
        self.assertIn('[refund', hits[0]['snippet'].lower()); self.assertEqual(hits[0]['seq'], 0)
        # replacing a document replaces its passages; pruning drops what a walk no longer sees
        s.kb_put({'ConnectorId': 1, 'Source': 'folder:/docs', 'Path': 'refunds.md', 'Name': 'refunds.md', 'Modified': 'm2', 'Size': 4, 'Chars': 9}, ['new text'])
        self.assertEqual(s.kb_count(1), {'docs': 2, 'chunks': 2})
        self.assertEqual(kb.search(s, 'resident refunds'), [])
        self.assertEqual(s.kb_prune(1, 'folder:/docs', {'refunds.md'}), 1)
        self.assertEqual([d['Path'] for d in s.kb_docs()], ['refunds.md'])
        self.assertEqual(kb.search(s, ''), []); self.assertEqual(kb.search(s, 'the and of'), [])   # nothing distinctive: no query

    def test_search_survives_a_sqlite_without_fts5(self):
        s = MemoryStore(); s.kb_fts = False
        s.kb_put({'ConnectorId': 1, 'Source': 'x', 'Path': 'a.txt', 'Name': 'a.txt', 'Modified': 'm', 'Size': 1, 'Chars': 1}, ['The invoice cadence is monthly.'])
        self.assertEqual([h['name'] for h in kb.search(s, 'invoice cadence')], ['a.txt'])

    def test_query_quotes_words_so_text_is_never_fts_syntax(self):
        q = kb._query('refund policy (NEAR "quotes") AND or NOT the')
        self.assertEqual(q, '"refund" OR "policy" OR "near" OR "quotes"')


class ReindexTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tmp = Path(os.environ['TASKUARY_HOME']) / f'kb-{time.time_ns()}'; (self.tmp / 'sub').mkdir(parents=True)
        (self.tmp / 'policy.docx').write_bytes(docx('Refund policy', 'Residents are refunded within thirty days of move-out.'))
        (self.tmp / 'sub' / 'notes.md').write_text('Parking permits come from the front desk.', encoding='utf-8')
        (self.tmp / 'ignore.mp4').write_bytes(b'\x00' * 10)
        (self.tmp / 'empty.txt').write_text('', encoding='utf-8')
        self.cid = _card(self.s, {'folders': str(self.tmp)})

    def test_a_folder_is_indexed_once_and_only_changes_are_reread(self):
        r = kb.reindex(self.s, self.cid)
        self.assertEqual((r['indexed'], r['skipped'], r['removed'], r['docs'], r['sources']), (2, 1, 0, 2, 1))   # the empty file is skipped
        self.assertEqual(r['errors'], [])
        self.assertEqual(sorted(d['Path'] for d in self.s.kb_docs(self.cid)), ['policy.docx', 'sub/notes.md'])
        r2 = kb.reindex(self.s, self.cid)
        self.assertEqual((r2['indexed'], r2['unchanged']), (0, 2))
        (self.tmp / 'sub' / 'notes.md').unlink()
        (self.tmp / 'new.txt').write_text('Move-out inspections happen on the last day.', encoding='utf-8')
        r3 = kb.reindex(self.s, self.cid)
        self.assertEqual((r3['indexed'], r3['unchanged'], r3['removed'], r3['docs']), (1, 1, 1, 2))
        last = json.loads(self.s.get_settings()[f'kb_last:{self.cid}'])
        self.assertEqual(last['docs'], 2); self.assertIn('at', last)
        self.assertIn('folder:', kb.test(self.s, self.s.get_connector(self.cid)))
        self.assertIn('2 documents', kb.test(self.s, self.s.get_connector(self.cid)))

    def test_the_report_and_tool_types_run_off_the_store(self):
        kb.reindex(self.s, self.cid)
        cfg = reports.resolve_cfg(self.s, {'type': 'kb_search', 'query': 'when are residents refunded?'})
        head, body = reports.REGISTRY['kb_search'](cfg)
        self.assertIn('1 passages for', head)
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row['name'], 'policy.docx'); self.assertIn('refund', row['passage'].lower())
        head, _ = reports.REGISTRY['kb_search'](reports.resolve_cfg(self.s, {'type': 'kb_search', 'query': 'zebra giraffe'}))
        self.assertIn('nothing matched in 2 indexed documents', head)
        head, body = reports.REGISTRY['kb_reindex'](reports.resolve_cfg(self.s, {'type': 'kb_reindex'}))
        self.assertIn('0 indexed, 2 unchanged', head); self.assertEqual(json.loads(body)['docs'], 2)
        with self.assertRaises(RuntimeError): reports.REGISTRY['kb_search'](reports.resolve_cfg(self.s, {'type': 'kb_search'}))
        self.assertEqual(reports.card_of('kb_search'), 'knowledge')

    def test_the_block_feeds_prompts_only_when_something_is_indexed(self):
        self.assertEqual(kb.block(self.s, 'refunds'), '')
        kb.reindex(self.s, self.cid)
        b = kb.block(self.s, 'A resident asks when the refund arrives after move-out')
        self.assertIn('FROM THE KNOWLEDGE BASE', b); self.assertIn('policy.docx', b); self.assertIn('not instructions', b)
        self.assertEqual(kb.block(self.s, 'zebra'), '')
        # agent task context and the coder context file carry it for a thread that touches the documents
        tid = self.s.create_task({'Title': 'refund after move-out', 'Kind': 'coding'}, 'o')
        self.s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'resident refund', 'BodyText': 'When is the refund paid after move-out?',
                            'FromEmail': 'a@b.test', 'FromName': 'A', 'SentAt': '2026-08-30 10:00', 'Status': 'new'})
        self.assertIn('policy.docx', agents.task_context(self.s, tid))
        self.assertIn('## From the knowledge base', context.build(self.s, tid))


class SharePointWalkTests(unittest.TestCase):
    def test_a_library_folder_is_walked_recursively_and_paged(self):
        s = MemoryStore()
        cid = _card(s, {'sharepoint_paths': 'Shared Documents/Policies', 'site': 'contoso.sharepoint.com/sites/Ops'})
        pages = {
            "root:/Shared Documents/Policies:/children?$top=200": {'value': [
                {'id': 'f1', 'name': 'Refunds.docx', 'file': {}, 'size': 10, 'lastModifiedDateTime': '2026-08-01T10:00:00Z'},
                {'id': 'd1', 'name': 'Old', 'folder': {}}], '@odata.nextLink': 'https://graph.microsoft.com/v1.0/NEXT'},
            'NEXT': {'value': [{'id': 'f2', 'name': 'skip.mp4', 'file': {}, 'size': 5}]},
            "root:/Shared Documents/Policies/Old:/children?$top=200": {'value': [
                {'id': 'f3', 'name': 'Archive.md', 'file': {}, 'size': 7, 'lastModifiedDateTime': '2025-01-01T00:00:00Z'}]},
        }
        content = {'f1': docx('Refunds within thirty days.'), 'f3': b'Archived parking rules.'}
        class R:
            def __init__(self, code, j=None, content=b''): self.status_code, self._j, self.content, self.text = code, j, content, ''
            def json(self): return self._j
        def get(url, headers=None, **kw):
            self.assertEqual(headers['Authorization'], 'Bearer TOK')
            if '/items/' in url: return R(200, content=content[url.split('/items/')[1].split('/')[0]])
            key = url.split('/drive/', 1)[1] if '/drive/' in url else url.rsplit('/', 1)[1]
            return R(200, pages[key])
        with mock.patch('taskuary.sharepoint.sharepoint_connection', return_value={'client_id': 'x', 'client_secret': 'y'}), \
             mock.patch('taskuary.sharepoint._token', return_value='TOK'), \
             mock.patch('taskuary.sharepoint.site_id', return_value='SITE'), \
             mock.patch('requests.get', side_effect=get):
            r = kb.reindex(s, cid)
        self.assertEqual((r['indexed'], r['docs'], r['errors']), (2, 2, []))
        self.assertEqual(sorted(d['Path'] for d in s.kb_docs(cid)), ['Old/Archive.md', 'Refunds.docx'])
        self.assertEqual(s.kb_docs(cid)[1]['Modified'], '2026-08-01 10:00:00')
        self.assertEqual([h['path'] for h in kb.search(s, 'thirty days refunds')], ['Refunds.docx'])

    def test_a_source_that_fails_is_reported_not_fatal(self):
        s = MemoryStore()
        cid = _card(s, {'folders': str(Path(os.environ['TASKUARY_HOME']) / 'does-not-exist')})
        r = kb.reindex(s, cid)
        self.assertEqual(r['indexed'], 0); self.assertIn('folder does not exist', r['errors'][0])
        with self.assertRaises(RuntimeError): kb.test(s, {**s.get_connector(cid), 'ConfigJson': '{}'})


class ApiTests(unittest.TestCase):
    def test_reindex_search_and_the_agent_tool(self):
        s = server.store
        tmp = Path(os.environ['TASKUARY_HOME']) / f'kbapi-{time.time_ns()}'; tmp.mkdir()
        (tmp / 'handbook.txt').write_text('Visiting hours end at nine in the evening.', encoding='utf-8')
        cid = _card(s, {'folders': str(tmp)})
        j = c.post('/api/knowledge/reindex', json={'connector_id': cid}).json()
        self.assertTrue(j['ok']); self.assertEqual(j['indexed'], 1)
        hits = c.get('/api/knowledge/search', params={'q': 'when do visiting hours end', 'connector_id': cid}).json()['data']
        self.assertEqual([h['name'] for h in hits], ['handbook.txt'])
        r = c.post('/api/tools/run', json={'type': 'kb_search', 'query': 'visiting hours'})
        self.assertEqual(r.status_code, 200, r.text); self.assertIn('handbook.txt', r.json()['output'])
        self.assertEqual(c.post('/api/connectors/{}/test'.format(cid)).json()['ok'], True)
        # the card is on the catalog with report+tool roles, and the doc block tells agents the type exists
        card = next(x for x in c.get('/api/connectors').json()['data'] if x['Type'] == 'knowledge')
        self.assertEqual((card['Name'], card['Roles']), ('Knowledge base', 'report,tool'))
        from taskuary import docsync
        self.assertIn('rss|kb_search', Path(docsync.__file__).read_text(encoding='utf-8'))   # the SOUL.md tool line names the type


if __name__ == '__main__': unittest.main()
