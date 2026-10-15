"""Did the receiving server verify the From address? (RFC 8601 Authentication-Results, DMARC/DKIM.)

A From header is the sender's own claim: anyone can type a colleague's address, or the owner's own domain, into it.
The receiving server's Authentication-Results is the evidence. verdict() reads it to 'pass', 'fail' or 'none'.

Trust is asymmetric: a sender can write their own Authentication-Results header into the mail before it is sent, and
the receiving server adds its result on TOP. So a fail counts wherever it appears (forging one gains nothing), but a
pass counts only from the topmost result's server - the authserv-id of the first Authentication-Results - and an
ARC-Authentication-Results only when that same server sealed it. Exchange's own X-MS-Exchange-Organization-AuthAs
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


def verdict(headers, internal: bool = False) -> str:
    """'pass', 'fail' or 'none' for a mail's raw headers (see the module docstring for what counts). `internal` honours
    Exchange's X-MS-Exchange-Organization-AuthAs, which only a Graph read can vouch Exchange itself wrote."""
    hs = _pairs(headers)
    frm = email.utils.parseaddr(next((v for k, v in hs if k == 'from'), ''))[1]
    dom = frm.rsplit('@', 1)[-1].strip().lower() if '@' in frm else ''
    ars = [parse(v) for k, v in hs if k == 'authentication-results']
    arcs = [parse(v, arc=True) for k, v in hs if k == 'arc-authentication-results']
    top = ars[0][0] if ars else None
    # a nameless top (Exchange Online writes none) vouches for itself alone: any sender can write a nameless one below it
    mine = [rs for i, (sid, rs) in enumerate(ars) if i == 0 or (top and sid == top)] + [rs for sid, rs in arcs if top and sid == top]
    trusted = [r for rs in mine for r in rs]
    every = [r for _, rs in ars for r in rs] + [r for sid, rs in arcs if top and sid == top for r in rs]
    if internal and any(k == 'x-ms-exchange-organization-authas' and v.strip().lower() == 'internal' for k, v in hs): return 'pass'
    if any(m == 'dmarc' and v == 'pass' for m, v, _ in trusted): return 'pass'
    if any(m == 'dkim' and v == 'pass' and _aligned(p.get('header.d', ''), dom) for m, v, p in trusted): return 'pass'
    # Exchange's composite verdict outranks its raw DMARC: reason 130 is an ARC rescue of forwarded or list mail
    if any(m == 'compauth' and v == 'pass' for m, v, _ in trusted): return 'none'
    if any(m == 'dmarc' and v in _DMARC_FAIL for m, v, _ in every): return 'fail'
    if any(m == 'dkim' and v == 'fail' and _aligned(p.get('header.d', ''), dom) for m, v, p in every): return 'fail'
    return 'none'
