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


def trusted_orgs(store) -> list:
    """The organisations the owner said are theirs (Trust their organisation, 2026-10-22: "hit trust domain and then all users from
    that domain are good"): [{'domain', 'tenant'}] - a mail domain, and the Teams organisation it was learned with - or
    [{'team', 'name'}], a Slack workspace (Slack has no domains, 2026-10-26)."""
    try: v = json.loads(store.get_setting('trusted_orgs') or '[]')
    except (TypeError, ValueError): return []
    return [o for o in v if isinstance(o, dict)] if isinstance(v, list) else []


_ORG_KEYS = ('domain', 'tenant', 'team')

def org_of(store, domain: str = '', tenant: str = '', team: str = '') -> dict | None:
    "The trusted organisation this domain, Teams tenant or Slack workspace is, or None. A public mail domain is never one."
    want = {'domain': (domain or '').lower(), 'tenant': (tenant or '').lower(), 'team': team or ''}
    if want['domain'] in PUBLIC_MAIL: want['domain'] = ''
    return next((o for o in trusted_orgs(store) if any(v and o.get(k) == v for k, v in want.items())), None)


def _opener(store, tid: int) -> dict | None:
    "The task's first line that is not ours - whose organisation Trust their organisation names (ingest.from_opener's reading)."
    from .ingest import is_ours
    return next((m for m in store.list_messages(tid) if not is_ours(m)), None)


def sender_org(store, m: dict) -> dict:
    """Which organisation a stored line's sender is in, as far as can be told: {'domain', 'tenant'} by mail or Teams, {'team', 'name'}
    on Slack; {} when there is none to name - a public mail domain, a chat with no organisations (WhatsApp, Telegram...), or a
    Slack line recorded before its workspace was (2026-10-26): that one is judged per person, as it always was - no guessing."""
    from .ingest import CHAT_CHANNELS
    ch, meta = (m.get('Channel') or '').lower(), _chat_meta(m)
    if ch == 'slack': return {k: v for k, v in (('team', str(meta.get('team') or '')), ('name', str(meta.get('team_name') or ''))) if v} if meta.get('team') else {}
    if ch in CHAT_CHANNELS and ch != 'teams': return {}
    addr, tenant = str(m.get('FromEmail') or '').lower(), str(meta.get('tenant') or '')
    if ch == 'teams' and (not tenant or '@' not in addr):
        from .channels import teams_member
        got = teams_member(store, m.get('SourceName') or '', m.get('ConversationId') or '', addr)
        tenant, addr = tenant or got.get('tenant', ''), addr if '@' in addr else got.get('email', '')
    d = _domain(addr)
    return {k: v for k, v in (('domain', '' if d in PUBLIC_MAIL else d), ('tenant', tenant)) if v}


def trust_org(store, tid: int, actor: str) -> dict:
    """The owner's word that the task's opener's whole organisation is theirs: its mail domain (and, from Teams, its tenant) - or its
    Slack workspace - joins trusted_orgs, and the task is vouched for. Raises ValueError when there is no organisation to name (a
    public mail domain, a sender nobody can place)."""
    from . import origin
    m = _opener(store, tid)
    if not m: raise ValueError('nobody else wrote on this task')
    if not (o := sender_org(store, m)):
        d = _domain(m.get('FromEmail'))
        raise ValueError(f'{d} is a public mail service, so it cannot be trusted as one organisation - use Trust them' if d in PUBLIC_MAIL
                         else "Taskuary can't tell which organisation they are from - use Trust them")
    orgs = trusted_orgs(store)
    hit = next((x for x in orgs if any(o.get(k) and x.get(k) == o[k] for k in _ORG_KEYS)), None)
    if hit: hit.update({k: v for k, v in o.items() if v and not hit.get(k)})
    else: orgs.append(o)
    store.set_setting('trusted_orgs', json.dumps(orgs), actor)
    origin.raise_to(store, tid, 'trusted', actor)
    return {'domain': o.get('domain', ''), 'tenant': o.get('tenant', ''), **{k: o[k] for k in ('team', 'name') if o.get(k)}}


