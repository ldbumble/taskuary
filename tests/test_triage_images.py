"""A message with a picture on it goes through triage like any other.

Reproduced 2026-09-02 from a real Timeline: two mails from the same person, same thread subject,
one with a spreadsheet screenshot attached. The plain one became a task; the one with the picture
was filed as "AI triage returned an answer it could not read as a verdict". The model had never
been asked - `_guarded` took two positional arguments and classify_intent calls it with
`images=[...]` when the mail carries one, so the call raised a TypeError three frames down and the
verdict was thrown away. Live since 2026-08-20, when images were added to the triage prompt.
"""
import json, unittest

from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

PNG = [{'mime': 'image/png', 'b64': 'iVBORw0KGgo='}]


def _store():
    s = MemoryStore()
    s.save_connector({'ConnectorId': s.get_connector_by_type('openai')['ConnectorId'],
                      'Active': 1, 'Secret': 'sk-x'}, 'o')
    return s


class ImageTriageTests(unittest.TestCase):
    def _ingest(self, images, seen=None, verdict=None):
        s = _store()
        def llm(system, user, max_tokens=None, images=None):
            if seen is not None: seen.append(images)
            return json.dumps(verdict or {'intent': 'task', 'kind': 'general', 'why': 'they asked for something'})
        out = ingest_message(s, {'external_id': 'm1', 'channel': 'email', 'subject': 'RE: Avid rec',
                                 'body': 'This is the file that I imported', 'from_name': 'Tova',
                                 'from_email': 'tova@corp.example', 'to': ['me@corp.example'],
                                 'sent_at': '2026-09-02 15:01:00', 'source_name': 'me@corp.example',
                                 'images': images}, llm=llm)
        return s, out, s._one('SELECT Decision, ParseError FROM route WHERE MessageId=?', (out['message_id'],))

    def test_an_attached_picture_does_not_throw_the_verdict_away(self):
        _s, out, route = self._ingest(PNG)
        self.assertIsNone(route['ParseError'])
        self.assertEqual((out['status'], route['Decision']), ('created', 'create'))

    def test_the_picture_actually_reaches_the_brain(self):
        """It is not enough not to crash: a screenshot of the error IS the request, so the model
        has to be handed it."""
        seen = []
        self._ingest(PNG, seen=seen)
        self.assertEqual(seen, [PNG])

    def test_a_mail_with_no_picture_is_unchanged(self):
        seen = []
        _s, out, route = self._ingest(None, seen=seen)
        self.assertEqual(seen, [None])
        self.assertIsNone(route['ParseError'])
        self.assertEqual(out['status'], 'created')

    def test_a_brain_that_really_fails_still_files_and_says_why(self):
        """The wrapper's actual job survives: an exception is caught, recorded and filed."""
        s = _store()
        def llm(system, user, max_tokens=None, images=None): raise RuntimeError('the model is down')
        out = ingest_message(s, {'external_id': 'm2', 'channel': 'email', 'subject': 'RE: Avid rec',
                                 'body': 'text', 'from_name': 'Tova', 'from_email': 'tova@corp.example',
                                 'to': ['me@corp.example'], 'sent_at': '2026-09-02 15:01:00',
                                 'source_name': 'me@corp.example', 'images': PNG}, llm=llm)
        self.assertEqual(out['status'], 'filed')
        route = s._one('SELECT Decision, ParseError FROM route WHERE MessageId=?', (out['message_id'],))
        self.assertEqual(route['Decision'], 'file')
        self.assertIn('the model is down', route['ParseError'] or '')


if __name__ == '__main__':
    unittest.main()
