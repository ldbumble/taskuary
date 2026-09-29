"""Minimal GitHub helpers (optional): a fine-grained PAT is all the config."""
import re

import requests
from loguru import logger

GH = 'https://api.github.com'
def _h(tok): return {'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}


# ── GITHUB'S NO, IN WORDS ─────────────────────────────────────────────────────────────────
# A refused merge reached the owner as "403 Client Error: Forbidden for url: https://api.github.com/..." (2026-09-29).
# GitHub says exactly what was missing - `x-accepted-github-permissions: contents=write` - and nothing read it.
PERMS = {'contents': 'Contents', 'pull_requests': 'Pull requests', 'issues': 'Issues', 'actions': 'Actions',
         'workflows': 'Workflows', 'administration': 'Administration', 'checks': 'Checks'}
WHERE = 'github.com - Settings - Developer settings - Personal access tokens'


class Refused(RuntimeError):
    """GitHub said no. `needs` names the token permission when that was the reason ("Contents: write") - a token's
    grant, not a state of the pull request, so no agent can fix it and a retry repeats it."""
    def __init__(self, msg: str, status: int = 0, needs: str = ''):
        super().__init__(msg); self.status, self.needs = status, needs


def needs_of(r) -> str:
    """'contents=write; contents=write,workflows=write' -> 'Contents: write' (the first way GitHub accepts)."""
    first = str(r.headers.get('x-accepted-github-permissions') or '').split(';')[0].strip()
    return ', '.join(f"{PERMS.get(k, k.replace('_', ' ').capitalize())}: {v}" for k, _, v in
                     (p.strip().partition('=') for p in first.split(',') if '=' in p))


def _ok(r, what: str):
    """The response when GitHub said yes; otherwise Refused, saying what the owner can do about it."""
    if getattr(r, 'ok', True) and int(getattr(r, 'status_code', 200) or 200) < 400: return r
    try: why = str(r.json().get('message') or '')
    except ValueError: why = r.text[:200]
    needs = needs_of(r) if r.status_code == 403 else ''
    if r.status_code == 401: msg = f'GitHub refused the token (expired or revoked) - paste a new one on the GitHub connection'
    elif needs and 'not accessible' in why.lower():
        msg = f'the GitHub token may not {what} - it needs {needs} for this repository ({WHERE})'
    elif r.status_code == 404: msg = f'GitHub cannot see that with this token - it may be private to the token, or gone'
    else: msg = f'GitHub would not {what}: {why or r.status_code}'
    raise Refused(msg, r.status_code, needs)


# WHAT THIS TOKEN MAY DO HERE. The role GET /repos reports is the USER's - a fine-grained token with none of the grants
# still reads "admin", and the card offered a Close out that could only 403. GitHub has no endpoint that lists a token's
# grants, so each is asked with a request that CANNOT succeed: a branch at a commit that does not exist, a pull request
# between branches that do not exist, an issue with no title, a re-run of run 0. Missing the grant is a 403 naming it;
# having it is the validation error (422) or a 404 - nothing is ever created.
GRANT_PROBES = (('contents', 'post', '/git/refs', {'ref': 'refs/heads/taskuary-permission-probe', 'sha': '0' * 40}),
                ('pull_requests', 'post', '/pulls', {'head': 'taskuary-probe-none-0', 'base': 'taskuary-probe-none-1', 'title': ''}),
                ('issues', 'post', '/issues', {}),
                ('actions', 'post', '/actions/runs/0/rerun-failed-jobs', None))
GRANT_TTL = 900
_GRANTS: dict = {}               # (token hash, repo) -> (at, {perm: bool})


def _gkey(tok, repo):
    import hashlib
    return hashlib.sha256(str(tok or '').encode()).hexdigest()[:16], str(repo or '').lower()


def grants(tok, repo, fresh: bool = False) -> dict:
    """{perm: True|False} for this token on this repo - False only where GitHub said so (a 403 naming it). Cached per
    token and repo; a new token is a new key, so pasting one is re-read at once. A probe that errors is left True -
    GitHub still decides at the act, and its refusal is then remembered (learn)."""
    import time
    k = _gkey(tok, repo)
    at, got = _GRANTS.get(k, (0, None))
    if got is not None and not fresh and time.time() - at < GRANT_TTL: return dict(got)
    out = {}
    for perm, method, path, body in GRANT_PROBES:
        try:
            r = requests.request(method, f'{GH}/repos/{repo}{path}', headers=_h(tok), json=body, timeout=15)
            out[perm] = not (r.status_code == 403 and 'not accessible' in r.text.lower())
        except requests.RequestException as e:
            logger.debug(f'github: the {perm} probe on {repo} did not answer - {e}'); out[perm] = True
    _GRANTS[k] = (time.time(), out)
    return dict(out)


def learn(tok, repo, err):
    """A real act GitHub refused for a missing grant: remember it, so the next card does not offer it again."""
    import time
    if not isinstance(err, Refused) or not err.needs: return
    perm = next((k for k, w in PERMS.items() if err.needs.startswith(w + ':')), None)
    if not perm: return
    k = _gkey(tok, repo)
    at, got = _GRANTS.get(k, (time.time(), {}))
    _GRANTS[k] = (at, {**(got or {}), perm: False})

# Markdown and HTML both, because an issue template uses whichever the writer's editor produced:
# ![shot](https://github.com/user-attachments/assets/<uuid>) or <img src="..." />. Only the hosts
# GitHub itself serves attachments from - an issue body is a stranger's text on a public repo, and
# following an arbitrary URL out of it is an SSRF with extra steps.
_IMG_MD = re.compile(r'!\[[^\]]*\]\((https?://[^\s)]+)\)')
_IMG_TAG = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
_IMG_HOSTS = ('github.com/user-attachments/', 'user-images.githubusercontent.com/',
              'private-user-images.githubusercontent.com/', 'raw.githubusercontent.com/')


def body_images(tok, body: str, cap: int = 4, max_bytes: int = 5_000_000) -> list:
    """[(media_type, base64)] for the pictures embedded in an issue or PR body.

    A bug report's whole content is often the screenshot: the template's own headings come through
    empty and the words are in the image. Triage read the empty text and filed it as informational
    (the owner, 2026-09-04: "when you triage github issues you have to read the image"). Mail has
    solved this since Graph hands attachments over inline - see channels.images_for_triage, whose
    docstring is about the same failure - and this is the GitHub end of it.
    """
    import base64
    seen, out = set(), []
    for rx in (_IMG_MD, _IMG_TAG):
        for url in rx.findall(body or ''):
            if len(out) >= cap: return out
            if url in seen or not any(h in url for h in _IMG_HOSTS): continue
            seen.add(url)
            try:
                r = requests.get(url, headers={'Authorization': f'Bearer {tok}'} if tok else {},
                                 timeout=20, stream=True)
                if r.status_code != 200: continue
                ct = str(r.headers.get('Content-Type') or '').split(';')[0].lower()
                if not ct.startswith('image/') or ct in ('image/svg+xml',): continue
                raw = r.raw.read(max_bytes + 1, decode_content=True) or b''
                if not raw or len(raw) > max_bytes: continue
                out.append((ct, base64.b64encode(raw).decode()))
            except Exception as e:
                logger.debug(f'github: could not read the image on an item - {e}')
    return out


def create_issue(tok, repo, title, body):
    r = _ok(requests.post(f'{GH}/repos/{repo}/issues', headers=_h(tok), json={'title': title, 'body': body}, timeout=20), 'open an issue')
    j = r.json()
    return {'number': j['number'], 'url': j['html_url']}

def comment_issue(tok, repo, number, body):
    """One comment on an issue or PR - how a Taskuary reply reaches a GitHub author."""
    r = _ok(requests.post(f'{GH}/repos/{repo}/issues/{number}/comments', headers=_h(tok), json={'body': body}, timeout=20),
            f'comment on #{number}')
    return r.json().get('html_url')


def close_issue(tok, repo, number, comment=None):
    # the close first: a comment that landed before a refused close was posted AGAIN by the retry
    _ok(requests.patch(f'{GH}/repos/{repo}/issues/{number}', headers=_h(tok), json={'state': 'closed'}, timeout=20), f'close #{number}')
    if comment: comment_issue(tok, repo, number, comment)

def open_pr(tok, repo, head, base, title, body, draft=True):
    """A DRAFT pull request by default: a branch pushed for review is not a merge request
    yet - it merges only on the owner's yes (merge_pr). 422 with 'already exists' comes back
    as the existing PR instead of an error - opening twice is a retry, not a mistake."""
    r = requests.post(f'{GH}/repos/{repo}/pulls', headers=_h(tok), timeout=20,
                      json={'title': title, 'body': body, 'head': head, 'base': base, 'draft': draft})
    if r.status_code == 422 and 'already exist' in r.text:
        ex = list_prs(tok, repo, head=head)
        if ex: return ex[0]
    _ok(r, 'open a pull request')
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
    r = _ok(requests.get(f'{GH}/repos/{repo}/pulls/{number}', headers=_h(tok), timeout=20), f'read #{number}')
    j = r.json()
    # mergeable_state is GitHub's verdict on THIS repo's rules for THIS pull request - clean, unstable (a check it does not
    # require is red), blocked (a required check, review or rule), behind (must be up to date), dirty (conflicts), draft,
    # or unknown while GitHub is still computing it. The close-out reads it instead of guessing at each repo's protection.
    return {'number': j['number'], 'url': j['html_url'], 'head': j['head']['ref'],
            'sha': j['head']['sha'], 'state': j['state'], 'draft': j.get('draft'),
            'merged': j.get('merged'), 'mergeable': j.get('mergeable'), 'node_id': j.get('node_id'),
            'mergeable_state': j.get('mergeable_state') or 'unknown', 'base': (j.get('base') or {}).get('ref'),
            'maintainer_can_modify': bool(j.get('maintainer_can_modify')),
            'same_repo': ((j.get('head') or {}).get('repo') or {}).get('full_name') == ((j.get('base') or {}).get('repo') or {}).get('full_name')}


def repo_info(tok, repo) -> dict:
    """What this repository allows and what the token may do in it: the merge methods its settings permit, and the
    token's own role (`permissions`: admin / maintain / push / triage / pull)."""
    r = _ok(requests.get(f'{GH}/repos/{repo}', headers=_h(tok), timeout=20), f'read {repo}')
    j = r.json()
    return {'methods': [m for m, k in (('squash', 'allow_squash_merge'), ('merge', 'allow_merge_commit'), ('rebase', 'allow_rebase_merge'))
                        if j.get(k, True)],
            'permissions': j.get('permissions') or {}, 'default_branch': j.get('default_branch')}


def update_branch(tok, repo, number, expected_sha=None) -> str:
    """GitHub's own "Update branch": merges the base into the pull request, so its checks run fresh against today's base."""
    r = requests.put(f'{GH}/repos/{repo}/pulls/{number}/update-branch', headers=_h(tok), timeout=30,
                     json={'expected_head_sha': expected_sha} if expected_sha else {})
    _ok(r, f'update #{number}')
    return (r.json() or {}).get('message') or 'Updating the branch'


def rerun_failed(tok, repo, sha) -> int:
    """Re-run the failed jobs of every Actions run on this commit; the number of runs asked. Checks from other CI
    systems cannot be re-run from here."""
    r = _ok(requests.get(f'{GH}/repos/{repo}/actions/runs', headers=_h(tok), params={'head_sha': sha, 'per_page': 50}, timeout=20),
            'read the checks')
    n = 0
    for run in r.json().get('workflow_runs') or []:
        if run.get('conclusion') not in ('failure', 'timed_out', 'cancelled'): continue
        x = requests.post(f"{GH}/repos/{repo}/actions/runs/{run['id']}/rerun-failed-jobs", headers=_h(tok), timeout=20)
        _ok(x, 're-run checks'); n += 1
    return n


def merge_pr(tok, repo, number, sha, title=None, message=None, method='squash', p=None) -> str:
    """Merge a pull request - only ever from the owner's approved close-out (proposals 'merge_pr').
    GitHub refuses to merge a draft, so it is marked ready first. `sha` pins the head that was
    reviewed: a commit pushed after the owner looked is a 409, never a silent merge."""
    p = p or pr(tok, repo, number)
    if p.get('draft'):
        q = 'mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}'
        r = _ok(requests.post(f'{GH}/graphql', headers=_h(tok), json={'query': q, 'variables': {'id': p['node_id']}}, timeout=20),
                f'mark #{number} ready for review')
        if r.json().get('errors'): raise RuntimeError(f"GitHub would not mark #{number} ready: {r.json()['errors'][0].get('message')}")
    body = {'merge_method': method, 'sha': sha, **({'commit_title': title} if title else {}), **({'commit_message': message} if message else {})}
    r = requests.put(f'{GH}/repos/{repo}/pulls/{number}/merge', headers=_h(tok), json=body, timeout=30)
    if r.status_code in (405, 409, 422):
        try: why = r.json().get('message')
        except ValueError: why = ''
        raise Refused(f"GitHub refused to merge #{number}: {why or r.text[:200]}", r.status_code)
    return _ok(r, f'merge #{number}').json().get('sha') or ''


def close_pr(tok, repo, number):
    """Close a pull request WITHOUT merging it - the close-out's other answer (proposals.close_pr)."""
    _ok(requests.patch(f'{GH}/repos/{repo}/pulls/{number}', headers=_h(tok), json={'state': 'closed'}, timeout=20), f'close #{number}')


def closed_by(tok, repo, number) -> str:
    """The login that closed an issue or merged a pull request - the list endpoint leaves it out, the item carries it."""
    r = requests.get(f'{GH}/repos/{repo}/issues/{number}', headers=_h(tok), timeout=20)
    r.raise_for_status()
    return str((r.json().get('closed_by') or {}).get('login') or '')


def pr_diff(tok, repo, number) -> str:
    """The pull request's own unified diff, as GitHub serves it - what a review of a PR task is
    a review OF. The checkout's diff is the agent's footprint; this is the contributor's."""
    r = requests.get(f'{GH}/repos/{repo}/pulls/{number}', headers={**_h(tok), 'Accept': 'application/vnd.github.diff'}, timeout=30)
    r.raise_for_status()
    return r.text


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
                out.append({'id': c.get('id'), 'kind': kind, 'who': u.get('login'), 'assoc': c.get('author_association') or '',
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


def issue_comments(tok, repo, number, since=None, limit=50):
    """The conversation ON an issue or PR. An issue body is what somebody meant to say the day
    they filed it; the answer to "what changed" is usually down here. `since` is an ISO stamp."""
    p = {'per_page': min(limit, 100), 'sort': 'created', 'direction': 'asc'}
    if since: p['since'] = since
    r = requests.get(f'{GH}/repos/{repo}/issues/{number}/comments', headers=_h(tok), params=p, timeout=30)
    r.raise_for_status()
    return r.json()[:limit]


def whoami(tok) -> str:
    """The login this token acts as - so the hub can tell its OWN comments from a person's."""
    r = requests.get(f'{GH}/user', headers=_h(tok), timeout=20)
    r.raise_for_status()
    return r.json().get('login') or ''


def repo_tree(tok, repo, limit=3000) -> list:
    """Every file path on the default branch, in one call. What a repo COVERS is written in its own
    file names - app/routers/ap_invoice.py, sql/, reports/ - and a README is only what somebody meant
    to build on the day they started. [] for an empty or unreachable repo; never raises."""
    try:
        r = requests.get(f'{GH}/repos/{repo}', headers=_h(tok), timeout=20)
        if r.status_code != 200: return []
        branch = r.json().get('default_branch') or 'main'
        t = requests.get(f'{GH}/repos/{repo}/git/trees/{branch}', headers=_h(tok),
                         params={'recursive': '1'}, timeout=30)
        if t.status_code != 200: return []
        return [x['path'] for x in (t.json().get('tree') or []) if x.get('type') == 'blob'][:limit]
    except Exception:
        return []


def readme_text(tok, repo) -> str:
    """The repo's README (decoded), '' when there isn't one."""
    import base64
    r = requests.get(f'{GH}/repos/{repo}/readme', headers=_h(tok), timeout=20)
    if r.status_code == 404: return ''
    r.raise_for_status()
    return base64.b64decode(r.json().get('content') or '').decode('utf-8', 'replace')
