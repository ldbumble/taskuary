"""THE SIGNATURE UNDER EVERY EMAIL TASKUARY PREPARES (the owner, 2026-10-28: "on replies there was no signature with it. It should
use the default signature always (you can put that as a setting)").

One layer, three doors:
- what the owner sees: every review row carries `Signature`, the block that will go under it, and the reply box shows it - an
  empty box opens on it, a draft without it gets it - so what is in the box is what goes;
- what is made: every draft is signed once as it is filed (responder.signed, agent_signed, a forward's draft), and what leaves is
  exactly what the box held - `verdicts.decide` signs nothing (2026-11-17: signing at send put the block under the owner's own
  "Thanks, Alex", a line the box never showed);
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


def as_sent(store, rv: dict, text: str, msg: dict = None) -> str:
    """The text as it goes out: an email's words as plain text (chatformat.plain_text: Markdown left in the box went out as stars and
    hashes), the block under them as it stands - nothing added, so a sign-off of the owner's own is the last line; chat untouched."""
    from .chatformat import plain_text
    t = str(text or '').rstrip()
    if not t.strip() or not is_email(store, rv, msg): return str(text or '')
    body = unsigned(t, for_review(store, rv, msg))
    return (plain_text(body) or body) + t[len(body):]


def agent_signed(store, rv: dict, text: str, msg: dict = None) -> str:
    """An agent's draft as it is filed: the agent's own sign-off ("Best,\\nAlex Doyle") taken off and the saved block put on once -
    the drafter's own road (responder.signed). It was filed as written, and the box put the block under the agent's name: signed
    twice (walk 2026-10-29). Chat: the owner's name lines off, nothing on (outbox)."""
    from .responder import chat_said, own_names, signed
    text = str(text or '').strip()
    if not text: return text
    if not is_email(store, rv, msg): return chat_said(store, text)
    sig = for_review(store, rv, msg)
    out = signed(text, sig, own_names(store))
    if (rv or {}).get('ReviewId'): _say_ending(store, rv['ReviewId'], replaced(text, out, sig))
    return out


ENDING, _SEP = 'Your saved signature replaced the ending the agent wrote', ' · '
def replaced(text: str, out: str, sig: str) -> str:
    "The ending the agent wrote that the signer took off for the saved block - '' when it wrote none, or wrote the block itself."
    from .chatformat import plain_text
    mine = unsigned(text, sig)
    words, kept = (plain_text(mine) or mine).split(), unsigned(out, sig).split()
    return ' '.join(words[len(kept):]) if sig.strip() and len(words) > len(kept) and words[:len(kept)] == kept else ''


def _say_ending(store, rid: int, gone: str):
    """THE CARD SAYS WHERE ITS ENDING IS NOT THE AGENT'S (walk 6, 2026-11-23: the agent ended a letter as he asked, the signer put his saved block
    on, and it left with his full name - said to the agent alone, never on the card he pressed). One line under the card's reason, on every
    road that files an agent's email; the line a re-save left is replaced, never stacked."""
    from . import words
    was = str((store.get_review(rid) or {}).get('Reason') or '').split(_SEP + ENDING)[0]
    now = was + (f'{_SEP}{ENDING} ("{gone[:80]}") - {words.name("replies")} changes it' if gone else '')
    if now != str((store.get_review(rid) or {}).get('Reason') or ''): store.update_review_reason(rid, now)


def told(store) -> str:
    """THE AGENT IS TOLD HOW ITS EMAILS ARE SIGNED, up front (the recorded walk, 2026-11-11: asked to "sign it Alex" it wrote that, the card
    showed the saved block, and it warned the owner to check the card): one sentence for every agent that can draft an email - '' with
    the switch off."""
    from .responder import signature_for
    from . import words
    # ...AND A SIGN-OFF HE ASKS FOR BECOMES THE SAVED ONE (the walk, 2026-11-21: told "I sign every email 'Best, Alex'", Codex withdrew its own
    # card when the signer put "Alex Doyle" back, and left the email as prose with nothing to press): kept through remember (keep), never fought
    sig = ' / '.join(l.strip() for l in signature_for(store).splitlines() if l.strip())
    return f'HOW AN EMAIL IS SIGNED: Taskuary puts the owner\'s saved signature ("{sig[:200]}") under every email, in place of a sign-off of yours.' if sig else ''


SIG_LINES, SIG_WIDTH = 6, 70          # a sign-off block's shape: name, title, company, a phone, a line or two more
def keep(store, sig: str, actor: str = 'owner') -> str:
    """HOW THE OWNER SIGNS, SAID TO ANY AGENT OR THE ASSISTANT, IS THE SAVED SIGNATURE (the walk, 2026-11-21: kept as a memory line, it never
    reached a card - the signer reads Settings' Email signature, not the memory): the block signature_for puts under every email, its lines
    as given ("Best,\nAlex"). The one it replaces is kept in the audit row."""
    block = '\n'.join(l.strip() for l in str(sig or '').replace('\\n', '\n').strip().strip('"\'').splitlines() if l.strip())
    if not block: raise ValueError('say the signature, as it goes under an email')
    # ...AND ONLY A SIGN-OFF BLOCK IS ONE (round 4, 2026-11-22: "Training spend requires sign-off from Marcus Reed (...). Email signature: Alex."
    # became the signature under every email, the fact kept nowhere): a few short lines, by their shape - a sentence goes to memory instead
    lines = block.splitlines()
    if len(lines) > SIG_LINES or any(len(l) > SIG_WIDTH for l in lines):
        raise ValueError(f'not kept as the signature: a signature is the short block that goes under an email ("Best," then "Alex" on its own '
                         f'line) - at most {SIG_LINES} lines of {SIG_WIDTH} characters. Keep just that block with section signature, and any '
                         'other fact with remember in its own section')
    was = str(store.get_setting('email_signature') or '')
    # ...AND THE DRAFTS WAITING FOR HIS SEND CARRY IT TOO (the fix1 walk, 2026-11-21: told the old draft kept the old sign-off, the agent asked
    # him "tell me if you want it set up again"): each email still unsent that ends with the block it had is re-signed - plain code, the
    # signer's own road. One he wrote his own ending on is left as he wrote it
    from .responder import own_names, signed
    waiting = [r for r in store._rows("SELECT * FROM review WHERE Status IN ('pending','held') AND Kind<>'action' AND IFNULL(DraftText,'')<>''")
               if is_email(store, r)]
    olds = {r['ReviewId']: for_review(store, r) for r in waiting}
    store.set_setting('email_signature', block, actor)
    moved = []
    for r in waiting:
        old, new, text = olds[r['ReviewId']], for_review(store, r), str(r['DraftText']).rstrip()
        if not old or not new or old == new or not text.endswith(old.strip()): continue
        store.save_review_draft(r['ReviewId'], signed(text, new, (*own_names(store), *old.splitlines()))); moved.append(r['ReviewId'])
    store.audit('setting', 0, 'signature_kept', actor, detail={'before': was, 'after': block, 'resigned': moved})
    return block


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

