"""Is this someone the owner already deals with?

The one place a stranger's text turns into an agent on the owner's machine with nobody in
between is the coding agent's auto-start. Every comparable tool gates that on the SENDER -
OpenClaw pairs unknown DMs, Copilot ignores users without write access, and this codebase
already does it for GitHub (GH_AUTO) - and email had no such gate. Now it does: a first-time
sender outside the owner's own domains still gets triaged and filed, the task still lands on
the Board; only the automatic session start waits for the owner's click.

"First-time" cannot mean "first time in Taskuary's table": the table starts on the day the
mailbox was connected, and someone the owner has written to weekly for three years would look
like a stranger. So the deep check asks the mailbox itself - has the owner ever SENT this
address anything (Sent Items, one search) - and it runs only for the rare message that reaches
the auto-start decision, once per address: a verified hit is remembered (sender_trust).

The rules are the owner's to see and switch (Settings, PW-079..081): own domains, verified Sent
Items evidence, and chat channels inside a workspace the owner controls. "Has written before" is
NOT one of them - a stranger's own earlier mail, a historical import or a retry never turns them
into someone the owner deals with.
"""
import json
from loguru import logger

from .projects import PUBLIC_MAIL

_SENT_FOLDERS = ('[Gmail]/Sent Mail', 'Sent', 'Sent Items', 'INBOX.Sent', 'Sent Messages')


def _domain(addr: str) -> str: return (addr or '').rsplit('@', 1)[-1].strip().lower() if '@' in (addr or '') else ''


def own_domains(store) -> set:
    """The owner's domains: every connected mailbox, plus the owner's address in settings/SOUL.md."""
    ds = {_domain(s.get('Address')) for s in store.list_sources(active_only=False) if s.get('Channel') == 'email'}
    ds.add(_domain((store.owner() or {}).get('owner_email')))
    return ds - {''}


def own_addresses(store) -> set:
    """The owner's exact addresses: every connected mailbox and the owner address in settings/SOUL.md."""
    xs = {(s.get('Address') or '').strip().lower() for s in store.list_sources(active_only=False) if s.get('Channel') == 'email'}
    xs.add(((store.owner() or {}).get('owner_email') or '').strip().lower())
    return {x for x in xs if '@' in x}


def auth(msg: dict) -> str:
    "The From verification ingest recorded (mailauth.verdict): on the msg dict, its mail_meta, or a row's MailMetaJson."
    if msg.get('auth'): return msg['auth']
    meta = msg.get('mail_meta')
    if not isinstance(meta, dict):
        try: meta = json.loads(msg.get('MailMetaJson') or 'null')
        except (TypeError, ValueError): meta = None
    return (meta.get('auth') if isinstance(meta, dict) else None) or 'none'


# THE SENTENCE IS THE ANSWER. These were fragments pasted after a colon - "assistant did not start: a member of a
# whatsapp chat you have not talked with one-to-one." - read on a task page by an owner who could not tell who, which
# chat or what to do (2026-10-16). Each is now a whole sentence naming the person and the channel; the caller adds what
# the owner can do next, and an allow-sentence reads after "Starting by itself:".
class Said(str):
    "A trust verdict's sentence. `.stranger` marks the first-time-sender rule, which ingest tags as a hold - by flag, not by its words."
    stranger = False

def _said(text: str, stranger: bool = False) -> Said:
    s = Said(text); s.stranger = stranger
    return s

_CH = {'whatsapp': 'WhatsApp', 'imessage': 'iMessage', 'google_chat': 'Google Chat', 'rocketchat': 'Rocket.Chat'}
def channel_name(ch) -> str: ch = str(ch or ''); return _CH.get(ch.lower(), ch[:1].upper() + ch[1:])
NOBODY = 'so no agent starts on their words by itself'


def _person(msg: dict, addr: str = '') -> str:
    "'Erin Blake (erin@vendor.example)', else the address - whoever the message says wrote it."
    name = ' '.join(str(msg.get('from_name') or '').split())
    if name and '@' not in name: return f'{name} ({addr})' if addr else name
    return addr or name or 'This sender'


