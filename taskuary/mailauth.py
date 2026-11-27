"""Did the receiving server verify the From address? (RFC 8601 Authentication-Results, DMARC/DKIM.)

A From header is the sender's own claim: anyone can type a colleague's address, or the owner's own domain, into it.
The receiving server's Authentication-Results is the evidence. verdict() reads it to 'pass', 'fail' or 'none'.

Trust is asymmetric: a sender can write their own Authentication-Results header into the mail before it is sent, and
the receiving server adds its result on TOP. So a fail counts wherever it appears (forging one gains nothing), but a
pass counts only from the RECEIVING server (RFC 8601 s.5: a result is believed only from an authserv-id the reader knows
is its own): the top-most Received header's `by` host - the hop the receiving server wrote as it took the mail in - and
only its own top-most stamp, with that exact authserv-id, among the headers ABOVE that hop: headers are prepended, so what stands
below the receiver's own Received may be the sender's typing, its id included (round 6), and reads as nothing.
A server that stamps nothing leaves the sender's own header as the top-most one (the red team, 2026-11-24: a typed
'dmarc=pass' read as verified), and no longer passes; nor does a typed id of a SIBLING host of the receiver's own
organisation (round 4: `mail.<its domain>` under `by mx.<its domain>` read as the receiver's word). A nameless
result (Exchange Online writes none) is Exchange's word only on a Graph read; an ARC-Authentication-Results counts
only from the receiving organisation too. Exchange's own X-MS-Exchange-Organization-AuthAs
is stripped from mail arriving from outside, so Internal there is the organisation's word - on a Graph read only:
over IMAP the header is just text, and the server that would have stripped it may not be Exchange."""
import email.message, email.utils, re

_DMARC_FAIL = {'fail', 'quarantine', 'reject'}


def _pairs(headers) -> list:
    "[(lower name, value)] from a Message, a dict (value or list), [(name, value)] or Graph's [{name, value}]."
    if headers is None: return []
    if isinstance(headers, email.message.Message): return [(k.lower(), str(v)) for k, v in headers.items()]
    if isinstance(headers, dict):
        return [(k.lower(), str(x)) for k, v in headers.items() for x in (v if isinstance(v, (list, tuple)) else [v])]
    out = []
    for h in headers:
        if isinstance(h, dict) and h.get('name'): out.append((str(h['name']).lower(), str(h.get('value') or '')))
        elif isinstance(h, (list, tuple)) and len(h) == 2: out.append((str(h[0]).lower(), str(h[1])))
    return out


def _uncomment(s: str) -> str:
    "Unfold, and drop (comments) - nested ones too - in one pass: a hostile header must not cost quadratic time."
    out, depth = [], 0
    for ch in re.sub(r'\r?\n[ \t]+', ' ', s):
        if ch == '(': depth += 1
        elif ch == ')' and depth:
            depth -= 1
            if not depth: out.append(' ')
        elif not depth: out.append(ch)
    return ''.join(out)


def parse(value: str, arc: bool = False) -> tuple:
    "(authserv-id, [(method, result, {prop: value})]) for one Authentication-Results value."
    segs = [x.strip() for x in _uncomment(value).split(';')]
    if arc and segs and re.fullmatch(r'i\s*=\s*\d+', segs[0], re.I): segs = segs[1:]
    sid = ''
    if segs and '=' not in segs[0]: sid = segs.pop(0).split()[0].lower() if segs[0].split() else ''
    res = []
    for s in segs:
        m = re.match(r'([a-z0-9_-]+)\s*=\s*([a-z0-9_-]+)', s, re.I)
        if not m: continue
        props = {k.lower(): v.strip('"').lower() for k, v in re.findall(r'([a-z]+\.[a-z0-9_-]+)\s*=\s*("[^"]*"|[^\s;]+)', s[m.end():], re.I)}
        res.append((m[1].lower(), m[2].lower(), props))
    return sid, res


def _aligned(d: str, frm: str) -> bool:
    "Relaxed alignment: the signing domain is the From domain, or one is a subdomain of the other (never a bare TLD)."
    if not (d and frm and '.' in d and '.' in frm): return False
    return d == frm or frm.endswith('.' + d) or d.endswith('.' + frm)


def org_domain(dom: str) -> str:
    "The organisation's own domain under a mail host: mail.aiprovider.example -> aiprovider.example; a country's co.uk kept whole."
    p = (dom or '').lower().strip('.').split('.')
    return '.'.join(p[-3:] if len(p) > 2 and len(p[-1]) == 2 and len(p[-2]) <= 3 else p[-2:])


_BY = re.compile(r'\bby\s+([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b', re.I)

def _by(v: str) -> str: return m[1].lower().rstrip('.') if (m := _BY.search(_uncomment(v))) else ''
def _own(hs) -> tuple:
    """(the host that took the mail in, the headers it wrote on top of that): the top-most Received naming its `by` host, and only what
    stands ABOVE it. A header is prepended, so nothing a sender typed can be above the hop the receiver wrote as it took the mail in -
    and everything below it can be (red team round 6: a typed result under the receiver's own id, below its Received, on a server that
    stamps nothing). A hop on top with no `from` and no host (Gmail's own hand-over names only an IP) is passed over; one that took the
    mail FROM someone and names no host is nobody this can name, and what a sender typed below it is never read as the receiver's."""
    for i, (k, v) in enumerate(hs):
        if k != 'received': continue
        if (h := _by(v)): return h, hs[:i]
        if re.match(r'\s*from\b', _uncomment(v), re.I): break
    return '', []


def _stamp(own: list, rcv: str, name: str) -> list:
    "The receiving host's own top-most `name` result - its exact authserv-id, among the headers it wrote (_own) - [] where it wrote none."
    return next((rs for k, v in own if k == name for sid, rs in [parse(v, arc=name != 'authentication-results')] if rcv and sid == rcv), [])


def verdict(headers, internal: bool = False) -> str:
    """'pass', 'fail' or 'none' for a mail's raw headers (see the module docstring for what counts). `internal`: a Graph read, where
    Exchange itself wrote the headers - its nameless top result and its X-MS-Exchange-Organization-AuthAs are its word."""
    hs = _pairs(headers)
    frm = email.utils.parseaddr(next((v for k, v in hs if k == 'from'), ''))[1]
    dom = frm.rsplit('@', 1)[-1].strip().lower() if '@' in frm else ''
    ars = [parse(v) for k, v in hs if k == 'authentication-results']
    rcv, own = _own(hs)
    arc = _stamp(own, rcv, 'arc-authentication-results')
    trusted = _stamp(own, rcv, 'authentication-results') + arc + (ars[0][1] if internal and ars and not ars[0][0] else [])
    every = [r for _, rs in ars for r in rs] + arc
    if internal and any(k == 'x-ms-exchange-organization-authas' and v.strip().lower() == 'internal' for k, v in hs): return 'pass'
    if any(m == 'dmarc' and v == 'pass' for m, v, _ in trusted): return 'pass'
    if any(m == 'dkim' and v == 'pass' and _aligned(p.get('header.d', ''), dom) for m, v, p in trusted): return 'pass'
    # Exchange's composite verdict outranks its raw DMARC: reason 130 is an ARC rescue of forwarded or list mail
    if any(m == 'compauth' and v == 'pass' for m, v, _ in trusted): return 'none'
    if any(m == 'dmarc' and v in _DMARC_FAIL for m, v, _ in every): return 'fail'
    if any(m == 'dkim' and v == 'fail' and _aligned(p.get('header.d', ''), dom) for m, v, p in every): return 'fail'
    return 'none'
