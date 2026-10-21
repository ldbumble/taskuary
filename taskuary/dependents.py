"""What leans on a connection - said on its card beside Remove, before the press (#238).

Remove wipes the card's credentials and settings and switches its sources off (store.reset_connector). What reads through
the card breaks quietly after that: a report or workflow that names it, a brain pointed at it, a card that borrows its
Microsoft app, a reply draft that would leave through it, a rule kept for its mailbox, a playbook whose `uses:` names its
kind. Each is found the way its own reader finds the card, so the line says what Remove would actually break. Remove
still acts at once - this is a line to read, not a question to answer."""
import json

from . import flow, playbooks, reports, settings_schema, workflows

# the settings a brain is picked on, in the words their own pages use (settings_schema labels the rest)
BRAIN_WORDS = {'triage_ai': 'Triage brain', 'triage_backup_ai': 'backup Triage brain', 'concierge_ai': 'Assistant tab brain',
               'assistant_ai': 'General agent brain', 'judge_ai': 'report judge'}
ORDER = ('workflow', 'report', 'brain', 'card', 'draft', 'rule', 'playbook', 'source')


def _cfg(s) -> dict:
    try: return json.loads(s or '{}') or {}
    except (TypeError, ValueError): return {}


def _ids(xs) -> set:
    return {int(x) for x in (xs if isinstance(xs, list) else []) if str(x).strip().isdigit()}


def _reads(cfg: dict, c: dict, default: bool) -> bool:
    """A report card or a step names this connection: by id, on `uses`, or by its type alone - then the type's default
    instance answers it (reports._connector), so only the default is leaned on."""
    if str(cfg.get('connector_id') or '') == str(c['ConnectorId']) or c['ConnectorId'] in _ids(cfg.get('uses')): return True
    t = cfg.get('type')
    return bool(t) and default and not cfg.get('connector_id') and reports.card_of(t) == c['Type']


def _borrowers(store, c: dict) -> list:
    """Cards with no Microsoft app of their own that ride this Outlook card's: Teams by its sign-in, SharePoint and Azure
    by its tenant app (channels.graph_creds, sharepoint_connection, reports.azure_connection)."""
    if c['Type'] != 'outlook': return []
    from .channels import graph_creds
    from .sharepoint import sharepoint_connection
    default = (store.get_connector_by_type('outlook') or {}).get('ConnectorId') == c['ConnectorId']
    out = []
    for o in (x for t in ('teams', 'sharepoint', 'azure') for x in store.connectors_by_type(t, with_secret=True)):
        if not o.get('Active'): continue
        try:
            if o['Type'] == 'teams': gcfg, _, borrowed = graph_creds(store, o); leans = borrowed and gcfg.get('_cid') == c['ConnectorId']
            elif o['Type'] == 'sharepoint': leans = default and sharepoint_connection(store, o['ConnectorId']).get('borrowed') == 'outlook'
            else:
                own = reports._card(store, 'azure', 'client_secret', o['ConnectorId'])
                leans = default and not (own.get('client_id') and own.get('client_secret')) and bool(_cfg(c.get('ConfigJson')).get('client_id'))
        except Exception: leans = False
        if leans: out.append(o.get('Name') or o['Type'])
    return out


def of(store, cid: int) -> list:
    """[{kind, names}] - each kind that leans on the card, in ORDER, with what it is called. Nothing leaning: []."""
    c = store.get_connector(cid)
    if not c: return []
    default = (store.get_connector_by_type(c['Type']) or {}).get('ConnectorId') == cid
    found = {k: [] for k in ORDER}
    srcs = store.list_sources(active_only=False)
    for s in srcs:
        if s.get('Channel') != 'report' or not s.get('Active') or s.get('Owner') == 'template': continue
        cfg = _cfg(s.get('ConfigJson'))
        steps = [x for x in cfg.get('flow') or [] if isinstance(x, dict) and x.get('kind') == 'source']
        if _reads(cfg, c, default) or any(_reads(x, c, default) for x in steps):
            found['workflow' if workflows.is_workflow(s) or flow.is_flow(cfg) else 'report'].append(cfg.get('title') or s.get('Address') or '')
    pick, knobs = f'connector:{cid}', settings_schema.knobs()
    for k, v in store.get_settings().items():
        if pick in {x.strip() for x in str(v or '').split(',')}: found['brain'].append(BRAIN_WORDS.get(k) or (knobs.get(k) or {}).get('label') or k)
    found['card'] = _borrowers(store, c)
    mine = [s for s in srcs if s.get('ConnectorId') == cid and s.get('Channel') != 'report']
    own = {(s.get('Channel'), str(s.get('Address') or '').lower()) for s in mine}
    found['draft'] = ['' for r in store._rows("SELECT m.Channel, m.SourceName FROM review r JOIN message m ON m.MessageId=r.MessageId "
                                              "WHERE r.Status='pending'") if (r['Channel'], str(r['SourceName'] or '').lower()) in own]
    boxes = {a for ch, a in own if ch == 'email' and a}
    found['rule'] = [p['Name'] or '' for p in store._rows('SELECT Name, Mailbox FROM policy WHERE Active=1')
                     if str(p['Mailbox'] or '').lower() in boxes]
    if default: found['playbook'] = [b['title'] for b in playbooks.list_all() if c['Type'] in (b.get('uses') or [])]
    found['source'] = [s.get('Address') or '' for s in mine if s.get('Active')]
    return [{'kind': k, 'names': found[k]} for k in ORDER if found[k]]