def known(store, msg: dict, exclude_mid=None, deep: bool = False) -> tuple:
    """(may this sender start a worker unattended, why). Three rules, each a Settings switch (PW-079
    to PW-081): a chat person the owner talks with (or a workspace item); the owner's own domains; and
    verified SENT evidence that THIS mailbox wrote to the exact address - what the store already
    holds, a hit remembered from an earlier lookup, and (deep) the mail server's own Sent Items,
    asked once per address. Prior incoming mail is never trust: a stranger's second message is a
    stranger's message. A lookup that fails is not proof either way and is said as such."""
    cfg = store.get_settings()
    on = lambda k: cfg.get(k, '1') == '1'
    from .store import OWN_CHANNELS
    ch = msg.get('channel') or ''
    if ch in OWN_CHANNELS:                                                                # X3: never "a chat you control"
        return True, _said('Taskuary wrote this report.' if ch == 'report' else "Taskuary's assistant wrote this.")
    from .ingest import CHAT_CHANNELS
    if ch.lower() in CHAT_CHANNELS: return _chat_known(store, msg, ch.lower(), exclude_mid, on('trust_non_email'))
    # a tracker, an alert or the local API is a workspace item, not a room of people - and GitHub has its own gate (GH_AUTO)
    if ch != 'email':
        return (True, _said(f'It came from {channel_name(ch) or "a workspace"}, a workspace you control.')) if on('trust_non_email') else \
               (False, _said(f'Starting an agent from {channel_name(ch) or "this channel"} is switched off in Settings, {NOBODY}.'))
    addr = (msg.get('from_email') or '').strip().lower()
    if not addr or '@' not in addr: return False, _said('This message has no sender address, so no agent starts on it by itself.')
    who = _person(msg, addr)
    # before any rule that reads the address: a forged From would otherwise borrow a colleague's trust, or the owner's own
    if auth(msg) == 'fail':
        return False, _said(f'{addr} failed sender verification (DMARC/DKIM), so the From address may be forged and no agent starts on it by itself.')
    if addr in own_addresses(store): return True, _said('It came from your own address.')
    # a public mail domain is everybody's: an owner on gmail.com made every stranger there 'your own domain'
    if _domain(addr) in own_domains(store) - PUBLIC_MAIL:
        return (True, _said(f'{addr} is on your own domain.')) if on('trust_own_domain') else \
               (False, _said(f'{who} is on your own domain, but trusting your own domain is switched off in Settings, {NOBODY}.'))
    if not on('trust_sent_history'):
        return False, _said(f'{who} is new here, and checking your Sent Items for people you know is switched off in Settings, {NOBODY}.', True)
    mailbox = (msg.get('source_name') or '').strip().lower()
    sent = _said(f'You have written to {addr} before - it is in your Sent Items.')
    if store.trusted_sender(mailbox, addr): return True, sent
    if store.wrote_to_locally(mailbox, addr, exclude_mid): return True, _said(f'You have written to {addr} before.')
    if deep:
        try: hit = wrote_to(store, mailbox, addr)
        except Exception as e:
            logger.warning(f'could not check Sent Items of {mailbox} for {addr}: {e}')
            return False, _said(f'Taskuary could not check the Sent Items of {mailbox or "this mailbox"} ({str(e)[:120]}), '
                                f'so it cannot tell whether you know {who}, and no agent starts on their words by itself.')
        if hit:
            store.remember_trust(mailbox, addr, 'in your Sent Items')
            return True, sent
    return False, _said(f'{who} is not on your domain and you have never written to them, {NOBODY}.', True)


def chat_key(msg: dict) -> str:
    "ingest._who's key for a chat sender, from a DB row or an ingest dict: their address or chat id, else their name."
    return str(msg.get('FromEmail') or msg.get('from_email') or msg.get('FromName') or msg.get('from_name') or '').strip().lower()


def _is_own(msg: dict) -> bool:
    "The owner's own line as channels.ingest_own_message stores it (X1): set by code. A display name of 'You' is anyone's."
    return (msg.get('Direction') or msg.get('direction')) == 'out' or (msg.get('Status') or msg.get('status')) == 'context'


def chat_aliases(msg: dict) -> tuple:
    """The same person's other platform id, as the poller recorded it (mail_meta / MailMetaJson 'alias'): WhatsApp names
    one person by phone in a direct chat and by LID in a group, and the two must not read as two people."""
    meta = msg.get('mail_meta')
    if not isinstance(meta, dict):
        try: meta = json.loads(msg.get('MailMetaJson') or 'null')
        except (TypeError, ValueError): meta = None
    a = str((meta or {}).get('alias') or '').strip().lower() if isinstance(meta, dict) else ''
    return (a,) if a else ()


