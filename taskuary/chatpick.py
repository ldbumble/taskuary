"""THE CHAT PICKER'S LIST: every chat on one connection a picker can offer, named, newest first (the owner, 2026-11-06, on Agent
channels: "it's just the code not the same as whatsapp dropdown. why is it not the same code with dropdown above").

One list for every picker on Settings > Phone & chats and the task's "Talk to this agent from…": the Assistant chat takes the rows
the owner is alone in (`mine`, remote_assistant.candidates); an agent channel takes any of them, with the ones it cannot bind marked
and the reason given (agentchannels.choices).

Where each list comes from:
  whatsapp  the paired account's roster over the bridge (messengers.wa_chats) - every chat and group it still belongs to
  telegram  the chats the bot has seen (a bot cannot be asked for its chats; the poller writes "discovered: <title>" for each)
  slack     the conversations the token is a member of (users.conversations) - the only ones its poll can read
  teams     the signed-in person's own chats (Graph /me/chats)
...and, on every channel, the chats Taskuary already holds messages from. A live list that will not answer (bridge restarting, token
refused) leaves the seen ones: the page has to render, and a picker that goes empty on a hiccup reads as "you have no chats".

Row: {to, name, kind: 'you'|'direct'|'group', people, mine, hint}. `kind` 'you' is a chat only the owner is in - their "Message
yourself" thread, or a WhatsApp group with nobody else in it, which is the one the agent-channel tip asks them to make.
"""
from loguru import logger

KINDS = ('whatsapp', 'telegram', 'slack', 'teams')


def connector(store, kind: str, cid=None):
    "The switched-on connection of that kind (that one, when `cid` names it), with its secret."
    cs = [c for c in (store.connectors_by_type(kind, with_secret=True) or []) if c and c.get('Active')]
    return next((c for c in cs if not cid or c['ConnectorId'] == int(cid)), None)


def _row(to, name='', kind='direct', people=None, mine=False, hint='', last=''):
    return {'to': str(to), 'name': name or str(to), 'kind': kind, 'people': people, 'mine': bool(mine), 'hint': hint, '_last': str(last or '')}


def _whatsapp(store, c) -> list:
    from . import messengers, remote_assistant, wanames
    rows, guide = messengers.wa_chats(c, store), remote_assistant.chat_of(c)
    me, out = messengers.wa_self_number(store, c), []
    for r in rows:
        mine, n, grp = remote_assistant.own_thread(store, c, r, guide), r.get('people'), bool(r.get('group'))
        solo = (grp and mine) or (not grp and bool(me) and r['jid'].split('@')[0].split(':')[0] == me)
        kind = 'you' if solo else 'group' if grp else 'direct'
        out.append({**_row(r['jid'], wanames.label(r['jid'], r.get('name')), kind, n, mine, r.get('phone') or '', r.get('last')),
                    'phone': r.get('phone') or ''})
    return out


def _telegram(store, c) -> list:
    out = []
    for s in store.list_sources(active_only=False):
        if (s.get('Channel') or '') != 'telegram' or (s.get('ConnectorId') not in (None, c['ConnectorId'])): continue
        cid = str(s.get('Address') or '').strip()
        if not cid or cid == '*' or not cid.lstrip('-').isdigit(): continue
        name = str(s.get('Owner') or '')
        # Telegram gives groups, supergroups and channels a NEGATIVE id and a person a positive one - the one thing a name cannot fake
        grp = cid.startswith('-')
        out.append(_row(cid, name.split(':', 1)[1].strip() if name.startswith('discovered:') else cid, 'group' if grp else 'direct', mine=not grp))
    return out


def _slack(store, c) -> list:
    from .channels import _slack as call
    out, cur = [], ''
    for _ in range(5):
        j = call(c.get('Secret') or '', 'users.conversations', types='public_channel,private_channel,mpim', exclude_archived='true', limit=200,
                 **({'cursor': cur} if cur else {}))
        for x in j.get('channels') or []:
            mp = bool(x.get('is_mpim'))
            out.append(_row(x['id'], ('group DM ' if mp else '#') + str(x.get('name') or x['id']), 'group', x.get('num_members'),
                            hint='private channel' if x.get('is_private') and not mp else ''))
        if not (cur := (j.get('response_metadata') or {}).get('next_cursor') or ''): break
    return out


def _teams(store, c) -> list:
    import requests
    from .channels import GRAPH
    from .outbound import _graph_token
    tok = _graph_token(store, 'teams', c['ConnectorId'])
    r = requests.get(f'{GRAPH}/me/chats', headers={'Authorization': f'Bearer {tok}'}, timeout=20, params={'$top': 50, '$expand': 'members'})
    r.raise_for_status()
    me = str(store.owner().get('owner') or '').strip().lower()
    out = []
    for x in r.json().get('value', []):
        ms = [m.get('displayName') or '' for m in x.get('members') or []]
        others = [m for m in ms if m and m.strip().lower() != me]
        grp = (x.get('chatType') or '') != 'oneOnOne'
        out.append(_row(x['id'], x.get('topic') or ', '.join(others[:4]) or 'Teams chat', 'group' if grp else 'direct', len(ms) or None,
                        last=x.get('lastUpdatedDateTime')))
    return out


LIVE = {'whatsapp': _whatsapp, 'telegram': _telegram, 'slack': _slack, 'teams': _teams}


def chats(store, kind: str, c=None) -> list:
    "Every chat on this connection, live list first then the ones Taskuary has seen, one row per chat, newest first."
    kind = str(kind or '').lower()
    if kind not in KINDS: raise ValueError(f"the channel is one of: {', '.join(KINDS)}")
    c = c or connector(store, kind)
    if not c: return []
    try: rows = LIVE[kind](store, c)
    except Exception as e:
        logger.debug(f'{kind}: the live chat list did not answer - the seen chats stand in: {e}'); rows = []
    by = {r['to']: r for r in rows}
    from .outbound import _chat_id
    for r in store.chats(None):
        if (r.get('Channel') or '').lower() != kind: continue
        to = _chat_id(kind, r.get('Cid'))
        if not to or to in by or kind == 'telegram': continue      # Telegram: the sources above are the seen chats, ids and all
        grp = to.endswith('@g.us') or (kind == 'teams' and '@thread' in to) or (kind == 'slack' and to[:1] in 'CG')
        by[to] = _row(to, r.get('Name') or to, 'group' if grp else 'direct', last=r.get('Last'))
    if kind == 'whatsapp':
        from . import wanames
        for r in by.values(): r['name'] = wanames.label(r['to'], '' if r['name'] == r['to'] else r['name'])
    live = {r['to'] for r in rows}
    out = list(by.values())
    # the live list keeps its own order (it is the roster's newest first); the seen ones follow it, newest first
    out = [r for r in out if r['to'] in live] + sorted((r for r in out if r['to'] not in live), key=lambda r: r['_last'], reverse=True)
    return [{k: v for k, v in r.items() if not k.startswith('_')} for r in out]
