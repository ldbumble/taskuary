"""THE SIGNATURE UNDER EVERY EMAIL TASKUARY PREPARES (the owner, 2026-10-28: "on replies there was no signature with it. It should
use the default signature always (you can put that as a setting)").

One layer, three doors:
- what the owner sees: every review row carries `Signature`, the block that will go under it, and the reply box shows it - an
  empty box opens on it, a draft without it gets it - so what is in the box is what goes;
- what leaves: `verdicts.decide` signs the approved text once more before it is sent, so a draft filed before this, an agent's
  draft, a forward or the owner's own typed words all end with it exactly once;
- what it is: `responder.signature_for` - the sending mailbox's own (its card), else Settings → Replies → Email signature, else
  STYLE.md's sign-off line, else the owner's name. `sign_replies` off: none anywhere.

Chat (Teams, Slack, WhatsApp, Telegram...) never gets one, and an invite answered or booked (calwrite) keeps its own body.

Neither provider puts the account's own signature on what Taskuary sends: Gmail's is added by its web and phone apps, not on SMTP,
and Outlook's by the Outlook client, not on Graph's sendMail - so there is no auto-signature to detect, and the guard against a
second copy is the text itself (`responder.with_signature` reads the tail). Neither hands its signature over either - Graph has
no signature in mailboxSettings, and a Gmail card here is IMAP/SMTP with no settings API - so the one to offer is read off the
mailbox's own sent mail (`suggest`), for the owner to confirm in Settings.
"""
from . import outbound

ON = 'sign_replies'
OFFERED = 'email_signature_offered'      # '1' once Settings has offered the one read off the sent mail: offered once, not every visit
NO_SIG = ('calendar', 'zoho_invoice')    # envelopes whose body is not a letter from the owner


def on(store) -> bool: return str(store.get_setting(ON, '1') or '1').strip().lower() not in ('0', 'false', 'off', 'no')


def _env(rv) -> dict:
    import json
    try: return json.loads((rv or {}).get('Deliver') or '{}') or {}
    except (TypeError, ValueError, AttributeError): return {}


def is_email(store, rv: dict, msg: dict = None) -> bool:
    """Does this review leave as an EMAIL from the owner - a reply on an email thread, or a message they started by email."""
    env = _env(rv)
    if env.get('kind') in NO_SIG or (rv or {}).get('Kind') == 'action': return False
    if env.get('kind') == 'reply' or not env.get('channel'):
        if msg is None and (rv or {}).get('MessageId'): msg = store.get_message(rv['MessageId'])
        return str((msg or {}).get('Channel') or (rv or {}).get('Channel') or env.get('channel') or '').lower() == 'email'
    return str(env.get('channel')).lower() == 'email'


def for_review(store, rv: dict, msg: dict = None, memo: dict = None) -> str:
    """The block that goes under this review when it is sent - '' for chat, an invite, a proposal, or with the switch off."""
    from .responder import signature_for
    if msg is None and (rv or {}).get('MessageId'): msg = store.get_message(rv['MessageId'])
    if not is_email(store, rv, msg): return ''
    box = outbound.sending_mailbox(store, rv, msg)
    k = str(box or '').lower()
    if memo is not None and k in memo: return memo[k]
    sig = signature_for(store, box)
    if memo is not None: memo[k] = sig
    return sig


def unsigned(text: str, sig: str) -> str:
    """The words above the signature: what the owner actually wrote. A box holding only the signature is an empty box."""
    t = str(text or '').rstrip()
    s = str(sig or '').strip()
    return t[:-len(s)].rstrip() if s and t.endswith(s) else t


def sign(store, rv: dict, text: str, msg: dict = None) -> str:
    """The text as it goes out: an email as plain text (chatformat.plain_text: the owner's or a writer's Markdown left in the box
    went out as stars and hashes) with the signature once at the end - never a second copy; chat untouched."""
    from .responder import with_signature
    from .chatformat import plain_text
    if not str(text or '').strip() or not is_email(store, rv, msg): return str(text or '')
    sig = for_review(store, rv, msg)
    body = plain_text(unsigned(text, sig)) or str(text)
    return with_signature(body, sig) if sig else body


def agent_signed(store, rv: dict, text: str, msg: dict = None) -> str:
    """An agent's draft as it is filed: the agent's own sign-off ("Best,\\nAlex Doyle") taken off and the saved block put on once -
    the drafter's own road (responder.signed). It was filed as written, and the box put the block under the agent's name: signed
    twice (walk 2026-10-29). Chat: the owner's name lines off, nothing on (outbox)."""
    from .responder import signed, strip_signoff, own_lines
    text = str(text or '').strip()
    if not text: return text
    if is_email(store, rv, msg): return signed(text, for_review(store, rv, msg))
    return strip_signoff(text, own_lines(store)) or text


def suggest(store, mailbox: str = None) -> str:
    """The signature this mailbox's own sent mail ends with - read, never saved: the owner checks it before it goes on anything."""
    from .responder import learn_signature
    store.set_setting(OFFERED, '1', 'system')
    return learn_signature(store, mailbox=mailbox)


def overview(store) -> dict:
    """What Settings shows: the switch, the default, and - with more than one mailbox - each one's own (blank: the default)."""
    boxes = outbound.mailboxes(store)
    rows = []
    if len(boxes) > 1:
        for b in boxes: rows.append({'address': b['address'], 'card': b.get('card') or '', 'signature': outbound.card_signature(store, b['address'])})
    default = str(store.get_setting('email_signature') or '').strip()
    return {'on': on(store), 'default': default, 'mailboxes': rows,
            'offer': not default and not any(r['signature'] for r in rows) and store.get_setting(OFFERED, '') != '1'}


def save_mailbox(store, address: str, sig: str) -> dict:
    """One mailbox's own signature, on the card that sends as it (outbound.card_signature reads it there)."""
    from .channels import _cfg
    box = outbound._box(store, address)
    if not box: raise ValueError(f'{address} is not a connected mailbox')
    c = store.get_connector(box['connector_id'])
    cfg = _cfg(c)
    per = dict(cfg.get('signatures') or {}) if isinstance(cfg.get('signatures'), dict) else {}
    per[box['address'].lower()] = str(sig or '').strip()
    store.set_connector_config(box['connector_id'], {**cfg, 'signatures': per})
    return {'address': box['address'], 'signature': per[box['address'].lower()]}
