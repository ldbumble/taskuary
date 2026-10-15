"""The reply writer sees the pictures on the thread (the owner, 2026-10-15: "is it not seeing the full message? the image is
there higher up the chat"). A WhatsApp sender sent an ad and asked about its wording; the draft said "send me the image you
mean", because the writer read the thread as text and a picture was "(no text - see the attachment)"."""
import tempfile
from pathlib import Path

from taskuary import ingest, responder
from taskuary.store import MemoryStore

PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')


def _thread(s, d):
    tid = s.create_task({'Title': 'Erin asks about the ad wording', 'Summary': 's', 'Kind': 'reply', 'Source': 'whatsapp'}, 'router')
    a = s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'FromName': 'Erin Blake', 'FromEmail': 'whatsapp:1',
                       'ConversationId': 'wa-1', 'SentAt': '2026-10-15 14:59:00', 'BodyText': '(no text - see the attachment)', 'Status': 'filed'})
    f = Path(d) / 'ad.png'; f.write_bytes(PNG)
    s.add_attachment({'MessageId': a, 'ExternalId': 'wa:ad', 'Name': 'ad.png', 'ContentType': 'image/png', 'Path': str(f), 'Size': len(PNG)})
    s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'FromName': 'Erin Blake', 'FromEmail': 'whatsapp:1', 'ConversationId': 'wa-1',
                   'SentAt': '2026-10-15 16:30:00', 'BodyText': 'Can we borrow their wording?', 'Status': 'routed'})
    return tid


def test_the_writer_is_handed_the_threads_pictures_and_told_to_look():
    seen = {}
    def llm(system, user, max_tokens=None, images=None):
        seen.update(user=user, images=images); return 'Yes - their line works if we make it about local-first.'
    with tempfile.TemporaryDirectory() as d:
        s = MemoryStore(); tid = _thread(s, d)
        responder.draft_reply(s, tid, llm=llm)
    assert seen['images'] and seen['images'][0][0] == 'image/png'
    assert 'never ask for one they already sent' in seen['user']
    assert '(sent ad.png)' in seen['user']                        # the thread names the picture where it was sent


def test_a_text_only_brain_still_drafts():
    def llm(system, user, max_tokens=None): return 'Sure.'     # takes no images: asked again without them
    with tempfile.TemporaryDirectory() as d:
        s = MemoryStore(); tid = _thread(s, d)
        assert responder.draft_reply(s, tid, llm=llm).strip() == 'Sure.'


def test_the_thread_names_an_attachment_only_message():
    with tempfile.TemporaryDirectory() as d:
        s = MemoryStore(); _thread(s, d)
        lines = ingest.exchange_lines(s, {'conversation_id': 'wa-1', 'subject': None, 'sent_at': None})
    assert any('(sent ad.png)' in l for l in lines) and not any('no text - see the attachment' in l for l in lines)
