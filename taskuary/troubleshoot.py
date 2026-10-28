"""WHEN THE APP ITSELF IS NOT WORKING, THE CHAT LOOKS INTO IT (the owner, 2026-10-23: "if it can't solve something simply it should not
start fixing the app. it should start inline without task and if it can't solve it create issue on github no? it could restart broken
bridge or explain why something is not working simply. it should not create task for just updating things" - and "if we do that we need
to see what it's thinking like general agent").

Asked "whatsapp isn't working", the Assistant thought for a minute and brought up the WhatsApp card - the bridge's state, its log and the
card's last error were all a read away, and none was read. The MODEL still decides that the words are about the app (no word list), and
calls these: `health` reads what the app knows about one part of itself, `repair` runs the one simple repair that part has (the same
verbs its own card presses: Restart bridge, a sync, Test it) and reads it again. Each read and each press is a STEP - the general agent's
step shape (website/src/agentSteps.js) - drawn in the chat as it happens and kept on the answer. What it found decides the buttons under
the answer, by data: it works now (none), a place that fixes it (that fix, the failure's own button), or neither (Report this bug - the
scrubbed, previewed popup). Never a task, never an agent.
"""
from pathlib import Path
from loguru import logger
from . import appfacts, buttons, redact

SYNC = None                # the server's chat-lane poll for one connector type, set at import (server.py): typ -> added | False
LOG_LINES, LINE = 8, 220
HOW = ('restart_bridge', 'sync', 'test')
SAYS = {'restart_bridge': 'Restarted the WhatsApp bridge', 'sync': 'Synced {name}', 'test': 'Asked {name} again'}
OPEN_CARD = 'Open the connection'      # the connection card's own button (assistantCards.jsx), and where Pair again and Sign in are


def _cut(s, n=LINE) -> str:
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n - 1] + '…'


def step(n: int, kind: str, summary: str, detail: str = '', ok: bool = True) -> dict:
    return {'id': f'trouble-{n}', 'kind': kind, 'summary': _cut(summary, 160), 'detail': redact.scrub(str(detail or ''))[:3000],
            'status': 'done' if ok else 'error'}


def find(store, name: str = '', connector_id=None) -> dict | None:
    """The connection named - by its card's name, then by its type ("whatsapp" for a card the owner renamed)."""
    hit = appfacts.find_connection(store, name, connector_id)
    w = str(name or '').strip().lower()
    return hit or next((c for c in sorted(appfacts.connections(store), key=lambda c: not c['active']) if w and c['type'] == w), None)


def _tail(path: Path, n=LOG_LINES) -> list:
    try:
        with open(path, 'rb') as fh:
            fh.seek(max(0, path.stat().st_size - 16384)); text = fh.read().decode('utf-8', 'replace')
    except OSError: return []
    return [_cut(l) for l in text.splitlines() if l.strip()][-n:]


def _app_log(typ: str) -> list:
    "The app's own log errors that name this connection's type."
    from .lookups import _log_errors
    try: return [_cut(l) for l in _log_errors(40) if typ and typ in l.lower()][-LOG_LINES:]
    except Exception: return []


def _bridge(store, c: dict) -> dict:
    """The WhatsApp bridge this machine runs, asked directly: {up, line, fix, manager, log} - `fix` is the status line's next step."""
    from . import messengers, wabridge
    row = store.get_connector(c['connector_id'], with_secret=True) or {}
    mgr = wabridge.state()
    try: st = messengers.wa_status(row); up = True
    except Exception as e: st, up = {'line': f'not answering - {_cut(e, 160)}', 'fix': 'restart' if wabridge.managed(row) else ''}, False
    return {'up': up, 'line': st.get('line') or '', 'fix': st.get('fix') or '', 'managed': wabridge.managed(row), 'node': bool(wabridge.node()),
            'manager': f"{mgr.get('phase')}{' - ' + mgr['detail'] if mgr.get('detail') else ''}", 'log': _tail(wabridge.log()),
            'admits': (st.get('filter') or {}).get('jids')}


