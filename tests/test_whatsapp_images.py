"""A photo on WhatsApp is the message.

The bridge downloaded voice notes and nothing else, so a screenshot arrived as its caption -
or, with no caption, as nothing at all. "on my laptop. words look weird" reached triage as a
sentence about nothing, with the picture of the broken words dropped on the floor, and was
filed as no task (the owner, 2026-08-31).

Telegram already did this properly: the picture is attached to the message AND handed to triage
as something the model can see. This is WhatsApp catching up.
"""
import base64
import json
import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest import mock

from taskuary import messengers
from taskuary.store import MemoryStore

PNG = base64.b64decode(  # 1x1 png - small, real, and a type the vision path accepts
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def _store():
    s = MemoryStore()
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
    return s, s.get_connector_by_type('whatsapp', with_secret=True)


def _photo(tmp, name='shot.png') -> str:
    p = Path(tmp) / name
    p.write_bytes(PNG)
    return str(p)


def _poll(s, c, msg, **kw):
    feed = {'seq': 9, 'messages': [{'seq': 9, 'jid': '155@s.whatsapp.net', 'ts': 1755700000, **msg}]}
    with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
        return messengers.poll_whatsapp(s, c, s.list_sources(), llm=None, **kw)


class APhotoArrivesTests(unittest.TestCase):
    def test_a_photo_with_no_caption_is_no_longer_dropped(self):
        s, c = _store()
        n = _poll(s, c, {'id': 'p1', 'name': 'Sam', 'text': '', 'image': _photo(mkdtemp()), 'imageMime': 'image/png'})
        rows = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")
        self.assertEqual((n, len(rows)), (1, 1))
        self.assertEqual(rows[0]['BodyText'], '(no text - see the attachment)')

    def test_the_picture_is_attached_to_the_message(self):
        s, c = _store()
        _poll(s, c, {'id': 'p2', 'name': 'Sam', 'text': 'words look weird',
                     'image': _photo(mkdtemp()), 'imageMime': 'image/png'})
        mid = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]['MessageId']
        atts = s.list_attachments(mid)
        self.assertEqual(len(atts), 1)
        self.assertEqual(atts[0]['ContentType'], 'image/png')

    def test_triage_is_handed_the_picture_to_look_at(self):
        """The whole point: the classifier SEES the screenshot, instead of ruling on a caption."""
        s, c = _store()
        seen = {}
        with mock.patch('taskuary.ingest.ingest_message', side_effect=lambda store, msg, **kw: (
                seen.update(msg), {'status': 'created', 'message_id': None})[1]) as ing:
            _poll(s, c, {'id': 'p3', 'name': 'Sam', 'text': 'words look weird',
                         'image': _photo(mkdtemp()), 'imageMime': 'image/png'})
        self.assertTrue(ing.called)
        self.assertEqual(len(seen['images']), 1)
        self.assertEqual(seen['images'][0][0], 'image/png')

    def test_a_caption_is_still_the_body(self):
        s, c = _store()
        _poll(s, c, {'id': 'p4', 'name': 'Sam', 'text': 'words look weird',
                     'image': _photo(mkdtemp()), 'imageMime': 'image/png'})
        self.assertEqual(s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]['BodyText'],
                         'words look weird')

    def test_a_picture_the_bridge_could_not_write_does_not_lose_the_message(self):
        s, c = _store()
        n = _poll(s, c, {'id': 'p5', 'name': 'Sam', 'text': 'look at this', 'image': 'C:/gone/nope.png'})
        rows = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")
        self.assertEqual((n, rows[0]['BodyText']), (1, 'look at this'))
        self.assertEqual(s.list_attachments(rows[0]['MessageId']), [])

    def test_vision_switched_off_still_files_the_attachment(self):
        """Settings → vision off means the model does not look; it does not mean we throw the
        picture away."""
        s, c = _store()
        s.set_setting('vision_enabled', '0', 'o')
        _poll(s, c, {'id': 'p6', 'name': 'Sam', 'text': 'look', 'image': _photo(mkdtemp()), 'imageMime': 'image/png'})
        mid = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]['MessageId']
        self.assertEqual(len(s.list_attachments(mid)), 1)

    def test_a_message_with_neither_words_nor_media_is_still_nothing(self):
        s, c = _store()
        self.assertEqual(_poll(s, c, {'id': 'p7', 'name': 'Sam', 'text': ''}), 0)


class TheBridgeTests(unittest.TestCase):
    """The download itself is Node, so what is checked here is that it asks for the image at
    all - the one line whose absence was the whole bug."""
    SRC = Path(__file__).resolve().parent.parent / 'taskuary' / 'whatsapp' / 'bridge.mjs'

    def test_the_bridge_downloads_images_as_well_as_audio(self):
        src = self.SRC.read_text(encoding='utf-8')
        self.assertIn('imageMessage', src)
        self.assertIn('image, imageMime', src)

    def test_both_kinds_go_through_one_download(self):
        """Two copies of a download-and-write block is how one of them stays broken."""
        self.assertEqual(self.SRC.read_text(encoding='utf-8').count('downloadMediaMessage(m'), 1)


if __name__ == '__main__':
    unittest.main()
