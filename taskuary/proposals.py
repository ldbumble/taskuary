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
from . import buttons

MARK = 'TASKUARY-PROPOSE'
BLOCK = re.compile(MARK + r'\s*(\{.*?\})', re.S)     # only for cutting junk a decode could not read (strip)
_DEC = json.JSONDecoder()


def spans(text: str):
    """(start, end, proposal-or-None) for every marker followed by a `{`. DECODED, not matched: a record nests
    objects ({"record": {"APBILLITEMS": [{...}]}}), and the lazy `{.*?}` this replaced stopped at the FIRST inner
    brace - every Intacct bill an agent proposed failed to parse and was dropped without a word, leaving a stray
    `}` in its report (found driving the AP portal workflow live, 2026-10-08). None = a marker nobody can read -
    still skipped, not reported: the seeds' own examples (`{"type": "<one of its tools>", ...}`) are such markers."""
    for m in re.finditer(re.escape(MARK) + r'\s*(?=\{)', text or ''):
        try: obj, end = _DEC.raw_decode(text, m.end())
        except ValueError: yield m.start(), m.end(), None; continue
        yield m.start(), end, obj if isinstance(obj, dict) else None


def strip(text: str) -> str:
    """The text with every proposal cut out - whole, nested braces and all - so none of it reaches a report."""
    text, out, at = text or '', [], 0
    for a, b, obj in spans(text):
        if obj is None: continue
        out.append(text[at:a]); at = b
    return BLOCK.sub('', ''.join(out) + text[at:])


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
    # the close-out of a task whose work is an open pull request (CLOSEOUT below): raised by the finish, never by an agent
    'merge_pr': ('merge the pull request this task opened', ('repo', 'number'), 'agent_push_enabled'),
    'run_tool': ('run one query/script through a tool connection', ('type',), None),
    # a workflow step that failed, fixed by the model on the owner's say-so (flow.repair): the new list is saved only past their yes
    'repair_workflow': ("change this workflow's steps to the repaired list", ('source_id', 'flow'), None),
    # the on-close "did this session do a kind of job that will recur?" answer (playbooks.draft),
    # and an agent that knows it did: a playbook is filed only past the owner's click
    'write_playbook': ('file a new PLAYBOOK - how this kind of job is done here - for the next agent to follow',
                       ('slug', 'text'), 'playbooks_enabled'),
    # what the outcome ledger counted about a kind of work, as a block on its playbook (playbook_facts.py): reflection proposes it,
    # the owner's yes writes it - a derived line never edits a playbook on its own (spec 2026-10-12, build step 5)
    'amend_playbook': ('add what the ledger learned to a playbook', ('slug', 'text'), 'playbooks_enabled'),
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
    'coding_auto_enabled': 'start the coding agent automatically on new coding work',
    'intent_classify_enabled': 'let the brain classify inbound mail at all',
    'answer_to_agent': 'what happens when an answer arrives for a waiting agent (auto / ask / off)',
    'poll_minutes': 'how often the mailboxes are read',
    'funnel_hours': 'how far back the pipe reaches',
    'funnel_max': 'how much the pipe holds at once',
    'task_return_minutes': 'how long an open task you cleared stays quiet before it comes back',
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
    if name in ('agent_push_enabled',): return store.get_setting(name) == '1'
    if name == 'playbooks_enabled': return store.get_setting(name, '1') == '1'
    import json as _j
    c = store.get_connector_by_type('github') or {}
    try: cfg = _j.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return bool(cfg.get({'github_reply': 'reply_comments'}.get(name, name)))


def parse(text: str) -> list:
    """Every well-formed proposal in a transcript. Junk is skipped, not guessed at."""
    out = []
    for _, _, j in spans(text):
        if j is None: continue
        a = str(j.get('action') or '').strip()
        # a merge is the owner's close-out, never an agent's ask - and no agent may mark its own ask as one
        if a in ACTIONS and a != 'merge_pr': out.append({**{k: v for k, v in j.items() if k != 'closeout'}, 'action': a})
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
        if name in ('poll_minutes', 'funnel_hours', 'funnel_max', 'task_return_minutes') and not v.isdigit():
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
    # A CLOSE-OUT IS THE OWNER'S OWN ACT (the owner, 2026-09-27: "ask me before merge then do it"): the switches gate what
    # an AGENT may ask for; the owner pressing Merge or Close issue on their own task needs no agent permission turned on.
    # Only Taskuary raises one (parse strips the mark from anything an agent wrote).
    if not p.get('closeout') and not _switch_ok(store, switch):
        return False, f'{a} is not permitted - the owner has that switch off'
    return True, words


