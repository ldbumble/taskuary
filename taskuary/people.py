"""A name becomes an address from the owner's own mail (docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

"Send an email to Gail" needs Gail's address. The look-up only knew people who had WRITTEN IN; someone the owner only
ever wrote to, or copied, was nobody. This searches both. Recipients are stored as bare addresses (channels._addrs), so
a name meets them through the address itself - every word of it in the local part (gail.moreno@), or initial + surname
(gmoreno@). One person is the answer; several are offered, never picked; none is nothing - nobody is guessed.
"""
import json, re

SCAN = 3000                  # the owner's sent mail read for recipients, newest first


def _words(name: str) -> list: return [w for w in re.findall(r'[a-z]+', str(name or '').lower()) if len(w) > 1]


def _fits(words: list, address: str) -> bool:
    local = re.sub(r'[^a-z]', '', address.split('@', 1)[0].lower())
    if not words or not local: return False
    return all(w in local for w in words) or (len(words) > 1 and local.startswith(words[0][0] + words[-1]))


def written_to(store) -> dict:
    """{address: (times, last sent)} over the To and Cc of the owner's own sent mail."""
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
    return seen


def resolve(store, name: str) -> dict:
    """{'address'} for exactly one person, {'candidates': [...]} for several (most written-to first), {} for none."""
    name = ' '.join(str(name or '').split())
    if '@' in name: return {'address': name}
    words = _words(name)
    if not words: return {}
    hits = {}
    for h in store.senders_like(name, limit=6) if hasattr(store, 'senders_like') else []:
        hits[h['Email']] = (h.get('N') or 1, str(h.get('Last') or ''))
    for a, (n, last) in written_to(store).items():
        if _fits(words, a): hits[a] = (hits.get(a, (0, ''))[0] + n, max(last, hits.get(a, (0, ''))[1]))
    if not hits: return {}
    ranked = [a for a, _ in sorted(hits.items(), key=lambda kv: kv[1], reverse=True)]     # most written-to, then newest
    return {'address': ranked[0]} if len(ranked) == 1 else {'candidates': ranked[:5]}
