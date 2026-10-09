"""What a chat SHOWS the owner: a chart, a picture, a table or a small page - only when the agent judges it makes the answer
easier to understand (the owner, 2026-10-09: "only if the agent thinks it's a good way to understand things - random scratch
stuff not"). The agent names the file on a [[TASKUARY-SHOW: path]] line; the turn copies it onto the task and the chat draws it
under that answer. These pin the marker, what may be shown, where it lands, and that nothing shown runs as Taskuary.
"""
import unittest
from pathlib import Path

from taskuary import config, general, selfclose, session_artifacts as sa
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 32


class ShowMarkerTests(unittest.TestCase):
    def test_the_line_comes_out_of_the_answer_and_names_the_file(self):
        text, named = selfclose.show_markers('Spend rose 8%.\n[[TASKUARY-SHOW: C:/x/scratch/spend.png]]\nSee the chart.')
        self.assertEqual(named, ['C:/x/scratch/spend.png'])
        self.assertNotIn('TASKUARY', text)
        self.assertIn('Spend rose 8%.', text)

    def test_the_instruction_says_only_when_it_helps(self):
        self.assertIn('[[TASKUARY-SHOW:', selfclose.SHOW_LINE)
        self.assertIn('Only when it truly helps', selfclose.SHOW_LINE)


class ShowFilesTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='August vendor spend')
        self.scratch = config.home() / 'scratch'; self.scratch.mkdir(parents=True, exist_ok=True)

    def shown(self):
        return [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'shown']

    def test_a_file_from_the_working_folder_is_copied_onto_the_task(self):
        f = self.scratch / 'spend.png'; f.write_bytes(PNG)
        general._show_files(self.s, self.tid, [str(f)], [])
        [row] = self.shown()
        self.assertEqual((row['Name'], row['ContentType']), ('spend.png', 'image/png'))
        self.assertTrue(sa.confined(row['Path']))           # its own copy, kept after the scratch folder is cleared
        f.unlink()
        self.assertEqual(Path(row['Path']).read_bytes(), PNG)

    def test_a_file_outside_the_working_folder_is_refused_and_the_task_says_so(self):
        outside = config.home() / 'secrets.png'; outside.write_bytes(PNG)
        general._show_files(self.s, self.tid, [str(outside)], [])
        self.assertEqual(self.shown(), [])
        self.assertTrue(any('Not shown' in (c.get('Body') or '') for c in self.s.list_comments(self.tid)))

    def test_only_pictures_pages_and_tables_can_be_shown(self):
        f = self.scratch / 'tool.exe'; f.write_bytes(b'MZ')
        general._show_files(self.s, self.tid, [str(f)], [])
        self.assertEqual(self.shown(), [])
        self.assertTrue(any('cannot be shown' in (c.get('Body') or '') for c in self.s.list_comments(self.tid)))


class ShownInTheChatTests(unittest.TestCase):
    def setUp(self):
        from taskuary import server
        self.server, self.s = server, MemoryStore()
        self.tid = Factory(self.s).task(title='August vendor spend', kind='general')
        scratch = config.home() / 'scratch'; scratch.mkdir(parents=True, exist_ok=True)
        (scratch / 'spend.png').write_bytes(PNG)
        (scratch / 'spend.html').write_text('<script>alert(1)</script>', encoding='utf-8')
        self.old, server.store = server.store, self.s

    def tearDown(self): self.server.store = self.old

    def get(self, url):
        from fastapi.testclient import TestClient
        return TestClient(self.server.app).get(url)

    def test_what_a_turn_showed_sits_under_the_answer_that_turn_filed(self):
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, 'How did vendor spend move?')
        general._show_files(self.s, self.tid, [str(config.home() / 'scratch' / 'spend.png')], [])
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Up 8% on July.')
        data = self.server._assistant_payload(self.tid)
        answer = [m for m in data['messages'] if m['role'] == 'assistant'][-1]
        self.assertEqual([p['after'] for p in data['published']], [answer['id']])

    def test_a_picture_is_served_as_itself_and_a_page_only_as_text(self):
        general._show_files(self.s, self.tid, [str(config.home() / 'scratch' / n) for n in ('spend.png', 'spend.html')], [])
        rows = {a['Name']: a for a in self.s.list_task_artifacts(self.tid)}
        pic = self.get(f"/api/task-artifacts/{rows['spend.png']['ArtifactId']}")
        self.assertEqual((pic.status_code, pic.headers['content-type'], pic.content), (200, 'image/png', PNG))
        page = self.get(f"/api/task-artifacts/{rows['spend.html']['ArtifactId']}")
        self.assertTrue(page.headers['content-type'].startswith('text/plain'))      # the sandboxed frame draws it, never this origin
        self.assertEqual(page.headers['x-content-type-options'], 'nosniff')


if __name__ == '__main__':
    unittest.main()
