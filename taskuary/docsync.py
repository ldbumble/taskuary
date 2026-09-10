"""Operator-doc automation: the docs are the agents' constitution, so connector changes
write themselves in. Two mechanisms, both non-destructive to hand-written prose:
- a marker-fenced 'Connected systems' block in SOUL.md, rebuilt on every connector/source
  change (only the fenced block is touched);
- the GitHub repository map: discovery only ADDS lines for
  repos missing from the doc, so per-repo notes the owner wrote are preserved.
"""
import json, re

CONN_START, CONN_END = '<!-- connections:start -->', '<!-- connections:end -->'
PROJECT_START, PROJECT_END = '<!-- projects:start -->', '<!-- projects:end -->'
REPO_MAP_HEADER = '## Repository map'
BLURB_CHARS = 600       # one routing-table entry, whole (triage.REPO_ABOUT is the same size).
                        # Models overrun the two-sentence brief by half and the coverage list is the
                        # half they overrun INTO, so the budget fits the answer rather than docking it.
# The poller's own map, not a second copy of it. This used to be a hand-kept duplicate that
# stopped at monday, so every connector added after it (gitlab, azdo, linear, trello, notion,
# sentry, pagerduty, aws, azure, and now clickup/todoist) was invisible to the agents: their
# sources never made it into the SOUL.md 'Connected systems' block.
from .channels import CH2SRC


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
    from . import reports
    doc = store.get_doc('soul') or ''
    if CONN_START not in doc or CONN_END not in doc: return
    srcs = store.list_sources()
    lines = []
    connectors = store.list_connectors()
    type_counts = {c['Type']: sum(x['Type'] == c['Type'] for x in connectors) for c in connectors}
    for c in connectors:
        if not c['Active']: continue
        mine = [s['Address'] for s in srcs
                if s['Channel'] == CH2SRC.get(c['Type']) and s['Active']
                and (s.get('ConnectorId') in (None, c['ConnectorId']))]
        # what each connection IS to the agents, not just that it exists
        what = '; '.join(role_text(store, r) for r in ('trigger', 'tool', 'report') if r in roles_of(c))
        name = c['Name'] + (f" [connector id {c['ConnectorId']}]" if type_counts[c['Type']] > 1 else '')
        if mine: lines.append(f"- {name}: {', '.join(sorted(mine)[:12])}" + (f" — {what}" if what else ''))
        elif what: lines.append(f"- {name} — {what}")
    for s in srcs:
        if s['Channel'] != 'report' or not s['Active']: continue
        cfg = json.loads(s.get('ConfigJson') or '{}')
        sched = reports.schedule_words(cfg)
        lines.append(f"- Report \"{cfg.get('title') or s['Address']}\" ({cfg.get('type', 'rest')}, {sched})")
    # the tool role is only real if the agents know how to reach it - spell out the call
    if any('tool' in roles_of(c) for c in store.list_connectors() if c['Active']):
        from . import config
        srv = config.load().get('server') or {}
        auth = ' (header X-Taskuary-Token)' if srv.get('token') else ''
        lines.append(f"- To USE one of the systems above, POST http://{srv.get('host', '127.0.0.1')}:{srv.get('port', 7787)}"
                     '/api/tools/run{auth} with {"type": "mssql|database|aws|s3_object|cloudwatch_logs|'
                     'azure|azure_blob|azure_logs|winrm|mcp|rest|sqlite|rss|kb_search|'
                     # intacct was reachable all along (the card carries the tool role by default) and
                     # was the one system this list never named, so the only road an agent could SEE
                     # to the ERP was "get a report pipeline saved first"
                     'intacct|intacct_fields|quickbooks|quickbooks_vendors|quickbooks_accounts|teller_accounts|teller_transactions|teller_balances|teller_spend|simplefin_accounts|simplefin_transactions|simplefin_balances|simplefin_spend'
                     '|yahoo_quotes|yahoo_history|edgar_filings|edgar_facts|coingecko_prices|fx_rates|'
                     'td_quotes|td_indicator|av_quotes|fred_series|markets_screen|'
                     'finnhub_quotes|finnhub_news|finnhub_earnings|finnhub_insiders|'
                     'polygon_bars|polygon_snapshot|tiingo_history|tiingo_news|'
                     'fmp_fundamentals|fmp_ratios|alpaca_quotes|alpaca_bars", ...} — '
                     'saved credentials are filled in for you; if several cards have that type, pass '
                     '"connector_id": <the id named above>; the raw output comes back. '
                     # the writes exist and are named, and the road to them is the proposal - an agent
                     # that finds no way to post a bill invents one
                     'WRITES to the books (quickbooks_bill, quickbooks_expense) are never yours to run directly: '
                     'propose one - TASKUARY-PROPOSE {"action": "run_tool", "type": "quickbooks_bill", "vendor": ..., '
                     '"amount": ..., "account": ..., "date": ..., "memo": ..., "doc_number": ...} in your session - '
                     'and the owner approves it in Review.'.replace('{auth}', auth))
    block = '\n'.join(lines) or '_(no connections yet — add them in the Connections tab)_'
    head, rest = doc.split(CONN_START, 1)
    _, tail = rest.split(CONN_END, 1)
    new = f'{head}{CONN_START}\n{block}\n{CONN_END}{tail}'
    if new != doc: store.save_doc('soul', new, actor)


