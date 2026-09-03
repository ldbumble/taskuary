"""Safe outputs: an agent PROPOSES a high-impact action, deterministic code validates it,
and it happens only after you approve. The best security idea in the field (GitHub's
agentic-workflows calls them safe outputs) and the one that actually fits here, because
Taskuary already has the approval queue to put a proposal in.

The distinction that matters: an agent with an auto-approve flag on your machine can already
do anything YOU can, so a permission profile Taskuary does not enforce would be theater.
What is real is moving the blast-radius actions OFF that road entirely - the agent cannot
open a pull request or post to a public thread by itself, it can only ask, in a shape this
module can check, and the answer is a review you approve.

The agent emits, anywhere in its transcript:

    TASKUARY-PROPOSE {"action": "open_pr", "why": "tests pass, ready for review"}

Unknown actions, bad shapes and unpermitted actions are REFUSED and recorded - a malformed
proposal is never a partially-executed one.
"""
import json, re
from loguru import logger

MARK = 'TASKUARY-PROPOSE'
BLOCK = re.compile(MARK + r'\s*(\{.*?\})', re.S)
MAX = 5                      # per transcript: a loop proposing 200 pushes is a bug, not intent

# action -> (what it does in words, required keys, the switch that must be ON for it to be
# proposable at all). Nothing here executes without an approved review.
ACTIONS = {
    # 'land' does whatever the owner's git_flow says (a draft PR, or straight onto the
    # default branch) - the agent asks to PUBLISH, the owner decides what publishing means.
    # open_pr / push_direct force one road for an agent that means one specifically.
    'land': ('publish this work (a draft pull request, or straight to the default branch - your setting)',
             (), 'agent_push_enabled'),
    'open_pr': ('open a DRAFT pull request for this task', (), 'agent_push_enabled'),
    'push_direct': ('push these commits STRAIGHT onto the default branch - no pull request',
                    (), 'agent_push_enabled'),
    'comment_issue': ('post a PUBLIC comment on the linked issue/PR', ('body',), 'github_reply'),
    'close_issue': ('close the linked GitHub issue', (), 'use_as_tracker'),
    'run_tool': ('run one query/script through a tool connection', ('type',), None),
    # the on-close "did this session do a kind of job that will recur?" answer (playbooks.draft),
    # and an agent that knows it did: a playbook is filed only past the owner's click
    'write_playbook': ('file a new PLAYBOOK - how this kind of job is done here - for the next agent to follow',
                       ('slug', 'text'), 'playbooks_enabled'),
    # An instruction that BELONGS in a switch should be written there, not left as a note the
    # classifier merely weighs - but nothing may change a switch on its own. So it arrives as a
    # proposal: the assistant says which switch it means, the owner's click applies it, and only the
    # keys below can ever be named (the owner, 2026-09-03: "yes do it that way ask user if it can
    # change setttings").
    'settings': ('change a setting you named - nothing else, and only once you approve it',
                 ('changes',), None),
}

# What a proposal may touch: routing and visibility only. Never a permission that lets anything OUT
# (agent_push_enabled, github_replies_ok, reply channels), never a token, key, model or document.
SETTING_ALLOW = {
    'coder_auto_enabled': 'start the coding agent automatically on new coding work',
    'auto_draft_enabled': 'write the reply draft in the background, before you look',
    'intent_classify_enabled': 'let the brain classify inbound mail at all',
    'answer_to_agent': 'what happens when an answer arrives for a waiting agent (auto / ask / off)',
    'poll_minutes': 'how often the mailboxes are read',
    'funnel_hours': 'how far back the pipe reaches',
    'funnel_max': 'how much the pipe holds at once',
    'timeline_fade': 'how old rows dim on the Timeline',
    'calendar_enabled': 'read your calendar',
    'learn_enabled': 'learn from your verdicts',
    'playbooks_enabled': 'let agents follow and propose playbooks',
    'agent_issues_enabled': 'treat GitHub issues as the tracker (off = GitHub items are Timeline rows, not tasks)',
}
# ...and the same rule for a CONNECTOR's own switches, which is where "PRs are Timeline items, not
# tasks" actually lives (store.github_permissions reads the connector first).
CONNECTOR_ALLOW = {'github': {'use_as_tracker': 'treat GitHub issues/PRs as the tracker'}}
SETTING_VALUES = {'answer_to_agent': ('auto', 'ask', 'off'), 'timeline_fade': ('none', 'soft', 'normal', 'strong')}


