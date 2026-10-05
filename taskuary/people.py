"""A name becomes an address from the owner's own mail (docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

"Send an email to Gail" needs Gail's address. The look-up only knew people who had WRITTEN IN; someone the owner only
ever wrote to, or copied, was nobody. This searches both. Recipients are stored as bare addresses (channels._addrs), so
a name meets them through the address itself. Only a WHOLE-WORD match can fill an address - every word of the name a
word of the address (gail.moreno@) or initial + surname (gmoreno@); "Ray" inside murray.jones@ is only offered, never
filled. One person is the answer; several are offered; none is nothing - nobody is guessed.
"""
import json, re

SCAN = 3000                  # the owner's sent mail read for recipients, newest first
_SENT = {}                   # id(store) -> (newest MessageId, {address: (times, last)}): rescanned only when mail arrives


def _words(text: str) -> list: return [w for w in re.findall(r'[a-z]+', str(text or '').lower()) if len(w) > 1]


def _whole(words: list, address: str, name: str = '') -> bool:
    local = address.split('@', 1)[0].lower()
    have = set(_words(local)) | set(_words(name))
    return bool(words) and (set(words) <= have or (len(words) > 1 and re.sub(r'[^a-z]', '', local) == words[0][0] + words[-1]))


def _part(words: list, address: str, name: str = '') -> bool:
    hay = re.sub(r'[^a-z]', '', address.split('@', 1)[0].lower()) + ' ' + str(name or '').lower()
    return bool(words) and all(w in hay for w in words)


def written_to(store) -> dict:
    """{address: (times, last sent)} over the To and Cc of the owner's own sent mail - one scan per new message."""
    with store.lock: newest = store.cx.execute('SELECT MAX(MessageId) FROM message').fetchone()[0]
    held = _SENT.get(id(store))
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
    _SENT[id(store)] = (newest, seen)
    return seen


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
    rank = lambda d: [a for a, _ in sorted(d.items(), key=lambda kv: kv[1], reverse=True)]    # most written-to, then newest
    if len(whole) == 1: return {'address': next(iter(whole))}       # one whole-word match outranks fragments of other names
    found = rank(whole) or rank(part)
    return {'candidates': found[:5]} if found else {}