def sync_projects(store, actor='system'):
    """Render structured project links into one replaceable, human-readable SOUL.md block.

    Raw addresses and provider ids stay in SQLite. The document names the people and channels,
    which is enough for an owner to understand it and avoids spraying contact identifiers into
    every agent prompt that receives part of SOUL.md.
    """
    from .projects import soul_rows
    doc = store.get_doc('soul') or ''
    rows = soul_rows(store)
    body = '\n'.join(rows) or '_(relationships appear after you route work to repositories)_'
    section = ('## Project relationships\n'
               f'{PROJECT_START}\n{body}\n{PROJECT_END}')
    if PROJECT_START in doc and PROJECT_END in doc:
        head, rest = doc.split(PROJECT_START, 1)
        _, tail = rest.split(PROJECT_END, 1)
        new = f'{head}{PROJECT_START}\n{body}\n{PROJECT_END}{tail}'
    elif REPO_MAP_HEADER in doc:
        head, tail = doc.split(REPO_MAP_HEADER, 1)
        new = f'{head.rstrip()}\n\n{section}\n\n{REPO_MAP_HEADER}{tail}'
    else:
        new = f'{doc.rstrip()}\n\n{section}\n'
    if new != doc: store.save_doc('soul', new, actor)


# Generated files, vendored trees and binaries say nothing about what a codebase COVERS, and they
# are most of what is in one. Dropping them is what leaves room for the paths that do say something.
_TREE_SKIP = re.compile(r'(^|/)(node_modules|\.git|venv|\.venv|env|dist|build|out|target|vendor|'
                        r'__pycache__|site-packages|coverage|\.next|\.nuxt|bin|obj)(/|$)|'
                        r'\.(png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot|pdf|zip|map|lock|csv|min\.js|min\.css)$', re.I)