# ONE CHAT, BY ITS NAME (2026-10-28: "the team chat is already connected and messages should be showing up on my feed, but aren't" - the
# Assistant read the card, said "connected, 14 chats", searched the mail for the group's name and found nothing: a group's messages were
# stored as "group chat", never under its name, and nothing said whether THAT group was one of the 14). The roster names it, the card's
# own switch says whether it comes in, and the messages kept from it say where they went - so the answer names the actual cause.
CHATS = "Open WhatsApp's Chats"
SHOWN_CHATS = 4


def chats_href(q: str = '') -> str:
    from urllib.parse import quote
    return '#connector=whatsapp&chats=' + quote(str(q or '').strip())


def _roster(store, c: dict) -> list:
    "The paired account's chats, named - the names kept on the last read when the bridge cannot be asked now."
    from . import messengers, wanames
    try: return messengers.wa_chats(store.get_connector(c['connector_id'], with_secret=True) or {}, store)
    except Exception as e:
        logger.debug(f'troubleshoot: the WhatsApp roster from the names kept - {e}')
        return [{'jid': j, 'name': nm, 'group': wanames.is_group(j)} for j, nm in wanames.names(store).items()]


def _kept(store, jid: str) -> dict:
    "What came in from one chat: {n, today, last, tid, title, status} - the newest message's task is where it shows."
    from datetime import date
    cid = f'whatsapp:{jid}'
    got = store._one("SELECT COUNT(*) n, SUM(SentAt>=?) today, MAX(SentAt) last FROM message WHERE ConversationId=? AND IFNULL(Direction,'in')<>'out'",
                     (date.today().isoformat(), cid)) or {}
    top = store._one('SELECT m.TaskId tid, m.Status mstatus, t.Title title, t.Status status FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId '
                     "WHERE m.ConversationId=? AND IFNULL(m.Direction,'in')<>'out' ORDER BY m.SentAt DESC, m.MessageId DESC LIMIT 1", (cid,)) or {}
    return {'n': int(got.get('n') or 0), 'today': int(got.get('today') or 0), 'last': str(got.get('last') or '')[:16],
            'tid': top.get('tid'), 'title': top.get('title') or '', 'status': top.get('status') or '', 'mstatus': top.get('mstatus') or ''}


def _went(k: dict) -> str:
    "Where the newest message from a chat is: the task it is on, or the lane it was filed in."
    if k['tid']: return f" - the newest is on TQ-{int(k['tid']):04d} \"{k['title']}\" ({'closed' if k['status'] == 'done' else k['status'] or 'open'})"
    return f" - the newest is on no task ({k['mstatus'] or 'waiting for triage'})"


def chat_check(store, c: dict, q: str, n: int = 0, admits=None) -> dict:
    """{ok, why, fix, open, steps}: is the chat called `q` coming in, and if it is, where it went. `admits`: the jids the bridge lets in."""
    from . import wanames
    from .timewords import plural
    q = str(q or '').strip()
    rows = _roster(store, c)
    on = {s['Address']: s for s in store.list_sources(active_only=False) if s.get('Channel') == 'whatsapp' and s.get('Address')}
    fold = wanames._fold
    hits = [r for r in rows if wanames.matches(q, r['jid'], r.get('name'))]
    # the one named exactly first, then the ones that come in - the roster's newest-first order kept within each
    hits.sort(key=lambda r: (fold((r.get('name') or '').strip()) != fold(q), not (on.get(r['jid']) or {}).get('Active')))
    name = lambda r: wanames.label(r['jid'], r.get('name'))
    fix = {'label': CHATS, 'href': chats_href(q if hits else '')}
    if not hits:
        why = f'no chat on this WhatsApp account is called "{q}"' + (f" - it has {plural(len(rows), 'chat')}, none by that name" if rows else '')
        return {'ok': False, 'why': why, 'fix': fix, 'open': None, 'steps': [step(n + 1, 'read', f'Looked for "{q}" in WhatsApp\'s chats: none by that name', ok=False)]}
    live = [r for r in hits if (on.get(r['jid']) or {}).get('Active')]
    off = [r for r in hits if r not in live]
    offs = ', '.join(f'"{name(r)}"' for r in off[:SHOWN_CHATS]) + (f' and {len(off) - SHOWN_CHATS} more' if len(off) > SHOWN_CHATS else '')
    if not live:
        why = (f"{offs} {'is' if len(off) == 1 else 'are'} not switched on under WhatsApp's Chats, so nothing from "
               f"{'it' if len(off) == 1 else 'them'} comes in - switch {'it' if len(off) == 1 else 'the one you mean'} on there")
        return {'ok': False, 'why': why, 'fix': fix, 'open': None,
                'steps': [step(n + 1, 'read', f"Looked for \"{q}\" in WhatsApp's chats: not switched on", why, ok=False)]}
    said, first, ok, repair = [], None, True, ''
    for r in live[:SHOWN_CHATS]:
        k = _kept(store, r['jid'])
        if admits is not None and r['jid'] not in admits:
            said.append(f'"{name(r)}" is switched on, but the bridge has not been told yet - a sync tells it'); ok, repair = False, 'sync'
        elif not k['n']:
            said.append(f'"{name(r)}" is switched on; nothing has come in from it since - a new message there will')
        else:
            said.append(f"\"{name(r)}\" is switched on and coming in: {plural(k['n'], 'message')} kept ({k['today']} today), the last at {k['last']}{_went(k)}")
            first = first or (k['tid'] and {'label': f"Open TQ-{int(k['tid']):04d}", 'href': f"#task={int(k['tid'])}"})
    if off: said.append(f'also by that name, not switched on: {offs}')
    why = '; '.join(said)
    return {'ok': ok, 'why': why, 'fix': None if ok else fix, 'open': first or None, 'repair': repair,
            'steps': [step(n + 1, 'read', f"Looked for \"{q}\" in WhatsApp's chats: {'coming in' if first else 'switched on'}", why, ok=ok)]}