def collect(store, task_id: int, transcript: str, actor='agent') -> list:
    """Turn an agent's proposals into pending reviews. Returns what was queued; refusals are
    recorded on the task so a refused proposal is visible, not silently dropped."""
    return [m for p in parse(transcript) for m in [queue(store, task_id, p, actor)] if m]


def queue(store, task_id: int, p: dict, actor='agent') -> dict | None:
    """ONE proposal through the gate: a pending review when it validates, a recorded refusal (None) when not."""
    ok, why = validate(store, p)
    if not ok:
        store.add_comment(task_id, actor, 'agent', f'PROPOSAL REFUSED ({p.get("action")}): {why}')
        store.audit('task', task_id, 'proposal_refused', actor, detail={'action': p.get('action'), 'why': why})
        return None
    # a close-out is not the agent's ask ("proposes to merge the pull request this task opened" was said of a stranger's PR)
    reason = (f"the close-out: {'merge pull request #' + str(p.get('number')) if p['action'] == 'merge_pr' else 'close the issue it came from'}"
              if p.get('closeout') else f'the agent proposes to {why}' + (f" - {p['why'][:200]}" if p.get('why') else ''))
    rid = store.add_review({'TaskId': task_id, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p), 'Reason': reason})
    store.audit('review', rid, 'proposed', actor, detail={'action': p['action']})
    logger.info(f'task {task_id}: proposal queued - {p["action"]} (rv{rid})')
    return {'reviewId': rid, 'action': p['action']}


# ── the close-out ────────────────────────────────────────────────────────────────────────
# What FINISHES a task depends on where it lives (the owner, 2026-09-27): mail is closed out by the reply, a pull
# request the agent opened by merging it, an issue by closing it with a comment - each the same yes-gated review as any
# proposal, raised by wrapup.finish; approving it runs that act alone, and Mark done is still the owner's (2026-10-18). The
# words (the summary, the closing comment) are the card's text; the act is plain code on the owner's click.
# ONE button word for every system (the owner, 2026-09-27: "if we have button to close out per system it will be endless")
# - approve, as it shows on an agent's proposal (buttons.json: Approve) - and per action only the sentence saying what it does
# there. A new connector adds a line here, never a word.
CLOSE_WORD = buttons.label('approve', 'action')
CLOSEOUT = {'merge_pr': 'merges the pull request on GitHub', 'close_issue': 'closes the issue on GitHub'}
_ISSUE = re.compile(r'github\.com/([^/]+/[^/]+)/issues/(\d+)')
_PULL = re.compile(r'github\.com/([^/]+/[^/]+)/pull/(\d+)')


def closeout_pending(store, tid: int):
    """The task's close-out still waiting on the owner, if any."""
    return next((r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
                 if _action(r) in CLOSEOUT), None)


# ── close-out and playbook are TWO things (the owner, 2026-10-01) ────────────────────────────────────────────────────
# Neither closes the task: its close-out (the reply sent, the pull request merged or closed, the issue closed) and the
# playbook proposal its agent left (approved or dismissed) are each said on the task, and only the owner's Mark done closes it
# (2026-10-18: "sending and closing are two steps, never automatic"). A sent reply used to dismiss the undecided playbook.
PLAYBOOK = 'write_playbook'


def playbook_pending(store, tid: int):
    """The playbook proposal still waiting on the owner's approve or dismiss, if any."""
    return next((r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
                 if _action(r) == PLAYBOOK), None)


def owed(store, tid: int) -> bool:
    """Something of the close-out still waits on the owner: a reply, a close-out act, any other proposal - not the playbook."""
    return any(_action(r) != PLAYBOOK for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,)))


