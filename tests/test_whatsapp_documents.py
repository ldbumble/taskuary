"""A file sent on WhatsApp has to arrive.

The bridge downloaded voice notes, then photos - and nothing else. So a .docx dropped into a chat
carried no text, no audio and no image, and the ingest, which requires one of those three, threw
the whole message away. "Taskuary Homepage Copy Updated Sep 2026.docx" was sent at 4:57 PM and
never reached the Timeline at all (the owner, 2026-09-01). Not filed, not dimmed - absent.

Same shape as the voice note before it and the photo after: the file IS the message.
"""
import base64
import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest import mock

from taskuary import messengers
from taskuary.store import MemoryStore

DOCX = b'PK\x03\x04' + b'\x00' * 40          # enough to be a real file on disk


def _store():
    s = MemoryStore()
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
    return s, s.get_connector_by_type('whatsapp', with_secret=True)


def _file(name='homepage-copy.docx') -> str:
    p = Path(mkdtemp()) / name
    p.write_bytes(DOCX)
    return str(p)


def _poll(s, c, msg, **kw):
    feed = {'seq': 9, 'messages': [{'seq': 9, 'jid': '155@s.whatsapp.net', 'ts': 1755700000, **msg}]}
    with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
        return messengers.poll_whatsapp(s, c, s.list_sources(), llm=None, **kw)


DOC_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


class ADocumentArrives(unittest.TestCase):
    def test_a_document_with_no_caption_is_no_longer_dropped(self):
        s, c = _store()
        n = _poll(s, c, {'id': 'd1', 'name': 'Gabi', 'text': '', 'doc': _file(),
                         'docMime': DOC_MIME, 'docName': 'Taskuary Homepage Copy.docx'})
        rows = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")
        self.assertEqual((n, len(rows)), (1, 1))
        self.assertEqual(rows[0]['BodyText'], '(no text - see the attachment)')

    def test_the_file_is_attached_under_the_name_the_sender_gave_it(self):
        """'Taskuary Homepage Copy.docx' is what the owner will look for - not the id we cached."""
        s, c = _store()
        _poll(s, c, {'id': 'd2', 'name': 'Gabi', 'text': 'the new copy',
                     'doc': _file('cached-id.docx'), 'docMime': DOC_MIME,
                     'docName': 'Taskuary Homepage Copy.docx'})
        mid = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]['MessageId']
        atts = s.list_attachments(mid)
        self.assertEqual(len(atts), 1)
        self.assertEqual(atts[0]['Name'], 'Taskuary Homepage Copy.docx')
        self.assertEqual(atts[0]['ContentType'], DOC_MIME)

    def test_a_caption_is_kept_as_the_body(self):
        s, c = _store()
        _poll(s, c, {'id': 'd3', 'name': 'Gabi', 'text': 'here is the rewrite', 'doc': _file(),
                     'docMime': DOC_MIME, 'docName': 'x.docx'})
        self.assertEqual(s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]['BodyText'],
                         'here is the rewrite')

    def test_a_file_that_cannot_be_read_does_not_lose_the_message(self):
        """The row still arrives; only the attachment is missing. Losing both is the old bug."""
        s, c = _store()
        n = _poll(s, c, {'id': 'd4', 'name': 'Gabi', 'text': 'sending it over',
                         'doc': '/no/such/file.docx', 'docMime': DOC_MIME, 'docName': 'f.docx'})
        self.assertEqual(n, 1)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='whatsapp'")), 1)

    def test_a_message_with_nothing_in_it_at_all_is_still_skipped(self):
        """The guard must still hold: no text, no audio, no image, no file is not a message."""
        s, c = _store()
        n = _poll(s, c, {'id': 'd5', 'name': 'Gabi', 'text': ''})
        self.assertEqual((n, len(s._rows("SELECT * FROM message WHERE Channel='whatsapp'"))), (0, 0))


if __name__ == '__main__':
    unittest.main()
