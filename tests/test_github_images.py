"""A bug report's content is often the screenshot, not the words.

An issue filed from a template comes through with its headings ("What happened", "Log lines",
"Environment") and nothing under them, because the reporter pasted an image. Triage read the empty
text and filed it as informational (the owner, 2026-09-04: "when you triage github issues you have
to read the image"). Mail has not had this problem since Graph started handing attachments over
inline - channels.images_for_triage's own docstring is about the same failure, in the same words -
and this is the GitHub end of it: read the pictures BEFORE the message row exists, so the classifier
that judges the item has seen what the item actually says.
"""
import base64
import unittest
from unittest import mock

from taskuary import channels, github


class BodyImagesTests(unittest.TestCase):
    PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')

    def _resp(self, ct='image/png', body=None, code=200):
        r = mock.Mock(status_code=code, headers={'Content-Type': ct})
        r.raw.read.return_value = self.PNG if body is None else body
        return r

    def test_the_screenshot_on_an_issue_is_read_and_handed_over_base64(self):
        body = '## What happened\n\n![shot](https://github.com/user-attachments/assets/abc-123)\n'
        with mock.patch.object(github.requests, 'get', return_value=self._resp()) as get:
            out = github.body_images('tok', body)
        self.assertEqual([ct for ct, _ in out], ['image/png'])
        self.assertEqual(base64.b64decode(out[0][1]), self.PNG)
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer tok')  # private repos need it

    def test_an_img_tag_counts_too_and_a_url_is_read_once(self):
        url = 'https://user-images.githubusercontent.com/1/x.png'
        body = f'<img src="{url}" />\n\n![again]({url})\n'
        with mock.patch.object(github.requests, 'get', return_value=self._resp()) as get:
            out = github.body_images('tok', body)
        self.assertEqual(len(out), 1)                     # the same picture twice is one picture
        self.assertEqual(get.call_count, 1)

    def test_only_github_s_own_attachment_hosts_are_followed(self):
        """An issue body is a stranger's text on a public repo. Fetching whatever URL it names
        would be an SSRF with extra steps, so the host list is the gate."""
        body = ('![a](https://evil.example.test/x.png)\n'
                '<img src="http://169.254.169.254/latest/meta-data/">\n'
                '![ok](https://github.com/user-attachments/assets/fine)\n')
        with mock.patch.object(github.requests, 'get', return_value=self._resp()) as get:
            out = github.body_images('tok', body)
        self.assertEqual(len(out), 1)
        self.assertIn('user-attachments', get.call_args.args[0])

    def test_what_is_not_a_picture_is_left_alone(self):
        cases = [('image/svg+xml', 'no provider takes SVG as image input'),
                 ('text/html', 'a login page where a picture was expected'),
                 ('application/pdf', 'not an image')]
        for ct, why in cases:
            with mock.patch.object(github.requests, 'get', return_value=self._resp(ct=ct)):
                self.assertEqual(github.body_images('tok', '![x](https://github.com/user-attachments/assets/a)'), [], why)

    def test_a_picture_too_big_to_send_is_skipped_rather_than_truncated(self):
        with mock.patch.object(github.requests, 'get', return_value=self._resp(body=b'x' * 40)):
            self.assertEqual(github.body_images('tok', '![x](https://github.com/user-attachments/assets/a)', max_bytes=8), [])

    def test_a_body_with_no_pictures_costs_no_requests(self):
        with mock.patch.object(github.requests, 'get') as get:
            self.assertEqual(github.body_images('tok', 'plain words, a `code span`, and a [link](https://x.test)'), [])
        get.assert_not_called()

    def test_a_fetch_that_fails_does_not_stop_the_item_being_ingested(self):
        with mock.patch.object(github.requests, 'get', side_effect=RuntimeError('network')):
            self.assertEqual(github.body_images('tok', '![x](https://github.com/user-attachments/assets/a)'), [])
        with mock.patch.object(github.requests, 'get', return_value=self._resp(code=404)):
            self.assertEqual(github.body_images('tok', '![x](https://github.com/user-attachments/assets/a)'), [])

    def test_the_cap_holds(self):
        body = '\n'.join(f'![s{i}](https://github.com/user-attachments/assets/{i})' for i in range(9))
        with mock.patch.object(github.requests, 'get', return_value=self._resp()):
            self.assertEqual(len(github.body_images('tok', body, cap=3)), 3)


class IngestHandsThemToTriageTests(unittest.TestCase):
    def test_the_issue_reaches_ingest_with_its_pictures_on_it(self):
        from taskuary.store import MemoryStore
        s = MemoryStore()
        item = {'number': 34, 'title': 'Connector', 'body': '## What happened\n\n![shot](https://github.com/user-attachments/assets/a)\n',
                'user': {'login': 'GG407JOIN'}, 'author_association': 'NONE',
                'updated_at': '2026-09-04T10:00:00Z', 'html_url': 'https://github.com/ldbumble/taskuary/issues/34'}
        src = {'Address': 'ldbumble/taskuary', 'ConfigJson': '{"issues": "tasks"}'}
        seen = {}
        def fake_ingest(store, msg, **kw):
            seen.update(msg); return {'status': 'created', 'message_id': 1}
        with mock.patch.object(channels, 'ingest_message', fake_ingest), \
             mock.patch('taskuary.github.list_items', return_value=[item]), \
             mock.patch('taskuary.github.body_images', return_value=[('image/png', 'AAA')]):
            channels.ingest_github_issues(s, src, 'tok', __import__('datetime').datetime(2026, 9, 4))
        self.assertEqual(seen['images'], [('image/png', 'AAA')])   # triage.classify_intent gets these
        self.assertIn('association: NONE', seen['body'])           # ...and still knows who is asking

    def test_vision_switched_off_means_no_pictures_are_fetched_at_all(self):
        from taskuary.store import MemoryStore
        s = MemoryStore(); s.set_setting('vision_enabled', '0', 't')
        item = {'number': 34, 'title': 'x', 'body': '![s](https://github.com/user-attachments/assets/a)',
                'user': {'login': 'someone'}, 'author_association': 'NONE',
                'updated_at': '2026-09-04T10:00:00Z', 'html_url': 'u'}
        src = {'Address': 'r/r', 'ConfigJson': '{"issues": "tasks"}'}
        seen = {}
        with mock.patch.object(channels, 'ingest_message', lambda store, msg, **kw: seen.update(msg) or {'status': 'created'}), \
             mock.patch('taskuary.github.list_items', return_value=[item]), \
             mock.patch('taskuary.github.body_images') as fetch:
            channels.ingest_github_issues(s, src, 'tok', __import__('datetime').datetime(2026, 9, 4))
        fetch.assert_not_called()
        self.assertEqual(seen['images'], [])


if __name__ == '__main__':
    unittest.main()