def closed_out(store, tid: int, actor: str, said: str) -> bool:
    """The close-out is done: said on the task, with what still waits (its emails, its playbook). The task STAYS OPEN - only
    the owner's Mark done closes it (the owner, 2026-10-18: "sending and closing are two steps, never automatic"); this used
    to close it whenever nothing else waited. False always: nothing closed."""
    from . import slots
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return False
    n = len(slots.open_(store, tid))
    store.audit('task', tid, 'closed_out', actor)
    rest = (f" {n} email{'s' if n != 1 else ''} still to go." if n else ' Its playbook still waits on your approve or dismiss.' if playbook_pending(store, tid)
            else f" {buttons.label('close')} when the task is finished.")
    store.add_comment(tid, actor, 'human', f'{said}{rest}')
    return False


def _action(rv) -> str:
    try: return str(json.loads((rv or {}).get('DraftText') or '{}').get('action') or '')
    except (TypeError, ValueError): return ''


def closeout_due(store, tid: int):
    """The close-out this task's finish owes, as the proposal to queue - None when there is none (no open pull
    request, no issue). The pull request is the one the agent opened, else the one the task CAME from - a
    contributor's PR the agent reviewed ends by merging or closing it just the same."""
    from . import ci, ghcloseout
    at, ref = ci.landing_of(store, tid) or {}, str((store.get_task(tid) or {}).get('SourceRef') or '')
    src = _PULL.search(ref)
    own = at.get('kind') == 'pr' and at.get('state') != 'closed' and not at.get('merged')
    if own or src:
        repo, num, sha = (at.get('repo'), at.get('number'), at.get('sha')) if own else (src.group(1), int(src.group(2)), None)
        # the GitHub card's choice: "Close out on a pull request = only close the task" leaves the PR to you
        if ghcloseout.cfg(store, repo)['pr'] != 'merge': return None
        # the mark is what was true when the PR opened; the head and the state are read now, so the card neither offers
        # a merge that already happened nor pins a commit older than the last push
        try:
            from . import github
            cur = github.pr(ci._conn(store)['Secret'], repo, num)
            if cur.get('state') == 'closed': return None
            sha = cur.get('sha') or sha
        except Exception as e: logger.warning(f'task {tid}: the pull request could not be read before its close-out ({e})')
        # `sha` pins the head the card describes: a commit pushed after it was raised is GitHub's 409, not a silent merge
        # `theirs`: the task came from this PR - somebody else's work, so GitHub writes its merge message, not our summary
        p = {'action': 'merge_pr', 'repo': repo, 'number': num, 'sha': sha, 'closeout': True, **({} if own else {'theirs': True}),
             'why': f'pull request #{num} is open'}
    elif _ISSUE.search(ref):
        if not ghcloseout.cfg(store, _ISSUE.search(ref).group(1))['issue']: return None
        p = {'action': 'close_issue', 'closeout': True, 'why': 'the issue this task came from is still open'}
    else: return None
    return p if validate(store, p)[0] else None


def backfill(store) -> int:
    """Tasks an agent finished BEFORE the close-out existed are waiting on a reply alone, and their pull request is
    still open with nothing asking to merge it (the owner, 2026-09-27: "don't see the merge PR button?"). Each sync
    offers their close-out once; a task that was ever offered one is never asked about again."""
    from . import ci, funnel
    busy, n = funnel.working_tids(store), 0
    for t in store.list_tasks():
        tid, ref = t['TaskId'], str(t.get('SourceRef') or '')
        # waiting on its reply, or a saved session whose answer is drafted - finished work either way (TQ-0767)
        if t.get('Status') not in ('waiting', 'open') or tid in busy: continue
        if t.get('Status') == 'open' and not store._one("SELECT 1 x FROM review WHERE TaskId=? AND Status='pending' AND Kind<>'action'", (tid,)): continue
        if not (_PULL.search(ref) or _ISSUE.search(ref) or (ci.landing_of(store, tid) or {}).get('kind') == 'pr'): continue
        if not _report(store, tid) and not any(str(c.get('Body') or '').startswith('The agent closed this itself') for c in store.list_comments(tid)): continue
        if store._rows("SELECT 1 x FROM review WHERE TaskId=? AND Kind='action' AND DraftText LIKE '%\"closeout\": true%'", (tid,)): continue
        due = closeout_due(store, tid)
        if due and closeout(store, tid, due, '' if due.get('theirs') or due['action'] == 'close_issue' else _report(store, tid), 'router'):
            n += 1
    return n


