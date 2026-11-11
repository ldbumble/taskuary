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
second copy is the text itself (`responder.with_signature` reads the tail). Graph has no signature in mailboxSettings, and
Gmail's own signature setting is not read yet - so with none set by the owner, the ending the mailbox's own sent mail plainly
shares signs (`account`, `confident`); a weaker ending is only offered in Settings (`suggest`).
"""
import threading, time
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


def told(store) -> str:
    """THE AGENT IS TOLD HOW ITS EMAILS ARE SIGNED, up front (the recorded walk, 2026-11-11: asked to "sign it Alex" it wrote that, the card
    showed the saved block, and it warned the owner to check the card): one sentence where it is told how to reply - '' with nothing saved."""
    from .responder import signature_for
    from . import words
    sig = ' / '.join(l.strip() for l in signature_for(store).splitlines() if l.strip())
    return (f'HOW AN EMAIL IS SIGNED: Taskuary signs every email itself with the owner\'s saved signature ("{sig[:200]}") and takes off any sign-off '
            f"you write, so how one is signed is not yours to change: asked to sign it another way, say that the draft carries the saved signature, "
            f"and that they can edit the draft before sending or change the signature in {words.name('replies')}.") if sig else ''


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
    # ...and what each account signs with by itself while nothing here is set (account)
    accounts = [{'address': b['address'], 'signature': s} for b in boxes if (s := account(store, b['address']))]
    return {'on': on(store), 'default': default, 'mailboxes': rows, 'accounts': accounts,
            'offer': not default and not accounts and not any(r['signature'] for r in rows) and store.get_setting(OFFERED, '') != '1'}


def save_mailbox(store, address: str, sig: str) -> dict:
    """One mailbox's own signature, on the card that sends as it (outbound.card_signature reads it there)."""
    from .channels import _cfg
    box = outbound._box(store, address)
    if not box: raise ValueError(f'{address} is not a connected mailbox')
    c = store.get_connector(box['connector_id'])
    cfg = _cfg(c)
    per = dict(cfg.get('signatures') or {}) if isinstance(cfg.get('signatures'), dict) else {}
    per[box['address'].lower()] = str(sig or '').strip()
    store.merge_connector_config(box['connector_id'], {'signatures': per})
    return {'address': box['address'], 'signature': per[box['address'].lower()]}


# THE ACCOUNT'S OWN SIGNATURE (a user, approved 2026-11-02: "when sending a message, I want taskuary to use the signature that exists
# in the gmail (or whatever) account"): with no signature of the owner's own on the card or in Settings, the one the mailbox already
# signs with - read off its sent mail, used unasked only when plainly a signature (CONFIDENT), else it stays the offer Settings makes.
# Graph has no signature to give (mailboxSettings carries none), and Gmail's own signature setting is not read yet (the owner,
# 2026-11-02: the sent-mail part ships first). Held on the card a day (DAY), read again behind the draft, never per draft.
ACCOUNT = 'account_signature'            # card config: {address: {signature, source: sent, at}}
DAY, RETRY = 86400, 3600                 # read again after a day; a failed read again after an hour, the last good one kept meanwhile
CONFIDENT = (6, 0.6, 2)                  # mails read at least, share ending with it at least, lines at least
_BUSY, _LOCK = set(), threading.Lock()


def _held(cfg, a): return cfg[ACCOUNT].get(a) if isinstance((cfg or {}).get(ACCOUNT), dict) else None


def account(store, mailbox) -> str:
    """The account's own signature for this mailbox, as held on its card - '' when it has none. Never read, or older than a day:
    read again in the background (the sent-mail read is slow), the held one used meanwhile."""
    from . import demo
    from .channels import _cfg
    box = outbound._box(store, mailbox)
    if not box or demo.enabled(): return ''
    held = _held(_cfg(store.get_connector(box['connector_id'])), box['address'].lower())
    if held is None or time.time() - float(held.get('at') or 0) > DAY: _later(store, box)
    return str((held or {}).get('signature') or '').strip()


def _later(store, box):
    k = (box['connector_id'], box['address'].lower())
    with _LOCK:
        if k in _BUSY: return
        _BUSY.add(k)
    def run():
        try: refresh(store, box)
        except Exception: pass                # asked again next time; a draft never waits on it
        finally:
            with _LOCK: _BUSY.discard(k)
    threading.Thread(target=run, daemon=True, name='account-signature').start()


def refresh(store, box) -> dict:
    """Read the mailbox's signature off its sent mail now and hold the answer on the card."""
    from .channels import _cfg
    a, ok = box['address'].lower(), True
    try: sig = confident(store, box['address'])
    except Exception: sig, ok = '', False
    with _LOCK:
        cfg = _cfg(store.get_connector(box['connector_id']) or {})
        # a read that failed keeps the last good one and is read again within the hour
        row = {'signature': sig, 'source': 'sent', 'at': time.time()} if ok else {**(_held(cfg, a) or {}), 'at': time.time() - DAY + RETRY}
        per = {**(cfg[ACCOUNT] if isinstance(cfg.get(ACCOUNT), dict) else {}), a: row}
        store.patch_connector_poll_state(box['connector_id'], config_set={ACCOUNT: per})
    return row


def confident(store, mailbox) -> str:
    """The closing lines this mailbox's sent mail shares, when they plainly ARE its signature - else ''. `suggest` offers any ending
    two mails share for the owner to check; used unasked it must end most of plenty of mail (CONFIDENT), be more than a sign-off
    word, carry the owner's own name, and not be a phone's "Sent from my iPhone"."""
    from .responder import signature_tail
    lines, n, read = signature_tail(store, mailbox=mailbox)
    least, share, rows = CONFIDENT
    if read < least or n < share * read or len(lines) < rows: return ''
    name, text = [w.lower() for w in str(store.get_setting('owner_name') or '').split() if len(w) > 1], '\n'.join(lines)
    if not any(w in text.lower() for w in name): return ''
    if any(l.lower().startswith(('sent from my', 'get outlook for', 'sent via')) for l in lines): return ''
    return text