def _switch_ok(store, name) -> bool:
    if not name: return True
    if name in ('agent_push_enabled',): return store.get_settings().get(name) == '1'
    if name == 'playbooks_enabled': return store.get_settings().get(name, '1') == '1'
    import json as _j
    c = store.get_connector_by_type('github') or {}
    try: cfg = _j.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return bool(cfg.get({'github_reply': 'reply_comments'}.get(name, name)))


def parse(text: str) -> list:
    """Every well-formed proposal in a transcript. Junk is skipped, not guessed at."""
    out = []
    for m in BLOCK.finditer(text or ''):
        try: j = json.loads(m.group(1))
        except ValueError: continue
        a = str(j.get('action') or '').strip()
        if a in ACTIONS: out.append({**j, 'action': a})
        if len(out) >= MAX: break
    return out


def setting_changes(p: dict) -> tuple:
    """(changes, reason). Every named switch checked against the allow-list BEFORE it is proposed -
    so a proposal the owner sees is one that could actually be applied."""
    out = []
    for c in (p.get('changes') or []):
        if not isinstance(c, dict): return [], 'a change must be an object'
        conn, name, val = str(c.get('connector') or '').strip().lower(), str(c.get('name') or '').strip(), c.get('value')
        if conn:
            if name not in CONNECTOR_ALLOW.get(conn, {}): return [], f'{conn}.{name} is not a switch a proposal may touch'
            out.append({'connector': conn, 'name': name, 'value': bool(val), 'says': CONNECTOR_ALLOW[conn][name]})
            continue
        if name not in SETTING_ALLOW: return [], f'{name} is not a switch a proposal may touch'
        v = str('1' if val is True else '0' if val is False else val).strip()
        if name in SETTING_VALUES and v not in SETTING_VALUES[name]:
            return [], f'{name} must be one of {", ".join(SETTING_VALUES[name])}'
        if name in ('poll_minutes', 'funnel_hours', 'funnel_max') and not v.isdigit():
            return [], f'{name} must be a whole number'
        out.append({'name': name, 'value': v, 'says': SETTING_ALLOW[name]})
    return out, '' if out else 'no change was named'


def validate(store, p: dict) -> tuple:
    """(ok, reason). The whole gate: known action, required fields present, switch on."""
    a = p.get('action')
    if a not in ACTIONS: return False, f'unknown action {a!r}'
    words, need, switch = ACTIONS[a]
    if a == 'settings':
        changes, why = setting_changes(p)
        if not changes: return False, why
        return True, 'change ' + '; '.join(f"{c['name']} -> {c['value']}" for c in changes)
    missing = [k for k in need if not str(p.get(k) or '').strip()]
    if missing: return False, f'{a} needs {", ".join(missing)}'
    if not _switch_ok(store, switch):
        return False, f'{a} is not permitted - the owner has that switch off'
    return True, words


def collect(store, task_id: int, transcript: str, actor='coder') -> list:
    """Turn an agent's proposals into pending reviews. Returns what was queued; refusals are
    recorded on the task so a refused proposal is visible, not silently dropped."""
    return [m for p in parse(transcript) for m in [queue(store, task_id, p, actor)] if m]


