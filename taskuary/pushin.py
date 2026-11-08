"""THE VENDORS THAT ONLY PUSH: LINE's Messaging API (webhook-only - there is no way to ask it for messages) and SendGrid Inbound Parse
(it posts each mail it receives). Mailgun is not here: it keeps what it receives and Taskuary polls it (inboxes.items_mailgun).

A PUBLIC ADDRESS IS THE OWNER'S. Taskuary listens on this computer and builds no relay or tunnel of its own (the share listener is LAN-only),
so the card says plainly that the vendor needs an https address reaching this port - the owner's own tunnel (cloudflared, ngrok) - and
names the path to put after it. server._outside_door lets exactly these paths through the Host check; nothing else on the port answers
under the tunnel's name, so the page that carries the owner token never does.

EACH PUSH PROVES ITSELF before a byte of it is kept:
  LINE      X-Line-Signature: base64 HMAC-SHA256 of the raw body, keyed by the channel secret (write-only on the card).
  SendGrid  a random key in the path, minted for the card and shown to the owner only; and, when the card holds the security policy's
            public key, the ECDSA signature over timestamp + body (X-Twilio-Email-Event-Webhook-Signature / -Timestamp).
What passes is QUEUED, not filed: the next sync drains the queue through the shared source road (inboxes.poll, `drained`), so a push is
triaged like any poll and an answer to the vendor never waits on a model.
"""
import base64, hashlib, hmac, json, secrets, time

KINDS = ('line', 'sendgrid')
MAX = 200                       # queued pushes per card: a flood the sync has not drained is not kept without end


class Refused(Exception): pass


def _tables(store):
    with store.lock:
        store.cx.execute('CREATE TABLE IF NOT EXISTS push_inbox (PushId INTEGER PRIMARY KEY, ConnectorId INTEGER, Body TEXT, At REAL)')
        store.cx.commit()


def _conf(c) -> dict:
    try: return json.loads(c.get('ConfigJson') or '{}') or {}
    except ValueError: return {}


def path(store, c) -> str:
    "The path after the owner's public address. SendGrid's carries the card's key, minted the first time it is asked for."
    if c['Type'] == 'line': return f"/api/inbound/line/{c['ConnectorId']}"
    key = _conf(c).get('inbound_key') or secrets.token_urlsafe(24)
    store.merge_connector_config(c['ConnectorId'], {'inbound_key': key})
    return f"/api/inbound/sendgrid/{c['ConnectorId']}/{key}"


def _line(c, conf, key, h, body, form) -> list:
    sec = str(conf.get('channel_secret') or '')
    if not sec: raise Refused('this LINE card has no channel secret, so nothing can be checked')
    want = base64.b64encode(hmac.new(sec.encode(), body, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(want, h.get('x-line-signature') or ''): raise Refused('the LINE signature does not match')
    try: ev = json.loads(body or b'{}').get('events') or []
    except ValueError: raise Refused('not a LINE webhook body')
    return [e for e in ev if e.get('type') == 'message' and e.get('mode', 'active') == 'active']


def _ecdsa_ok(pub: str, sig: str, ts: str, body: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError: raise Refused('the card holds a verification key, and this computer lacks the cryptography package to check it')
    try: serialization.load_der_public_key(base64.b64decode(pub)).verify(base64.b64decode(sig), ts.encode() + body, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError): return False
    return True


def _sendgrid(c, conf, key, h, body, form) -> list:
    if not (conf.get('inbound_key') and hmac.compare_digest(str(conf['inbound_key']), str(key or ''))): raise Refused('not this card\'s address')
    if (pub := conf.get('verify_key')) and not _ecdsa_ok(pub, h.get('x-twilio-email-event-webhook-signature') or '',
                                                         h.get('x-twilio-email-event-webhook-timestamp') or '', body):
        raise Refused('the SendGrid signature does not match')
    f = form or {}
    if not (f.get('from') or f.get('subject')): return []
    mid = next((l.split(':', 1)[1].strip() for l in str(f.get('headers') or '').splitlines() if l.lower().startswith('message-id:')), '')
    return [{k: str(f.get(k) or '')[:50000] for k in ('from', 'to', 'subject', 'text', 'html')} | {'message_id': mid, 'at': time.time()}]


READ = {'line': _line, 'sendgrid': _sendgrid}


def take(store, kind, cid, key, headers, body: bytes, form=None) -> int:
    "Check one push and queue what it carries. Refused: the vendor is told 403 and nothing is kept."
    c = store.get_connector(int(cid), with_secret=True)
    if kind not in READ or not c or c['Type'] != kind or not c.get('Active'): raise Refused('no such card, or it is switched off')
    got = READ[kind](c, _conf(c), key, {str(k).lower(): v for k, v in (headers or {}).items()}, body or b'', form)
    _tables(store)
    for x in got: store._exec('INSERT INTO push_inbox (ConnectorId, Body, At) VALUES (?,?,?)', (c['ConnectorId'], json.dumps(x), time.time()))
    store._exec('DELETE FROM push_inbox WHERE ConnectorId=? AND PushId NOT IN (SELECT PushId FROM push_inbox WHERE ConnectorId=? '
                'ORDER BY PushId DESC LIMIT ?)', (c['ConnectorId'], c['ConnectorId'], MAX))
    return len(got)


def drain(store, c) -> list:
    "What was pushed since the last sync, oldest first - handed over once and gone."
    _tables(store)
    rows = store._rows('SELECT PushId, Body FROM push_inbox WHERE ConnectorId=? ORDER BY PushId', (c['ConnectorId'],))
    if rows: store._exec(f"DELETE FROM push_inbox WHERE PushId IN ({','.join('?' * len(rows))})", [r['PushId'] for r in rows])
    return [json.loads(r['Body']) for r in rows]
