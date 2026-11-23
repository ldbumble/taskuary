"""A name becomes an address from the owner's own mail (docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

"Send an email to Gail" needs Gail's address. The look-up only knew people who had WRITTEN IN; someone the owner only
ever wrote to, or copied, was nobody. This searches both. Recipients are stored as bare addresses (channels._addrs), so
a name meets them through the address itself. Only a WHOLE-WORD match can fill an address - every word of the name a
word of the address (gail.moreno@) or initial + surname (gmoreno@); "Ray" inside murray.jones@ is only offered, never
filled. One person is the answer; several are offered; none is nothing - nobody is guessed.
"""
import json, re

SCAN = 3000                  # the owner's sent mail read for recipients, newest first


def _words(text: str) -> list: return [w for w in re.findall(r'[a-z]+', str(text or '').lower()) if len(w) > 1]


def _whole(words: list, address: str, name: str = '') -> bool:
    local = address.split('@', 1)[0].lower()
    have = set(_words(local)) | set(_words(name))
    return bool(words) and (set(words) <= have or (len(words) > 1 and re.sub(r'[^a-z]', '', local) == words[0][0] + words[-1]))


def _part(words: list, address: str, name: str = '') -> bool:
    hay = re.sub(r'[^a-z]', '', address.split('@', 1)[0].lower()) + ' ' + str(name or '').lower()
    return bool(words) and all(w in hay for w in words)


def at_domain(store, domain: str) -> list:
    """[(address, name)] of everyone at `domain` in the owner's mail - who wrote in, and whom he wrote to - most written-with first.
    A public mail service is nobody's company: [] - those who use it are strangers to each other. The owner himself is never one of them."""
    from .peoplesearch import org_of
    from .senders import own_addresses
    d = str(domain or '').strip().lower().lstrip('@')
    if not d or not org_of('@' + d): return []
    out = {h['Email']: h.get('Name') or '' for h in (store.senders_like(f'@{d}', limit=8) if hasattr(store, 'senders_like') else [])
           if h['Email'].endswith('@' + d)}
    for a in written_to(store):
        if a.lower().endswith('@' + d): out.setdefault(a.lower(), '')
    mine = own_addresses(store)
    return [(a, n) for a, n in out.items() if a.lower() not in mine]


def written_to(store) -> dict:
    """{address: (times, last sent)} over the To and Cc of the owner's own sent mail - one scan per new message."""
    # kept ON the store, rescanned only when mail arrives. Keyed by id(store) it outlived its store: a closed store's id
    # came back for the next one, whose own recipients were then never read (CI, 2026-10-05)
    with store.lock: newest = store.cx.execute('SELECT MAX(MessageId) FROM message').fetchone()[0]
    held = getattr(store, '_people_sent', None)
    if held and held[0] == newest: return held[1]
    seen = {}
    for r in store._rows("SELECT RecipientsJson, SentAt FROM message WHERE (Direction='out' OR Status='context') "
                         "AND RecipientsJson IS NOT NULL ORDER BY SentAt DESC LIMIT ?", (SCAN,)):
        try: rec = json.loads(r['RecipientsJson'] or '{}') or {}
        except ValueError: continue
        for a in (rec.get('to') or []) + (rec.get('cc') or []):
            a = str(a or '').strip().lower()
            if '@' not in a: continue
            n, last = seen.get(a, (0, ''))
            seen[a] = (n + 1, max(last, str(r.get('SentAt') or '')))
    store._people_sent = (newest, seen)
    return seen


_ADDR = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
def owner_lines(store, tid=None) -> list:
    """(address, the line it stands in) for every email address in the owner's OWN words - his memory (LEARNED.md: "Your people") and, on a
    task, what he typed on it. An address he gave is no guess (round 3, 2026-11-22: Paula's address was in his memory, and the agent was told
    it guessed it and asked him for it)."""
    texts = [str(store.get_doc('learned') or '')]
    if tid:
        from .general import USER_TYPE, WAITING_TYPE, is_brief
        t = store.get_task(int(tid)) or {}
        if t.get('OriginBase') == 'owner': texts.append(str(t.get('Summary') or ''))
        texts += [str(c.get('Body') or '') for c in store.list_comments(int(tid), internal=True)
                  if c.get('ActorType') in (USER_TYPE, WAITING_TYPE) and not is_brief(c)]
    return [(m.group(0).lower(), line) for x in texts for line in x.splitlines() for m in _ADDR.finditer(line)]
def said_by_owner(store, tid=None) -> set: return {a for a, _ in owner_lines(store, tid)}


def resolve(store, name: str) -> dict:
    """{'address'} for exactly one whole-word match, {'candidates': [...]} for several or for partial matches (most
    written-to first), {} for none."""
    name = ' '.join(str(name or '').split())
    if '@' in name: return {'address': name}
    words = _words(name)
    if not words: return {}
    whole, part = {}, {}
    def add(into, a, n, last): into[a] = (into.get(a, (0, ''))[0] + n, max(last, into.get(a, (0, ''))[1]))
    for h in store.senders_like(name, limit=6) if hasattr(store, 'senders_like') else []:
        a, n, last, who = h['Email'], h.get('N') or 1, str(h.get('Last') or ''), h.get('Name') or ''
        add(whole if _whole(words, a, who) else part, a, n, last)
    for a, (n, last) in written_to(store).items():
        if _whole(words, a): add(whole, a, n, last)
        elif _part(words, a): add(part, a, n, last)
    # ...and an address he gave in his own words, beside this name (owner_lines): his word is the surest there is
    for a, line in owner_lines(store):
        if _whole(words, a) or set(words) <= set(_words(line)): add(whole, a, 99, '9999')
    rank = lambda d: [a for a, _ in sorted(d.items(), key=lambda kv: kv[1], reverse=True)]    # most written-to, then newest
    if len(whole) == 1: return {'address': next(iter(whole))}       # one whole-word match outranks fragments of other names
    found = rank(whole) or rank(part)
    # ...AND WHERE THE WHOLE NAME FINDS NOBODY, WHO SHARES A WORD OF IT, offered and never picked (2026-11-17: asked for "Anna Carlini", the
    # bank's contact "Garlanian, Anna" was never offered, and an address was made up, sent and bounced)
    if not found and len(words) > 1:
        some = {}
        for w in (w for w in words if len(w) > 2):
            for h in store.senders_like(w, limit=6) if hasattr(store, 'senders_like') else []:
                if w in _words(h.get('Name') or '') or w in _words(h['Email'].split('@', 1)[0]): add(some, h['Email'], h.get('N') or 1, str(h.get('Last') or ''))
            for a_, (n, last) in written_to(store).items():
                if _whole([w], a_): add(some, a_, n, last)
        found = rank(some)
    return {'candidates': found[:5]} if found else {}


def keys(store, name: str = '', address: str = '') -> set:
    """THE ONE ANSWER TO WHO SOMEONE IS, as keys to compare (walk 6, CLI F9: Paula wrote by chat with a name and no address, so "to:
    paula@northwind.example" found "nobody called that on this task", and Gail was listed twice - by name off her chat, by address off her
    mail). Their address (as given, inside "Name <address>", or the one whole name finds - resolve) and their name, lowercased. Two shapes
    of one person share a key; set() for nobody."""
    raw, a = ' '.join(str(name or '').split()), str(address or '').strip().lower()
    if not a and (m := _ADDR.search(raw)): a, raw = m.group(0).lower(), raw.replace(m.group(0), '').strip(' <>"')
    if not a and raw: a = str(resolve(store, raw).get('address') or '').lower()
    return {k for k in (raw.lower(), a) if k}