def _chat_known(store, msg: dict, ch: str, exclude_mid, on: bool) -> tuple:
    """A chat is trusted per PERSON, not per room: anyone in a connected group chat could start an agent with full
    permissions. The owner's own line; someone the owner has talked with one-to-one in this channel, or answered (their
    line, then the owner's, in any of its chats - store.talked_with); or someone the owner vouched for (release, Trust this
    task). Being in a room the owner is in counts for nothing. Switched off, only the owner."""
    if _is_own(msg): return True, _said('These are your own words.')
    who, room, alias = chat_key(msg), channel_name(ch), chat_aliases(msg)
    name = ' '.join(str(msg.get('from_name') or msg.get('FromName') or '').split()) or who
    if not on: return False, _said(f'{name or "Someone"} wrote in {room}, where only your own messages start an agent by themselves (Settings).')
    if not who: return False, _said(f'Nobody can tell who wrote this in {room}, so no agent starts on it by itself.')
    if any(store.trusted_sender(ch, k) for k in (who, *alias)): return True, _said(f'You vouched for {name}.')
    how = store.talked_with(ch, who, exclude_mid, alias)
    if how == 'dm': return True, _said(f'You talk with {name} one-to-one on {room}.')
    if how == 'answered': return True, _said(f'You have answered {name} on {room} before.')
    return False, _said(f"{name} wrote in {room}, and you haven't talked with them one-to-one or answered them there, {NOBODY}.")


def vouch(store, rows) -> None:
    """The owner's say-so for the task's OPENER (release, Trust this task) - the first line on it that is not ours, as
    ingest.from_opener reads it: remembered per channel and person. Everyone else a group put on the task stays a stranger."""
    from .ingest import CHAT_CHANNELS, is_ours
    m = next((m for m in rows if not is_ours(m)), None)
    ch = ((m or {}).get('Channel') or '').lower()
    if ch in CHAT_CHANNELS and (who := chat_key(m)): store.remember_trust(ch, who, 'you vouched for them')


def wrote_to(store, mailbox: str, addr: str) -> bool:
    """Has THIS mailbox ever sent addr anything? Asked of the mail server that holds the history
    Taskuary does not. True/False is an answer; a failure RAISES, because 'could not check' is not
    'no' (PW-080) - the caller says so and leaves the task for a manual start."""
    if not (mailbox and addr): return False
    src = next((s for s in store.list_sources(active_only=False)
                if s.get('Channel') == 'email' and (s.get('Address') or '').lower() == mailbox.lower()), None)
    c = store.get_connector(src['ConnectorId'], with_secret=True) if src and src.get('ConnectorId') else None
    # no connection to ask is absence of evidence, not a failed lookup: the sender is simply a stranger here
    if not c: return False
    if c['Type'] == 'outlook': return _graph_wrote_to(c, mailbox, addr)
    if c['Type'] in ('gmail', 'imap'): return _imap_wrote_to(c, addr)
    raise RuntimeError(f"{c['Type']} has no Sent Items lookup")


def _graph_wrote_to(c, mailbox, addr) -> bool:
    import requests
    from .channels import graph_token, GRAPH
    cfg = {**json.loads(c.get('ConfigJson') or '{}'), '_cid': c['ConnectorId']}
    tok = graph_token(cfg, c.get('Secret'))
    r = requests.get(f'{GRAPH}/users/{mailbox}/mailFolders/sentitems/messages', timeout=20,
                     headers={'Authorization': f'Bearer {tok}'}, params={'$search': f'"to:{addr}"', '$top': 1, '$select': 'id'})
    r.raise_for_status()
    return bool(r.json().get('value'))


def _imap_wrote_to(c, addr) -> bool:
    from .imapmail import _login
    M, _user = _login(c)
    try:
        for f in _SENT_FOLDERS:
            typ, _ = M.select(f'"{f}"', readonly=True)
            if typ != 'OK': continue
            typ, data = M.search(None, 'TO', f'"{addr}"')
            return typ == 'OK' and bool(data and data[0])
    finally:
        try: M.logout()
        except Exception: pass
    return False
