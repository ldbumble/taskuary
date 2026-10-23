"""Leaving a mailing list, on the owner's press and never without it.

A list says how to leave it in its own headers: RFC 2369's List-Unsubscribe names a mailto: and/or a web link, and RFC 8058's
List-Unsubscribe-Post: List-Unsubscribe=One-Click says the https one may be POSTed to with no page in between. `parse` reads both
at ingest (channels._header_marks, imapmail.protocol_marks) into the row's MailMetaJson `unsub`; `run` is the FYI card's
Unsubscribe (buttons.json): the one-click POST where the list offers it, else the link for the owner to finish on (the owner,
2026-10-22: Unsubscribe on FYI, picked from the gaps). Parsing, not reading - no subject or body word ever offers it.
"""
import json, re
from loguru import logger

_LINK = re.compile(r'<\s*([^>\s]+)\s*>')
ONE_CLICK = 'List-Unsubscribe=One-Click'


def parse(h) -> dict | None:
    """{'via': 'post'|'url'|'mailto', 'url'?, 'mailto'?} from a mail's headers (any case-insensitive .get(name)), else None.
    `post` only for an https link the list said takes the one-click POST - RFC 8058 allows nothing else."""
    links = _LINK.findall(' '.join(str(h.get('List-Unsubscribe') or '').split()))
    url = next((u for u in links if u.lower().startswith('https://')), None) or next((u for u in links if u.lower().startswith('http://')), None)
    mail = next((u for u in links if u.lower().startswith('mailto:')), None)
    if not (url or mail): return None
    post = bool(url and url.lower().startswith('https://')) and ONE_CLICK.lower() in ''.join(str(h.get('List-Unsubscribe-Post') or '').split()).lower()
    return {'via': 'post' if post else 'url' if url else 'mailto', **({'url': url[:2000]} if url else {}), **({'mailto': mail[:500]} if mail else {})}


def of(row: dict | None) -> dict | None:
    "The `unsub` ingest stored on a message row (its MailMetaJson), or None."
    try: u = (json.loads((row or {}).get('MailMetaJson') or '{}') or {}).get('unsub')
    except (TypeError, ValueError): return None
    return u if isinstance(u, dict) and u.get('via') in ('post', 'url', 'mailto') else None


def _post(url: str):
    """The RFC 8058 POST. Every hop of a link a stranger wrote is checked first (webguard): the POST leaves from the owner's
    machine, and a list that names a loopback or metadata address would otherwise reach the owner's own network. No redirect is
    followed - RFC 8058 says the sender must not answer with one."""
    import requests
    from . import webguard
    webguard.check_url(url)
    return requests.post(url, data={'List-Unsubscribe': 'One-Click'}, timeout=20, allow_redirects=False)


def run(store, mid: int, actor: str = 'owner') -> dict:
    """The owner pressed Unsubscribe on message `mid`. One-click: POSTed here, {'via': 'post'}. Otherwise {'via': 'url'|'mailto',
    'link'} - the page or the mail is the owner's to finish, so nothing is claimed done that the list has not confirmed.
    Raises LookupError when the row offers no way off, RuntimeError when the list refused the POST."""
    m = store.get_message(int(mid))
    u = of(m)
    if not u: raise LookupError('this message names no way to unsubscribe')
    if u['via'] == 'post':
        r = _post(u['url'])
        if not (200 <= int(getattr(r, 'status_code', 0) or 0) < 300): raise RuntimeError(f'the list answered {getattr(r, "status_code", "nothing")} - it did not take the unsubscribe')
        out = {'via': 'post'}
    else: out = {'via': u['via'], 'link': u.get('url') or u.get('mailto')}
    from .store import _now
    # the press is kept on the row, so the button is not offered on it again and the "is it working?" numbers can count it
    store._exec("UPDATE message SET MailMetaJson=json_set(IFNULL(MailMetaJson, '{}'), '$.unsub.done', ?) WHERE MessageId=?", (_now(), int(mid)))
    try: store.audit('message', int(mid), 'unsubscribe', actor, detail={'via': out['via']})
    except Exception as e: logger.warning(f'unsubscribe on {mid}: not audited - {e}')
    return out
