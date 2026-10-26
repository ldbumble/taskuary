"""A WhatsApp chat is found by WHO it is - the person's name, their phone number, the group's name - never by its JID.

The owner, 2026-10-23: "whatsapp search should be by phone number, name or group name not id's. you can show id's in small
under but it has to be searched by normal things". Every picker matched `name + jid`, so a group was found by typing
1203630... and a person by their number only when it was typed exactly as WhatsApp stores it, with no + or spaces.

The names come from the bridge's roster (whatsapp/roster.mjs: the name the owner saved, a group's subject, a person's own
push name) and are kept here, in one setting, so a picker still names a chat while the bridge is restarting - its roster
lives in memory and the saved names arrive a moment after it connects. The JS twin is website/src/waChats.js."""
import json, re, unicodedata

KEY = 'wa_names'                 # {jid: name}, merged on every roster read


# ...and a LID (<n>@lid): WhatsApp addresses most 1:1 chats by one now, and those rows were neither kept nor named (2026-10-26)
def is_jid(s) -> bool: return str(s or '').endswith(('@s.whatsapp.net', '@g.us', '@lid'))
def is_group(jid) -> bool: return str(jid or '').endswith('@g.us')
def digits(s) -> str: return re.sub(r'\D', '', str(s or ''))
def _fold(s) -> str: return ''.join(c for c in unicodedata.normalize('NFKD', str(s or '')) if not unicodedata.combining(c)).casefold()


def number(jid) -> str:
    """The phone number in a person's JID, digits only - '' for a group, whose id is not a number anyone has."""
    m = re.match(r'^(\d+)(?::\d+)?@s\.whatsapp\.net$', str(jid or ''))
    return m.group(1) if m else ''


def fmt_phone(d) -> str:
    """+1 555-010-0123 for a North American number, +<digits> for the rest - no country table guessed at."""
    d = digits(d)
    if not d: return ''
    return f'+1 {d[1:4]}-{d[4:7]}-{d[7:]}' if len(d) == 11 and d[0] == '1' else '+' + d


def phone(jid) -> str: return fmt_phone(number(jid))


def bare(name, jid) -> bool:
    """No name at all, or a name that is only the chat's own number/id standing in for one (the poller's from_name fallback)."""
    n = str(name or '').strip()
    return not n or n == jid or n == str(jid or '').split('@')[0] or (bool(number(jid)) and digits(n) == number(jid) and not re.search(r'[^\d\s+()\-.]', n))


def names(store) -> dict:
    try: return json.loads(store.get_setting(KEY) or '{}') or {}
    except (TypeError, ValueError): return {}


def remember(store, rows, key: str = 'jid'):
    """Keep every real name the roster gave, so the next read - bridge up or not - can say it."""
    known = names(store)
    new = {r[key]: r['name'].strip() for r in rows if is_jid(r.get(key)) and not bare(r.get('name'), r[key])}
    if any(known.get(k) != v for k, v in new.items()): store.set_setting(KEY, json.dumps({**known, **new}), 'whatsapp')


def name_of(store, jid, known: dict = None) -> str:
    n = (names(store) if known is None else known).get(jid) or ''
    return '' if bare(n, jid) else n


def label(jid, name='') -> str:
    """What a chat is called on screen: its name, else its number, else - a group nobody has named yet - 'WhatsApp group'."""
    return name if not bare(name, jid) else phone(jid) or ('WhatsApp group' if is_group(jid) else str(jid or ''))


def is_phone_query(q) -> bool:
    q = str(q or '').strip()
    return len(digits(q)) >= 3 and not re.search(r'[^\d\s+()\-./]', q)


def matches(q, jid, name='') -> bool:
    """The query against the chat's name and its phone number - never the JID. A query of digits and punctuation is a phone
    number in whatever form it was typed: +1 (555) 010-0123, 0015550100123, 555 0100 all find the same person."""
    q = str(q or '').strip()
    if not q: return True
    num = number(jid)
    if is_phone_query(q):
        d = digits(q)
        return bool(num) and any(x and x in num for x in {d, d[2:] if d.startswith('00') else '', d.lstrip('0')})
    hay = _fold(f"{'' if bare(name, jid) else name} {fmt_phone(num)}")
    return all(_fold(w) in hay for w in q.split())


def user(jid) -> str: return str(jid or '').split('@')[0].split(':')[0]


def fill(store, rows, key: str = 'jid', name: str = 'name') -> list:
    """Each row named (the roster's name, else the one kept, else what its last message was signed with, else the name its
    person signed a message with anywhere - a group they are both in) and given `phone`."""
    known, seen = names(store), {}
    try:
        for r in store.chats(None):
            cid = str(r.get('Cid') or '')
            if (r.get('Channel') or '').lower() == 'whatsapp' and cid.startswith('whatsapp:'): seen[cid[9:]] = r.get('Name') or ''
    except Exception: pass
    signed = None
    for r in rows:
        jid = r.get(key) or ''
        if not is_jid(jid): continue
        if bare(r.get(name), jid):
            r[name] = name_of(store, jid, known) or ('' if is_group(jid) or bare(seen.get(jid), jid) else seen[jid])
        if bare(r.get(name), jid) and not is_group(jid):
            if signed is None: signed = _signed(store)
            if not bare(n := signed.get(user(jid), ''), jid): r[name] = n
        r['phone'] = phone(jid)
    return rows


def _signed(store) -> dict:
    """{number or LID: the name they last signed a WhatsApp message with}, under both of a person's ids (the poller keeps the
    other one as the message's `alias`). Read once per fill, and only when a row has no better name."""
    out = {}
    try: rows = store._rows("SELECT FromEmail, FromName, MailMetaJson FROM message WHERE Channel='whatsapp' "
                            "AND IFNULL(Direction,'in')<>'out' AND IFNULL(FromName,'')<>'' ORDER BY SentAt")
    except Exception: return out
    for r in rows:
        try: alias = (json.loads(r.get('MailMetaJson') or '{}') or {}).get('alias') or ''
        except (TypeError, ValueError, AttributeError): alias = ''
        n = r['FromName'].strip()
        if not re.search(r'[^\d\s+()\-.]', n): continue          # the poller's number-for-a-name fallback names nobody
        for i in (r.get('FromEmail') or '', alias):
            if str(i).startswith('whatsapp:') and i[9:]: out[i[9:]] = n
    return out
