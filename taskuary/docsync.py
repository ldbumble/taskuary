"""Operator-doc automation: the docs are the agents' constitution, so connector changes
write themselves in. Two mechanisms, both non-destructive to hand-written prose:
- a marker-fenced 'Connected systems' block in SOUL.md, rebuilt on every connector/source
  change (only the fenced block is touched);
- the GitHub repository map (FanApp's update_repo_map): discovery only ADDS lines for
  repos missing from the doc, so per-repo notes the owner wrote are preserved.
"""
import json

CONN_START, CONN_END = '<!-- connections:start -->', '<!-- connections:end -->'
REPO_MAP_HEADER = '## Repository map'
CH2SRC = {'outlook': 'email', 'teams': 'teams', 'slack': 'slack', 'github': 'github'}


def sync_connections(store, actor='system'):
    doc = store.get_doc('soul') or ''
    if CONN_START not in doc or CONN_END not in doc: return
    srcs = store.list_sources()
    lines = []
    for c in store.list_connectors():
        mine = [s['Address'] for s in srcs
                if s['Channel'] == CH2SRC.get(c['Type']) and s['Active']
                and (s.get('ConnectorId') in (None, c['ConnectorId']))]
        if c['Active'] and mine: lines.append(f"- {c['Name']}: {', '.join(sorted(mine)[:12])}")
    for s in srcs:
        if s['Channel'] != 'report' or not s['Active']: continue
        cfg = json.loads(s.get('ConfigJson') or '{}')
        sched = f"every {cfg['every_minutes']}m" if cfg.get('every_minutes') else f"daily {cfg.get('daily_at', '')}".strip()
        lines.append(f"- Report \"{cfg.get('title') or s['Address']}\" ({cfg.get('type', 'rest')}, {sched})")
    block = '\n'.join(lines) or '_(no connections yet — add them in the Connectors tab)_'
    head, rest = doc.split(CONN_START, 1)
    _, tail = rest.split(CONN_END, 1)
    new = f'{head}{CONN_START}\n{block}\n{CONN_END}{tail}'
    if new != doc: store.save_doc('soul', new, actor)


def update_repo_map(store, repos: list, actor='github'):
    """repos: [{full_name, description, archived}] - append unknown repos under the map
    header in SOUL.md so EVERY agent knows which repo owns what."""
    doc = store.get_doc('soul') or ''
    have = doc.lower()
    adds = [f"- **{r['full_name']}**: {(r.get('description') or '').strip() or 'no description on GitHub - fill me in'}"
            + (' (archived - do not touch)' if r.get('archived') else '')
            for r in repos if r['full_name'].lower() not in have]
    if not adds: return
    if REPO_MAP_HEADER in doc:
        head, rest = doc.split(REPO_MAP_HEADER, 1)
        doc = head + REPO_MAP_HEADER + rest.rstrip() + '\n' + '\n'.join(adds) + '\n'
    else:
        doc = (doc.rstrip() + f'\n\n{REPO_MAP_HEADER}\n'
               'Route each coding task to the repo whose purpose matches; when unsure, escalate.\n'
               + '\n'.join(adds) + '\n')
    store.save_doc('soul', doc, actor)