def _tree_digest(paths: list, cap: int = 2000) -> str:
    """The file tree as evidence of coverage, small enough to put in a prompt: the top-level folders
    with their weights, then an equal SHARE of the sample per folder - strided within each.

    "What does this system cover" is a question about breadth, so every folder gets the same voice
    however big it is. A stride across the whole sorted tree does not: FanApp's 518-file website/ is
    contiguous once sorted and swallowed 99% of the sample, burying the fifty sql/ scripts and
    twenty-seven reports/ that are the actual answer."""
    keep = sorted(p for p in paths if not _TREE_SKIP.search(p))
    if not keep: return ''
    groups = {}
    for p in keep: groups.setdefault(p.split('/')[0] if '/' in p else '(root)', []).append(p)
    head = 'Top-level folders: ' + ', '.join(
        f'{d} ({len(v)})' for d, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:20])
    room = max(0, cap - len(head) - 8)
    share = max(1, room // max(1, len(groups)) // 28)
    out = []
    for xs in groups.values(): out += xs[::max(1, len(xs) // share)][:share]
    return head + '\nFiles: ' + ', '.join(sorted(out))[:room]


def _fit(text: str, cap: int) -> str:
    """Cut to the last COMPLETE sentence that fits. A routing-table entry that stops mid-word
    ("...Azure SQL and Blob Storage data handling, facility and employee ID audits, Viventium payroll s")
    reads as broken data rather than as a description of anything."""
    t = ' '.join((text or '').split())
    if len(t) <= cap: return t
    cut = t[:cap]
    stop = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    # any sentence end that leaves a real description beats a word cut: at > cap//2 a summary whose
    # only full stop sat early fell through to the word branch and ended "...approval reminders, and"
    return (cut[:stop + 1] if stop > cap // 4 else cut.rsplit(' ', 1)[0]).rstrip(' ,;:-')


BLURB_SYSTEM = (
    'You describe a codebase for a ROUTING TABLE - the one entry a triage model reads to decide '
    'whether an incoming request belongs to this repository. Two plain sentences, under 45 words, no '
    'markdown, no bullet points. Say what the system IS, then what it COVERS: the business areas, '
    'integrations, data sources and kinds of work its code actually handles, in the words a colleague '
    'would use for them. The file and folder names are your evidence of coverage - a README says what '
    'somebody meant to build, the tree shows what is there. Name concrete domains, never generic '
    'praise, and never a list of programming languages or frameworks.')


def _readme_blurb(tok, repo, llm) -> str:
    """No GitHub description? Read the repository itself - its README for what it is, its file tree
    for what it covers - and summarize. Falls back to the README's first prose line with no AI.

    It read the README alone, which for a big internal system is a paragraph written years ago:
    FanApp came back "an enterprise integration platform connecting MFA systems with HR, finance,
    identity, training, email, database and third-party APIs", which is true of half the estate and
    never mentions the bank feeds. The tree names them (TQ-0443)."""
    from .github import readme_text, repo_tree
    try: txt = readme_text(tok, repo)
    except Exception: txt = ''
    tree = _tree_digest(repo_tree(tok, repo))
    if not (txt.strip() or tree): return ''
    if llm:
        try:
            said = (llm(BLURB_SYSTEM, f'Repository {repo}\n\nREADME:\n{txt[:4000]}\n\nFILE TREE:\n{tree}') or '').strip()
            return _fit(' '.join(said.splitlines()), BLURB_CHARS)
        except Exception:
            pass
    lines = [l.strip() for l in txt.splitlines()
             if l.strip() and not l.startswith(('#', '!', '[', '<', '|', '-', '='))]
    return lines[0][:160] if lines else ''


def update_repo_map(store, repos: list, actor='github', tok=None, llm=None):
    """repos: [{full_name, description, archived}] - append unknown repos under the map
    header in SOUL.md so EVERY agent knows which repo owns what. Repos without a GitHub
    description get summarized from their README (AI one-liner when available)."""
    from .projects import ensure_repositories
    ensure_repositories(store, repos, actor)
    doc = store.get_doc('soul') or ''
    # Only the MAP's own lines count as already-listed. This read the whole document, so a repo
    # merely NAMED anywhere in SOUL.md - the operator's own prose, or the project block that
    # sync_projects writes as this function's last statement - was skipped forever and never got
    # the one line saying what it is. The map stayed empty, triage was handed bare owner/name
    # strings with no purpose attached, and could not place a word of the work against them.
    from .terminal import _REPO_LINE
    listed = {mt.group(1).strip().lower() for mt in _REPO_LINE.finditer(doc)}
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
            for r in repos if r['full_name'].lower() not in listed]
    if not adds:
        if healed: store.save_doc('soul', doc, actor)
        sync_projects(store, actor)
        return
    if REPO_MAP_HEADER in doc:
        head, rest = doc.split(REPO_MAP_HEADER, 1)
        doc = head + REPO_MAP_HEADER + rest.rstrip() + '\n' + '\n'.join(adds) + '\n'
    else:
        doc = (doc.rstrip() + f'\n\n{REPO_MAP_HEADER}\n'
               'Route each coding task to the repo whose purpose matches; when unsure, escalate.\n'
               + '\n'.join(adds) + '\n')
    store.save_doc('soul', doc, actor)
    sync_projects(store, actor)