def _report(store, tid: int) -> str:
    """The agent's filed result - the summary a close-out raised after the finish carries."""
    from .wrapup import is_report, report_body
    b = next((report_body(c.get('Body')) for c in reversed(store.list_comments(tid)) if is_report(c.get('Body'))), '')
    return b.split('\n\nLAST MESSAGE', 1)[0].strip()


def closeout(store, tid: int, p: dict, text: str = '', actor='agent'):
    """Queue the close-out `closeout_due` named. `text` is what the card shows and the owner may edit:
    the summary a merge is squashed with, or the comment an issue is closed with."""
    if closeout_pending(store, tid): return None
    return queue(store, tid, {**p, 'text': (text or '').strip()}, actor)


def settle(store, rv: dict, verb: str, actor='owner') -> None:
    """After the owner answered a proposal: Approve ran only that act (the owner, 2026-10-18) - the task stays open for Mark
    done, and is said to be on them once nothing else of it waits; "not yet" on a close-out leaves it open and on them."""
    tid = rv.get('TaskId')
    if not tid or _action(rv) == PLAYBOOK: return
    # a pull request opened on the owner's yes AFTER the agent finished is still a task that ends by merging it
    if _action(rv) in ('land', 'open_pr') and verb in ('approve', 'edit') and (store.get_task(tid) or {}).get('Status') != 'dropped':
        due = closeout_due(store, tid)
        if due and due['action'] == 'merge_pr' and closeout(store, tid, due, _report(store, tid), actor):
            store.update_task(tid, {'Status': 'waiting'}, actor)
        return
    if _action(rv) not in CLOSEOUT:
        # a proposal a finished agent left waiting (wrapup.finish): once the last one is answered, yes or no, the task is
        # back on the owner - open, nobody else's turn - for their Mark done. It used to close here.
        if (store.get_task(tid) or {}).get('Status') == 'waiting' and not owed(store, tid) and \
                store._one("SELECT 1 x FROM audit WHERE EntityType='task' AND EntityId=? AND Action='awaits_proposals' LIMIT 1", (tid,)):
            store.update_task(tid, {'Status': 'open'}, actor)
            closed_out(store, tid, actor, 'Every proposal is answered.')
        return
    if verb not in ('approve', 'edit'):
        store.update_task(tid, {'Status': 'open'}, actor)
        return
    if owed(store, tid): return
    closed_out(store, tid, actor, 'Closed out.')


def close_pr(store, rv: dict, actor='owner') -> dict:
    """The merge close-out's other answer: the work is not wanted, so the pull request is closed on GitHub without
    merging (the owner, 2026-09-27). The owner's own act, like the merge - and like it, it leaves the task open for Mark done."""
    p = json.loads(rv.get('DraftText') or '{}')
    if p.get('action') != 'merge_pr': raise RuntimeError('only a pull request close-out can be closed without merging')
    ok, why = validate(store, p)
    if not ok: raise RuntimeError(f'refused at execution: {why}')
    from . import ci, github
    c, repo, num = ci._conn(store), p['repo'], int(p['number'])
    cur = github.pr(c['Secret'], repo, num)
    if cur.get('merged'): raise RuntimeError(f'#{num} is already merged on GitHub - nothing to close')
    if cur.get('state') != 'closed': github.close_pr(c['Secret'], repo, num)
    if ci.pr_of(store, rv['TaskId']): ci._save_pr(store, rv['TaskId'], {**ci.pr_of(store, rv['TaskId']), 'state': 'closed', 'merged': False}, actor)
    out = {'closed': f'{repo}#{num}', 'merged': False}
    store.add_comment(rv['TaskId'], actor, 'human', f'Closed pull request {repo}#{num} without merging it.')
    store.audit('review', rv['ReviewId'], 'pr_closed_unmerged', actor, detail=out)
    return out


from .ghcloseout import Refused as ChecksRed      # a close-out GitHub's state refuses now, with what the card may offer instead


