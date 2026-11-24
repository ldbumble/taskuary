"""A file an agent makes for a task is served from that task's outputs folder, previewed, and named in its brief (outputs.py).

The shape of the bug: a researcher on Codex saved a workbook under scratch/outputs/TQ-n/, cited it with a raw marker, and when
asked to send it wrote a link to /outputs/TQ-n/<file> - a route the server never had, so the owner clicked into a 404."""
import os, shutil, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import config, guard, outputs, server
from taskuary.store import MemoryStore, task_ref


def _book(path: Path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = 'Vendors'
    ws.append(['Vendor', 'Contact', 'Annual cost'])
    ws.append(['Payworth', 'Gail Moreno', 1200])
    ws.append(['Trainly', 'Ray Colton', 480])
    ws['E1'] = '=SUM(C2:C3)'
    notes = wb.create_sheet('Notes'); notes.append(['Checked by Alex Doyle', 'x' * 900])
    path.parent.mkdir(parents=True, exist_ok=True); wb.save(path)


class TaskOutputsTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.tid = self.store.create_task({'Title': 'Compare training vendors', 'Kind': 'general'}, 'owner')
        self.other = self.store.create_task({'Title': 'Another task', 'Kind': 'general'}, 'owner')
        self.dir = outputs.folder(self.tid)
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        _book(self.dir / 'vendor comparison.xlsx')
        (self.dir / 'notes.md').write_text('# Vendors\n\nPayworth is cheaper.', encoding='utf-8')
        (self.dir / 'page.html').write_text('<script>alert(1)</script>', encoding='utf-8')
        outputs.folder(self.other).mkdir(parents=True, exist_ok=True)
        (outputs.folder(self.other) / 'secret.txt').write_text('not yours', encoding='utf-8')
        (config.home() / 'config.toml').touch()
        p = mock.patch.object(server, 'store', self.store); p.start(); self.addCleanup(p.stop)
        self.client = TestClient(server.app)

    def test_a_picture_carries_its_own_shape_so_the_page_reserves_it(self):
        """The design round, 2026-11-18: every picture in a turn was squeezed into one fixed height - a square drawn half the chat's width.
        The page draws it at its own shape, its room reserved before it loads: its pixels, read off the file's header."""
        import struct, zlib
        png = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 1200, 630, 8, 2, 0, 0, 0) + b'\0' * 4 + zlib.compress(b'')
        gif = b'GIF89a' + struct.pack('<HH', 300, 900) + b'\0' * 8
        jpg = b'\xff\xd8' + b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\0' + b'\0' * 9 + b'\xff\xc0' + struct.pack('>HBHH', 17, 8, 768, 1024) + b'\0' * 12
        for name, body, dims in (('post.png', png, [1200, 630]), ('tall.gif', gif, [300, 900]), ('photo.jpg', jpg, [1024, 768])):
            (self.dir / name).write_bytes(body)
            self.assertEqual(outputs.row(self.tid, self.dir / name, name).get('dims'), dims, name)
        self.assertNotIn('dims', outputs.row(self.tid, self.dir / 'notes.md', 'notes.md'))

    def test_a_video_carries_its_own_shape_an_upright_one_upright(self):
        """The owner, 2026-11-23: an upright video the agent made stood the chat's whole width, letterboxed in a 16:9 frame. Its shape is read
        off its header as a picture's is - an MP4's track header, turned as a phone's matrix turns it, and a WebM's pixel sizes."""
        import struct
        def box(k, body): return struct.pack('>I4s', 8 + len(body), k) + body
        def mp4(w, h, turned=False):
            m = (0, 1 << 16, 0, -(1 << 16), 0, 0, 0, 0, 1 << 30) if turned else (1 << 16, 0, 0, 0, 1 << 16, 0, 0, 0, 1 << 30)
            tkhd = b'\0\0\0\x03' + b'\0' * 20 + b'\0' * 16 + struct.pack('>9i', *m) + struct.pack('>II', w << 16, h << 16)
            sound = b'\0\0\0\x03' + b'\0' * 36 + struct.pack('>9i', *m) + b'\0' * 8      # ...an audio track has no size: the video's is read
            return box(b'ftyp', b'isom\0\0\0\0') + box(b'moov', box(b'trak', box(b'tkhd', sound)) + box(b'trak', box(b'tkhd', tkhd)))
        webm = b'\x1aE\xdf\xa3' + b'\0' * 20 + b'\xe0\x88' + b'\xb0\x82' + struct.pack('>H', 720) + b'\xba\x82' + struct.pack('>H', 1280)
        for name, body, dims in (('upright.mp4', mp4(720, 1280), [720, 1280]), ('phone.mov', mp4(1280, 720, True), [720, 1280]),
                                 ('wide.mp4', mp4(1280, 720), [1280, 720]), ('clip.webm', webm, [720, 1280])):
            (self.dir / name).write_bytes(body)
            self.assertEqual(outputs.row(self.tid, self.dir / name, name).get('dims'), dims, name)
        (self.dir / 'cut.mp4').write_bytes(box(b'ftyp', b'isom') + b'\0\0')
        self.assertNotIn('dims', outputs.row(self.tid, self.dir / 'cut.mp4', 'cut.mp4'), 'a file cut short has no shape, and no error')

    def test_the_folder_is_the_one_the_agent_picked(self):
        self.assertEqual(outputs.folder(17), config.home() / 'scratch' / 'outputs' / 'TQ-0017')

    def test_a_file_in_the_tasks_own_folder_is_served(self):
        listed = self.client.get(f'/api/task-outputs/{self.tid}').json()['data']
        names = {r['name']: r for r in listed}
        self.assertEqual(set(names), {'vendor comparison.xlsx', 'notes.md', 'page.html'})
        book = names['vendor comparison.xlsx']
        self.assertEqual((book['kind'], book['preview']), ('output', 'sheet'))
        self.assertNotIn(str(config.home()), str(listed))                       # a name, never where it lives on disk
        got = self.client.get(book['url'], params={'download': 'true'})
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.content, (self.dir / 'vendor comparison.xlsx').read_bytes())
        self.assertIn('attachment', got.headers['content-disposition'])
        self.assertEqual(self.client.get(f'/api/task-outputs/{self.tid}/notes.md').content, (self.dir / 'notes.md').read_bytes())

    def test_a_page_never_runs_as_taskuary(self):
        got = self.client.get(f'/api/task-outputs/{self.tid}/page.html')
        self.assertTrue(got.headers['content-type'].startswith('text/plain'))
        self.assertEqual(got.headers['x-content-type-options'], 'nosniff')

    def test_a_video_plays_in_place_and_seeks(self):
        "Gabi, 2026-11-08: the MP4 opened as its raw bytes - it is a video the page plays, streamed in ranges so it seeks."
        (self.dir / 'opening test.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(range(256)) * 8)
        row = next(r for r in self.client.get(f'/api/task-outputs/{self.tid}').json()['data'] if r['name'] == 'opening test.mp4')
        self.assertEqual((row['preview'], row['content_type']), ('video', 'video/mp4'))
        got = self.client.get(row['url'])
        self.assertEqual((got.status_code, got.headers['content-type']), (200, 'video/mp4'))
        self.assertIn('inline', got.headers['content-disposition'])
        part = self.client.get(row['url'], headers={'Range': 'bytes=0-15'})
        self.assertEqual((part.status_code, len(part.content)), (206, 16))
        self.assertIn('attachment', self.client.get(row['url'], params={'download': 'true'}).headers['content-disposition'])

    def test_nothing_outside_the_folder_is_served(self):
        (config.home() / 'scratch' / 'outputs' / 'loose.txt').write_text('above the folder', encoding='utf-8')
        for bad in ('..%2Floose.txt', '../loose.txt', '..%5Cloose.txt', f'..%2F{task_ref(self.other)}%2Fsecret.txt',
                    'secret.txt', 'C:%2FWindows%2Fwin.ini', '%2Fetc%2Fpasswd', 'notes.md:stream', 'nothing-here.xlsx'):
            got = self.client.get(f'/api/task-outputs/{self.tid}/{bad}')       # a client may fold `..` itself: then no such route
            self.assertIn(got.status_code, (404, 422), bad)
            self.assertNotIn('above the folder', got.text); self.assertNotIn('not yours', got.text)
        for bad in ('../loose.txt', '..\\loose.txt', '/etc/passwd', 'C:/x', 'C:x', '\\\\host\\share\\x', 'a//b', './notes.md', ''):
            self.assertIsNone(outputs.resolve(self.tid, bad), bad)
        self.assertEqual(self.client.get(f'/api/task-outputs/999/notes.md').status_code, 404)

    def test_a_link_out_of_the_folder_is_not_followed(self):
        outside = config.home() / 'outside.txt'; outside.write_text('mine', encoding='utf-8')
        try: os.symlink(outside, self.dir / 'link.txt')
        except (OSError, NotImplementedError): self.skipTest('this machine cannot make a symlink')
        self.assertIsNone(outputs.resolve(self.tid, 'link.txt'))
        self.assertNotIn('link.txt', {r['name'] for r in outputs.listing(self.tid)})

    def test_a_workbook_previews_as_rows(self):
        got = self.client.get(f'/api/task-outputs/{self.tid}/vendor%20comparison.xlsx', params={'preview': 'true'}).json()
        self.assertEqual(got['sheet'], 'Vendors')
        self.assertEqual(got['sheets'], ['Vendors', 'Notes'])
        self.assertEqual(got['rows'][0][:3], ['Vendor', 'Contact', 'Annual cost'])
        self.assertEqual(got['rows'][1][:3], ['Payworth', 'Gail Moreno', '1200'])
        self.assertFalse(got['more_rows'])
        notes = self.client.get(f'/api/task-outputs/{self.tid}/vendor%20comparison.xlsx', params={'preview': 'true', 'sheet': 'Notes'}).json()
        self.assertEqual(notes['sheet'], 'Notes')
        self.assertLessEqual(len(notes['rows'][0][1]), outputs.CELL)               # a cell is capped
        self.assertEqual(self.client.get(f'/api/task-outputs/{self.tid}/notes.md', params={'preview': 'true'}).status_code, 422)

    # A WORKBOOK ASKED FOR WHILE ITS AGENT STILL WRITES IT (the owner's live task, 2026-11-17: the file card asked for its preview the second the
    # agent was saving it, read half a zip - "File is not a zip file" - and kept "could not be read" over a workbook that was fine a moment later):
    # a file that changed just now and does not read is waited on until it stops changing, then read
    def test_a_workbook_still_being_written_is_read_once_it_settles(self):
        import threading, time
        whole = (self.dir / 'vendor comparison.xlsx').read_bytes(); half = self.dir / 'census.xlsx'
        half.write_bytes(whole[:len(whole) // 2])
        # ...its writer pauses well under the second a file must stand still to count as done (outputs.settled): a pause of a whole second
        # tied with it, and on a slow runner the check read the half file as finished (Windows CI, 2026-11-18)
        threading.Timer(0.3, lambda: half.write_bytes(whole)).start()
        got = self.client.get(f'/api/task-outputs/{self.tid}/census.xlsx', params={'preview': 'true'})
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()['sheet'], 'Vendors')

    def test_a_broken_workbook_that_is_not_changing_says_so_at_once(self):
        import time
        bad = self.dir / 'broken.xlsx'; bad.write_bytes(b'not a workbook')
        old = time.time() - 120; os.utime(bad, (old, old))
        t0 = time.monotonic()
        self.assertEqual(self.client.get(f'/api/task-outputs/{self.tid}/broken.xlsx', params={'preview': 'true'}).status_code, 422)
        self.assertLess(time.monotonic() - t0, 2)

    def test_rows_and_columns_are_capped(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        for i in range(outputs.ROWS + 50): ws.append([f'r{i}c{j}' for j in range(outputs.COLS + 10)])
        wb.save(self.dir / 'big.xlsx')
        got = outputs.sheet(self.dir / 'big.xlsx')
        self.assertEqual((len(got['rows']), len(got['rows'][0])), (outputs.ROWS, outputs.COLS))
        self.assertTrue(got['more_rows'] and got['more_cols'])

    def test_without_openpyxl_the_workbook_is_download_only(self):
        with mock.patch.object(outputs, 'can_sheet', lambda: False):
            row = next(r for r in outputs.listing(self.tid) if r['name'].endswith('.xlsx'))
            self.assertIsNone(row['preview'])
            self.assertIn('Download', row['note'])
            got = self.client.get(f'/api/task-outputs/{self.tid}/vendor%20comparison.xlsx', params={'preview': 'true'})
            self.assertEqual(got.status_code, 501)
            self.assertEqual(self.client.get(row['url'], params={'download': 'true'}).status_code, 200)

    def test_the_assistant_payload_lists_them(self):
        got = self.client.get(f'/api/tasks/{self.tid}/assistant').json()
        self.assertIn('vendor comparison.xlsx', {r['name'] for r in got['outputs']})

    def test_a_download_link_carries_the_token_in_its_query(self):
        "An <a href> cannot send a header: the outputs route takes the token in the query, as attachments do."
        cfg = {**server.cfg, 'server': {**server.cfg['server'], 'token': 'owner-secret'}}
        with mock.patch.object(server, 'cfg', cfg):
            url = f'/api/task-outputs/{self.tid}/notes.md'
            self.assertEqual(self.client.get(url).status_code, 401)
            self.assertEqual(self.client.get(url, params={'token': 'owner-secret'}).status_code, 200)

    def test_a_strangers_session_reaches_only_its_own_tasks_outputs(self):
        d = lambda p: guard.stranger_denied('GET', p, {}, self.tid, lambda k, a: None)
        self.assertEqual(d(f'/api/task-outputs/{self.tid}'), '')
        self.assertEqual(d(f'/api/task-outputs/{self.tid}/notes.md'), '')
        self.assertTrue(d(f'/api/task-outputs/{self.other}/secret.txt'))
        self.assertTrue(d(f'/api/task-outputs/{self.tid}9/x'))

    def test_a_cli_chat_is_told_where_its_files_go(self):
        from taskuary import general
        sess = general.GeneralSession(self.store, self.tid)
        sess.pick, sess.provider, sess.model = 'cli:codex', 'codex', ''
        seen = []
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: seen.append(system) or 'Done.'):
            sess.send_prompt('make the comparison a spreadsheet')
        self.assertIn(str(outputs.folder(self.tid)), seen[0])
        self.assertIn('YOUR OUTPUTS FOLDER', seen[0])



def _stamp(p: Path, n: int):
    "Files written n minutes apart, so the newest is known."
    t = 1_790_000_000 + n * 60
    os.utime(p, (t, t))


class OneOfEachTests(unittest.TestCase):
    """The owner, 2026-10-28: "it looks like it created a million attachments". A workbook saved v1..v9 beside its helper script, its log
    and a temp folder: the workbook is listed ONCE - its newest version, the eight before it behind it.
    ...and nothing it made is hidden (the owner, 2026-11-15: "anything an agent creates should not be hidden of course"): the script, the log
    and the file in tmp/ are in the list too."""
    def setUp(self):
        self.store = MemoryStore()
        self.tid = self.store.create_task({'Title': 'Vendor pricing review', 'Summary': 'Compare what Payworth and Trainly charge.',
                                           'Kind': 'general'}, 'owner')
        self.other = self.store.create_task({'Title': 'Snag list for the new office', 'Kind': 'general'}, 'owner')
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        d = outputs.folder(self.tid); d.mkdir(parents=True, exist_ok=True)
        for i in range(1, 10):
            (d / f'pricing comparison v{i}.xlsx').write_bytes(b'x' * i); _stamp(d / f'pricing comparison v{i}.xlsx', i)
        for name in ('build_sheet.py', 'run.log'): (d / name).write_text('scratch', encoding='utf-8'); _stamp(d / name, 20)
        (d / 'tmp').mkdir(); (d / 'tmp' / 'rates.csv').write_text('a,b', encoding='utf-8'); _stamp(d / 'tmp' / 'rates.csv', 21)
        (d / 'summary.pdf').write_bytes(b'%PDF'); _stamp(d / 'summary.pdf', 5)
        o = outputs.folder(self.other); o.mkdir(parents=True, exist_ok=True)
        (o / 'snag list.xlsx').write_bytes(b'x'); (o / 'plan.md').write_text('# Plan', encoding='utf-8')

    def test_nine_versions_and_scratch_are_one_file_and_eight_earlier(self):
        made = outputs.deliverables(outputs.listing(self.tid))
        self.assertEqual(sorted(r['path'] for r in made), ['build_sheet.py', 'pricing comparison v9.xlsx', 'run.log', 'summary.pdf', 'tmp/rates.csv'])
        v9 = next(r for r in made if r['name'] == 'pricing comparison v9.xlsx')
        self.assertEqual(len(v9['earlier']), 8)
        self.assertEqual(v9['earlier'][0]['name'], 'pricing comparison v8.xlsx')

    def test_a_script_is_what_it_made_alone_or_beside_a_workbook_and_reads_as_text(self):
        # the owner, 2026-11-15: he asked for a query to review, the agent saved it as a file, and nothing of it stood in the chat
        t = self.store.create_task({'Title': 'Clear three columns on three rows', 'Kind': 'general'}, 'owner'); d = outputs.folder(t); d.mkdir(parents=True, exist_ok=True)
        (d / 'clear_columns.sql').write_text('BEGIN;\nUPDATE facilities SET fax = NULL WHERE id IN (14, 22, 31);\nCOMMIT;\n', encoding='utf-8')
        made = outputs.deliverables(outputs.listing(t))
        self.assertEqual([r['name'] for r in made], ['clear_columns.sql'])
        self.assertEqual(made[0]['preview'], 'text')                    # ...by its bytes: no list of extensions says what can be read
        (d / 'blob.bin').write_bytes(bytes([0, 1, 2, 255]) * 40)
        self.assertIsNone(next(r for r in outputs.listing(t) if r['name'] == 'blob.bin')['preview'])
        # ...and beside a workbook it is still in the list: nothing an agent made is hidden for its kind
        (d / 'rates.xlsx').write_bytes(b'x')
        self.assertEqual(sorted(r['name'] for r in outputs.deliverables(outputs.listing(t))), ['blob.bin', 'clear_columns.sql', 'rates.xlsx'])

    def test_a_family_is_one_name_without_its_version_marks(self):
        one = {outputs.family(n) for n in ('Vendor pricing v9.xlsx', 'vendor_pricing_final.xlsx', 'vendor pricing (2).xlsx',
                                           'vendor-pricing-20261027-1530.xlsx', 'Vendor Pricing_v2_final.xlsx', 'drafts/vendor pricing draft.xlsx')}
        self.assertEqual(one, {'vendor pricing.xlsx'})
        # ...and different things stay different: another year, another kind, a set the ask wanted
        self.assertEqual(len({outputs.family(n) for n in ('budget 2025.xlsx', 'budget 2026.xlsx', 'budget.pdf', 'region 1.csv', 'region 2.csv')}), 5)
        self.assertEqual(outputs.family('renew.docx'), 'renew.docx')

    def test_the_phone_offers_each_thing_once(self):
        from taskuary import remote_assistant
        self.assertEqual(sorted(r['name'] for r in remote_assistant.task_files(self.store, {'tid': self.tid})),
                         ['build_sheet.py', 'pricing comparison v9.xlsx', 'rates.csv', 'run.log', 'summary.pdf'])

    def test_the_assistant_finds_the_excel_on_the_task_about_vendor_pricing(self):
        from taskuary import concierge
        # what a file is about is read by meaning (embeddings, textsim), never by counting shared word stems (2026-10-28)
        from tests import fake_embed
        meaning = fake_embed.meaning({'pricing': ['pricing'], 'snag': ['snag']})
        meaning.__enter__(); self.addCleanup(meaning.__exit__, None, None, None)
        hits = outputs.find(self.store, 'vendor pricing', 'xlsx')
        # ...every sheet it made on that task, the table under tmp/ too (nothing it made is hidden, 2026-11-15) - the workbook once, its newest
        self.assertEqual(sorted((h['tid'], h['name']) for h in hits), [(self.tid, 'pricing comparison v9.xlsx'), (self.tid, 'rates.csv')])
        said = concierge.read_op(self.store, 'outputs.find', {'query': 'the excel on the task about vendor pricing', 'kind': 'xlsx'})
        self.assertIn('pricing comparison v9.xlsx', said)
        self.assertIn(f'/api/task-outputs/{self.tid}/pricing%20comparison%20v9.xlsx', said)
        self.assertIn(f'#task={self.tid}', said)
        self.assertIn('8 earlier versions', said)
        self.assertNotIn('build_sheet.py', said)
        # by the file's own name, by one task, and a miss says so
        self.assertIn('snag list.xlsx', concierge.read_op(self.store, 'outputs.find', {'query': 'snag', 'kind': 'excel'}))
        self.assertIn('plan.md', concierge.read_op(self.store, 'outputs.find', {'ref': task_ref(self.other)}))
        self.assertNotIn('pricing', concierge.read_op(self.store, 'outputs.find', {'ref': task_ref(self.other)}))
        self.assertIn('No file', concierge.read_op(self.store, 'outputs.find', {'query': 'payroll accruals', 'kind': 'pdf'}))

    def test_on_a_phone_no_link_is_given(self):
        from taskuary import concierge
        tok = concierge.DELIVERY.set(concierge.PHONE)
        try: said = concierge.read_op(self.store, 'outputs.find', {'query': 'vendor pricing'})
        finally: concierge.DELIVERY.reset(tok)
        self.assertIn('pricing comparison v9.xlsx', said)
        self.assertNotIn('/api/task-outputs', said)

    def test_the_catalogue_offers_it_within_the_index(self):
        from taskuary import toolcatalog
        b = toolcatalog.block()
        self.assertIn('"outputs.find"', b)
        self.assertLess(len(b), 7950)
        self.assertEqual(toolcatalog.valid('outputs.find', {}), '')
        self.assertTrue(toolcatalog.is_read('outputs.find'))


if __name__ == '__main__':
    unittest.main()


# WHAT HE ATTACHED IS NOT WHAT THE AGENT MADE (the stress round of New's attachments, recorded): a file attached in New is copied into the task's
# folder (outputs.take_in), and the chat's list of the files a turn made read every file in that folder - his own picture stood under the
# agent's first turn as a file it made, a large preview over the chat, and went a beat later when the turn's times settled
class HisFilesAreNotMadeTests(unittest.TestCase):
    def setUp(self):
        from taskuary import general
        self.s = MemoryStore()
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        d = config.home() / 'attachments' / 'prompt' / '209903'; d.mkdir(parents=True, exist_ok=True)
        pic = d / '20990301-090909-abc125-shot.png'; pic.write_bytes(b'\x89PNG fake'); self.addCleanup(pic.unlink, missing_ok=True)
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tid = self.c.post('/api/tasks', json={'Title': 'what is this', 'Summary': 'what is this', 'Files': [str(pic)], 'Kind': 'general'}).json()['taskId']
        (outputs.folder(self.tid) / 'answer.md').write_text('# It is a chart', encoding='utf-8')

    def test_the_chat_lists_only_what_the_agent_made(self):
        self.assertTrue((outputs.folder(self.tid) / 'shot.png').is_file())
        got = self.c.get(f'/api/tasks/{self.tid}/assistant').json()
        self.assertEqual({r['name'] for r in got['outputs']}, {'answer.md'})

    def test_one_a_turn_wrote_over_is_its_again(self):
        turn = outputs.turns_folder(self.tid); turn.mkdir(parents=True, exist_ok=True); self.addCleanup(shutil.rmtree, turn, True)
        (turn / '7.json').write_text('[{"path": "shot.png", "size": 1, "mtime": 1}]', encoding='utf-8')
        self.assertEqual({r['name'] for r in outputs.made(self.s, self.tid)}, {'answer.md', 'shot.png'})


def test_a_file_written_back_as_it_was_is_no_change_of_that_turn():
    """The walk, 2026-11-18: the agent saved its posts file again each turn, word for word, and the chat drew it whole under every answer. A
    turn that writes a file back as it was is not the turn that made it; one that changes a word is."""
    import time
    tid, f = 41, outputs.folder(41) / 'posts.txt'
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        f.write_text('LinkedIn: the portal launches Monday.', encoding='utf-8'); t0 = time.time() - 5
        assert [k['path'] for k in outputs.keep_turn(tid, 3, t0)] == ['posts.txt']
        os.utime(f, (time.time() + 2, time.time() + 2)); f.write_text('LinkedIn: the portal launches Monday.', encoding='utf-8')
        assert outputs.keep_turn(tid, 9, t0) == []
        assert outputs.made_by(tid) == {'posts.txt': 'comment-3'} and outputs.turn_versions(tid) == []
        f.write_text('LinkedIn: the portal launches Tuesday.', encoding='utf-8')
        assert [k['path'] for k in outputs.keep_turn(tid, 12, t0)] == ['posts.txt'] and outputs.made_by(tid)['posts.txt'] == 'comment-12'
    finally:
        shutil.rmtree(outputs.folder(tid), True); shutil.rmtree(outputs.turns_folder(tid), True)


class TasksSharingAFileHearItChange(unittest.TestCase):
    """Design round 6, D7: a research task added a "Print vendors" sheet to the board pack's workbook (another task's file); the pack's agent,
    told nothing, rebuilt the pack for a new headcount and wiped it; the research agent then said the files "still show 212" minutes after
    they showed 214. Whoever changes a file another live task uses, that task's agent hears it - and the task the file is of, when another
    wrote into it. Plain code over the folders: no per-task rule."""
    def setUp(self):
        import time
        from taskuary import general
        self.s, self.t0 = MemoryStore(), time.time() - 1
        self.pack = self.s.create_task({'Title': 'Build the Q3 board pack', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
        self.research = self.s.create_task({'Title': 'Compare print vendors', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
        self.done = self.s.create_task({'Title': 'An old look at the pack', 'Kind': 'general', 'Status': 'done'}, 'owner')
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        self.book = outputs.folder(self.pack) / 'Q3 board pack working.xlsx'; _book(self.book)
        (outputs.folder(self.pack) / 'Q3 board report.pdf').write_bytes(b'%PDF-1.4 headcount 212')
        self.told = []
        p = mock.patch.object(general, 'to_agent', lambda store, tid, said, actor='owner', heard=None: self.told.append((tid, said)) or 'told')
        p.start(); self.addCleanup(p.stop)

    def turn(self, tid, *cmds):
        return [{'type': 'tool_call', 'name': 'PowerShell', 'detail': {'args': {'command': c}}} for c in cmds]

    def test_a_file_written_into_by_another_task_and_then_rebuilt_is_heard_by_each_side(self):
        from taskuary import sharedfiles
        path = str(self.book).replace('/', os.sep)
        # ...the research turn adds its sheet into the pack's workbook: the pack's agent hears its file changed
        os.utime(self.book, None)
        got = sharedfiles.turn_ended(self.s, self.research, self.turn(self.research, f'py print_vendors.py "{path}"'), self.t0, [])
        self.assertEqual(got, [(self.pack, 'Q3 board pack working.xlsx')])
        self.assertIn("TQ-%04d's agent just changed Q3 board pack working.xlsx (this task's)" % self.research, self.told[-1][1])
        self.assertIn('Read it again before you say what it holds', self.told[-1][1])
        # ...and when the pack's agent rebuilds it for 214, the research task that uses it hears - the done task does not
        self.s.audit('task', self.done, sharedfiles.USED, 'taskuary', 'system', {'task': self.pack, 'paths': ['Q3 board pack working.xlsx']})
        self.told.clear()
        got = sharedfiles.turn_ended(self.s, self.pack, [], self.t0, [{'path': 'Q3 board pack working.xlsx'}, {'path': 'Q3 board report.pdf'}])
        self.assertEqual(got, [(self.research, 'Q3 board pack working.xlsx')])
        self.assertEqual(len(self.told), 1); self.assertIn(f"({task_ref(self.pack)}'s, which you use)", self.told[0][1])

    def test_a_file_only_read_is_used_and_a_turn_that_names_no_file_uses_none(self):
        from taskuary import sharedfiles
        old = self.t0 - 3600; os.utime(self.book, (old, old))
        got = sharedfiles.turn_ended(self.s, self.research, self.turn(self.research, f'cd "{outputs.folder(self.pack)}"; py -c "read" "Q3 board pack working.xlsx"'), self.t0, [])
        self.assertEqual((got, self.told), ([], []), 'reading changes nothing, and nobody is told')
        self.assertEqual(sharedfiles.users(self.s, self.pack, 'Q3 board pack working.xlsx'), {self.research})
        self.assertEqual(sharedfiles.named('Get-ChildItem C:/work', self.research), {})


def test_a_tasks_agent_works_in_a_folder_of_its_own_never_the_shared_scratch():
    """Walk 9, 2026-11-23: every general agent ran in the one scratch folder, and a Glob for the file attached to its ask listed another
    task's deck, report and charts. Its own folder is where it works; another task's scratch work is not its to read."""
    import json as _json
    from taskuary import agents, llm, readgate
    s = MemoryStore()
    s.upsert_agent('claude', 'coding', 'cli', _json.dumps({'cmd': 'claude', 'args': ['-p']}))
    got = {}
    def run_cli(prof, prompt, trace, **kw): got['cwd'] = prof.get('cwd'); return ('ok', 's1', None)
    with mock.patch.object(agents, 'run_cli', run_cli), mock.patch.object(agents, 'cli_has_flag', return_value=False), \
         mock.patch.object(agents, '_resolve_cmd', return_value=['claude']):
        llm.make_cli_llm(s, 'claude', cli_tools=True, task_id=7)('sys', 'user')
    assert Path(got['cwd']).resolve() == outputs.work_folder(7).resolve()
    assert Path(got['cwd']).resolve() != (config.home() / 'scratch').resolve()
    other = outputs.work_folder(3) / 'draft.md'; other.write_text('theirs', encoding='utf-8')
    with mock.patch.object(readgate, '_open', return_value=[]):          # ...the test's home sits in the temp folder, which is open to all
        held, never = readgate.judge(s, 7, [str(other)], got['cwd'])
        assert held or never, "another task's scratch work is not this task's"
        assert readgate.judge(s, 7, [str(outputs.work_folder(7) / 'mine.md')], got['cwd']) == ([], '')
