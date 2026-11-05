"""Pictures with a prompt: /api/prompt-image saves them, and only paths it saved may reach an agent's prompt."""
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from taskuary import config, server

c = TestClient(server.app)
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 32


class PromptImageTests(unittest.TestCase):
    def test_an_image_with_no_task_is_saved_under_attachments(self):
        r = c.post('/api/prompt-image', content=PNG, headers={'Content-Type': 'image/png'})
        self.assertEqual(r.status_code, 200, r.text)
        p = Path(r.json()['path'])
        self.assertTrue(p.is_file())
        self.assertTrue(p.resolve().is_relative_to((config.home() / 'attachments').resolve()))

    def test_only_an_image_is_taken(self):
        r = c.post('/api/prompt-image', content=b'hello', headers={'Content-Type': 'text/plain'})
        self.assertEqual(r.status_code, 415)

    def test_a_path_the_server_did_not_save_never_reaches_a_prompt(self):
        saved = c.post('/api/prompt-image', content=PNG, headers={'Content-Type': 'image/png'}).json()['path']
        outside = Path(config.home()) / 'config.toml'
        outside.touch()
        self.assertEqual(server.prompt_images([saved, str(outside), 'C:/Windows/win.ini', '../../etc']), [str(Path(saved).resolve())])

    def test_the_prompt_names_the_files_after_the_words(self):
        saved = c.post('/api/prompt-image', content=PNG, headers={'Content-Type': 'image/png'}).json()['path']
        text = server.with_images('why does this fail?', [saved])
        self.assertTrue(text.startswith('why does this fail?\n\nATTACHED IMAGES'))
        self.assertIn(str(Path(saved).resolve()), text)
        self.assertEqual(server.with_images('as is', []), 'as is')

    def test_any_file_is_saved_by_its_name_and_named_as_a_file(self):
        r = c.post('/api/prompt-file', content=b'%PDF-1.4 hello', headers={'X-File-Name': 'q3%20report.pdf'})
        self.assertEqual(r.status_code, 200, r.text)
        p = Path(r.json()['path'])
        self.assertTrue(p.is_file() and p.name.endswith('q3 report.pdf'))
        self.assertEqual(server.prompt_images([str(p)]), [str(p.resolve())])
        self.assertIn('ATTACHED FILES (read these files)', server.with_images('read it', [str(p)]))

    def test_a_file_name_never_climbs_out_of_its_folder(self):
        p = Path(c.post('/api/prompt-file', content=b'x', headers={'X-File-Name': '..%2F..%2Fconfig.toml'}).json()['path'])
        self.assertTrue(p.resolve().is_relative_to((config.home() / 'attachments' / 'prompt').resolve()))

    def test_an_empty_or_huge_file_is_refused(self):
        self.assertEqual(c.post('/api/prompt-file', content=b'').status_code, 422)
        self.assertEqual(c.post('/api/prompt-file', content=b'0' * (server.IMG_MAX + 1)).status_code, 413)


if __name__ == '__main__':
    unittest.main()
