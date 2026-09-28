"""What Close out does on GitHub - the owner's CHOICES, on the GitHub connection card (the owner, 2026-09-28: "let's make
this on the connector setup ... what close/merge pr does and what permissions they need").

Choices only. What each repository REQUIRES - branch protection, required checks and reviews, rulesets - is never copied
here: GitHub states it per pull request as `mergeable_state`, read fresh at every close-out, and GitHub's own refusal is
the last word. A copy would go stale and disagree with the rule it copied.

The connection holds the defaults (ConfigJson `closeout`); a followed repository may override any of them (its source's
ConfigJson `closeout`), because two repos can close out differently.
"""
import json

DEFAULTS = {
    'pr': 'merge',          # merge | task - Close out merges the pull request, or only closes the task and leaves it
    'method': 'squash',     # squash | merge | rebase - used when the repo allows it, else the first it does
    'red': 'merge',         # merge | ask - checks the repo does NOT require are red: merge with a note, or stop and ask
    'anyway': False,        # Close out anyway past the repo's own rules - an admin token only, and only on this press
    'update': True,         # offer Update branch when the pull request is behind and its author allows maintainer edits
    'rerun': True,          # offer Re-run checks when checks failed
    'issue': True,          # Close out on a task from an issue closes the issue
    'comment': True,        # the reply to the PR/issue author is posted as the close-out's comment
}
CHOICES = {'pr': ('merge', 'task'), 'method': ('squash', 'merge', 'rebase'), 'red': ('merge', 'ask')}


def _json(s) -> dict:
    try: return json.loads(s or '{}') or {}
    except (TypeError, ValueError): return {}


def clean(d: dict) -> dict:
    """Only known keys with allowed values - what the card may save."""
    out = {}
    for k, v in (d or {}).items():
        if k not in DEFAULTS or v is None: continue
        if k in CHOICES:
            if v in CHOICES[k]: out[k] = v
        else: out[k] = bool(v)
    return out


def cfg(store, repo: str = None) -> dict:
    """The close-out settings in force for `repo`: defaults, then the connection's, then the repo's own override."""
    conn = store.get_connector_by_type('github') or {}
    out = {**DEFAULTS, **clean(_json(conn.get('ConfigJson')).get('closeout'))}
    if repo:
        src = next((s for s in store.list_sources(active_only=False)
                    if s.get('Channel') == 'github' and str(s.get('Address') or '').lower() == repo.lower()), None)
        if src: out.update(clean(_json(src.get('ConfigJson')).get('closeout')))
    return out


class Refused(RuntimeError):
    """A close-out GitHub's state says cannot run now - with what the card may offer instead."""
    def __init__(self, reason: str, offers=()):
        super().__init__(reason); self.offers = list(offers)