def trust_offer(store, tid: int) -> dict | None:
    """The two presses that lift a stranger's hold, worded for the channel (the owner, 2026-10-26: "we should have button on untrusted
    user to either trust user or trust domain and then we won't have issue again"): {'person': 'Trust Erin', 'org': 'Trust everyone at
    vendor.example' | 'Trust <workspace>' | None} - no organisation button where there is none to name, rather than one that fails."""
    m = _opener(store, tid)
    if not m: return None
    meta, ch = _chat_meta(m), (m.get('Channel') or '').lower()
    # a Slack line's name is a user id (U0...): its profile's real name when the poller recorded one, else "them"
    words = str(meta.get('name') or ('' if ch == 'slack' else m.get('FromName')) or '').split()
    first = words[0] if words and '@' not in words[0] else ''
    # a From that failed verification may be forged: vouching for the person is the owner's call, a whole organisation never rides on it
    o = {} if auth(m) == 'fail' else sender_org(store, m)
    org = (f"Trust {o['name']}" if o.get('name') else 'Trust their Slack workspace') if o.get('team') else \
          f"Trust everyone at {o['domain']}" if o.get('domain') else 'Trust their organisation on Teams' if o.get('tenant') else None
    return {'person': f'Trust {first}' if first else 'Trust them', 'org': org}


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
    if (o := org_of(store, _domain(addr))):
        return True, _said(f"Everyone at {o.get('domain') or _domain(addr)} is trusted - you said so.")
    if not on('trust_sent_history'):
        return False, _said(f'{who} is new here, and checking your Sent Items for people you know is switched off in Settings, {NOBODY}.', True)
    mailbox = (msg.get('source_name') or '').strip().lower()
    sent = _said(f'You have written to {addr} before - it is in your Sent Items.')
    if (r := store.trusted_sender(mailbox, addr)): return True, sent if r == 'in your Sent Items' else _said(f'You vouched for {who}.')
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


def _chat_meta(msg: dict) -> dict:
    "What the poller recorded about a chat line: an ingest dict's mail_meta, or a stored row's MailMetaJson."
    meta = msg.get('mail_meta')
    if not isinstance(meta, dict):
        try: meta = json.loads(msg.get('MailMetaJson') or 'null')
        except (TypeError, ValueError): meta = None
    return meta if isinstance(meta, dict) else {}


def chat_aliases(msg: dict) -> tuple:
    """The same person's other platform id, as the poller recorded it (MailMetaJson 'alias'): WhatsApp names one person by
    phone in a direct chat and by LID in a group, and the two must not read as two people."""
    a = str(_chat_meta(msg).get('alias') or '').strip().lower()
    return (a,) if a else ()


def _teams_org(store, msg: dict, who: str, vouched: list) -> bool:
    "Is this Teams sender staff of the owner's own organisation? (senders._chat_known)"
    from .channels import ORG_REASON, teams_org
    meta, acct = _chat_meta(msg), str(msg.get('source_name') or msg.get('SourceName') or '')
    if meta.get('internal') or ORG_REASON in vouched: return True
    if _domain(who) in (own_domains(store) | {_domain(acct)}) - PUBLIC_MAIL - {''}: return True
    return 'internal' not in meta and bool(teams_org(store, acct, who))


def _slack_own(store, msg: dict, team: str) -> bool:
    """Is this Slack workspace the owner's own? The poller's word at ingest ('internal'), else - it could not ask auth.test then -
    any Slack connection's own workspace as kept since (channels.slack_own_team)."""
    meta = _chat_meta(msg)
    if 'internal' in meta: return bool(meta['internal'])
    for c in store.connectors_by_type('slack') or []:
        try: own = json.loads(c.get('ConfigJson') or '{}').get('team_id')
        except (TypeError, ValueError): own = None
        if own and own == team: return True
    return False


