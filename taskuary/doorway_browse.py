"""The phone doorway's half of the canvas redesign (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md).

The desktop's sidebar walks the rail by SECTION and browses Connections and Settings as sections -> list -> one, all by
clicks. A WhatsApp or Telegram chat has no sidebar, so the same steps arrive as numbered picks (remote_assistant.run_act):
"Walk FYI" walks that section and Next stays inside it until it is empty, then says so; "Connections" lists the
catalogue's groups, a group lists its cards, a card opens as text with its state and the way back. Nothing here asks a
model - a pick is a button (remote_assistant.run_act). What the rail calls a section is funnel.level_of's to say.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import funnel

SECTION_KEY = 'remote_section'          # {section, seen} while a section is being walked in one chat
WALKED = ('task', 'later', 'reports', 'ideas', 'fyi')   # the sections a chat offers to walk - agents working are not walked


def section_rows(items: list) -> list:
    """'Walk <section>' picks for every section the rail holds right now, in the rail's order."""
    have = {funnel.level_of(i) for i in items or [] if not i.get('settling')}
    return [(f'Walk {funnel.SECTION_WORDS[s]}', {'t': 'section', 'section': s}) for s in WALKED if s in have]


def _key(chat: dict) -> str: return f"{SECTION_KEY}:{chat.get('channel')}:{chat.get('chat')}"


def _now() -> datetime: return datetime.now()


def held(store, chat: dict | None) -> dict | None:
    """The section this chat is walking - over once it is older than the quiet hours: a walk abandoned in the morning
    must not capture a Next days later (the final review)."""
    if not chat: return None
    try: v = json.loads(store.get_setting(_key(chat)) or 'null')
    except ValueError: return None
    if not (isinstance(v, dict) and v.get('section')): return None
    from .processing_unread import return_minutes
    try: at = datetime.fromisoformat(str(v.get('at') or ''))
    except ValueError: return None
    return v if _now() - at <= timedelta(minutes=return_minutes(store)) else None


def hold(store, chat: dict | None, section: str | None, seen=()):
    if chat: store.set_setting(_key(chat), json.dumps({'section': section, 'seen': list(seen), 'at': _now().isoformat(timespec='seconds')})
                               if section else '', 'assistant')


def next_in(store, section: str, seen) -> dict | None:
    return funnel.section_next((funnel.pile(store) or {}).get('items') or [], section, seen=seen)


# ── browsing Connections and Settings, as numbered picks ─────────────────────────────────────────────────────────
def _connected(store) -> dict:
    """{type: 'connected' | 'off' | 'failing' | 'not connected'} - the card's state, said the way the desktop card says it."""
    out = {}
    for c in store.list_connectors() or []:
        t = c.get('Type')
        state = 'failing' if c.get('LastError') else 'connected' if c.get('Active') and (c.get('HasSecret') or c.get('LastSyncAt') or c.get('Secret')) \
            else 'off' if not c.get('Active') else 'not connected'
        if out.get(t) != 'connected': out[t] = state
    return out


def browse(store, area: str, section: str = None, open_: str = None) -> tuple[str, list]:
    """(what to say, the picks under it) for one browse step. Back is always a pick; so is the way up."""
    if area == 'connections': return _connections(store, section, open_)
    if area == 'settings': return _settings(store, section, open_)
    return f'I cannot browse {area} here yet - it is on the desktop.', []


def _connections(store, section, open_):
    from . import connectorcatalog
    cards = [c for c in connectorcatalog.cards() if c.get('group')]
    state = _connected(store)
    groups = []
    for c in cards:
        if c['group'] not in groups: groups.append(c['group'])
    up = [('Back to Connections', {'t': 'browse', 'area': 'connections'})]
    if open_:
        c = connectorcatalog.by_type(open_) or {'title': open_, 'desc': ''}
        said = state.get(open_) or ('planned' if c.get('planned') else 'not connected')
        text = f"{c['title']} - {said}.\n{c.get('desc') or ''}".strip()
        text += '\n\nSay "set it up" and I walk you through it, or open it on the desktop to fill it in.' if said != 'connected' else ''
        return text, [(f'Back to {section}', {'t': 'browse', 'area': 'connections', 'section': section})] + up if section else up
    if section:
        rows = [c for c in cards if c['group'] == section]
        lines = [f"· {c['title']} - {state.get(c['type']) or ('planned' if c.get('planned') else 'not connected')}" for c in rows]
        picks = [(c['title'], {'t': 'browse', 'area': 'connections', 'section': section, 'open': c['type']}) for c in rows if not c.get('planned')]
        return f"CONNECTIONS · {section.upper()} · {len(rows)}\n" + '\n'.join(lines), picks[:12] + up
    on = sum(1 for v in state.values() if v == 'connected')
    lines = [f"{g} · {sum(1 for c in cards if c['group'] == g)}" for g in groups]
    return (f'Connections - {on} connected. Pick a section:\n' + '\n'.join(f'· {x}' for x in lines),
            [(g, {'t': 'browse', 'area': 'connections', 'section': g}) for g in groups])


def _schema() -> dict:
    return json.loads((Path(__file__).with_name('settings_schema.json')).read_text(encoding='utf-8'))


def _settings(store, section, open_):
    schema, st = _schema(), store.get_settings()
    knobs = schema.get('knobs') or {}
    up = [('Back to Settings', {'t': 'browse', 'area': 'settings'})]
    def value(k):
        v = st.get(k)
        kind = (knobs.get(k) or {}).get('type')
        if kind == 'switch': return 'on' if str(v if v is not None else '1').strip() not in ('0', 'false', 'off', '') else 'off'
        return str(v) if v not in (None, '') else '(not set)'
    if open_:
        m = knobs.get(open_) or {'label': open_}
        text = f"{m.get('label') or open_}\n{m.get('desc') or ''}\nnow: {value(open_)}".strip()
        text += '\n\nSay what it should be and I propose the change for your yes.'
        return text, [(f'Back to {section}', {'t': 'browse', 'area': 'settings', 'section': section})] + up if section else up
    if section:
        rows = [(k, m) for k, m in knobs.items() if m.get('group') == section]
        lines = [f"· {m.get('label') or k}: {value(k)}" for k, m in rows]
        return (f"SETTINGS · {section.upper()}\n" + ('\n'.join(lines) or 'Its controls are on the desktop.'),
                [(m.get('label') or k, {'t': 'browse', 'area': 'settings', 'section': section, 'open': k}) for k, m in rows][:12] + up)
    groups = [g for g in schema.get('groups') or [] if any(m.get('group') == g for m in knobs.values())]
    return ('Settings - pick a section:\n' + '\n'.join(f'· {g}' for g in groups),
            [(g, {'t': 'browse', 'area': 'settings', 'section': g}) for g in groups])