def health(store, name: str = '', connector_id=None, n: int = 0, chat: str = '') -> dict:
    """What the app knows about one connection now: {name, type, cid, ok, why, repair, fix, steps}. `repair` is the simple repair it
    has ('' when none), `fix` the place that fixes it when no repair here can ({label, href}). No name: everything failing (the bell).
    `chat`: one WhatsApp chat by its name - whether it comes in and where it went (chat_check); a name that is no connection's is
    tried as a chat's too, since "the team chat isn't coming in" names the chat, not the card."""
    c = find(store, name, connector_id)
    wa = next((x for x in sorted(appfacts.connections(store), key=lambda x: not x['active']) if x['type'] == 'whatsapp'), None)
    if not c and wa and wa['active'] and (chat or name):
        c, chat = wa, chat or name
    if not c: return _overall(store, name, n)
    steps, typ, nm = [], c['type'], c['name']
    card = {'label': OPEN_CARD, 'href': f'#connector={typ}'}
    sync = f"last sync {c['last_sync'][:16]}" if c['last_sync'] else 'never synced'
    said = 'switched off' if not c['active'] else f"on, {sync}" + (f" - last error: {c['last_error']}" if c['last_error'] else '')
    steps.append(step(n + 1, 'read', f"Checked {nm}: {_cut(said, 110)}", c['last_error'], ok=c['active'] and not c['last_error']))
    out = {'name': nm, 'type': typ, 'cid': c['connector_id'], 'ok': c['active'] and not c['last_error'], 'why': said, 'repair': '', 'fix': None,
           'steps': steps, 'log': []}
    if not c['active']: return {**out, 'why': f'{nm} is switched off', 'fix': card}
    if typ == 'whatsapp':
        b = _bridge(store, c)
        steps.append(step(n + 2, 'read', f"Asked the WhatsApp bridge: {b['line'] or 'no answer'}",
                          '\n'.join([f"manager: {b['manager']}", *b['log']]), ok=b['up'] and not b['fix']))
        out.update(log=b['log'], bridge=b['line'])
        if not b['node']: return {**out, 'ok': False, 'why': 'Node.js, which the bridge runs on, is not installed on this computer', 'fix': card}
        if b['fix'] == 'restart' and b['managed']: return {**out, 'ok': False, 'why': f"the bridge is {b['line'] or 'not answering'}", 'repair': 'restart_bridge'}
        if b['fix'] == 'restart': return {**out, 'ok': False, 'why': 'the bridge runs somewhere else, not on this computer - it is started where it runs', 'fix': card}
        if b['fix'] == 'pair': return {**out, 'ok': False, 'why': f"{b['line']} - the phone has to link it again (Pair again, with the phone in hand)", 'fix': card}
        if not b['up'] or not b['line'].startswith('Connected'): return {**out, 'ok': False, 'why': b['line'] or 'the bridge is not answering', 'fix': card}
        out['ok'] = True
        if c['last_error']: return {**out, 'ok': False, 'why': f"the bridge answers but the last sync failed: {c['last_error']}", 'repair': 'sync'}
        if chat:
            ch = chat_check(store, c, chat, len(steps) + n, b.get('admits'))
            return {**out, 'ok': ch['ok'], 'why': ch['why'], 'fix': ch['fix'], 'open': ch['open'], 'repair': ch.get('repair') or '',
                    'chat': chat, 'steps': steps + ch['steps']}
    logged = _app_log(typ)
    if logged: steps.append(step(len(steps) + n + 1, 'read', f"Read the app's log: {len(logged)} recent error{'s' if len(logged) > 1 else ''} about {nm}",
                                 '\n'.join(logged), ok=False))
    out['log'] = out['log'] or logged
    from . import problems
    full = store.get_connector(c['connector_id']) or {}
    if problems.signed_out({**full, 'Type': typ}):
        return {**out, 'ok': False, 'why': 'Microsoft signed you out - it needs you to sign in again', 'fix': {'label': 'Sign in again', 'href': card['href']}}
    if out['ok'] or typ == 'whatsapp': return out
    # an error on a card nothing here restarts is asked again first (Test it). What that cannot clear is the owner's - a refused sign-in
    # (outbound.auth_fix, the failure shape's own reading), a key never given, a fix the failed test left - or it is ours: a bug report
    from . import failures, outbound
    signin = outbound.auth_fix(RuntimeError(c['last_error']))
    left = (failures.standing(store, 'connector', c['connector_id']) or {}).get('fix')
    fix = {'label': signin['label'], 'href': card['href']} if signin else left if isinstance(left, dict) and left.get('href') else None
    return {**out, 'repair': 'test', 'fix': fix or (card if not c['has_secret'] else None)}


