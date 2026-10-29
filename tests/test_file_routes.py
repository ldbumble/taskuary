"""Every road to a file an agent made, a page it showed or published, or a mail attachment: Open and Download both reach it.

The owner, 2026-10-28: "this did not work - both preview and download?". On a copy of their home every file the page offered
answered 200 - the roads broke around the routes: the desktop window cancelled every download (pywebview ships downloads off), a
terminal agent saved its workbooks to Downloads where no route reaches, a published page titled with an en dash was a 500 on Open
and Download (a hand-written Content-Disposition), and a file gone from disk took the window to a raw JSON 404 with no way back."""
import shutil, unittest, zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import quote, unquote

from fastapi.testclient import TestClient

from taskuary import config, outputs, server, session_artifacts
from taskuary.store import MemoryStore, task_ref

NAMES = ('vendor pricing v9.xlsx', 'TQ-0012 % Collected all-in-one v9.xlsx', 'Q3 #2 rates.csv', 'Résumé – Gail Moreno.md',
         '報告 summary.pdf', 'plain.txt')


def _docx(path: Path):
    "A Word document as Word writes one - the parts the preview reads, nothing else."
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body = (f'<w:document xmlns:w="{W}"><w:body>'
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Vendor review</w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">Payworth is </w:t></w:r><w:r><w:t>cheaper.</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Vendor</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Cost</w:t></w:r></w:p></w:tc></w:tr>'
            '<w:tr><w:tc><w:p><w:r><w:t>Trainly</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>480</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '<w:p/></w:body></w:document>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>'); z.writestr('word/document.xml', body)


class FileRoutesTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.tid = self.store.create_task({'Title': 'Compare training vendors', 'Kind': 'general'}, 'owner')
        self.dir = outputs.folder(self.tid); self.dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        for i, n in enumerate(NAMES): (self.dir / n).write_bytes(f'file {i} {n}'.encode('utf-8'))
        _docx(self.dir / 'review.docx')
        (config.home() / 'config.toml').touch()
        p = mock.patch.object(server, 'store', self.store); p.start(); self.addCleanup(p.stop)
        self.client = TestClient(server.app)

    def rows(self): return {r['name']: r for r in self.client.get(f'/api/task-outputs/{self.tid}').json()['data']}

    # -- the outputs folder ------------------------------------------------------------------------------------------------------
    def test_every_name_the_listing_gives_opens_and_downloads_as_itself(self):
        rows = self.rows()
        self.assertEqual(set(rows), {*NAMES, 'review.docx'})
        for n in NAMES:
            url = rows[n]['url']
            self.assertNotIn(' ', url); self.assertNotIn('#', url)          # '%', '#' and the rest travel encoded
            self.assertEqual(unquote(url.rsplit('/', 1)[1]), n)
            got = self.client.get(url, params={'download': 'true'})
            self.assertEqual(got.status_code, 200, n)
            self.assertEqual(got.content, (self.dir / n).read_bytes(), n)
            cd = got.headers['content-disposition']
            self.assertTrue(cd.startswith('attachment;'), cd)
            self.assertIn(quote(n) if quote(n) != n else f'"{n}"', cd)        # the file's own name, RFC 5987 where it is not plain
            self.assertEqual(self.client.head(url).status_code, 200, n)       # what the page asks before it saves

    def test_open_is_inline_for_what_the_page_draws_and_attachment_for_the_rest(self):
        rows = self.rows()
        def get(n, **q): return self.client.get(rows[n]['url'], params=q)
        self.assertTrue(get('報告 summary.pdf').headers['content-disposition'].startswith('inline'))
        self.assertEqual(get('報告 summary.pdf').headers['content-type'], 'application/pdf')
        self.assertTrue(get('Q3 #2 rates.csv').headers['content-disposition'].startswith('inline'))
        self.assertTrue(get('Q3 #2 rates.csv').headers['content-type'].startswith('text/plain'))
        self.assertTrue(get('vendor pricing v9.xlsx').headers['content-disposition'].startswith('attachment'))

    def test_a_file_that_is_gone_says_so_with_its_folder(self):
        url = self.rows()['TQ-0012 % Collected all-in-one v9.xlsx']['url']
        (self.dir / 'TQ-0012 % Collected all-in-one v9.xlsx').unlink()
        got = self.client.get(url, params={'download': 'true'})
        self.assertEqual(got.status_code, 404)
        why = got.json()['detail']
        self.assertIn('TQ-0012 % Collected all-in-one v9.xlsx was moved or deleted', why)
        self.assertIn(str(self.dir), why)                                     # where to look: its folder
        self.assertEqual(self.client.head(url).status_code, 404)

    def test_a_word_document_previews_as_its_words(self):
        row = self.rows()['review.docx']
        self.assertEqual(row['preview'], 'document')
        got = self.client.get(row['url'], params={'preview': 'true'}).json()
        self.assertEqual(got['blocks'], [{'text': 'Vendor review', 'heading': True}, {'text': 'Payworth is cheaper.'},
                                         {'rows': [['Vendor', 'Cost'], ['Trainly', '480']]}])
        self.assertFalse(got['more'])
        (self.dir / 'broken.docx').write_bytes(b'not a zip')
        self.assertEqual(self.client.get(f'/api/task-outputs/{self.tid}/broken.docx', params={'preview': 'true'}).status_code, 422)

    def test_a_long_document_previews_its_start(self):
        W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        paras = ''.join(f'<w:p><w:r><w:t>line {i}</w:t></w:r></w:p>' for i in range(outputs.DOC_BLOCKS + 20))
        with zipfile.ZipFile(self.dir / 'long.docx', 'w') as z: z.writestr('word/document.xml', f'<w:document xmlns:w="{W}"><w:body>{paras}</w:body></w:document>')
        got = outputs.document(self.dir / 'long.docx')
        self.assertEqual(len(got['blocks']), outputs.DOC_BLOCKS)
        self.assertTrue(got['more'])

    # -- pages shown and published -----------------------------------------------------------------------------------------------
    def _artifact(self, name, kind, ctype, body, suffix):
        d = session_artifacts.root() / str(self.tid); d.mkdir(parents=True, exist_ok=True)
        p = d / f'{kind}-{len(list(d.iterdir()))}{suffix}'; p.write_text(body, encoding='utf-8')
        self.addCleanup(shutil.rmtree, d, True)
        return self.store.add_task_artifact({'TaskId': self.tid, 'Name': name, 'ContentType': ctype, 'Size': p.stat().st_size,
                                             'Path': str(p), 'Kind': kind, 'CreatedBy': 'agent'}), p

    def test_a_page_titled_with_an_en_dash_opens_and_downloads(self):
        aid, p = self._artifact('Taken care of – the vendor review', 'claude_artifact', 'text/html', '<h1>Review</h1><script>x()</script>', '.html')
        opened = self.client.get(f'/api/task-artifacts/{aid}')
        self.assertEqual(opened.status_code, 200)                             # was UnicodeEncodeError: a 500
        self.assertTrue(opened.headers['content-type'].startswith('text/plain'))   # never run as Taskuary
        saved = self.client.get(f'/api/task-artifacts/{aid}', params={'download': 'true'})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.content, p.read_bytes())
        cd = saved.headers['content-disposition']
        self.assertTrue(cd.startswith('attachment;'))
        self.assertIn(quote('Taken care of – the vendor review.html'), cd)     # its own extension: it opens in a browser
        self.assertEqual(saved.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.head(f'/api/task-artifacts/{aid}').status_code, 200)

    def test_a_name_with_a_quote_keeps_the_header_whole(self):
        aid, _ = self._artifact('The "final" plan.md', 'shown', 'text/markdown', '# Plan', '.md')
        cd = self.client.get(f'/api/task-artifacts/{aid}', params={'download': 'true'}).headers['content-disposition']
        self.assertIn(quote('The "final" plan.md'), cd)

    def test_a_page_gone_from_disk_says_so(self):
        aid, p = self._artifact('plan.md', 'shown', 'text/markdown', '# Plan', '.md')
        p.unlink()
        got = self.client.get(f'/api/task-artifacts/{aid}', params={'download': 'true'})
        self.assertEqual(got.status_code, 404)
        self.assertIn('plan.md was moved or deleted', got.json()['detail'])

    # -- mail attachments --------------------------------------------------------------------------------------------------------
    def test_an_attachment_gone_from_disk_is_told_apart_from_one_never_saved(self):
        d = config.home() / 'attachments' / '77'; d.mkdir(parents=True, exist_ok=True); self.addCleanup(shutil.rmtree, d, True)
        p = d / 'rates – 2026.xlsx'; p.write_bytes(b'xlsx')
        kept = self.store.add_attachment({'MessageId': 77, 'Name': p.name, 'ContentType': outputs.content_type(p.name), 'Size': 4, 'Inline': 0, 'Path': str(p)})
        never = self.store.add_attachment({'MessageId': 77, 'Name': 'cloud link.pdf', 'ContentType': 'application/pdf', 'Size': 0, 'Inline': 0, 'Path': ''})
        got = self.client.get(f'/api/attachments/{kept}', params={'download': 'true'})
        self.assertEqual((got.status_code, got.content), (200, b'xlsx'))
        self.assertIn(quote(p.name), got.headers['content-disposition'])
        self.assertEqual(self.client.head(f'/api/attachments/{kept}').status_code, 200)
        p.unlink()
        self.assertIn('was moved or deleted', self.client.get(f'/api/attachments/{kept}').json()['detail'])
        self.assertIn('never saved', self.client.get(f'/api/attachments/{never}').json()['detail'])

    # -- the roads around the routes ---------------------------------------------------------------------------------------------
    def test_email_someone_attaches_a_file_the_agent_made(self):
        seen = {}
        def draft(store, tid, to, about, cc, subject, files, actor, **kw):
            seen['files'] = files; return {'ok': True, 'review_id': 1}
        with mock.patch('taskuary.outbox.task_email', draft):
            got = self.client.post(f'/api/tasks/{self.tid}/emails', json={'to': 'erin@northwind.example', 'attach': [
                {'kind': 'output', 'path': 'TQ-0012 % Collected all-in-one v9.xlsx'}]})
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(seen['files'], [('TQ-0012 % Collected all-in-one v9.xlsx', (self.dir / 'TQ-0012 % Collected all-in-one v9.xlsx').read_bytes())])
        with mock.patch('taskuary.outbox.task_email', draft):
            for bad in ('../secret.txt', 'missing.xlsx'):
                got = self.client.post(f'/api/tasks/{self.tid}/emails', json={'to': 'erin@northwind.example', 'attach': [{'kind': 'output', 'path': bad}]})
                self.assertEqual(got.status_code, 422, bad)

    def test_a_terminal_agent_is_told_where_its_files_go(self):
        "By its environment and its standing rules - never the seed, which a real TUI types under a budget (test_terminal)."
        from taskuary import terminal
        env = terminal.session_env('coding', self.tid)
        self.assertEqual(env[outputs.ENV], str(outputs.folder(self.tid)))
        self.assertTrue(outputs.folder(self.tid).is_dir())
        self.assertNotIn(outputs.ENV, terminal.session_env('coding', None))          # a bare shell has no task folder
        self.assertNotIn(outputs.ENV, terminal.session_env('coding', self.tid, stranger=True))
        older = terminal.with_fence_rule('Rules from before files had a folder.')     # an owner's AGENT.md copy from before it hears it
        self.assertIn(f'${outputs.ENV}', older)
        self.assertEqual(terminal.with_fence_rule(older), older)
        template = (Path(outputs.__file__).parent / 'templates' / 'agent.md').read_text(encoding='utf-8')
        self.assertIn(f'${outputs.ENV}', template)

    def test_the_desktop_window_saves_downloads(self):
        from taskuary import desktop
        fake = type('webview', (), {'settings': {'ALLOW_DOWNLOADS': False}})
        self.assertTrue(desktop.allow_downloads(fake))
        self.assertTrue(fake.settings['ALLOW_DOWNLOADS'])
        self.assertFalse(desktop.allow_downloads(type('old', (), {})))       # an old pywebview has no switch, and downloads already


if __name__ == '__main__':
    unittest.main()
