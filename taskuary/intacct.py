"""Sage Intacct: the XML gateway, as a read connection.

Ported from a working client the owner already had. What came across is the PROTOCOL -
session login, readByQuery with paging, and the object lookup - not the twenty-six per-object
wrapper classes, whose whole content was a hardcoded field list each. Those lists are the thing
that goes stale when Intacct adds a field, and `lookup` already asks the server for the real
one, so a report names the object and the fields it wants and the wrapper layer disappears.

Two calls carry everything:
  query(cfg, object, fields, filters, limit)  -> [ {FIELD: value}, ... ]
  fields_of(cfg, object)                      -> [ {'ID', 'DESCRIPTION', 'DATATYPE'}, ... ]

fields_of is not a convenience. Nobody remembers that a GL entry's amount is AMOUNT but a bill's
is TOTALENTERED, and the composer (see compose.py) hands the field list to the model so a report
written in English is built against the schema this company actually has, custom fields included,
instead of a plausible guess.

Auth is FIVE credentials, which is unusual enough to be worth naming: a sender id and password
identify the integration (issued by Sage to whoever wrote the client), a user id and password
identify the person, and a company id picks the tenant. The first pair is not a second factor on
the second - they authorise different things, and the web login's password is NOT the API user's.
"""
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from loguru import logger

GATEWAY = 'https://api.intacct.com/ia/xml/xmlgw.phtml'
PAGE = 1000                  # Intacct's own cap is 2000; smaller pages fail sooner and pause less
TIMEOUT = 60                 # a wide readByQuery over a year of GL is genuinely slow
SESSION_TTL = 1500           # Sage expires an API session well before an hour; renew at 25 min
CREDS = ('sender_id', 'sender_password', 'user_id', 'user_password', 'company_id')

# '=' is what a person writes; these are what the gateway calls them.
OPS = {'=': 'equalto', '!=': 'notequalto', '>': 'greaterthan', '<': 'lessthan',
       '>=': 'greaterthanorequalto', '<=': 'lessthanorequalto',
       'like': 'like', 'in': 'in', 'isnull': 'isnull', 'isnotnull': 'isnotnull'}

_sessions = {}               # company_id -> (session_id, endpoint, when)


class IntacctError(RuntimeError): pass