def _overall(store, name: str, n: int) -> dict:
    "No connection by that name: what the bell says is failing, so the model can name the one it meant - or say nothing is."
    from . import problems
    rows = problems.collect(store, all_of_them=True)
    said = '; '.join(f"{p['title']} ({_cut(p['detail'], 120)})" for p in rows[:6]) or 'nothing is failing right now'
    return {'name': name or 'Taskuary', 'type': '', 'cid': None, 'ok': not rows, 'why': said, 'repair': '', 'fix': None, 'log': [],
            'steps': [step(n + 1, 'read', f"Checked what is failing: {len(rows) or 'nothing'}", said, ok=not rows)], 'unknown': bool(name)}


def repair(store, name: str, how: str, n: int = 0, chat: str = '') -> dict:
    """The one simple repair, run - the same verb the connection's card presses - and the connection read again: {..health, did, steps}."""
    h = health(store, name, n=n, chat=chat)
    if not h['cid']: return {**h, 'did': '', 'said': f'There is no connection called {name!r}.'}
    how = how if how in HOW else h['repair']
    # a sync and a test are safe on any connection that is on; a bridge is restarted only where this computer runs it
    if not how or h['why'].endswith('switched off') or (how == 'restart_bridge' and h['repair'] != how):
        return {**h, 'did': '', 'said': f"{h['name']} has no {how or 'repair'} to run here - {h['why']}."}
    # what it read before the press is not drawn twice: the model read it a step ago (app.health), and the press reads it again after
    nm, ok, detail = h['name'], True, ''
    try:
        if how == 'restart_bridge':
            from . import wabridge
            store.audit('connector', h['cid'], 'wa_bridge_restart', 'assistant')
            wabridge.restart(filter_policy=wabridge.filter_policy(store, h['cid']))
            ok = wabridge.wait_listening(25); detail = f"manager: {wabridge.state().get('phase')} {wabridge.state().get('detail') or ''}"
        elif how == 'sync':
            if not SYNC: raise RuntimeError('no sync is wired up here')
            got = SYNC(h['type']); ok = got is not False; detail = f'{got} new' if ok and got else 'nothing new' if ok else 'the sync did not run (busy)'
        from .channels import test_connector
        t = test_connector(store, h['cid'])
        store.audit('connector', h['cid'], 'test_ok' if t['ok'] else 'test_failed', 'assistant', detail=t['detail'])
        ok, detail = ok and t['ok'], '\n'.join(x for x in (detail, t['detail']) if x)
        from . import funnel
        funnel.invalidate()
    except Exception as e:
        logger.warning(f'troubleshoot: {how} on {nm} failed - {e}'); ok, detail = False, str(e)
    after = health(store, name, n=n + 1, chat=chat)
    again = [{**s, 'summary': s['summary'].replace('Checked ', 'Checked again: ', 1) if i == 0 else s['summary']} for i, s in enumerate(after['steps'])]
    return {**after, 'steps': [step(n + 1, 'run', SAYS[how].format(name=nm), detail, ok=ok), *again], 'did': how, 'worked': ok and after['ok']}


