"""A page a Claude session publishes is the session's OUTPUT - it belongs on the task that ran it.

Claude Code's Artifact tool publishes a private page on claude.ai and answers with its url, its id, its
title, its version and the local file it published from. Taskuary heard every one of those (a terminal
session's PostToolUse hook, a general agent's stream-json) and threw the answer away, so the one thing the
agent made for the owner to look at was findable only in the agent's own scrollback (the owner, 2026-10-02:
"claude code uses artifacts and we should save that on a task that uses claude"). These pin the capture on
both roads, one row per page however often it is republished, and the local copy the preview reads.
"""
import os, tempfile, unittest
from pathlib import Path

from taskuary import agents, claude_artifacts as ca, hooks, terminal as term
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.test_hooks_events import CWD, Base

URL = 'https://claude.ai/code/artifact/0f0e0d0c-0000-4000-8000-000000000001'
AID = '0f0e0d0c-0000-4000-8000-000000000001'


def result(path='', version='v1', title='Northwind ledger check', url=URL, aid=AID):
    return {'url': url, 'path': path, 'artifact_id': aid, 'title': title, 'updated': False,
            'audience': 'owner', 'version': version, 'capabilities': {}}


class PublishedTests(unittest.TestCase):
    def test_the_tools_own_answer_is_read(self):
        got = ca.published(result(path=r'C:\tmp\page.html'))
        self.assertEqual(got, {'url': URL, 'artifact_id': AID, 'title': 'Northwind ledger check', 'version': 'v1', 'path': r'C:\tmp\page.html'})

    def test_the_text_line_is_enough_when_the_structure_is_missing(self):
        """stream-json carries the structure as tool_use_result; a CLI that sends only the text still said it"""
        got = ca.published(None, rf'Published C:\tmp\page one.html at {URL}' + '\n\nStored - contract 0.1')
        self.assertEqual((got['url'], got['artifact_id'], got['path']), (URL, AID, r'C:\tmp\page one.html'))

    def test_anything_else_is_not_a_publish(self):
        for r, text in [({'url': 'https://example.com/page'}, ''), ({}, 'Published nothing'), (None, ''),
                        ({'stdout': 'ok'}, f'see {URL}')]:            # a url merely MENTIONED is not one this session published
            self.assertIsNone(ca.published(r, text), (r, text))

    def test_a_stream_event_names_its_publish(self):
        j = {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'content': f'Published x.html at {URL}'}]},
             'tool_use_result': result()}
        self.assertEqual(ca.from_stream(j)['artifact_id'], AID)
        self.assertIsNone(ca.from_stream({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'done'}]}}))
        self.assertIsNone(ca.from_stream({'type': 'assistant', 'tool_use_result': result()}))


class KeepTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Check the ledger')
        self.dir = tempfile.mkdtemp()

    def page(self, body='<h1>v1</h1>'):
        p = Path(self.dir) / 'page.html'; p.write_text(body, encoding='utf-8'); return str(p)

    def rows(self): return [a for a in self.s.list_task_artifacts(self.tid) if a['Kind'] == ca.KIND]

    def test_a_publish_lands_on_the_task_with_a_local_copy(self):
        ca.keep(self.s, self.tid, ca.published(result(path=self.page())), by='coder')
        (row,) = self.rows()
        self.assertEqual((row['Url'], row['ExtId'], row['Version'], row['Name']), (URL, AID, 'v1', 'Northwind ledger check'))
        self.assertEqual(Path(row['Path']).read_text(encoding='utf-8'), '<h1>v1</h1>')
        self.assertTrue(Path(row['Path']).resolve().is_relative_to(Path(ca.session_artifacts.root()).resolve()))

    def test_a_republish_updates_the_one_row(self):
        """the Artifact tool republishes to the same url while the work runs - one page, one row, the newest copy"""
        ca.keep(self.s, self.tid, ca.published(result(path=self.page())), by='coder')
        ca.keep(self.s, self.tid, ca.published(result(path=self.page('<h1>v2</h1>'), version='v2', title='Ledger check, final')), by='coder')
        (row,) = self.rows()
        self.assertEqual((row['Version'], row['Name']), ('v2', 'Ledger check, final'))
        self.assertEqual(Path(row['Path']).read_text(encoding='utf-8'), '<h1>v2</h1>')

    def test_no_local_file_still_keeps_the_link(self):
        ca.keep(self.s, self.tid, ca.published(result(path=os.path.join(self.dir, 'gone.html'))), by='coder')
        (row,) = self.rows()
        self.assertEqual(row['Url'], URL); self.assertFalse(row['Path'])

    def test_a_huge_or_foreign_file_is_not_copied(self):
        big = Path(self.dir) / 'big.html'; big.write_bytes(b'x' * (ca.MAX_COPY + 1))
        exe = Path(self.dir) / 'tool.exe'; exe.write_bytes(b'MZ')
        for p in (big, exe):
            self.assertIsNone(ca._copy(self.tid, AID, str(p)), p)


class HookRoadTests(Base):
    def test_a_terminal_sessions_publish_reaches_its_task(self):
        self.session()
        p = Path(tempfile.mkdtemp()) / 'page.html'; p.write_text('<p>hi</p>', encoding='utf-8')
        self.fire('PostToolUse', tool_name='Artifact', tool_input={'file_path': str(p)}, tool_response=result(path=str(p)))
        rows = [a for a in self.s.list_task_artifacts(self.tid) if a['Kind'] == ca.KIND]
        self.assertEqual([r['Url'] for r in rows], [URL])

    def test_another_tools_answer_is_left_alone(self):
        self.session()
        self.fire('PostToolUse', tool_name='Bash', tool_input={'command': 'echo'}, tool_response={'stdout': URL})
        self.assertEqual([a for a in self.s.list_task_artifacts(self.tid) if a['Kind'] == ca.KIND], [])


class RowTests(unittest.TestCase):
    def test_the_page_gets_the_link_and_the_preview(self):
        from taskuary import server
        row = server._artifact_row({'ArtifactId': 7, 'Name': 'Ledger check', 'Kind': ca.KIND, 'Path': r'C:\x.html',
                                    'Url': URL, 'Version': 'v2', 'ContentType': 'text/html'})
        self.assertEqual((row['external_url'], row['version'], row['url']), (URL, 'v2', '/api/task-artifacts/7'))


class StreamRoadTests(unittest.TestCase):
    def test_a_general_agents_publish_is_said_as_its_own_event(self):
        seen = []
        j = {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'ok'}]}, 'tool_use_result': result()}
        agents._published(j, lambda *a: seen.append(a))
        self.assertEqual([(k, d['url']) for k, _n, d in seen], [('artifact', URL)])
        agents._published({'type': 'user', 'message': {'content': []}}, lambda *a: seen.append(a))
        self.assertEqual(len(seen), 1)


class PreviewEndpointTests(unittest.TestCase):
    def test_the_copy_is_served_as_text_never_as_a_page(self):
        """the preview draws it in a sandboxed frame; opening the url itself must not run it as Taskuary"""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = Factory(s).task(title='Check the ledger')
        p = Path(tempfile.mkdtemp()) / 'page.html'; p.write_text('<script>alert(1)</script>', encoding='utf-8')
        row = ca.keep(s, tid, ca.published(result(path=str(p))), by='coder')
        old, server.store = server.store, s
        try: r = TestClient(server.app).get(f"/api/task-artifacts/{row['ArtifactId']}")
        finally: server.store = old
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers['content-type'].startswith('text/plain'))
        self.assertEqual(r.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(r.text, '<script>alert(1)</script>')
