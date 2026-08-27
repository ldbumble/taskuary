"""Minimal GitHub helpers (optional): a fine-grained PAT is all the config."""
import requests

GH = 'https://api.github.com'
def _h(tok): return {'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}

def create_issue(tok, repo, title, body):
    r = requests.post(f'{GH}/repos/{repo}/issues', headers=_h(tok), json={'title': title, 'body': body}, timeout=20)
    r.raise_for_status()
    j = r.json()
    return {'number': j['number'], 'url': j['html_url']}

def comment_issue(tok, repo, number, body):
    """One comment on an issue or PR - how a Taskuary reply reaches a GitHub author."""
    r = requests.post(f'{GH}/repos/{repo}/issues/{number}/comments', headers=_h(tok), json={'body': body}, timeout=20)
    r.raise_for_status()
    return r.json().get('html_url')


def close_issue(tok, repo, number, comment=None):
    if comment:
        requests.post(f'{GH}/repos/{repo}/issues/{number}/comments', headers=_h(tok), json={'body': comment}, timeout=20).raise_for_status()
    requests.patch(f'{GH}/repos/{repo}/issues/{number}', headers=_h(tok), json={'state': 'closed'}, timeout=20).raise_for_status()

def open_pr(tok, repo, head, base, title, body, draft=True):
    """A DRAFT pull request by default: a branch pushed for review is not a merge request
    yet, and Taskuary never merges. 422 with 'already exists' comes back as the existing PR
    instead of an error - opening twice is a retry, not a mistake."""
    r = requests.post(f'{GH}/repos/{repo}/pulls', headers=_h(tok), timeout=20,
                      json={'title': title, 'body': body, 'head': head, 'base': base, 'draft': draft})
    if r.status_code == 422 and 'already exist' in r.text:
        ex = list_prs(tok, repo, head=head)
        if ex: return ex[0]
    r.raise_for_status()
    j = r.json()
    return {'number': j['number'], 'url': j['html_url'], 'head': head, 'base': base, 'state': j['state']}


def list_prs(tok, repo, head=None, state='open'):
    params = {'state': state, 'per_page': 20}
    if head: params['head'] = f"{repo.split('/')[0]}:{head}"
    r = requests.get(f'{GH}/repos/{repo}/pulls', headers=_h(tok), params=params, timeout=20)
    r.raise_for_status()
    return [{'number': x['number'], 'url': x['html_url'], 'head': x['head']['ref'],
             'base': x['base']['ref'], 'state': x['state'], 'sha': x['head']['sha'],
             'draft': x.get('draft'), 'title': x.get('title')} for x in r.json()]


def pr(tok, repo, number):
    r = requests.get(f'{GH}/repos/{repo}/pulls/{number}', headers=_h(tok), timeout=20)
    r.raise_for_status()
    j = r.json()
    return {'number': j['number'], 'url': j['html_url'], 'head': j['head']['ref'],
            'sha': j['head']['sha'], 'state': j['state'], 'draft': j.get('draft'),
            'merged': j.get('merged'), 'mergeable': j.get('mergeable')}


def checks(tok, repo, sha):
    """Every check run for a commit, plus the legacy commit statuses some CIs still use.
    {state: success|failure|pending|none, failed: [...], counts} - one verdict, and the
    NAMES of what failed, because 'CI is red' is not something an agent can act on."""
    runs, statuses = [], []
    try:
        r = requests.get(f'{GH}/repos/{repo}/commits/{sha}/check-runs', headers=_h(tok),
                         params={'per_page': 100}, timeout=20)
        r.raise_for_status()
        runs = r.json().get('check_runs') or []
    except requests.RequestException:
        pass
    try:
        r = requests.get(f'{GH}/repos/{repo}/commits/{sha}/status', headers=_h(tok), timeout=20)
        r.raise_for_status()
        statuses = r.json().get('statuses') or []
    except requests.RequestException:
        pass
    done = [c for c in runs if c.get('status') == 'completed']
    bad = [c for c in done if c.get('conclusion') in ('failure', 'timed_out', 'cancelled', 'action_required')]
    bad += [s for s in statuses if s.get('state') in ('failure', 'error')]
    pending = [c for c in runs if c.get('status') != 'completed'] + [s for s in statuses if s.get('state') == 'pending']
    state = 'failure' if bad else 'pending' if pending else 'success' if (runs or statuses) else 'none'
    return {'state': state, 'total': len(runs) + len(statuses), 'pending': len(pending),
            'failed': [{'name': c.get('name') or c.get('context'),
                        'url': c.get('html_url') or c.get('target_url'),
                        'summary': ((c.get('output') or {}).get('summary') or c.get('description') or '')[:300]}
                       for c in bad][:8]}


def pr_review_comments(tok, repo, number, since=None):
    """Human comments on a pull request - both kinds: line notes on the diff, and the
    conversation on the PR itself. `id` and `url` come back too, because a comment that lands
    on the timeline needs to be de-duplicated across polls and to link to where it was said."""
    out = []
    for kind, path in (('review', f'/repos/{repo}/pulls/{number}/comments'),
                       ('conversation', f'/repos/{repo}/issues/{number}/comments')):
        try:
            r = requests.get(f'{GH}{path}', headers=_h(tok), timeout=20,
                             params={'per_page': 50, **({'since': since} if since else {})})
            r.raise_for_status()
            for c in r.json():
                u = (c.get('user') or {})
                if u.get('type') == 'Bot': continue
                out.append({'id': c.get('id'), 'kind': kind, 'who': u.get('login'),
                            'body': (c.get('body') or '')[:2000], 'path': c.get('path'),
                            'url': c.get('html_url'), 'at': c.get('created_at')})
        except requests.RequestException:
            continue
    return sorted(out, key=lambda c: str(c.get('at') or ''))


def list_accessible_repos(tok):
    r = requests.get(f'{GH}/user/repos', headers=_h(tok), params={'per_page': 100, 'sort': 'pushed'}, timeout=20)
    r.raise_for_status()
    return [{'full_name': x['full_name'], 'description': x.get('description'), 'archived': x.get('archived'),
             'private': bool(x.get('private'))}
            for x in r.json()]


def list_items(tok, repo, since=None, state='open', limit=25):
    """Open issues AND pull requests, newest activity first - the /issues endpoint carries
    both, a 'pull_request' key telling them apart. `since` is an ISO timestamp - GitHub
    returns everything updated after it."""
    p = {'state': state, 'sort': 'updated', 'direction': 'desc', 'per_page': min(limit, 100)}
    if since: p['since'] = since
    r = requests.get(f'{GH}/repos/{repo}/issues', headers=_h(tok), params=p, timeout=30)
    r.raise_for_status()
    return r.json()[:limit]


def list_issues(tok, repo, since=None, state='open', limit=25):
    """Just the issues - pull requests filtered out."""
    return [i for i in list_items(tok, repo, since, state, limit=100) if 'pull_request' not in i][:limit]


def readme_text(tok, repo) -> str:
    """The repo's README (decoded), '' when there isn't one."""
    import base64
    r = requests.get(f'{GH}/repos/{repo}/readme', headers=_h(tok), timeout=20)
    if r.status_code == 404: return ''
    r.raise_for_status()
    return base64.b64decode(r.json().get('content') or '').decode('utf-8', 'replace')
