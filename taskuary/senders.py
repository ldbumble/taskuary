"""Is this someone the owner already deals with?

The one place a stranger's text turns into an agent on the owner's machine with nobody in
between is the coding agent's auto-start. Every comparable tool gates that on the SENDER -
OpenClaw pairs unknown DMs, Copilot ignores users without write access, and this codebase
already does it for GitHub (GH_AUTO) - and email had no such gate. Now it does: a first-time
sender outside the owner's own domains still gets triaged and filed, the task still lands on
the Board; only the automatic session start waits for the owner's click.

"First-time" cannot mean "first time in Taskuary's table": the table starts on the day the
mailbox was connected, and someone the owner has written to weekly for three years would look
like a stranger. So the deep check asks the mailbox itself - has the owner ever SENT this
address anything (Sent Items, one search) - and it runs only for the rare message that reaches
the auto-start decision, once per address: from then on the table knows them.

Chat senders (Teams, Slack, ...) are already inside a workspace the owner controls; the gate
is email only.
"""
import json
from loguru import logger

_SENT_FOLDERS = ('[Gmail]/Sent Mail', 'Sent', 'Sent Items', 'INBOX.Sent', 'Sent Messages')


def _domain(addr: str) -> str: return (addr or '').rsplit('@', 1)[-1].strip().lower() if '@' in (addr or '') else ''


def own_domains(store) -> set:
    """The owner's domains: every connected mailbox, plus the owner's address in settings/SOUL.md."""
    ds = {_domain(s.get('Address')) for s in store.list_sources(active_only=False) if s.get('Channel') == 'email'}
    ds.add(_domain((store.owner() or {}).get('owner_email')))
    return ds - {''}


def known(store, msg: dict, exclude_mid=None, deep: bool = False) -> tuple:
    """(is_known, why). Cheap first - channel, own domain, our own table - and the mailbox
    lookup only when asked (deep) and nothing cheaper answered."""
    if (msg.get('channel') or '') != 'email': return True, 'not email'
    addr = (msg.get('from_email') or '').strip().lower()
    if not addr or '@' not in addr: return False, 'no sender address'
    if _domain(addr) in own_domains(store): return True, 'your own domain'
    if store.known_sender(addr, exclude_mid): return True, 'has written before'
    if deep and wrote_to(store, msg.get('source_name'), addr): return True, 'in your Sent Items'
    return False, f'first message from {addr}'


def wrote_to(store, mailbox: str, addr: str) -> bool:
    """Has THIS mailbox ever sent addr anything? Asked of the mail server that holds the
    history Taskuary does not. Any failure is 'no' - an agent not starting is recoverable."""
    if not (mailbox and addr): return False
    src = next((s for s in store.list_sources(active_only=False)
                if s.get('Channel') == 'email' and (s.get('Address') or '').lower() == mailbox.lower()), None)
    c = store.get_connector(src['ConnectorId'], with_secret=True) if src and src.get('ConnectorId') else None
    if not c: return False
    try:
        if c['Type'] == 'outlook': return _graph_wrote_to(c, mailbox, addr)
        if c['Type'] in ('gmail', 'imap'): return _imap_wrote_to(c, addr)
    except Exception as e:
        logger.warning(f'could not check Sent Items of {mailbox} for {addr}: {e}')
    return False


def _graph_wrote_to(c, mailbox, addr) -> bool:
    import requests
    from .channels import graph_token, GRAPH
    cfg = {**json.loads(c.get('ConfigJson') or '{}'), '_cid': c['ConnectorId']}
    tok = graph_token(cfg, c.get('Secret'))
    r = requests.get(f'{GRAPH}/users/{mailbox}/mailFolders/sentitems/messages', timeout=20,
                     headers={'Authorization': f'Bearer {tok}'}, params={'$search': f'"to:{addr}"', '$top': 1, '$select': 'id'})
    r.raise_for_status()
    return bool(r.json().get('value'))


def _imap_wrote_to(c, addr) -> bool:
    from .imapmail import _login
    M, _user = _login(c)
    try:
        for f in _SENT_FOLDERS:
            typ, _ = M.select(f'"{f}"', readonly=True)
            if typ != 'OK': continue
            typ, data = M.search(None, 'TO', f'"{addr}"')
            return typ == 'OK' and bool(data and data[0])
    finally:
        try: M.logout()
        except Exception: pass
    return False
