"""Auto-replies are never triaged (the owner, 2026-09-25: "all auto replies should be ignored period, when it comes to
triage"). An out-of-office answering the owner's own reply was triaged, filed onto the urgent task it answered, and
then spoke for that task on the rail ("This is an out-of-office auto-reply...").

What says a message is an auto-reply is the mail system's own mark, never a reading of what it says:
- the header RFC 3834 defines for it (Auto-Submitted: anything but "no"), and the older X-Autoreply / X-Autorespond /
  Precedence: auto_reply that Exchange and others still send - where the connector has the headers (IMAP);
- the subject prefix the mail system itself writes on one ("Automatic reply:", "Out of office:") - where it does not
  (Graph returns no headers on a listing).

An auto-reply is stored (status `autoreply`) so the Advisor still knows who is away, and nothing else: no triage, no
task, no rail row, never the line that speaks for a card, never "they answered".
"""
import re

SUBJECT = re.compile(r'^(automatic reply|auto(matic)?[ -]?reply|out of (the )?office)', re.I)
STATUS = 'autoreply'


def from_headers(msg) -> bool:
    """An email.message.Message (or any .get(name)) the sender's system marked as an automatic answer."""
    auto = str(msg.get('Auto-Submitted') or '').strip().lower()
    if auto and not auto.startswith('no'): return True
    if msg.get('X-Autoreply') or msg.get('X-Autorespond'): return True
    return str(msg.get('Precedence') or '').strip().lower() == 'auto_reply'


def is_auto(m: dict) -> bool:
    """An ingest dict (subject, auto_reply) or a stored row (Subject, Status)."""
    if not m: return False
    if m.get('auto_reply') or m.get('Status') == STATUS: return True
    return bool(SUBJECT.match(str(m.get('subject') or m.get('Subject') or '')))
