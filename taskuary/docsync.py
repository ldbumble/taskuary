"""Operator-doc automation: the docs are the agents' constitution, so connector changes
write themselves in. Two mechanisms, both non-destructive to hand-written prose:
- a marker-fenced 'Connected systems' block in SOUL.md, rebuilt on every connector/source
  change (only the fenced block is touched);
- the GitHub repository map: discovery only ADDS lines for
  repos missing from the doc, so per-repo notes the owner wrote are preserved.
"""
import json

CONN_START, CONN_END = '<!-- connections:start -->', '<!-- connections:end -->'
REPO_MAP_HEADER = '## Repository map'
CH2SRC = {'outlook': 'email', 'teams': 'teams', 'slack': 'slack', 'github': 'github',
          'telegram': 'telegram', 'whatsapp': 'whatsapp', 'gmail': 'email', 'imap': 'email',
          'jira': 'jira', 'asana': 'asana', 'monday': 'monday'}


# The tool blurb used to say "create/update things in it as the work needs" - and an agent
# handed that read it as licence to open a GitHub issue for every task it worked, duplicating
# a tracker that already exists. The licence now follows the agent_issues_enabled setting.
ROLE_TEXT = {'trigger': 'inbound trigger — new items land on the timeline and go through triage',
             'report': 'scheduled report source'}
TOOL_TEXT = {'0': 'yours to read, and to create/update things in ONLY when the task explicitly '
                  'asks for it — never issues or tracker items for your own work: the task is the record',
             '1': 'yours to use — read from it and create/update things in it as the work needs'}

def role_text(store, role):
    if role == 'tool': return TOOL_TEXT['1' if store.github_permissions()[0] else '0']
    return ROLE_TEXT.get(role)


def sync_connections(store, actor='system'):
    from .store import roles_of
    doc = store.get_doc('soul') or ''
    if CONN_START not in doc or CONN_END not in doc: return
    srcs = store.list_sources()
    lines = []
    for c in store.list_connectors():
        if not c['Active']: continue
        mine = [s['Address'] for s in srcs
                if s['Channel'] == CH2SRC.get(c['Type']) and s['Active']
                and (s.get('ConnectorId') in (None, c['ConnectorId']))]
        # what each connection IS to the agents, not just that it exists
        what = '; '.join(role_text(store, r) for r in ('trigger', 'tool', 'report') if r in roles_of(c))
        if mine: lines.append(f"- {c['Name']}: {', '.join(sorted(mine)[:12])}" + (f" — {what}" if what else ''))
        elif what: lines.append(f"- {c['Name']} — {what}")
    for s in srcs:
        if s['Channel'] != 'report' or not s['Active']: continue
        cfg = json.loads(s.get('ConfigJson') or '{}')
        sched = ('on startup' if cfg.get('on_startup')
                 else f"cron {cfg['cron']}" if cfg.get('cron')
                 else f"every {cfg['every_minutes']}m" if cfg.get('every_minutes')
                 else f"daily {cfg.get('daily_at', '')}".strip())
        lines.append(f"- Report \"{cfg.get('title') or s['Address']}\" ({cfg.get('type', 'rest')}, {sched})")
    # the tool role is only real if the agents know how to reach it - spell out the call
    if any('tool' in roles_of(c) for c in store.list_connectors() if c['Active']):
        from . import config
        srv = config.load().get('server') or {}
        auth = ' (header X-Taskuary-Token)' if srv.get('token') else ''
        lines.append(f"- To USE one of the systems above, POST http://{srv.get('host', '127.0.0.1')}:{srv.get('port', 7787)}"
                     '/api/tools/run{auth} with {"type": "mssql|database|aws|s3_object|cloudwatch_logs|'
                     'azure|azure_blob|azure_logs|winrm|mcp|rest|sqlite|rss", ...} — '
                     'saved credentials are filled in for you; the raw output comes back.'.replace('{auth}', auth))
    block = '\n'.join(lines) or '_(no connections yet — add them in the Connectors tab)_'
    head, rest = doc.split(CONN_START, 1)
    _, tail = rest.split(CONN_END, 1)
    new = f'{head}{CONN_START}\n{block}\n{CONN_END}{tail}'
    if new != doc: store.save_doc('soul', new, actor)


def _readme_blurb(tok, repo, llm) -> str:
    """No GitHub description? Read the repo's README instead - AI one-liner when an AI
    connector is up, else the first real prose line."""
    try:
        from .github import readme_text
        txt = readme_text(tok, repo)
    except Exception:
        txt = ''
    if not txt.strip(): return ''
    if llm:
        try:
            return (llm('You describe codebases for a routing table. ONE plain sentence, <25 words, '
                        'no markdown: what the repository is and does.',
                        f'Repository {repo} README:\n\n{txt[:5000]}') or '').strip().splitlines()[0][:200]
        except Exception:
            pass
    lines = [l.strip() for l in txt.splitlines()
             if l.strip() and not l.startswith(('#', '!', '[', '<', '|', '-', '='))]
    return lines[0][:160] if lines else ''


def update_repo_map(store, repos: list, actor='github', tok=None, llm=None):
    """repos: [{full_name, description, archived}] - append unknown repos under the map
    header in SOUL.md so EVERY agent knows which repo owns what. Repos without a GitHub
    description get summarized from their README (AI one-liner when available)."""
    doc = store.get_doc('soul') or ''
    have = doc.lower()
    PLACEHOLDER = 'no description on GitHub - fill me in'
    def _desc(r):
        return ((r.get('description') or '').strip()
                or (tok and _readme_blurb(tok, r['full_name'], llm))
                or PLACEHOLDER)
    # re-discovery heals earlier placeholder lines once a README summary is available
    healed = False
    for r in repos:
        old = f"- **{r['full_name']}**: {PLACEHOLDER}"
        if old in doc:
            d = _desc(r)
            if d != PLACEHOLDER: doc, healed = doc.replace(old, f"- **{r['full_name']}**: {d}"), True
    adds = [f"- **{r['full_name']}**: {_desc(r)}"
            + (' (archived - do not touch)' if r.get('archived') else '')
            for r in repos if r['full_name'].lower() not in have]
    if not adds:
        if healed: store.save_doc('soul', doc, actor)
        return
    if REPO_MAP_HEADER in doc:
        head, rest = doc.split(REPO_MAP_HEADER, 1)
        doc = head + REPO_MAP_HEADER + rest.rstrip() + '\n' + '\n'.join(adds) + '\n'
    else:
        doc = (doc.rstrip() + f'\n\n{REPO_MAP_HEADER}\n'
               'Route each coding task to the repo whose purpose matches; when unsure, escalate.\n'
               + '\n'.join(adds) + '\n')
    store.save_doc('soul', doc, actor)
