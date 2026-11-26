"""WHAT A CARD'S HARNESS SENDS LEAVES THROUGH TASKUARY (the owner, 2026-11-26: SSNs and dates of birth masked "in everything that reaches the
model, including files the agent opens itself" - and nothing added to the gateway). A card's agent is the Codex CLI or OpenCode (harness.py),
and a file it reads with its own shell rode straight to the card's endpoint in the CLI's next request, past every door redact.py shuts.

So the harness is pointed HERE, a door on Taskuary's own server (server.card_relay), and this sends each request on to the card's endpoint
with its body scrubbed by the one mask (redact.scrub_body) and hands the answer back as it comes, byte for byte, stream and all.

It is no open proxy: it answers this computer alone (the route), a caller holding the card's own relay token (token) - which is what the
harness is handed in place of the card's key, so the key never enters the CLI's process at all - and it sends only to the address the
card's own calls go to (llm.endpoint), with the key from the store. A body it cannot read (compressed, not text) is refused, never sent."""
import asyncio, hashlib, hmac, json, secrets
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from . import redact

_OWN = secrets.token_bytes(32)          # keys the token where the server has none of its own (guard._key): this run's alone
# ITS OWN THREADS, NEVER THE APP'S: a request is held for as long as its model thinks (WAIT), and on the server's shared pool of forty a
# few agents streaming at once would leave no thread for a page's own reads. One per request in flight; past ROOM a request waits its turn
ROOM = 64
_POOL = ThreadPoolExecutor(max_workers=ROOM, thread_name_prefix='taskuary-relay')
WAIT = (15, 900)                        # seconds to connect, and between two bytes of an answer - a model thinking is not a dead line
# what is the connection's own, the caller's sign-in, or says how a body was packed: never carried across
_NOT_SENT = {'host', 'authorization', 'content-length', 'accept-encoding', 'connection', 'transfer-encoding', 'keep-alive', 'cookie',
             'x-taskuary-token', 'proxy-authorization', 'upgrade', 'te'}
_NOT_BACK = {'content-length', 'content-encoding', 'transfer-encoding', 'connection', 'keep-alive', 'set-cookie'}


def token(server: dict, cid) -> str:
    "What a card's harness signs in to the relay with: the server's own key over the card it is for - that card's road, nothing else."
    from . import guard
    return f'r1.{int(cid)}.' + hmac.new(guard._key(server, 'card relay') or _OWN, f'card:{int(cid)}'.encode(), hashlib.sha256).hexdigest()


def base(server: dict, cid) -> str:
    """The address a card's harness is pointed at: this server, on this computer - loopback wherever the server listens there (every
    address, or a loopback one), else the one address it is bound to, which the door takes from this computer alone (here)."""
    h = str(server.get('host') or '').strip()
    if h in ('0.0.0.0', '::', '') or h.lower() == 'localhost': h = '127.0.0.1'
    return f'http://{f"[{h}]" if ":" in h else h}:{server.get("port") or 7787}/relay/card-{int(cid)}'


def here(client: str, bound: str) -> bool:
    """Is the caller this computer: a loopback address, or - where the server listens on one address of its own and no loopback - that
    very address, which only a connection made on this computer comes from."""
    import ipaddress
    c = str(client or '').split('%')[0]
    try: return ipaddress.ip_address(c).is_loopback or (bool(bound) and ipaddress.ip_address(c) == ipaddress.ip_address(str(bound).split('%')[0]))
    except ValueError: return False


def signed(server: dict, cid, headers) -> bool:
    a = str((headers or {}).get('authorization') or '')
    from . import guard
    return a[:7].lower() == 'bearer ' and guard.token_matches(a[7:].strip(), token(server, cid))


def masked(body: bytes, headers) -> tuple:
    "(the body as it may leave, how many of its strings changed). ValueError where it cannot be read - it is then not sent."
    if not body: return body, 0
    if (enc := str((headers or {}).get('content-encoding') or '').strip().lower()) not in ('', 'identity'):
        raise ValueError(f'a body packed as {enc} cannot be read here - send it as it is')
    try: text = body.decode('utf-8')
    except UnicodeDecodeError: raise ValueError('a body that is not text cannot be read here') from None
    hits = []
    try: out = json.dumps(redact.scrub_body(json.loads(text), hits), ensure_ascii=False, separators=(',', ':'))
    except ValueError: out = redact.scrub(text); hits += [''] * (out != text)
    return (out.encode('utf-8'), len(hits)) if hits else (body, 0)       # nothing to take out: the caller's own bytes go


def _said(status: int, line: str) -> tuple:
    "A refusal in the shape both CLIs read an endpoint's own error in."
    return status, {'content-type': 'application/json'}, iter([json.dumps({'error': {'message': line, 'type': 'taskuary_relay', 'code': status}}).encode()]), lambda: None


def send(store, cid: int, method: str, path: str, query: str, headers, body: bytes) -> tuple:
    """(status, headers, the answer's bytes as they arrive, what closes it) of one request sent on to card `cid`'s own endpoint, masked.
    The address and the key are the card's, read here - nothing the caller sent chooses where this goes."""
    import requests
    from . import harness
    if harness._card(store, f'connector:{int(cid)}') is None: return _said(404, 'This AI card is off or has no key - turn it on under Connections.')
    if '..' in path.split('/'): return _said(400, 'That address is not one this card answers.')
    t, cfg, key = harness._cfg(store, cid)
    try: to, header, extra, _ = harness._provider(t, cfg)
    except (RuntimeError, ValueError) as e: return _said(502, str(e))
    try: out, n = masked(body, headers)
    except ValueError as e:
        logger.warning(f'relay: card {cid} {method} /{path} not sent - {e}')
        return _said(415, f'Taskuary did not send this: {e}.')
    h = {k: v for k, v in headers.items() if k.lower() not in _NOT_SENT and k.lower() != header.lower()}
    h.update(extra); h['Accept-Encoding'] = 'identity'                    # the answer comes as its own bytes, and goes back as them
    if header: h[header] = key
    elif key: h['Authorization'] = f'Bearer {key}'
    try: r = requests.request(method, f'{to}/{path}' + (f'?{query}' if query else ''), headers=h, data=out or None, stream=True,
                              timeout=WAIT, allow_redirects=False)        # ...a redirect would carry the key to another address
    except requests.RequestException as e:
        logger.warning(f'relay: card {cid} {method} /{path} - its endpoint did not answer ({type(e).__name__})')
        return _said(502, "This AI card's address did not answer. Check the address on its card, then try again.")
    logger.info(f'relay: card {cid} {method} /{path} -> {r.status_code}, {n} masked')

    return r.status_code, {k: v for k, v in r.headers.items() if k.lower() not in _NOT_BACK}, r.iter_content(chunk_size=None), r.close


async def ask(*a) -> tuple:
    "send, for the server's loop: (status, headers, the answer as it arrives) - the request and every read of its answer on the relay's own threads."
    loop = asyncio.get_running_loop()
    status, headers, it, close = await loop.run_in_executor(_POOL, send, *a)

    async def chunks():
        # ...closed from here whichever way it ends - the answer's end, or a caller that hung up while a read still waits on its thread
        try:
            while (c := await loop.run_in_executor(_POOL, next, it, None)) is not None: yield c
        finally: close()
    return status, headers, chunks()
