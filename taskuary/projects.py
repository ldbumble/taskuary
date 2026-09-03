"""Small, evidence-backed relationships between people, channels, projects and repositories.

This is intentionally not a general graph database. A project is the hub; typed links point at
it. Only an owner's explicit repository choice teaches an identity link. Automatic repo guesses
are read-only consumers of that evidence, never new evidence themselves.
"""
import re

ROUTE_CONFIDENCE = .80       # two different owner-routed tasks (.72, then .86)
CONTEXT_CONFIDENCE = .70     # one choice may inform triage, clearly labelled tentative
REPO_KIND = 'repository'
PUBLIC_MAIL = {'gmail.com', 'outlook.com', 'hotmail.com', 'live.com', 'yahoo.com', 'icloud.com',
               'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'fastmail.com'}


def _field(row: dict, *names):
    for name in names:
        if row.get(name) not in (None, ''): return row[name]
    return None


def _whatsapp_id(value: str) -> str:
    value = str(value or '').removeprefix('whatsapp:').strip().lower()
    return value.partition('@')[0].split(':', 1)[0]


def identity_of(message: dict):
    """(channel, provider identity, display label), or None when the row cannot name a person.

    Email/Teams normally carry FromEmail. WhatsApp now stores the sender JID; older direct-chat
    rows fall back to their conversation JID. A group conversation is never treated as a person.
    """
    channel = str(_field(message, 'Channel', 'channel') or '').strip().lower()
    if not channel or channel in ('report', 'assistant', 'calendar'): return None
    value = _field(message, 'FromEmail', 'from_email')
    conv = str(_field(message, 'ConversationId', 'conversation_id') or '')
    if not value and channel == 'whatsapp' and conv.startswith('whatsapp:'):
        candidate = conv[len('whatsapp:'):]
        if not candidate.endswith('@g.us'): value = candidate
    if not value and channel in ('telegram', 'imessage') and conv.startswith(channel + ':'):
        value = conv[len(channel) + 1:]
    if not value: return None
    value = _whatsapp_id(value) if channel == 'whatsapp' else str(value).strip().lower()
    if not value: return None
    label = str(_field(message, 'FromName', 'from_name') or '').strip()
    if label.lower() in ('you', 'me'): return None
    return channel, value, label


def identities_of(message: dict):
    """The person identity plus a safe company-domain identity where one exists."""
    identity = identity_of(message)
    if not identity: return []
    out = [identity]
    kind, value, _label = identity
    if kind == 'email' and '@' in value:
        domain = value.rsplit('@', 1)[1]
        if domain and domain not in PUBLIC_MAIL:
            out.append(('email_domain', domain, domain))
    return out


def ensure_repository(store, repo: str, description: str = None, actor: str = 'github') -> int:
    """Give a discovered/selected repository a project node and a certain repository edge."""
    repo = str(repo or '').strip()
    if not repo or repo == 'none': raise ValueError('a repository project needs a repository')
    existing = [x for x in store.project_links(kind=REPO_KIND) if x['Value'].lower() == repo.lower()]
    if existing:
        store.ensure_project(existing[0]['ProjectName'], description, actor)
        return existing[0]['ProjectId']
    pid = store.ensure_project(repo, description, actor)
    store.upsert_project_link(pid, REPO_KIND, repo, repo, 1.0, True, actor)
    return pid


def ensure_repositories(store, repos: list, actor: str = 'github'):
    for row in repos or []:
        repo = row.get('full_name') if isinstance(row, dict) else row
        if repo:
            ensure_repository(store, repo, (row.get('description') if isinstance(row, dict) else None), actor)


def learn_task_repository(store, task_id: int, repo: str, actor: str = 'owner') -> bool:
    """Learn every inbound identity on a task from one explicit repository selection."""
    pid = ensure_repository(store, repo, actor=actor)
    changed = False
    seen = set()
    for message in store.list_messages(task_id):
        if str(message.get('Direction') or 'in') == 'out' or message.get('Status') == 'context': continue
        for identity in identities_of(message):
            if identity[:2] in seen: continue
            seen.add(identity[:2])
            kind, value, label = identity
            lid = store.upsert_project_link(pid, kind, value, label, source='repo_choice')
            changed = store.add_project_evidence(lid, task_id, 'owner chose repository') or changed
    return changed


def backfill(store) -> int:
    """Replay current explicit repo tags. Evidence uniqueness makes this safe on every startup."""
    changed = 0
    for task in store.list_tasks():
        match = re.search(r'(?:^|[\s,])repo:([^\s,]+)', str(task.get('Tags') or ''))
        if match and match.group(1) != 'none':
            changed += bool(learn_task_repository(store, task['TaskId'], match.group(1), 'history'))
    return changed


def _identity_links(store, message: dict, floor: float = CONTEXT_CONFIDENCE):
    identity = identity_of(message)
    if not identity: return [], None
    kind, value, label = identity
    exact = [x for x in store.project_links(kind=kind)
             if x['Value'].casefold() == value.casefold()
             and (x['Confirmed'] or float(x['Confidence'] or 0) >= floor)]
    if exact: return exact, 'identity'
    if kind == 'email' and '@' in value:
        domain = value.rsplit('@', 1)[1]
        if domain not in PUBLIC_MAIL:
            company = [x for x in store.project_links(kind='email_domain')
                       if x['Value'].casefold() == domain.casefold()
                       and (x['Confirmed'] or float(x['Confidence'] or 0) >= ROUTE_CONFIDENCE)]
            if company: return company, 'company email domain'
    # Same display name across channels is useful context but never an automatic repo route.
    # Names collide; the owner confirms it by selecting a repo on that channel once.
    if label:
        named = [x for x in store.project_links()
                 if x['Kind'] != REPO_KIND and str(x.get('Label') or '').casefold() == label.casefold()
                 and (x['Confirmed'] or float(x['Confidence'] or 0) >= ROUTE_CONFIDENCE)]
        if len({x['ProjectId'] for x in named}) == 1: return named[:1], 'same display name'
    return [], None


def context_for_message(store, message: dict):
    """Only the small relevant project slice for triage, never the whole relationship graph."""
    links, matched_by = _identity_links(store, message)
    if not links: return None
    rows = []
    for link in links:
        repos = [x['Value'] for x in store.project_links(link['ProjectId'], REPO_KIND)]
        rows.append({'project': link['ProjectName'], 'repositories': repos,
                     'relationship': ('possible cross-channel identity' if matched_by == 'same display name'
                                      else 'learned from explicit repository choices'),
                     'evidence': int(link.get('EvidenceCount') or 0),
                     'confidence': round(float(link.get('Confidence') or 0), 2),
                     'tentative': not bool(link.get('Confirmed')) and float(link.get('Confidence') or 0) < ROUTE_CONFIDENCE})
    return rows[0] if len(rows) == 1 else {'candidates': rows, 'relationship': 'ambiguous; do not guess'}


def repositories_for_task(store, task_id: int):
    """Strong exact-identity repositories for routing, plus a human-readable reason."""
    task_messages = store.list_messages(task_id)
    direct = [str(m.get('SourceName') or '').strip() for m in task_messages
              if m.get('Channel') == 'github' and str(m.get('SourceName') or '').strip()]
    if direct: return list(dict.fromkeys(direct)), 'the GitHub item belongs to this repository'
    projects, evidence, labels = set(), 0, set()
    for message in task_messages:
        for kind, value, label in identities_of(message):
            for link in store.project_links(kind=kind):
                if link['Value'].casefold() != value.casefold(): continue
                if not (link['Confirmed'] or float(link['Confidence'] or 0) >= ROUTE_CONFIDENCE): continue
                projects.add(link['ProjectId']); evidence = max(evidence, int(link.get('EvidenceCount') or 0))
                if label and kind != 'email_domain': labels.add(label)
    repos = [x['Value'] for pid in projects for x in store.project_links(pid, REPO_KIND)]
    repos = list(dict.fromkeys(repos))
    who = ', '.join(sorted(labels)) or 'this sender'
    reason = f'learned from {evidence} owner repository choices for {who}'
    return repos, reason


def soul_rows(store) -> list:
    """Readable project summaries for SOUL.md; raw addresses/JIDs remain in structured storage."""
    out = []
    for project in store.list_projects():
        links = store.project_links(project['ProjectId'])
        identities = [x for x in links if x['Kind'] not in (REPO_KIND, 'email_domain')]
        domains = [x['Value'] for x in links if x['Kind'] == 'email_domain']
        if not identities: continue
        repos = [x['Value'] for x in links if x['Kind'] == REPO_KIND]
        people = {}
        for link in identities:
            label = str(link.get('Label') or '').strip() or 'unnamed contact'
            people.setdefault(label, set()).add(link['Kind'])
        drivers = ', '.join(f"{name} ({', '.join(sorted(channels))})" for name, channels in sorted(people.items()))
        evidence = max((int(x.get('EvidenceCount') or 0) for x in identities), default=0)
        maturity = 'learned' if any(x['Confirmed'] or float(x['Confidence'] or 0) >= ROUTE_CONFIDENCE for x in identities) else 'learning'
        repo_text = ', '.join(f'`{r}`' for r in repos) or '(repository not linked)'
        domain_text = f"; company domains: {', '.join(sorted(domains))}" if domains else ''
        out.append(f"- **{project['Name']}** — repositories: {repo_text}; people: {drivers}{domain_text}; "
                   f'{maturity} from {evidence} owner-routed task{"s" if evidence != 1 else ""}')
    return out