def words(h: dict, desk: bool = True) -> str:
    "The result for the model, with what it may do next - never a tool that does not fit. A phone has no buttons: its words say where."
    lines = [f"{h['name']}{' (' + h['type'] + ')' if h['type'] else ''}: {h['why']}"]
    if h.get('bridge'): lines.append(f"bridge: {h['bridge']}")
    if h.get('log'): lines += ['recent log:'] + [f'  {l}' for l in h['log'][-5:]]
    if h.get('said'): lines.append(h['said'])
    if h.get('did'): lines.append(f"you ran {h['did']}: it {'worked' if h.get('worked') else 'did not fix it'}.")
    if h.get('unknown'): lines.append('No connection has that name - those are what is failing. CALL app.health with the right one, or ask which.')
    elif h['ok'] and h.get('chat'): lines.append('That chat is coming in. Say so in a sentence or two - where its messages went, by the task named'
                                               + (' (its button comes up under your answer).' if desk and h.get('open') else '.'))
    elif h['ok']: lines.append('It works now. Say so in one short sentence - what you checked' + (' and what you did.' if h.get('did') else '.'))
    elif h['repair'] and not h.get('did'):
        lines.append(f'A simple repair runs from here: CALL: {{"kind": "app.repair", "params": {{"name": "{h["name"]}", "how": "{h["repair"]}"}}}}')
    elif h['fix']: lines.append('It needs the owner: say plainly why in a sentence or two. '
                                + (f"Its button ({h['fix']['label']}) comes up under your answer." if desk else
                                   f"Say where they press it at their desk: {h['fix']['label']}, on its card under Connections."))
    else: lines.append('Nothing here fixes it: say plainly what is wrong, and that '
                       + (f"{buttons.label('report_bug')}, under your answer," if desk else f"{buttons.label('report_bug')}, at their desk,")
                       + " drafts a report for the app's tracker - they read it before it is sent.")
    return '\n'.join(lines)


def chips(h: dict) -> list:
    """The buttons under the answer, from what was found: none when it works, the fix's own place, else Report this bug - the popup
    drafted from these facts (bugreport scrubs them before the owner sees the draft)."""
    if h and h.get('ok') and h.get('open'): return [{'verb': 'go', 'href': h['open']['href'], 'label': h['open']['label']}]
    if not h or h.get('ok') or h.get('unknown'): return []
    if h.get('fix'): return [{'verb': 'go', 'href': h['fix']['href'], 'label': h['fix']['label']}]
    # ...and a repair the turn named but never ran: the card that holds its button (Restart bridge, Test it)
    if h.get('repair') and not h.get('did'): return [{'verb': 'go', 'href': f"#connector={h['type']}", 'label': OPEN_CARD}]
    return [{'verb': 'bug', 'label': buttons.label('report_bug'),
             'report': {'message': f"{h['name']} is not working: {h['why']}" + ('\n' + '\n'.join(h['log'][-LOG_LINES:]) if h.get('log') else ''),
                        'screen': 'Assistant', 'route': f"connector {h['type']}" if h['type'] else ''}}]
