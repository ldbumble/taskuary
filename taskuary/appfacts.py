"""What the assistant knows about the APP - every report and workflow, setting, connection, agent
and brain - read off the tables the tabs read, never typed in.

Asked from WhatsApp to "run me the AR report", the assistant had no list of reports at all: it knew
the pile and nothing else (the owner, 2026-09-18). This is the STATE block that rides every turn of
the general road (concierge.say), and the finders the look-ups use (concierge.read_op). It writes
nothing and asks no model anything - and it rides in none of the scripts (walk.py, the composer),
which reach no model to begin with.
"""
import json
from . import settings_schema

# the deterministic roads, by the names the owner says (spec: "Scripts"). Static on purpose: a script
# is the same every time and needs no model, so its name and its promise are shipped, not computed.
SCRIPTS = [('walk me through my tasks', 'Next through the pile, one item at a time - the core'),
           ('set up Taskuary', 'the tour of the app, stop by stop; from a chat it opens on your connections'),
           ('set up a report', 'describe a check or a workflow in your words and the composer builds it')]


def _cfg(src) -> dict:
    try: return json.loads(src.get('ConfigJson') or '{}') or {}
    except ValueError: return {}


def reports(store) -> list:
    """Every report and workflow with its clock, its reach and its last outcome. `last_ok` is None for
    a report that never ran - unknown is not failed."""
    from . import reports as rep, workflows
    out = []
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        cfg = _cfg(src)
        runs = store.report_runs(src['SourceId'], 1) or []
        last = runs[0] if runs else None
        out.append({'source_id': src['SourceId'], 'title': cfg.get('title') or src.get('Address') or '',
                    'workflow': bool(workflows.is_workflow(cfg)), 'schedule': rep.schedule_words(cfg), 'reach': rep.reach_of(cfg),
                    'active': bool(src.get('Active')), 'last_at': str((last or {}).get('at') or ''),
                    'last_ok': (not last.get('failed')) if last else None,
                    'last_said': str((last or {}).get('error') or (last or {}).get('summary') or (last or {}).get('said') or '')[:200]})
    return out


def settings(store) -> list:
    """Every knob the schema names, with its value in the schema's words. Keys the schema does not
    know (bookkeeping: ingest_status, per-task cursors) are not settings and are left out."""
    vals, out = store.get_settings(), []
    for key, meta in settings_schema.knobs().items():
        v = vals.get(key, '')
        out.append({'key': key, 'group': meta['group'], 'label': meta['label'], 'type': meta['type'], 'value': str(v or ''),
                    'said': settings_schema.describe(key, v)})
    return out


def connections(store) -> list:
    return [{'connector_id': c['ConnectorId'], 'type': c.get('Type') or '', 'name': c.get('Name') or c.get('Type') or '',
             'active': bool(c.get('Active')), 'has_secret': bool(c.get('HasSecret')),
             'last_sync': str(c.get('LastSyncAt') or ''), 'last_error': str(c.get('LastError') or '')[:200]}
            for c in store.list_connectors()]


def agents(store) -> list:
    return [{'name': a['Name'], 'kind': a.get('Kind') or '', 'active': bool(a.get('Active', 1))}
            for a in store.list_agents(active_only=False)]


def brains(store) -> list:
    """'triage brain: Azure OpenAI' for each brain slot - the words walk._brain_name already resolves."""
    from .aidefaults import SLOTS
    from .walk import _brain_name
    st = store.get_settings()
    return [f"{s['label'].lower()}: {_brain_name(store, st.get(s['key']))}" for s in SLOTS]


def _match(rows, want: str, field: str, id_field: str, id_val):
    """id wins when given; otherwise case-insensitive containment on the name - the rule report.read
    already used, kept in one place."""
    if id_val is not None and str(id_val).strip():
        hit = next((r for r in rows if str(r[id_field]) == str(id_val).strip()), None)
        if hit: return hit
    w = (want or '').strip().lower()
    return next((r for r in rows if w and w in str(r[field]).lower()), None) if w else None


def _live_first(rows): return sorted(rows, key=lambda r: not r['active'])     # "mailbox" means the one that is on, not the catalogue's IMAP card


def find_report(store, title: str = '', source_id=None): return _match(_live_first(reports(store)), title, 'title', 'source_id', source_id)
def find_connection(store, name: str = '', connector_id=None): return _match(_live_first(connections(store)), name, 'name', 'connector_id', connector_id)


def state_block(store, cap: int = 2500) -> str:
    """Counts and names first; detail is the look-ups' job. Capped so a turn stays quick - past the
    cap a family says how many more there are and which look-up has them."""
    reps = reports(store); wfs = [r for r in reps if r['workflow']]; plain = [r for r in reps if not r['workflow']]
    # the connector table holds the whole CATALOGUE from first launch (82 cards, most never switched
    # on), so "connections" means the live ones; the rest are a count, or the block is a card list
    conns = connections(store); live = [c for c in conns if c['active']]; off = len(conns) - len(live)
    def named(rows, f, n=12, more='reports.list'):
        names = [f(r) for r in rows[:n]]
        if len(rows) > n: names.append(f'+{len(rows) - n} more - {more} has them all')
        return '; '.join(names) if names else 'none'
    def rep_line(r): return r['title'] + ('' if r['active'] else ' (off)') + (' - last run failed' if r['last_ok'] is False else '')
    def con_line(c): return c['name'] + (' - erroring' if c['last_error'] else '') + ('' if c['has_secret'] or c['type'] in ('imap', 'ollama') else ' (no key yet)')
    lines = ['THE APP RIGHT NOW (read from its own tables; look things up by name for detail)',
             f"  {len(plain)} report{'s' if len(plain) != 1 else ''}: {named(plain, rep_line)}",
             f"  {len(wfs)} workflow{'s' if len(wfs) != 1 else ''}: {named(wfs, rep_line)}",
             f"  {len(live)} connected: {named(live, con_line, more='connections.list')}" + (f"; {off} catalogue cards off" if off else ''),
             f"  agents: {', '.join(a['name'] for a in agents(store)) or 'none'} | brains: {'; '.join(brains(store))}",
             f"  settings: {len(settings_schema.knobs())} knobs in groups {', '.join(settings_schema.GROUPS)} - "
             'setting.read <key or label> says one, settings.list <group> a group',
             '  scripts you can start by name: ' + '; '.join(f'"{n}" - {what}' for n, what in SCRIPTS)]
    out = '\n'.join(lines)
    return out if len(out) <= cap else out[:cap - 1] + '…'