ORG_TRUST = 'at an organisation you trust'

def _teams_trusted_org(store, msg: dict, who: str, vouched: list) -> dict | None:
    "The trusted organisation a Teams sender is in (trust_org) - asked of the chat's members once per person, then remembered."
    if not trusted_orgs(store): return None
    if ORG_TRUST in vouched: return {'domain': ''}
    if (o := org_of(store, _domain(who), _chat_meta(msg).get('tenant'))) is not None: return o
    from .channels import teams_member
    got = teams_member(store, str(msg.get('source_name') or msg.get('SourceName') or ''),
                       str(msg.get('conversation_id') or msg.get('ConversationId') or ''), who)
    o = org_of(store, _domain(got.get('email')), got.get('tenant'))
    if o is not None: store.remember_trust('teams', who, ORG_TRUST)
    return o


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
    vouched = [r for k in (who, *alias) if (r := store.trusted_sender(ch, k))]
    # TEAMS IS INTERNAL (the owner, 2026-10-21: "Teams should be always safe since it's internal"): a colleague in the owner's own
    # organisation needs no history - the directory's word, recorded at ingest or remembered per person (channels.ORG_REASON), or
    # an address on the owner's own domain or the Teams account's. A line recorded before anyone could tell (no 'internal': Graph
    # refused the lookup, or it predates 0.3.9.15) is resolved now, once per person (channels.teams_org). A guest or a
    # federated user from another organisation is judged like any chat sender.
    if ch == 'teams' and _teams_org(store, msg, who, vouched): return True, _said(f'{name} is in your own organisation on Teams.')
    if ch == 'teams' and (o := _teams_trusted_org(store, msg, who, vouched)):
        return True, _said(f"{name} is at {o.get('domain') or 'an organisation'} you trust.")
    # SLACK HAS NO DOMAINS (the owner chose, 2026-10-26): a member of the owner's own workspace is known like Teams' own organisation;
    # a guest or a Slack Connect sender from another company (another user_team) is judged per person, and Trust their organisation
    # names their workspace. A line recorded before the workspace was (no 'team') is judged per person, as it always was.
    if ch == 'slack' and (team := str(_chat_meta(msg).get('team') or '')):
        if _slack_own(store, msg, team): return True, _said(f'{name} is in your own Slack workspace.')
        if (o := org_of(store, team=team)): return True, _said(f"{name} is in {o.get('name') or 'a Slack workspace'}, a workspace you trust.")
    if vouched: return True, _said(f'You vouched for {name}.')
    how = store.talked_with(ch, who, exclude_mid, alias)
    # A TEAMS SENDER'S HISTORY BEFORE THEIR ID (2026-10-26, the owner: "we have talked to this person a million times"): until
    # 2026-10-14 a Teams sender the directory could not place - a colleague in a sister tenant - was stored with no address, so
    # their lines are keyed by display name; since then by Graph id, which none of those lines carry, and weeks of answers in a
    # group chat read "you haven't answered them". Their name is matched to those name-keyed lines - and only in THIS
    # conversation, so copying a colleague's name elsewhere borrows nothing (the reason the id replaced the name).
    conv = str(msg.get('conversation_id') or msg.get('ConversationId') or '')
    if not how and ch == 'teams' and who.startswith('teams:') and name and name.lower() != who and conv:
        how = store.talked_with(ch, who, exclude_mid, (*alias, name), conversation=conv)
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
    # ...and a mail sender too, per mailbox like the Sent Items hit: their next mail is no stranger's either ("then we won't have issue
    # again", 2026-10-26). A From that failed verification may be forged - the task is vouched for, the address is not remembered.
    elif ch == 'email' and '@' in (addr := str(m.get('FromEmail') or '')) and auth(m) != 'fail':
        store.remember_trust(m.get('SourceName') or '', addr, 'you vouched for them')


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