def _el(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None: e.text = str(text)
    return e


def _control(root, cfg):
    c = _el(root, 'control')
    _el(c, 'senderid', cfg['sender_id']); _el(c, 'password', cfg['sender_password'])
    _el(c, 'controlid', 'taskuary'); _el(c, 'uniqueid', 'false')
    _el(c, 'dtdversion', '3.0'); _el(c, 'includewhitespace', 'false')
    return c


def _post(url, doc):
    """The endpoint comes back from Sage's own login response, so it is not the owner's URL and
    is not a URL an agent chose either - it is pinned to intacct.com rather than trusted. A
    login that answers with somewhere else is a bug or an attack, and neither should be posted
    credentials."""
    host = (urlparse(url).hostname or '').lower()
    if not (host == 'intacct.com' or host.endswith('.intacct.com')):
        raise IntacctError(f'refusing to post credentials to {host or url} - not a Sage Intacct endpoint')
    body = ET.tostring(doc, encoding='utf-8', xml_declaration=True)
    r = requests.post(url, data=body, headers={'Content-Type': 'application/xml'}, timeout=TIMEOUT)
    r.raise_for_status()
    return ET.fromstring(r.content)


def _check(res):
    """Intacct answers 200 with <status>failure</status>, so the HTTP code says nothing. The
    error text is in description2 and is usually the only clue about what the API user cannot
    see, which makes it worth carrying to the owner verbatim rather than reducing to 'failed'."""
    if 'failure' not in [s.text for s in res.iter('status')]: return
    msgs = [d.text for d in res.iter('description2') if d.text] or \
           [d.text for d in res.iter('description') if d.text]
    raise IntacctError('; '.join(msgs)[:500] or 'Intacct returned failure with no description')


def _missing(cfg): return [k for k in CREDS if not str(cfg.get(k) or '').strip()]


def login(cfg, force=False):
    """(session_id, endpoint), cached per company. Every call after this one rides the session,
    which is the difference between one login and one login per report row."""
    if miss := _missing(cfg):
        raise IntacctError('the Intacct connection is missing ' + ', '.join(miss).replace('_', ' '))
    key = cfg['company_id']
    hit = _sessions.get(key)
    if hit and not force and time.time() - hit[2] < SESSION_TTL: return hit[0], hit[1]

    root = ET.Element('request'); _control(root, cfg)
    op = _el(root, 'operation')
    login_el = _el(_el(op, 'authentication'), 'login')
    _el(login_el, 'userid', cfg['user_id']); _el(login_el, 'companyid', cfg['company_id'])
    _el(login_el, 'password', cfg['user_password'])
    if ent := str(cfg.get('entity_id') or '').strip(): _el(login_el, 'locationid', ent)
    _el(_el(_el(op, 'content'), 'function', controlid='login'), 'getAPISession')

    res = _post(cfg.get('gateway') or GATEWAY, root)
    _check(res)
    sid = res.findtext('.//sessionid')
    end = res.findtext('.//endpoint') or (cfg.get('gateway') or GATEWAY)
    if not sid: raise IntacctError('Intacct accepted the login but returned no session id')
    _sessions[key] = (sid, end, time.time())
    logger.info(f"intacct: session open for company {cfg['company_id']}")
    return sid, end


def _envelope(cfg, sid):
    root = ET.Element('request'); _control(root, cfg)
    op = _el(root, 'operation')
    _el(_el(op, 'authentication'), 'sessionid', sid)
    return root, _el(_el(op, 'content'), 'function', controlid='q')


def _filter_xml(parent, filters):
    """filters = [[FIELD, op, value], ...], ANDed. One condition needs no <and> wrapper and
    Intacct rejects the empty one, so the single case is spelled separately."""
    if not filters: return
    fil = _el(parent, 'filter')
    tgt = _el(fil, 'and') if len(filters) > 1 else fil
    for f in filters:
        field, op, val = (list(f) + [None])[:3]
        name = OPS.get(str(op).strip().lower())
        if not name: raise IntacctError(f'unknown filter operator {op!r} - use one of {", ".join(OPS)}')
        cond = _el(tgt, name)
        _el(cond, 'field', field)
        if name == 'in':
            for v in (val if isinstance(val, (list, tuple)) else [val]): _el(cond, 'value', v)
        elif name not in ('isnull', 'isnotnull'):
            _el(cond, 'value', val)


def _rows(res, tag='data'):
    data = next(res.iter(tag), None)
    return [{c.tag: (c.text or '') for c in rec} for rec in list(data or [])]


def query(cfg, obj, fields=None, filters=None, limit=PAGE, order=None):
    """readByQuery, paged until `limit` is reached. Fields default to every one the object has,
    because a report asking for 'the vendor list' should not have to know that vendors carry
    forty columns - and asking Intacct is cheaper than being wrong about it."""
    sid, end = login(cfg)
    fields = list(fields or [])
    out, offset = [], 0
    while len(out) < limit:
        root, fn = _envelope(cfg, sid)
        q = _el(fn, 'query')
        _el(q, 'object', obj)
        sel = _el(q, 'select')
        for f in (fields or ['*']): _el(sel, 'field', f)
        _filter_xml(q, filters)
        if order:
            o = _el(q, 'orderby')
            for f, d in order: _el(_el(o, 'descending' if str(d).lower().startswith('desc') else 'ascending'), 'field', f)
        page = min(PAGE, limit - len(out))
        _el(q, 'pagesize', page); _el(q, 'offset', offset)
        opts = _el(q, 'options'); _el(opts, 'showprivate', 'true'); _el(opts, 'returnformat', 'xml')

        res = _post(end, root)
        _check(res)
        batch = _rows(res)
        out.extend(batch)
        data = next(res.iter('data'), None)
        remaining = int((data.get('numremaining') or 0) if data is not None else 0)
        # both conditions matter: a short page means the server ran out, numremaining means it
        # says so. Trusting only the second loops forever on an object that omits the attribute.
        if not batch or len(batch) < page or remaining <= 0: break
        offset += len(batch)
    return out[:limit]


def fields_of(cfg, obj):
    """What this company's copy of the object actually has, custom fields included. This is the
    call that lets someone write a report in English and get one built against the real schema."""
    sid, end = login(cfg)
    root, fn = _envelope(cfg, sid)
    _el(_el(fn, 'lookup'), 'object', obj)
    res = _post(end, root)
    _check(res)
    return [{'ID': f.findtext('ID') or '', 'LABEL': f.findtext('LABEL') or '',
             'DATATYPE': f.findtext('DATATYPE') or ''}
            for f in res.iter('Field')]


def probe(cfg):
    """One real call for the Test button: log in, then read the company's own record. A green
    card that only proves the password was accepted hides the usual failure, which is an API
    user with no permission on anything worth reading."""
    sid, end = login(cfg, force=True)
    try: n = len(query(cfg, 'LOCATION', ['LOCATIONID', 'NAME'], limit=50))
    except IntacctError as e: return f'login OK for {cfg["company_id"]}, but reads are refused: {e}'
    return f'login OK for {cfg["company_id"]} · {n} location(s) readable · session {sid[:8]}…'