def queue(store, task_id: int, p: dict, actor='coder') -> dict | None:
    """ONE proposal through the gate: a pending review when it validates, a recorded refusal (None) when not."""
    ok, why = validate(store, p)
    if not ok:
        store.add_comment(task_id, actor, 'agent', f'PROPOSAL REFUSED ({p.get("action")}): {why}')
        store.audit('task', task_id, 'proposal_refused', actor, detail={'action': p.get('action'), 'why': why})
        return None
    rid = store.add_review({'TaskId': task_id, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p),
                            'Reason': f'the agent proposes to {why}' + (f" - {p['why'][:200]}" if p.get('why') else '')})
    store.audit('review', rid, 'proposed', actor, detail={'action': p['action']})
    logger.info(f'task {task_id}: proposal queued - {p["action"]} (rv{rid})')
    return {'reviewId': rid, 'action': p['action']}


def execute(store, rv: dict, actor='owner', final_text: str = None) -> dict:
    """Run an APPROVED proposal. Called from the verdict road, and it re-validates: the
    switch may have gone off between proposing and approving, and the approval does not
    grant the permission.

    `final_text` is what was in the Review box when the owner approved. For a proposed
    playbook the box shows the page itself (not the JSON envelope), so an edited page is
    what gets filed - the owner tightening an `alone:` line before the first run is the point."""
    p = json.loads(rv.get('DraftText') or '{}')
    if p.get('action') == 'write_playbook' and str(final_text or '').strip() and not str(final_text).lstrip().startswith('{'):
        p['text'] = final_text
    ok, why = validate(store, p)
    if not ok: raise RuntimeError(f'refused at execution: {why}')
    tid, a = rv.get('TaskId'), p['action']
    if a in ('land', 'open_pr', 'push_direct'):
        from . import ci
        fn = {'land': ci.land, 'open_pr': ci.open_for_task, 'push_direct': ci.push_direct}[a]
        r = fn(store, tid, actor)
        out = {'pr': r.get('number'), 'branch': r.get('branch'), 'sha': (r.get('sha') or '')[:7],
               'url': r.get('url')}
        out = {k: v for k, v in out.items() if v}
    elif a in ('comment_issue', 'close_issue'):
        from . import github
        from .ci import _conn
        c, t = _conn(store), store.get_task(tid) or {}
        ref = str(t.get('SourceRef') or '')
        m = re.search(r'github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+)', ref)
        if not m: raise RuntimeError('this task carries no GitHub issue/PR to act on')
        repo, num = m.group(1), int(m.group(2))
        if a == 'comment_issue':
            url = github.comment_issue(c['Secret'], repo, num, p['body'])
            out = {'commented': f'{repo}#{num}', 'url': url}
        else:
            github.close_issue(c['Secret'], repo, num, p.get('body'))
            out = {'closed': f'{repo}#{num}'}
    elif a == 'settings':
        changes, why = setting_changes(p)
        if not changes: raise RuntimeError(why)
        done = []
        for c in changes:
            if c.get('connector'):
                conn = store.get_connector_by_type(c['connector'])
                if not conn: raise RuntimeError(f"no {c['connector']} connector to change")
                cfg = json.loads(conn.get('ConfigJson') or '{}')
                cfg[c['name']] = c['value']
                store.save_connector({**dict(conn), 'ConfigJson': json.dumps(cfg)}, actor)
                done.append(f"{c['connector']}.{c['name']} = {c['value']}")
            else:
                store.set_setting(c['name'], str(c['value']), actor)
                done.append(f"{c['name']} = {c['value']}")
        out = {'changed': done}
    elif a == 'write_playbook':
        from . import playbooks
        slug = playbooks.write(p['slug'], p['text'])
        out = {'playbook': slug, 'path': str(playbooks.folder() / f'{slug}.md')}
    else:                                   # run_tool
        from .reports import REGISTRY, resolve_cfg
        head, body = REGISTRY[p['type']](resolve_cfg(store, {k: v for k, v in p.items() if k != 'action'}))
        out = {'headline': str(head)[:200], 'output': (body or '')[:2000]}
    store.add_comment(tid, actor, 'human', f'APPROVED PROPOSAL ({a}): {json.dumps(out)[:600]}')
    store.audit('review', rv['ReviewId'], 'proposal_executed', actor, detail={'action': a, 'result': out})
    return out
