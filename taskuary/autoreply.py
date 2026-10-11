"""Auto-replies are never triaged (the owner, 2026-09-25: "all auto replies should be ignored period, when it comes to
triage"). An out-of-office answering the owner's own reply was triaged, filed onto the urgent task it answered, and
then spoke for that task on the rail ("This is an out-of-office auto-reply...").

What says a message is an auto-reply is the mail system's own mark, never a reading of what it says: the header
RFC 3834 defines for it (Auto-Submitted: auto-replied), and the older X-Autoreply / X-Autorespond / Precedence:
auto_reply that Exchange and others still send. IMAP and Gmail hand over the raw headers; Graph returns them as
`internetMessageHeaders` on the body fetch (channels.MAIL_BODY_SELECT), read through headers() below.

The subject prefix ("Automatic reply:", "Out of office:") used to decide it where Graph sent no headers - and so a
colleague's "Out of office coverage for Friday - can you take my calls?" was stored as an auto-reply and never
triaged (2026-10-11: "everything should be ai"). Words are the model's to read; this module reads only the protocol.

Auto-Submitted: auto-GENERATED is not a reply - it is a system writing on its own (an alert, a notification), which
is a sender class (categories.header_class), triaged like anything else.

An auto-reply is stored (status `autoreply`) so the Advisor still knows who is away, and nothing else: no triage, no
task, no rail row, never the line that speaks for a card, never "they answered".
"""
import email.message

STATUS = 'autoreply'


def headers(m: dict) -> email.message.Message:
    """Graph's internetMessageHeaders ([{name, value}]) as an email.message.Message - one case-insensitive .get() for
    every connector, so the same header rules read IMAP's raw mail and Graph's list alike."""
    out = email.message.Message()
    for h in (m or {}).get('internetMessageHeaders') or []:
        if isinstance(h, dict) and h.get('name'): out[str(h['name'])] = str(h.get('value') or '')
    return out


def from_headers(msg) -> bool:
    """An email.message.Message (or any .get(name)) the sender's system marked as an automatic answer."""
    if str(msg.get('Auto-Submitted') or '').strip().lower().startswith('auto-replied'): return True
    if msg.get('X-Autoreply') or msg.get('X-Autorespond'): return True
    return str(msg.get('Precedence') or '').strip().lower() == 'auto_reply'


def is_auto(m: dict) -> bool:
    """An ingest dict (auto_reply, set by the connector from the headers) or a stored row (Status / MsgStatus)."""
    if not m: return False
    return bool(m.get('auto_reply')) or STATUS in (m.get('Status'), m.get('MsgStatus'))