def execute(store, rv: dict, actor='owner', final_text: str = None, skip_checks: bool = False) -> dict:
    """Run an APPROVED proposal. Called from the verdict road, and it re-validates: the
    switch may have gone off between proposing and approving, and the approval does not
    grant the permission.

    `final_text` is what was in the Review box when the owner approved. For a proposed
    playbook the box shows the page itself (not the JSON envelope), so an edited page is
    what gets filed - the owner tightening an `alone:` line before the first run is the point."""
    p = json.loads(rv.get('DraftText') or '{}')
    edited = str(final_text or '').strip() and not str(final_text).lstrip().startswith('{')
    if edited and (p.get('action') in ('write_playbook', 'amend_playbook') or (p.get('action') in CLOSEOUT and p.get('text'))):
        p['text'] = final_text.strip()
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
            github.close_issue(c['Secret'], repo, num, p.get('body') or p.get('text'))
            out = {'closed': f'{repo}#{num}'}
    elif a == 'merge_pr':
        from . import ci, github, ghcloseout
        c, repo, num = ci._conn(store), p['repo'], int(p['number'])
        # GITHUB'S STATE DECIDES, the same reading that drew the card (ghcloseout.assess): what this repo's rules say about
        # this pull request, never our guess at them. "Close out anyway" passes only what the card offered it for.
        seen = ghcloseout.assess(store, repo, num)
        cur = seen['pr']
        if seen['state'] == 'merged': out = {'merged': f'{repo}#{num}', 'already': True}
        elif seen['state'] == 'closed': raise RuntimeError(f'#{num} was closed on GitHub without merging - nothing to merge')
        else:
            if not seen['ok'] and not (skip_checks and 'anyway' in seen['offers']):
                raise ChecksRed(seen['reason'] + ' - nothing was merged or sent', seen['offers'])
            # the PR's own title leads the squash (GitHub's default); the summary, when there is one, is its body
            try:
                sha = github.merge_pr(c['Secret'], repo, num, p.get('sha') or cur['sha'], None, p.get('text') or None,
                                      method=seen['method'], p=cur)
            except github.Refused as e:
                github.learn(c['Secret'], repo, e)          # the next card reads the grant GitHub just named as missing
                raise
            out = {'merged': f'{repo}#{num}', 'sha': sha[:7], 'url': cur.get('url'), 'method': seen['method'],
                   **({'note': seen['note']} if seen['note'] else {})}
        if ci.pr_of(store, tid): ci._save_pr(store, tid, {**ci.pr_of(store, tid), 'state': 'closed', 'merged': True}, actor)
        if not out.get('already'):                   # the ledger: still merged in two weeks? (an already-merged PR was not our act)
            from . import outcomes
            outcomes.record(store, 'pr.merged', 'task', tid, actor, facts={'pr': num})
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
    elif a in ('write_playbook', 'amend_playbook'):
        from . import playbooks
        if a == 'amend_playbook' and p.get('block') and not edited:      # the ledger's block onto the page as it is NOW (playbook_facts)
            from .people_pages import splice
            p['text'] = splice(playbooks.read(p['slug']) or p['text'], p['block'])
        slug = playbooks.write(p['slug'], p['text'])
        out = {'playbook': slug, 'path': str(playbooks.folder() / f'{slug}.md')}
    elif a == 'repair_workflow':
        from . import flow
        if not isinstance(p.get('flow'), list): raise RuntimeError('the repaired steps are not a list')
        d = flow.apply(store, p['source_id'], p['flow'], actor, p.get('why') or '')       # re-validated there, and audited
        out = {'workflow': int(p['source_id']), 'changed': flow.diff_text(d)[:1200]}
    else:                                   # run_tool
        from .reports import REGISTRY, resolve_cfg
        # the owner approved THIS query, so it may commit - the one road to a write on a read-level SQL card
        head, body = REGISTRY[p['type']](resolve_cfg(store, {**{k: v for k, v in p.items() if k != 'action'}, '_write': True}))
        out = {'headline': str(head)[:200], 'output': (body or '')[:2000]}
    if tid: store.add_comment(tid, actor, 'human', f'APPROVED PROPOSAL ({a}): {json.dumps(out)[:600]}')   # a task-less one has no card to say it on
    store.audit('review', rv['ReviewId'], 'proposal_executed', actor, detail={'action': a, 'result': out})
    return out