def assess(store, repo: str, number: int, pr: dict = None) -> dict:
    """ONE READING OF THE PULL REQUEST, for drawing the card and for guarding the merge alike (the owner, 2026-09-28: "the
    close out should use api to get the state of the pr and have the correct buttons"):
    {state, ok, reason, note, offers, method, pr} - `ok` is whether Close out may merge now; `offers` are the card's
    other buttons (update, rerun, anyway); `note` rides with an allowed merge (red checks the repo does not require)."""
    import time
    from . import github
    from .ci import _conn
    tok, c = _conn(store)['Secret'], cfg(store, repo)
    p = pr or github.pr(tok, repo, number)
    if p.get('mergeable_state') == 'unknown' and not p.get('merged') and p.get('state') == 'open':
        time.sleep(1.5); p = github.pr(tok, repo, number)          # GitHub computes it on the first read; ask once more
    info = github.repo_info(tok, repo)
    admin = bool(info['permissions'].get('admin'))
    method = c['method'] if c['method'] in info['methods'] else (info['methods'] or ['squash'])[0]
    base, st = p.get('base') or 'the base branch', p.get('mergeable_state') or 'unknown'
    out = {'state': st, 'ok': False, 'reason': '', 'note': '', 'offers': [], 'method': method, 'pr': p}
    if p.get('merged'): return {**out, 'state': 'merged', 'reason': f"#{number} is already merged on GitHub"}
    if p.get('state') == 'closed': return {**out, 'state': 'closed', 'reason': f"#{number} was closed on GitHub without merging"}
    red = []
    if st in ('unstable', 'blocked'):
        try: red = [f['name'] or '?' for f in github.checks(tok, repo, p['sha'])['failed']]
        except Exception: red = []
    rerun = ['rerun'] if c['rerun'] and red else []
    if st == 'dirty':
        return {**out, 'reason': f"it has merge conflicts with {base} - send it back to the agent to resolve them, or ask its author"}
    if st == 'behind':
        can = p.get('same_repo') or p.get('maintainer_can_modify')
        return {**out, 'reason': f"it is behind {base}, and this repository requires it to be up to date"
                + ('' if can or not c['update'] else " - its author has not allowed maintainers to update it"),
                'offers': ['update'] if c['update'] and can else []}
    if st == 'blocked':
        why = f"its required checks are failing ({', '.join(red)})" if red else "a rule of this repository blocks it (a required review or check)"
        return {**out, 'reason': why, 'offers': rerun + (['anyway'] if c['anyway'] and admin else [])}
    if st == 'unstable' and red:
        if c['red'] == 'ask':
            return {**out, 'reason': f"checks this repository does not require are failing ({', '.join(red)})", 'offers': rerun + ['anyway']}
        return {**out, 'ok': True, 'note': f"checks this repository does not require are failing ({', '.join(red)})", 'offers': rerun}
    # clean, has_hooks, draft (marked ready first), unknown: GitHub decides at the merge and its refusal is shown
    return {**out, 'ok': True}


# what each choice needs from the token, in GitHub's words for a fine-grained token, and the role that carries it
NEEDS = (
    ('pr', 'Merge a pull request', 'Contents: write', 'push'),
    ('update', 'Update a behind branch', 'Pull requests: write', 'push'),
    ('rerun', 'Re-run failed checks', 'Actions: write', 'push'),
    ('issue', 'Close an issue', 'Issues: write', 'triage'),
    ('comment', 'Post your reply as the comment', 'Issues / Pull requests: write', 'triage'),
    ('anyway', 'Close out anyway, past the repo\'s rules', 'Administration (repo admin)', 'admin'),
)
_ROLE = ('pull', 'triage', 'push', 'maintain', 'admin')


def check(store) -> list:
    """Per followed repository: every close-out act the settings turn on, and whether the token's role there carries it.
    A role is what GitHub reports for the token; a fine-grained token can still lack one permission inside a role
    (Actions most often) - that shows on first use, in GitHub's own words."""
    from . import github
    from .ci import _conn
    tok = _conn(store)['Secret']
    rows = []
    for s in store.list_sources(active_only=True):
        if s.get('Channel') != 'github': continue
        repo, c = s['Address'], cfg(store, s['Address'])
        try: info = github.repo_info(tok, repo)
        except Exception as e:
            rows.append({'repo': repo, 'error': str(e)[:200]}); continue
        perms = info['permissions']
        have = max((i for i, r in enumerate(_ROLE) if perms.get(r)), default=-1)
        acts = []
        for key, what, needs, role in NEEDS:
            on = (c[key] == 'merge') if key == 'pr' else bool(c[key])
            if not on: continue
            acts.append({'key': key, 'what': what, 'needs': needs, 'ok': have >= _ROLE.index(role)})
        rows.append({'repo': repo, 'role': _ROLE[have] if have >= 0 else 'none', 'methods': info['methods'],
                     'method': c['method'] if c['method'] in info['methods'] else (info['methods'] or ['squash'])[0], 'acts': acts})
    return rows
