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
import json, re, time
from .say import said as _said            # a failure written to the chat is said in his words (say.py)
from loguru import logger
from .timewords import plural
from . import buttons, words

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
    # ...and the brackets a marker was written in (round 4, 2026-11-22: "[[TASKUARY-PROPOSE {...}]]" left "[[]]" - an answer that was not empty,
    # so the line saying the proposal was not put on a card never showed: a dead end)
    return re.sub(r'\[\[\s*\]\]', '', BLOCK.sub('', ''.join(out) + text[at:]))


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
    'run_tool': ('run a step in a connected system', ('type',), None),
    # the close-out of a task from a Jira, Monday or Linear item (trackers.py, 2026-10-25): its comment, and the move to done - raised by
    # the finish like merge_pr, never by an agent (an agent's own comment or move is a run_tool on jira_comment, linear_move, ...)
    'close_item': ('comment on the tracker item this task came from and move it to done', ('tracker', 'item'), None),
    # a workflow step that failed, fixed by the model on the owner's say-so (flow.repair): the new list is saved only past their yes
    'repair_workflow': ("change this workflow's steps to the repaired list", ('source_id', 'flow'), None),
    'change_setup': ("change a report's or dashboard's setup", ('source_id', 'patch'), None),
    # the on-close "did this session do a kind of job that will recur?" answer (playbooks.draft),
    # and an agent that knows it did: a playbook is filed only past the owner's click
    'write_playbook': ('file a new PLAYBOOK - how this kind of job is done here - for the next agent to follow',
                       ('slug', 'text'), 'playbooks_enabled'),
    # what the outcome ledger counted about a kind of work, as a block on its playbook (playbook_facts.py): reflection proposes it,
    # the owner's yes writes it - a derived line never edits a playbook on its own (spec 2026-10-12, build step 5)
    # ...and lessons onto a playbook page (playbooks.with_lessons, the owner 2026-11-05)
    'amend_playbook': ('add what was learned to a playbook', ('slug', 'text'), 'playbooks_enabled'),
    # An instruction that BELONGS in a switch should be written there, not left as a note the
    # classifier merely weighs - but nothing may change a switch on its own. So it arrives as a
    # proposal: the assistant says which switch it means, the owner's click applies it, and only the
    # keys below can ever be named (the owner, 2026-09-03: "yes do it that way ask user if it can
    # change setttings").
    'settings': ('change a setting you named - nothing else, and only once you approve it',
                 ('changes',), None),
    # a browser act that can't be undone, HELD before it ran (browsergate.py, 2026-10-25): raised only by the shell hook, never an
    # agent's marker - approving it runs that exact command in that task's browser, on the page it was held on
    'browser_act': ("do this in the agent's browser", ('sid', 'args'), None),
    # ...and a shell step that leaves the machine - a push, a merge, a public post, a publish, a mail - HELD the same way (shellgate.py,
    # the owner's ruling 2026-10-28): raised only by the shell hook; approving it runs that exact command in the folder it was held in
    # ...or, a read outside the task's folders with no command (readgate.py), lets the task read those folders
    'shell_act': ("run this step of the agent's", ('sid',), None),
    # ...and a desktop act that can't be undone, HELD the same way (agentdesktop.py, 2026-10-31): approving it runs that exact command
    'desktop_act': ("do this in an app on the owner's desktop", ('sid', 'args'), None),
    # A PART OF THE TASK THAT IS ANOTHER JOB (the owner, 2026-11-10: "random things that triage puts in one task that doesn't belong really,
    # (where agent should suggest break out to new task)"): the agent names what goes, the owner's press runs the task page's own split
    # (reshape.split_task) - nothing moves before it
    'break_out': ('break part of this task out into a task of its own', ('title',), None),
    # A SCRIPT WRITTEN ON THE JOB, KEPT AS A ROUTINE (the owner, 2026-11-10: "agent should be able to after building one should say should
    # we save this"): the card shows the script whole, and the owner's press is the save (workflows.save_script_routine) - nothing is
    # saved or run before it, and it is the one door by which an agent's script ever reaches a schedule
    'save_routine': ('save this routine or report', ('title',), None),
}
FAILED_NOTE = 'failed'      # a pressed act that failed: settled, its error kept (ActError) - its agent sets up what goes next
HELD_ACTS = ('browser_act', 'shell_act', 'desktop_act')     # raised by a hook before the act ran - never an agent's marker
# ...each by its own gate, which runs it on the owner's yes (perform) and tells its agent their no (declined) - and where it was held, as its
# card says it. One table: the card's reason (queue), the yes (execute) and the no (settle) each spelled the three out
HELD_IN = {'browser_act': "in the agent's browser", 'shell_act': "in the agent's shell", 'desktop_act': 'on your desktop'}
def _gate(a: str):
    from . import agentdesktop, browsergate, shellgate
    return {'browser_act': browsergate, 'shell_act': shellgate, 'desktop_act': agentdesktop}[a]
# WHAT NO AGENT MAY ASK FOR, AND THE MARKS NONE MAY PUT ON ITS OWN ASK - one list for both doors: the marker (parse) and the tool
# (agenttools.proposal_of). They were two, and had drifted (the spine audit, 2026-11-09): the tool's did not name the held steps, so an agent
# could file a "held step" of its own - a command of its choosing, on the card the owner reads as one Taskuary stopped
NOT_ASKED = ('merge_pr', 'close_item', 'repair_workflow', 'change_setup', *HELD_ACTS)
MARKS = ('closeout', 'flow_run')

# A POST IS DRAWN AS THE POST (the owner, 2026-11-05: "it's not showing the post and the image as a linkedin post and asking me if i want to
# post it"): a run_tool on one of these is the owner's words on a network, so its card shows them as a post, editable, with the picture
# where the network takes one - and what the owner left in the box is what goes. MEDIA: the ones that carry a picture from here.
POSTS = {'linkedin_post': 'LinkedIn', 'bluesky_post': 'Bluesky', 'mastodon_post': 'Mastodon', 'reddit_post': 'Reddit', 'x_post': 'X'}
MEDIA = {'linkedin_post', 'x_post'}


def is_post(p: dict) -> bool: return (p or {}).get('action') == 'run_tool' and (p or {}).get('type') in POSTS
# A POST ON A NETWORK NOT CONNECTED IS STILL ITS CARD, AND ITS PRESS HANDS IT TO THE AGENT FOR THE SITE (the owner, 2026-11-22: "card first,
# sign-in at the press"): the agent went to LinkedIn's sign-in before writing a word, then gave the posts back as prose. The card stands with
# the words and picture; Post via the browser saves them as he left them, once (decide_review takes one press), and hands them to its agent,
# whose final Post on the site the browser gate holds for his yes
BROWSER_POST = ('The owner pressed Post via the browser on your {network} post card. Post exactly these words on {network} in your browser'
                '{pic}: "{words}". If the site wants him signed in, hand him its sign-in; then press its final Post - Taskuary holds that press '
                'for his yes.')
def via_browser(store, rid: int, text: str, actor: str = 'owner') -> dict:
    "Post via the browser: {ok, status, told} - the post saved as he left it and handed to its agent; never twice, never a card that is not a post."
    rv = store.get_review(int(rid)) or {}
    try: p = json.loads(rv.get('DraftText') or '{}')
    except ValueError: p = {}
    if not is_post(p): return {'ok': False, 'why': 'Only a post goes through the browser.'}
    words = str(text if str(text or '').strip() else p.get('text') or '').strip()
    if not words: return {'ok': False, 'why': 'The post has no words to put up.'}
    p = {**p, 'text': words, 'result': {'browser': True}}
    if not store.decide_review(int(rid), 'approved', json.dumps(p), actor):
        return {'ok': True, 'status': (store.get_review(int(rid)) or {}).get('Status'), 'already': True}
    from . import general, outputs
    pic = f" with the picture {outputs.folder(int(rv['TaskId'])) / p['image']}" if p.get('image') else ''
    told = general.to_agent(store, int(rv['TaskId']), BROWSER_POST.format(network=POSTS[p['type']], pic=pic, words=words), actor, start=True)
    return {'ok': True, 'status': 'approved', 'told': told}


def picture_why(tid, p: dict) -> str:
    """'' when a post's `image` is a picture in the task's own folder it can carry; else what is wrong, said to the agent."""
    if not p.get('image'): return ''
    from . import linkedin, outputs
    # ...EVERY POST CARD CARRIES ITS PICTURE (the owner, 2026-11-20): one Taskuary cannot upload to that network (MEDIA) is shown on the card to
    # save and add by hand, never refused - the card says so (ActionCard)
    f = outputs.named(int(tid), p['image']) if tid else None
    if not f: return f"{p['image']} is not a file in your task folder - save the picture there first"
    if f.suffix.lower() not in linkedin.IMAGE_TYPES: return f'{f.name} is not a PNG, JPG or GIF picture'
    return ''


def _edited(p: dict, final_text, fields: dict = None) -> dict:
    """An act's box IS its words: what the owner left there is what goes (an empty box is not a post, so it stays as proposed) - in the key
    its catalogue card edits (a post's `text`, a tracker comment's `body`). `fields`: the choices the owner changed on the card (who sees a
    post, post now or save as draft), only those the card declares editable (connectorcatalog.owner_edits)."""
    from . import connectorcatalog as cat
    t, act = str(final_text or '').strip(), cat.action_for((p or {}).get('type')) if (p or {}).get('action') == 'run_tool' else None
    k = cat.text_key(act) or ('text' if is_post(p) else None)
    if k and t and not t.startswith('{'): p = {**p, k: t}
    return cat.owner_edits(p, fields) if fields else p


def _ran(res) -> dict:
    """An executor's answer as the card reads it: (headline, body), or the {rows, columns} a connector returns - its first row's
    link the place it landed. Unpacking that dict as a pair read its two KEYS: a LinkedIn post said "rows" / "columns"."""
    if isinstance(res, dict):
        rows = res.get('rows') or []
        first = rows[0] if rows and isinstance(rows[0], dict) else {}
        return {k: v for k, v in {'headline': str(res.get('headline') or f"{len(rows)} row{'s' * (len(rows) != 1)}")[:200],
                                  'output': json.dumps(rows, default=str)[:2000], 'url': first.get('url') or ''}.items() if v}
    head, body = res
    return {'headline': str(head)[:200], 'output': (body or '')[:2000]}


def receipt(rv: dict, final_text, out: dict, fields: dict = None) -> str:
    """What an approved proposal keeps as its FinalText: as proposed, with the owner's edit and what it did - so a post still says
    "Posted" and its link when the chat is read again."""
    try: p = json.loads(rv.get('DraftText') or '{}')
    except ValueError: return rv.get('DraftText')
    # ...every act keeps what it did, so its card reads as its result once pressed - "Approved · ran", its link (the owner, 2026-11-09)
    return json.dumps({**(_edited(p, final_text, fields) if p.get('action') == 'run_tool' else p), 'result': out}, default=str)

# What a proposal may touch: routing and visibility only. Never a permission that lets anything OUT
# (agent_push_enabled, github_replies_ok, reply channels), never a token, key, model or document.
SETTING_ALLOW = {
    'coding_auto_enabled': 'start the coding agent automatically on new coding work',
    'intent_classify_enabled': 'let the brain classify inbound mail at all',
    'answer_to_agent': 'what happens when an answer arrives for a waiting agent (auto / ask / off); off also keeps new work on a task out of its live agent',
    'poll_minutes': 'how often the mailboxes are read',
    'funnel_hours': 'how far back the pipe reaches',
    'funnel_max': 'how much the pipe holds at once',
    'calendar_enabled': 'read your calendar',
    'playbooks_enabled': 'let agents follow and propose playbooks',
    'agent_issues_enabled': 'treat GitHub issues as the tracker (off = GitHub items are rows on the work rail, not tasks)',
}
# ...and the same rule for a CONNECTOR's own switches, which is where "PRs are Timeline items, not
# tasks" actually lives (store.github_permissions reads the connector first).
CONNECTOR_ALLOW = {'github': {'use_as_tracker': 'treat GitHub issues/PRs as the tracker'}}
SETTING_VALUES = {'answer_to_agent': ('auto', 'ask', 'off')}   # timeline_fade retired with the Timeline (audit, 2026-11-05)


# A REFUSAL NAMES THE SWITCH THAT REFUSED, AND OPENS IT (design round 2, 2026-11-18): "the owner has that switch off" named none, and an agent
# told the owner to "turn on pull requests under Policies" - a page of mail rules with no such switch. Each switch by its label where the owner
# sees it, and the link that opens that place; GitHub's are read where its card keeps them (store.github_permissions), never a second copy
SWITCHES = {'agent_push_enabled': ('Agents may push / deploy', 'the GitHub card', '#connector=github'),
            'use_as_tracker': ('GitHub is the issue tracker', 'the GitHub card', '#connector=github'),
            'github_reply': ('Reply to issue/PR authors', 'the GitHub card', '#connector=github'),
            'playbooks_enabled': ('Use playbooks', words.name('sorting'), words.href('sorting') + '&key=playbooks_enabled')}
def _switch_ok(store, name) -> bool:
    if not name: return True
    if name == 'agent_push_enabled': return store.github_permissions()[1]
    if name == 'use_as_tracker': return store.github_permissions()[0]
    if name == 'playbooks_enabled': return store.get_setting(name, '1') == '1'
    import json as _j
    c = store.get_connector_by_type('github') or {}
    try: cfg = _j.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return bool(cfg.get({'github_reply': 'reply_comments'}.get(name, name)))
def switch_off(name) -> str:
    "The switch `name` said as the owner finds it, with its link: what an agent passes on, never a place of its own guessing."
    label, where, href = SWITCHES[name]
    return f'"{label}" is off on {where} - [open it]({href}); only the owner turns it on'


def parse(text: str) -> list:
    """Every well-formed proposal in a transcript. Junk is skipped, not guessed at."""
    out = []
    for _, _, j in spans(text):
        if j is None: continue
        a = str(j.get('action') or '').strip()
        # a merge is the owner's close-out, never an agent's ask - and no agent may mark its own ask as one. A workflow repair is
        # raised by the run itself (flow._repair_now): an agent that read a mail asking for one could rewrite any workflow, with
        # its own words for what changes on the card the owner approves
        # ...and `flow_run` is the run a workflow's own write waits in: an agent's run_tool naming one would mark that step done
        if (a in ACTIONS or a in ('push', 'deploy')) and a not in NOT_ASKED: out.append({**{k: v for k, v in j.items() if k not in MARKS}, 'action': a})
        if len(out) >= MAX: break
    return out


def setting_changes(p: dict) -> tuple:
    """(changes, reason). Every named switch checked against the allow-list BEFORE it is proposed -
    so a proposal the owner sees is one that could actually be applied."""
    out, got = [], p.get('changes') or []
    # ...{switch: value} is the same changes written as one object - read as such: its keys came through below as "a change must be an object"
    if isinstance(got, dict): got = [got] if 'name' in got else [{'name': k, 'value': v} for k, v in got.items()]
    for c in (got if isinstance(got, list) else [got]):
        if not isinstance(c, dict): return [], 'each change is {"name": a switch, "value": its new value} - {"connector", "name", "value"} for a connection\'s own switch'
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


def unknown_tool(t) -> str:
    "Why `t` is no tool a run_tool can run - '' when it is one; the names nearest it said so the agent can propose it again."
    from .reports import REGISTRY
    t = str(t or '').strip()
    if not t or t == 'mcp' or t in REGISTRY: return ''
    near = sorted(k for k in REGISTRY if k.startswith(t) or t in k)[:6]
    return f"there is no tool {t!r}" + (f" - did you mean {', '.join(near)}?" if near else '')


def validate(store, p: dict) -> tuple:
    """(ok, reason). The whole gate: known action, required fields present, switch on."""
    a = p.get('action')
    if a not in ACTIONS: return False, f'unknown action {a!r}'
    words, need, switch = ACTIONS[a]
    if a == 'settings':
        changes, why = setting_changes(p)
        if not changes: return False, why
        return True, 'change ' + '; '.join(f"{c['name']} -> {c['value']}" for c in changes)
    # ...an MCP call is a call to one of its server's tools: none named could only fail at the press
    missing = [k for k in (*need, *(('tool',) if a == 'run_tool' and p.get('type') == 'mcp' else ())) if not str(p.get(k) or '').strip()]
    if missing: return False, f'{a} needs {", ".join(missing)}'
    # ...A TOOL THAT IS NOT ONE IS REFUSED TO ITS AGENT NOW, NEVER AT HIS PRESS (the Hydrogen walk, 2026-11-19: a card for a tool named
    # "linkedin" raised, its Approve answered "Failed 'linkedin'" - and nothing before the press said LinkedIn was not connected)
    if a == 'run_tool' and (bad := unknown_tool(p.get('type'))): return False, bad
    # NOTHING EMPTY IS PUT IN FRONT OF THE OWNER: a playbook that could not be filed, or says nothing of how the job is done, is refused at
    # this one gate - the tool, a marker in the agent's words, the on-close question - and its writer is told what it lacks
    if a == PLAYBOOK:
        from . import playbooks
        try: playbooks.check(str(p.get('text') or ''))
        except ValueError as e: return False, str(e)
    from . import trackers
    if (a == 'close_item' or p.get('type') in trackers.TYPES) and (why := trackers.check(p)): return False, why
    # A CLOSE-OUT IS THE OWNER'S OWN ACT (the owner, 2026-09-27: "ask me before merge then do it"): the switches gate what
    # an AGENT may ask for; the owner pressing Merge or Close issue on their own task needs no agent permission turned on.
    # Only Taskuary raises one (parse strips the mark from anything an agent wrote).
    if not p.get('closeout') and not _switch_ok(store, switch):
        return False, f'{a} is not permitted - {switch_off(switch)}'
    return True, words


def collect(store, task_id: int, transcript: str, actor='agent', refused: list | None = None) -> list:
    """Turn an agent's proposals into pending reviews. Returns what was queued; refusals are
    recorded on the task so a refused proposal is visible, not silently dropped.
    ...AND HEARD (the stress round, 2026-11-10): a mark is read once its turn is over, so the agent that wrote it got no answer - a
    refused one was a line on the task it never saw, under an answer that said "Proposed - it waits on the task for your yes". Each
    refusal is kept as one its agent has not heard (unheard) for its next turn, and appended to `refused` for the caller's own words."""
    from . import landing                         # ...a git act is the landing card's buttons where the task has work to land
    def one(p):
        try: return None if landing.from_proposal(store, task_id, p) else queue(store, task_id, p, actor, refused, unheard=True)    # the card is the review
        except ValueError as e:                   # ...said on the task, never dropped silently
            store.add_comment(task_id, 'taskuary', 'agent', f"The {p.get('action')} proposal was not put on the card: {_said(e)}")
            store.audit('task', task_id, 'proposal_refused', actor, detail={'action': p.get('action'), 'why': str(e), 'unheard': True})
            if refused is not None: refused.append(str(e))
            return None
    return [m for p in parse(transcript) for m in [one(p)] if m]


def unheard(store, tid: int, since: str = '') -> list:
    "[(action, why)] of the proposals refused on task `tid` from `since` on that their agent was never answered about (collect), oldest first."
    def d(r):
        try: return json.loads(r.get('Detail') or '{}') or {}
        except ValueError: return {}
    rows = store._rows("SELECT * FROM audit WHERE EntityType='task' AND EntityId=? AND Action='proposal_refused' AND CreatedAt>=? ORDER BY Id", (int(tid), since or ''))
    return [(x.get('action') or 'the proposal', x.get('why') or '') for x in map(d, rows) if x.get('unheard')]


# WHAT A TOOL RUN WILL DO, in words (the owner, 2026-10-21): the card said "run one query/script through a tool connection" over the
# proposal's raw JSON for what was a file written to the HR share. The verb is the action's scope (scopes.needs), the place is the
# first key that says where, the connection by its own name.
WHERE_KEYS = ('path', 'to', 'folder', 'table', 'url', 'bucket', 'key', 'container', 'blob', 'channel', 'list', 'database', 'item')


# WHAT A BREAK-OUT MOVES, AS THE TASK HOLDS IT NOW - read when it is filed and again at the press (a message may have left the task between):
# the messages by the ids the agent's brief carries (m12), the to-dos by theirs. `moves` is the card's words for them, one line each
def _many(x) -> list: return list(x) if isinstance(x, (list, tuple)) else [] if x in (None, '') else [x]
def break_out(store, tid, p: dict) -> tuple:
    "(the proposal with its messages and to-dos as ids the task has, '') - or (p, why it cannot go)."
    from .mailsearch import message_id
    try: want = list(dict.fromkeys(message_id(x) for x in _many(p.get('messages'))))
    except ValueError as e: return p, str(e)
    msgs, todo = {m['MessageId']: m for m in store.list_messages(int(tid))}, {i.get('id'): i for i in store.task_checklist(int(tid))}
    items = list(dict.fromkeys(str(x) for x in _many(p.get('items'))))
    if off := [f'm{m}' for m in want if m not in msgs] + [i for i in items if i not in todo]:
        return p, f"{', '.join(off)}: not on this task - name its own messages (their m-ids) and to-dos (their ids)"
    if not want and not items: return p, 'break_out needs what goes to the new task: `messages` (their m-ids), `items` (to-do ids), or both'
    if len(want) == len(msgs): return p, 'that moves every message off this task - break out only the part that is another matter'
    line = lambda m: f"{m.get('FromName') or m.get('FromEmail') or m.get('SourceName') or m.get('Channel') or 'message'}: " \
                     + ' '.join(str(m.get('BodyText') or m.get('Subject') or '').split())[:140]
    moves = [line(msgs[m]) for m in want] + [f"to-do: {todo[i]['text']}" for i in items]
    return {**p, 'title': str(p['title']).strip()[:200], 'messages': want, 'items': items, 'moves': '\n'.join(moves)}, ''
def _draft(r: dict) -> dict:
    try: d = json.loads(r.get('DraftText') or '{}')
    except ValueError: return {}
    return d if isinstance(d, dict) else {}
def break_out_words(p: dict) -> str:
    n = [plural(len(p[k]), w) for k, w in (('messages', 'message'), ('items', 'to-do')) if p.get(k)]
    return f"move {' and '.join(n)} to a task of its own, \"{p['title'][:120]}\""


# A REFUSAL THAT STEERS (the owner, 2026-11-05, from the open-source assistants: a tool's error says what to try next): "the reason is on
# the task" sent the agent to a page it cannot read - it is told the reason, and the next move
# AN ACT ON "THE LINKED ISSUE" NEEDS ONE (the stress round, 2026-11-10): a comment or a close proposed on a task that came from mail passed
# every check, stood as a card, and its Approve could only ever fail - "this task carries no GitHub issue/PR to act on". Asked at the door,
# so the agent is told while it can still ask another way, and read by the press from the same place
_LINKED = re.compile(r'github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+)')
NO_LINK = 'this task carries no GitHub issue/PR to act on'
def linked(store, tid) -> tuple | None:
    "(repo, number) of the GitHub issue or pull request task `tid` came from - None when it came from anywhere else."
    m = _LINKED.search(str((store.get_task(tid) or {}).get('SourceRef') or '')) if tid else None
    return (m.group(1), int(m.group(2))) if m else None


def refusal_line(why) -> str:
    return (f"the proposal was refused: {why or 'it did not validate'}. Fix that and propose it again - or, if it cannot be fixed from "
            "here, say in your answer what is missing and who could supply it.")


def tool_words(store, p: dict) -> str:
    from . import reports, scopes, trackers
    t = str(p.get('type') or '')
    if t in trackers.TYPES: return trackers.words(p)
    # ...a post its card declares is said by that card's own press ("post to X"): built from the tool's name it read "write x post on X
    # (Twitter)" on the next card's line (design round 6, D3)
    from .connectorcatalog import action_for
    if (act := action_for(t)) and act.get('kind') == 'post' and (press := str(act.get('press') or '')): return press[:1].lower() + press[1:]
    verb = {'read': 'read', 'write': 'write', 'admin': 'run'}.get(scopes.needs(t), 'run')
    if t.endswith('_move'): verb = 'move'
    where = next((str(p[k]) for k in WHERE_KEYS if p.get(k)), '')
    code = ' '.join(str(p.get('query') or p.get('script') or '').split())
    what = where or (f"this {'query' if p.get('query') else 'script'}: {code[:120]}" if code else t.replace('_', ' '))
    try: c = reports._connector(store, reports.card_of(t), p.get('connector_id'))
    except (TypeError, ValueError): c = None
    on = (c or {}).get('Name') or ''
    return f"{verb} {what}" + (f" on {on}" if on else '')


def queue(store, task_id: int, p: dict, actor='agent', refused: list | None = None, unheard: bool = False) -> dict | None:
    """ONE proposal through the gate: a pending review when it validates, a recorded refusal (None) when not - its reason appended to
    `refused`, so the agent that proposed it is told why and can fix it (refusal_line). `unheard`: no answer goes back to it now (collect)."""
    from . import trackers
    # an agent's comment or move on "the ticket" means the item this task came from: named on the proposal, so the card says which
    if p.get('action') == 'run_tool' and p.get('type') in trackers.TYPES and not str(p.get('item') or '').strip():
        it = trackers.item_of(store, task_id)
        if it and it['tracker'] == trackers.TYPES[p['type']][0]: p = {**p, 'item': it['item']}
    # ...and an agent's says WHAT to run, never WHERE (reports.query_only, as tools/run): its connection by number, never a host, a
    # credential or a program of its own - which the owner's Approve ran, the body winning over the card (resolve_cfg). A workflow's
    # write is the owner's own saved step and keeps what he saved
    several = ''
    if p.get('action') == 'run_tool' and actor != 'workflow':
        from .reports import REGISTRY, query_only, tool_card
        p = {**query_only(p), **({'connector_id': p['connector_id']} if str(p.get('connector_id') or '').strip() else {})}
        # ...on THE card it will run on, pinned now (reports.tool_card): the press ran the first card of its type, under a card naming it
        if p.get('type') in REGISTRY and not p.get('connector_id'):
            try: p = {**p, **({'connector_id': c['ConnectorId']} if (c := tool_card(store, p['type'])) else {})}
            except ValueError as e: several = str(e)
    # ...a run's ask to change its own routine is the card a run's own repair is (workflows.change_of): one card, one save
    routine = ''
    if p.get('action') == 'change_routine':
        from . import workflows
        p, routine = workflows.change_of(store, task_id, p) if actor != 'workflow' else ({}, 'change_routine is an agent\'s ask')
        p = p or {'action': 'change_routine'}
    ok, why = validate(store, p) if not routine else (False, routine)
    if ok and several: ok, why = False, several
    # ...a new GitHub issue names its repository and a title, said to the agent now rather than at the press
    if ok and p.get('action') == 'run_tool' and p.get('type') == 'github_issue':
        from .github import issue_check, issue_labels
        if why := issue_check(p): ok = False
        elif p.get('labels'): p = {**p, 'labels': ', '.join(issue_labels(p['labels']))}
    # ...a picture on a post is one in the task's own folder, named - never a path the agent wrote (execute resolves it again)
    if ok and p.get('action') == 'run_tool':
        p = {k: v for k, v in p.items() if k != 'image_path'}
        if p.get('type') in POSTS: p = {**p, 'network': POSTS[p['type']]}       # ...its card says where in his words ("LinkedIn"), never "linkedin post"
        if why := picture_why(task_id, p): ok = False
        elif p.get('image'):                     # ...kept as its name in the folder: an agent names it by its full path as often as not
            from . import outputs
            p = {**p, 'image': outputs.rel(int(task_id), outputs.named(int(task_id), p['image']))}
    # ...and what the agent left unnamed on a card's choices comes from the connection's own defaults (Connections), so the card shows them
    if ok and p.get('action') == 'run_tool':
        from . import connectorcatalog as cat
        if act := cat.action_for(p.get('type')):
            c = store.get_connector(int(p['connector_id'])) if str(p.get('connector_id') or '').isdigit() else store.get_connector_by_type(act['card'])
            try: conf = json.loads((c or {}).get('ConfigJson') or '{}')
            except ValueError: conf = {}
            p = cat.with_defaults(p, conf)
            if bad := next((f for f in act['fields'] if f['key'] in p and not cat.choice_ok(f, p[f['key']])), None):
                ok, why = False, f"{bad['key']} must be one of: {', '.join(str(c['value']) for c in bad['choices'])}"
    if ok and p.get('action') == 'break_out':
        p, miss = break_out(store, task_id, p)
        if miss: ok, why = False, miss
    # ...ONE CARD PER ASK (the stress round, 2026-11-18): the same proposal again - a retried call - is the card already waiting, and a
    # break_out moving what a waiting one moves is refused: stood behind it, its press could only fail
    if ok:
        bare = lambda d: {k: v for k, v in d.items() if k != 'why'}
        waiting = [(r, _draft(r)) for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind='action' ORDER BY ReviewId",
                                                       (int(task_id),))]
        if same := next((r for r, d in waiting if bare(d) == bare(p)), None):
            return {'reviewId': same['ReviewId'], 'action': p['action'], 'already': True}
        if p.get('action') == 'break_out' and (r := next((r for r, d in waiting if d.get('action') == 'break_out' and (
                set(d.get('messages') or ()) & set(p['messages']) or set(d.get('items') or ()) & set(p['items']))), None)):
            ok, why = False, f"rv{r['ReviewId']} already moves part of that to a task of its own - take it back or replace it rather than a second card"
    if ok and p.get('action') == 'save_routine':
        from . import origin, workflows
        # ...never from work a stranger started: what their mail said may be what wrote the script
        cfg, miss = ({}, "a script from a task a stranger started is not offered as a routine") if origin.of_task(store, task_id)[0] == 'stranger' \
            else workflows.script_routine(store, p)
        if miss: ok, why = False, miss
        else: p = {**p, 'title': cfg['title'], 'runs': workflows.runs_words(cfg), 'steps': [s['label'] for s in cfg.get('flow') or []],
                   'kind': 'routine' if workflows.is_workflow(cfg) else 'report'}
    if ok and p.get('action') in ('comment_issue', 'close_issue') and not linked(store, task_id):
        ok, why = False, f"{NO_LINK} - a comment or an issue on a repository you name is a run_tool (the guide tool's `propose` topic)"
    # ...THE ONE RULE (actrule.decide): the same card he dismissed since his last line is his no - refused in his voice, never a second card.
    # A post, a payment, a PR stays his press however often he approved its like (big); a held act's gate asks it at the hook
    if ok and actor != 'workflow' and p['action'] not in HELD_ACTS:
        from . import actrule
        what = tool_words(store, p) if p['action'] == 'run_tool' else p['action'].replace('_', ' ')
        how, told = actrule.decide(store, task_id, [{'what': what, 'key': actrule.card_key(p)}], big=True)
        if how == 'dismissed': ok, why = False, told
    if not ok:
        store.add_comment(task_id, actor, 'agent', f'PROPOSAL REFUSED ({p.get("action")}): {why}')
        store.audit('task', task_id, 'proposal_refused', actor, detail={'action': p.get('action'), 'why': why, **({'unheard': True} if unheard else {})})
        if refused is not None: refused.append(why)
        return None
    # a close-out is not the agent's ask ("proposes to merge the pull request this task opened" was said of a stranger's PR), and
    # neither is a workflow's own repair or write, raised by the run itself (flow.py) with no agent anywhere on the task
    said = (tool_words(store, p) if p['action'] == 'run_tool' else break_out_words(p) if p['action'] == 'break_out'
            else (f"save a script as the routine \"{p['title']}\", to run {p['runs']}" if p.get('script') else
                  f"create the {p.get('kind') or 'routine'} \"{p['title']}\", to run {p['runs']}" + (f" - built from {p['based_on']}" if p.get('based_on') else ''))
            if p['action'] == 'save_routine'
            else f"change the routine \"{p['title']}\"" if p['action'] == 'repair_workflow' and actor != 'workflow'
            else f"change the {p.get('kind') or 'report'} \"{p['title']}\"" if p['action'] == 'change_setup' else why)
    # ...nor a held browser act: the agent did not propose it, it tried it, and the hook stopped it (browsergate.check)
    # ...a shell step by what it does, never its raw line: the card folds the command under "Show the command"
    reason = (f"held before it ran, {HELD_IN[p['action']]}: {p.get('what') or ('a step' if p['action'] == 'shell_act' else p.get('command'))}"
              + (f" - {p['why']}" if p.get('why') else '') if p['action'] in HELD_ACTS else
              f"finishing it: {'merge pull request #' + str(p.get('number')) if p['action'] == 'merge_pr' else trackers.words(p) if p['action'] == 'close_item' else 'close the issue it came from'}"
              if p.get('closeout') else f"the {'workflow asks' if actor == 'workflow' else 'agent proposes'} to {said}" + (f" - {p['why'][:200]}" if p.get('why') else ''))
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
CLOSEOUT = {'merge_pr': 'merges the pull request on GitHub', 'close_issue': 'closes the issue on GitHub',
            'close_item': 'posts the comment on the item and moves it to done in its tracker'}
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
# ...and lessons proposed for a playbook (amend_playbook) are the same kind of ask: the owner's yes or no on how a kind of
# job is done, never a close-out owed on the task - so it holds, settles and counts as the playbook does (the owner, 2026-11-05)
PLAYBOOKS = (PLAYBOOK, 'amend_playbook')


def playbook_pending(store, tid: int):
    """The playbook proposal still waiting on the owner's approve or dismiss, if any."""
    return next((r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
                 if _action(r) in PLAYBOOKS), None)


# A PLAYBOOK PROPOSAL IS ALWAYS SEEN (the owner, 2026-10-21). It is drafted after the task's ending, and a task that closed itself
# with nobody to answer - a workflow run, the owner's own chat, a coding session - was done by then: a pending review on a done task
# is shown nowhere (store._VISIBLE_PENDING), so the proposal waited where nobody could find it. Such a task waits for it instead,
# marked HELD, and goes back to done once the owner answers it, yes or no - the close was already theirs or the agent's.
HELD = 'held:playbook'


def hold_for_playbook(store, tid: int, actor: str) -> None:
    t = store.get_task(tid) or {}
    if t.get('Status') != 'done': return
    tags = [x for x in str(t.get('Tags') or '').split(',') if x.strip()]
    store.update_task(tid, {'Status': 'waiting', 'Tags': ','.join([*tags, HELD])}, actor)
    store.add_comment(tid, actor, 'agent', 'Kept open for its playbook proposal - approve or dismiss it, and the task closes again.')


def playbook_answered(store, tid: int, actor: str) -> None:
    t = store.get_task(tid) or {}
    tags = [x for x in str(t.get('Tags') or '').split(',') if x.strip()]
    if HELD not in tags or playbook_pending(store, tid): return
    from . import workerstate as ws          # ...never back to done under work still live on it (a Continue since, 2026-11-01)
    store.update_task(tid, {'Tags': ','.join(x for x in tags if x != HELD)}, actor)
    if not owed(store, tid) and not ws.live_work(store, tid):
        from . import concierge
        concierge.close_task(store, tid, actor, save=False)


def held_pending(store, tid) -> dict | None:
    """AN ACTION WAITING FOR THE OWNER'S YES on the task - a step a hook held (a `git push` the shell gate stopped), or a proposal its agent
    filed - as {rid, action, what}, the newest; None when none waits. Not a close-out (its own card, the reply's settle) nor the playbook
    (asked after the work ended). The Advisor read an agent's card as asking and lit nothing over the Approve it waited on (2026-11-02 audit)."""
    if not tid: return None
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' ORDER BY ReviewId DESC", (int(tid),)):
        try: p = json.loads(r.get('DraftText') or '{}') or {}
        except (TypeError, ValueError): p = {}
        if not isinstance(p, dict) or p.get('closeout') or p.get('action') in (*PLAYBOOKS, *CLOSEOUT): continue
        what = (p.get('what') or str(p.get('command') or '')[:160]) if p.get('action') in HELD_ACTS else ''
        return {'rid': r['ReviewId'], 'action': p.get('action') or '', 'what': ' '.join(str(what or r.get('Reason') or p.get('action') or 'a step').split())[:240]}
    return None


# A CARD YOU HAVE MOVED PAST IS OLD NEWS (the owner, 2026-11-10: "no once youa re passed it, it should stay where it is with buttons grayed
# out. You can ask the agent to bring it back?" - "check this code everywhere so actions both genral/coding agents are part of prompt that is
# old news once you move on to next one"). ONE RULE, every card kind and every agent: a card waiting for the owner's press is live from the turn
# that raised it until the conversation moves on - the owner's next line on the task, or the agent's next turn begun for anything but that
# card's own press. Then it is settled as passed: kept where it stood as its record, never pressable again, and its agent told once
# (passed_since) that it is old news and to raise it again if the step is still wanted. Each kind had its own road or none: a held step
# went past only on a pty's prompt hook, a page hand-over on the owner's words, and a proposal, a post or an agent's routine stayed
# pressable for ever under turns that had moved on.
# A REPLY OR EMAIL DRAFT IS THE AGENT'S TO RE-DECIDE (496eefb72 wakes it on the owner's line): it keeps, replaces or withdraws it in that
# turn (general.latest_block's WITHDRAW_LINE), and the page greys it while that turn runs - only actions are passed by the line itself.
# Nor the task's own finish (its close-out, its playbook): Taskuary raises those when the work ends, no turn of the agent's does
SET_ASIDE = 'set aside when you moved on'
LAND = 'land'                  # move_on's mark for the landing question (landing.pass_over) among the review ids


NOT_NEEDED = 'not needed - the agent finished without it'
PAGE_LEFT = 'the browser left the page it was held on'      # browsergate.left_page: greyed where it stood, no line of why


def passed(rv: dict | None) -> bool:
    "Whether review `rv` is a card the conversation moved past (move_on) - not pressable, and its press route says so (passed_why)."
    return bool(rv) and rv.get('Status') == 'superseded' and rv.get('DecideNote') in (SET_ASIDE, NOT_NEEDED, PAGE_LEFT)


def finished_without(store, tid: int) -> list:
    """A STEP HELD IN A TURN THAT THEN FINISHED THE JOB IS NOT LEFT LIT UNDER ITS ANSWER (the owner, 2026-11-16: a research turn's PDF read-back
    was held, it finished the report another way, and the Approve stood live under the complete answer). The turn's own word that its goal is
    met and checked (its summary's nothing_left - no reading of it) greys the steps held in that same turn in place, with the true line. ->
    the review ids."""
    from .shellgate import turn_of
    turn, out = turn_of(store, int(tid)), []
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' AND DeliveryClaim IS NULL", (int(tid),)):
        try: p = json.loads(r.get('DraftText') or '{}') or {}
        except (TypeError, ValueError): p = {}
        if isinstance(p, dict) and p.get('action') in HELD_ACTS and p.get('turn') == turn and store.decide_review(r['ReviewId'], 'superseded', None, 'taskuary', note=NOT_NEEDED):
            out.append(r['ReviewId'])
    if out: store.audit('task', tid, 'cards_passed', 'taskuary', 'system', {'rids': out, 'why': NOT_NEEDED})
    return out


def move_on(store, tid, before: str = None) -> list:
    """THE CONVERSATION ON TASK `tid` MOVED ON: a permission the agent waits on is passed (permissions.set_aside), and the landing question.
    AN ACTION CARD IS NOT (the owner, 2026-11-11, of a held step with a long query he asked a question about: "the question has 2 approve
    buttons? i thought we got rid of those??" - his line set the card aside, greyed, and the agent raised the step again beside it): a card
    that waits for his press stays lit until he presses it, a newer one takes its place or its agent withdraws it - as a reply does. A row an
    earlier build set aside keeps its record (passed). The marks passed."""
    if not tid: return []
    out = []
    try:
        from . import permissions
        permissions.set_aside(store, int(tid))
    except Exception as e: logger.debug(f'task {tid}: a permission waiting was not set aside - {e}')
    if out: store.audit('task', tid, 'cards_passed', 'taskuary', 'system', {'rids': out})
    return out


def set_aside_drafts(store, tid: int, before: float, actions: float = 0) -> list:
    """A CARD THE CHAT MOVED PAST IS SET ASIDE FOR GOOD AS ITS AGENT HEARS THE INPUT (the owner, 2026-11-16, said ~20 times: "The second a new
    prompt comes in, from manual or email, it should gray out the action card but never move"): every card older than the input at `before`
    (`_older` - one rule, every kind), and the landing question, stays where it stood, greyed, and its agent is told it was set aside because
    the chat moved on (cardqueue.screen - never that he declined), to raise it again under the newest line if it is still wanted.
    From the moment the input came in until then every surface already reads it greyed (written_past). Every road hears an input through
    conversation.hear, which calls this. `actions`: the old split by kind, read as the same input. -> the review ids (and LAND)."""
    from . import landing
    at = max(before or 0., actions or 0.)
    out = [r for r in _older(store, tid, at) if store.decide_review(r, 'superseded', None, 'taskuary', note=SET_ASIDE)]
    if landing.pass_over(store, int(tid), at): out.append(LAND)
    if out: store.audit('task', tid, 'cards_passed', 'taskuary', 'system', {'rids': out})
    return out


def restore_set_aside(store, tid: int) -> list:
    """A TURN THE AI NEVER ANSWERED SETS NOTHING ASIDE (design round 4, H3: a draft he needed stood greyed for 43 minutes while the provider
    failed turn after turn on the line after it). Set aside as its agent heard the input (set_aside_drafts), a card no answer has come under
    since stands again, live where it stood: no agent read past it. The input stays heard - the try after the failure answers it. -> ids."""
    from . import general
    rows = store.list_comments(int(tid), internal=True)
    answer = next((c['CreatedAt'] for c in reversed(rows) if c.get('ActorType') == general.ASSISTANT_TYPE and c.get('Actor') == 'assistant'
                   and not (lambda w, f: f and not w)(*general.failed_line(c.get('Body')))), '')
    out = [r['ReviewId'] for r in store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='superseded' AND DecideNote=? AND DecidedBy='taskuary' "
                                              "AND DecidedAt>=?", (int(tid), SET_ASIDE, str(answer or ''))) if store.restore_review(r['ReviewId'])]
    if out: store.audit('task', tid, 'cards_restored', 'taskuary', 'system', {'rids': out})
    return out


def _older(store, tid: int, before: float, actions: float = 0) -> list:
    """The pending cards an input at `before` stands after - set_aside_drafts' and written_past's ONE rule, read only. Every kind: a reply, an
    email, a calendar answer, the agent's act or held step, and Taskuary's own close-out, playbook or routine step alike (the owner, 2026-11-16:
    a close-out's Push stood lit above his newer line, and he scrolled up to press it). Only an email he wrote himself is his, never set aside,
    and a reply owed that nobody wrote is no card yet."""
    from .conversation import ep
    at = max(before or 0., actions or 0.)
    if not at: return []
    rows = store._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND DeliveryClaim IS NULL", (int(tid),))
    from . import bulkcard
    words = lambda r: bool(str(r.get('DraftText') or '').strip())
    # ...A REPLY'S WORDS BY WHEN THEY WERE WRITTEN (DraftAt), not when its card was raised: one owed is raised empty as its mail lands and the
    # agent writes it later - a line between the two is one it saw (CI, 2026-11-15). Older only: a stamp is no finer than its second, and an
    # input in the card's own second leaves it standing until its agent hears it
    def card(r):
        # ...but a bulk card at work runs on to its end, and shows it (bulkcard: the owner, 2026-11-16)
        if r.get('Batch') and bulkcard.running(store, r['Batch']): return False
        if r['Kind'] == 'slot': return words(r) and not str(r.get('Reason') or '').startswith('your email')
        return r['Kind'] == 'action' or words(r) or r['Kind'] not in ('draft_reply', 'draft')
    return [r['ReviewId'] for r in rows if card(r) and ep(r.get('DraftAt') or r['CreatedAt']) < at]


def moved_on(store, tid: int, after: float = 0.) -> float:
    """WHEN THE CHAT LAST MOVED ON, by an input no agent has heard yet: a line he typed (waiting, or kept for a turn not begun), a message that
    joined the thread - never his own Send come back from his Sent folder, nor a stranger's words held behind trust (origin.hold), which moved
    nothing on (recorded on the real CLI, 2026-11-15). Epoch seconds; 0. with none - or none newer than `after`, all that is asked."""
    from . import conversation, general, origin
    led = {(r['Kind'], r['Ref']) for r in store._rows("SELECT Kind, Ref FROM heard WHERE TaskId=?", (int(tid),))}
    lines = [conversation.ep(x['CreatedAt']) for x in store.list_comments(int(tid), internal=True)
             if x.get('ActorType') in (general.USER_TYPE, general.WAITING_TYPE) and not general.is_brief(x) and x.get('Actor') == 'owner'
             and (x.get('ActorType') == general.WAITING_TYPE or x.get('LineId') and ('line', str(x['LineId'])) not in led)]
    top = max([after, *lines])
    # ...newest first, and only as far as one counts: who sent it and whether it is held are asked of the few newer than his newest line
    mail = sorted((x for x in conversation._mail(store, int(tid)) if x['T'] > top and ('mail', str(x['MessageId'])) not in led), key=lambda x: -x['T'])
    if not mail: return top if top > after else 0.
    got = {}                                        # ...each asked once, and only of a message it is about
    mine = lambda x: (got['mine'] if 'mine' in got else got.setdefault('mine', general.went_from_here(store, int(tid))))(x)
    held = lambda x: str(x['MessageId']) in (got['held'] if 'held' in got else got.setdefault('held', {str(m) for m in (origin.hold(store, int(tid)) or {}).get('mids') or ()}))
    return next((x['T'] for x in mail if not (mine(x) if x.get('Own') else held(x))), top if top > after else 0.)


def written_past(store, tid: int) -> set:
    """THE CARDS THE CHAT HAS MOVED PAST - ONE FUNCTION FOR EVERY SURFACE (the owner, 2026-11-16: "it should be one code that action cards are no
    longer useful once the chat moves on. It should gray out immediately, but don't go away"): every pending card older than an input no agent
    has heard yet (moved_on, _older). From the moment the line is sent or the message joins, the chat draws it greyed where it stood
    (conversation.items) and what waits on his press leaves it out (store.waiting_reviews / waiting_on_owner: the pill, the rail, the board,
    the phone); `hear` settles it for good as its agent takes the input (set_aside_drafts, by this same rule). -> the review ids."""
    from .cardqueue import fresh
    return fresh(store, ('past', int(tid)), lambda: _written_past(store, tid))
def _written_past(store, tid: int) -> set:
    from .conversation import ep
    first = store._one("SELECT MIN(CreatedAt) AS a FROM review WHERE TaskId=? AND Status='pending'", (int(tid),))
    if not (first and first['a']): return set()
    return set(_older(store, tid, moved_on(store, tid, ep(first['a']))))      # ...an input in a card's own second moves nothing (_older)


# what an agent is told to do about a step that is no longer on his screen - one sentence, every road
AGAIN = ('If a step is still needed, raise it again as a new card (a step held for their press: run it again - Taskuary holds it anew); never '
         'say it still waits on them, and never ask them in words to press it.')
def passed_why(store, r: dict) -> str:
    """WHY A CARD STANDS GREYED, IN WHAT HAPPENED (the owner's live task, 2026-11-16: "there was no earlier draft. This is broken?" - he typed a
    line while the agent worked, the turn that never read it finished its draft after it, and the draft stood greyed reading "set aside when
    you moved on", as if he had done something to it). ONE sentence for every kind, from the input that moved the chat past it: the newest of
    his lines and the messages that came in, up to when it was set aside - written after it, or before the agent read it."""
    from . import continuity, general
    from .conversation import _mail, ep
    if r.get('DecideNote') == NOT_NEEDED: return 'Not needed - the agent finished without it'
    if r.get('DecideNote') == PAGE_LEFT: return ''
    card, end = ep(r.get('DraftAt') or r.get('CreatedAt')), ep(r.get('DecidedAt')) or time.time()
    # ...A REPLY TO FILED MAIL HAS NO TASK (2026-11-18): retired by his answer, its press crashed reading one - its thread is its own message's
    tid = int(r['TaskId']) if r.get('TaskId') else None
    his = [x for x in store.list_comments(tid, internal=True) if x.get('ActorType') in (general.USER_TYPE, general.WAITING_TYPE)
           and not general.is_brief(x) and x.get('Actor') == 'owner'] if tid else []
    lines = [(ep(x['CreatedAt']), f'your line "{w}"', WROTE_PAST.format(line=w)) for x in his for w in [_cut(general.line_words(x))]]
    # ...his own mail on the thread is his answer to whom it was with, never "you wrote again" (2026-11-17): the newest other sender before it
    # ...each placed by when it CAME IN, his too (2026-11-18): his mail was placed by when he sent it and theirs by when it arrived, so mail
    # polled together after a restart read "written before the agent read Erin's new message" over a draft his own answer had retired
    mails, who = [], ''
    came = lambda x: max(x['T'], ep(x.get('CreatedAt'))) if x.get('Own') else x['T']
    # ...and his mail that went to others, not to whom the card was for (a forward to Gail on Erin's thread), says whom it went to
    from .context import _recipients
    mine = continuity.addressees(store, r)
    from .ingest import is_ours
    m = store.get_message(r.get('MessageId')) if not tid and r.get('MessageId') else None
    rows = _mail(store, tid) if tid else [{**x, 'Own': is_ours(x), 'T': ep(x.get('CreatedAt'))}
                                         for x in (store.thread_messages(m['ConversationId']) if m and m.get('ConversationId') else [])]
    for at, x in sorted(((came(x), x) for x in rows), key=lambda p: (p[0], p[1]['MessageId'])):
        n = x.get('FromName') or x.get('FromEmail')
        if not x.get('Own'): who = n or who; mails.append((at, f"{n or 'a'}'s new message", f"Not sent - {n or 'someone'} wrote again after it")); continue
        if (went := _recipients(x)) and mine and not mine & {a.lower() for a in went}:
            mails.append((at, f"your mail to {', '.join(went)}", f"Not sent - you wrote to {', '.join(went)} yourself")); continue
        to = who or continuity.sent_to(store, r, 'them')
        mails.append((at, f'your answer to {to}', f'Not sent - you answered {to} yourself'))
    # ...the later of two in one second (a stamp is no finer): the input listed last came in last
    got = max(reversed([x for x in lines + mails if x[0] <= end + 1]), key=lambda x: x[0], default=None)
    if not got: return 'Not sent - set aside when the chat moved on'
    return got[2] if got[0] >= card else f'Not sent - written before the agent read {got[1]}'
# ...the sentence his line greys a card with - sent with each card it could grey (conversation `aside`), so the page says it from the frame he
# presses Enter, his line cut as _cut cuts it (chatStream.withMine), never words of its own that the read then swaps
WROTE_PAST = 'Not sent - you wrote "{line}" after it'
def _cut(w: str, n: int = 60) -> str: return (w := ' '.join(str(w or '').split()))[:n] + ('…' if len(w) > n else '')


def owed(store, tid: int) -> bool:
    """Something of the close-out still waits on the owner: a reply, a close-out act, any other proposal - not the playbook."""
    return any(_action(r) not in PLAYBOOKS for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,)))


def closed_out(store, tid: int, actor: str, said: str) -> None:
    """The close-out is done: said on the task, with what still waits (its emails, its playbook). The task STAYS OPEN - only
    the owner's Mark done closes it (the owner, 2026-10-18: "sending and closing are two steps, never automatic"); this used
    to close it whenever nothing else waited."""
    from . import slots
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return
    n = len(slots.open_(store, tid))
    store.audit('task', tid, 'closed_out', actor)
    rest = (f" {plural(n, 'email')} still to go." if n else ' Its playbook still waits on your approve or dismiss.' if playbook_pending(store, tid)
            else f" {buttons.label('close')} when the task is finished.")
    store.add_comment(tid, actor, 'human', f'{said}{rest}')


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
            cur = github.pr(ci._conn(store, repo)['Secret'], repo, num)
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
    else:
        from . import trackers
        p = trackers.closeout_due(store, tid)          # a Jira, Monday or Linear item: comment and move it to done, read from the tracker now
        if not p: return None
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
        from . import trackers
        if not (_PULL.search(ref) or _ISSUE.search(ref) or (ci.landing_of(store, tid) or {}).get('kind') == 'pr' or trackers.item_of(store, tid)): continue
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
    if tid and _action(rv) in PLAYBOOKS: return playbook_answered(store, tid, actor)
    if not tid: return
    # a held step dismissed: the waiting agent hears it was not done
    if _action(rv) in HELD_ACTS and verb not in ('approve', 'edit'): _gate(_action(rv)).declined(store, tid, json.loads(rv.get('DraftText') or '{}'))
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
            from . import general
            general.reopen(store, tid, actor, also=('waiting',))
            closed_out(store, tid, actor, 'Every proposal is answered.')
        return
    if verb not in ('approve', 'edit'):
        from . import general
        general.reopen(store, tid, actor, 'reopen', {'why': 'its close-out was turned down'}, also=('waiting', 'in_progress'))
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
    repo, num = p['repo'], int(p['number'])
    c = ci._conn(store, repo)
    cur = github.pr(c['Secret'], repo, num)
    if cur.get('merged'): raise RuntimeError(f'#{num} is already merged on GitHub - nothing to close')
    if cur.get('state') != 'closed': github.close_pr(c['Secret'], repo, num)
    if ci.pr_of(store, rv['TaskId']): ci._save_pr(store, rv['TaskId'], {**ci.pr_of(store, rv['TaskId']), 'state': 'closed', 'merged': False}, actor)
    out = {'closed': f'{repo}#{num}', 'merged': False}
    store.add_comment(rv['TaskId'], actor, 'human', f'Closed pull request {repo}#{num} without merging it.')
    store.audit('review', rv['ReviewId'], 'pr_closed_unmerged', actor, detail=out)
    return out


from .ghcloseout import Refused as ChecksRed      # a close-out GitHub's state refuses now, with what the card may offer instead


def execute(store, rv: dict, actor='owner', final_text: str = None, skip_checks: bool = False, fields: dict = None) -> dict:
    """Run an APPROVED proposal. Called from the verdict road, and it re-validates: the
    switch may have gone off between proposing and approving, and the approval does not
    grant the permission.

    `final_text` is what was in the Review box when the owner approved. For a proposed
    playbook the box shows the page itself (not the JSON envelope), so an edited page is
    what gets filed - the owner tightening an `alone:` line before the first run is the point."""
    p = json.loads(rv.get('DraftText') or '{}')
    edited = str(final_text or '').strip() and not str(final_text).lstrip().startswith('{')
    # ...a close-out's box too, EMPTY AS PROPOSED INCLUDED (the spine audit, 2026-11-09): a merge with no summary shows an empty box that
    # reads "GitHub writes the merge message" - what the owner typed into it was dropped, and GitHub wrote the message all the same
    if edited and p.get('action') in ('write_playbook', 'amend_playbook', *CLOSEOUT): p['text'] = final_text.strip()
    # a tracker close-out's box IS its comment: what the owner left there goes, emptied included (None = pressed off the card, as filed)
    if p.get('action') == 'close_item' and final_text is not None and not str(final_text).lstrip().startswith('{'): p['text'] = str(final_text).strip()
    p = _edited(p, final_text, fields)
    ok, why = validate(store, p)
    if not ok: raise RuntimeError(f'refused at execution: {why}')
    tid, a = rv.get('TaskId'), p['action']
    before = (store._one('SELECT MAX(Id) AS n FROM audit') or {}).get('n') or 0
    try: out = _run(store, rv, p, tid, a, actor, edited, skip_checks)
    except Exception as e:                  # ...the act itself ran and failed (verdicts settles its card), never a refusal before it ran
        try: e.ran = True
        except AttributeError: pass
        raise
    # ONE PRESS, SAID ONCE (the stress round, 2026-11-10): the code an act runs writes its own rows on the task in the presser's name - a split,
    # a pull request opened - and each was a second line beside the pressed card, and a second "the owner did" for its agent. They are the
    # card's: marked with it, and said by it (general.presses)
    if tid and rv.get('ReviewId'):
        store._exec("UPDATE audit SET Detail=json_set(IFNULL(NULLIF(Detail,''),'{}'),'$.review',?) WHERE Id>? AND EntityType='task' AND EntityId=? AND Actor=?",
                    (rv['ReviewId'], before, tid, actor))
    if tid: store.add_comment(tid, actor, 'human', f'APPROVED PROPOSAL ({a}): {json.dumps(out)[:600]}')   # a task-less one has no card to say it on
    store.audit('review', rv['ReviewId'], 'proposal_executed', actor, detail={'action': a, 'result': out})
    # a workflow run that stopped for this yes goes on from that step (flow.resume) - on its own thread, as a run starts: a last
    # agent step's first turn would otherwise hold the owner's click for as long as the agent works
    if isinstance(p.get('flow_run'), dict) and a in ('run_tool', 'repair_workflow'):
        from . import flow, workflows
        workflows._spawn(lambda: flow.resume(store, p['flow_run'], out if a == 'run_tool' else None))
    return out


def _run(store, rv: dict, p: dict, tid, a: str, actor: str, edited, skip_checks: bool) -> dict:
    "The act itself, for execute."
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
        if not (at := linked(store, tid)): raise RuntimeError(NO_LINK)
        repo, num = at
        c = _conn(store, repo)
        if a == 'comment_issue':
            url = github.comment_issue(c['Secret'], repo, num, p['body'])
            out = {'commented': f'{repo}#{num}', 'url': url}
        else:
            github.close_issue(c['Secret'], repo, num, p.get('body') or p.get('text'))
            out = {'closed': f'{repo}#{num}'}
    elif a == 'merge_pr':
        from . import ci, github, ghcloseout
        repo, num = p['repo'], int(p['number'])
        c = ci._conn(store, repo)
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
                store.merge_connector_config(conn['ConnectorId'], {c['name']: c['value']})
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
        elif a == 'amend_playbook' and p.get('lessons') and not edited:   # ...and its lessons, onto the page as it is NOW (with_lessons)
            p['text'] = playbooks.with_lessons(playbooks.read(p['slug']) or p['text'], p['lessons'])
        slug = playbooks.write(p['slug'], p['text'])
        out = {'playbook': slug, 'path': str(playbooks.folder() / f'{slug}.md')}
    elif a == 'repair_workflow':
        from . import flow, workflows
        if not isinstance(p.get('flow'), list): raise RuntimeError('the repaired steps are not a list')
        # the fix was written against the steps as they stood then: a change made since would be thrown away by approving it
        now = flow.steps_of(workflows.cfg_of(store.get_source(int(p['source_id'])) or {}))
        if p.get('was') != now: raise RuntimeError('the steps have changed since this fix was written - run the workflow again, or Fix with AI on it')
        d = flow.apply(store, p['source_id'], p['flow'], actor, p.get('why') or '') if p['flow'] != now else []      # re-validated there, and audited
        # ...its clock and its name through the same one save the editor uses (workflows.save): one card, one press
        if p.get('patch'): workflows.save(store, {'SourceId': int(p['source_id']), 'ConfigPatch': p['patch']}, actor)
        out = {'workflow': int(p['source_id']), 'changed': (str(p.get('changes') or '') or flow.diff_text(d))[:1200]}
    elif a == 'change_setup':
        from . import workflows
        src = store.get_source(int(p['source_id']))
        if not src: raise RuntimeError(f"that {p.get('kind') or 'report'} is gone - nothing was changed")
        now = workflows.cfg_of(src)
        # ...written against the setup as it stood then: a change made since is never thrown away by approving this one
        if any(now.get(k) != v for k, v in (p.get('was') or {}).items()):
            raise RuntimeError(f"the {p.get('kind') or 'report'} has changed since this was written - nothing was changed; ask the agent again")
        workflows.save(store, {'SourceId': int(p['source_id']), 'ConfigPatch': p['patch']}, actor)      # ...its editor's own save
        out = {'source': int(p['source_id']), 'changed': str(p.get('changes') or '')[:1200]}
    elif a in HELD_ACTS: out = _gate(a).perform(store, tid, p)
    elif a == 'close_item':
        from . import trackers
        out = trackers.close_out(store, p)
        out['said'] = trackers.said(out)
    elif a == 'break_out':
        from . import reshape
        from .store import task_ref
        p, miss = break_out(store, tid, p)
        if miss: raise RuntimeError(f'{miss} - nothing was moved')
        # ...ONE JOB IS ONE TASK (the owner's live app 2026-11-18): a part broken out that an open task already IS goes there - triage reads it
        # (ingest.same_work), as it reads every message and every start - its messages and to-dos moved to it, then its agent told in Taskuary's
        # words by the one road into it (general.to_agent; started where none ever worked it): the owner pressed the card, he never typed this
        from . import general, ingest
        if (same := ingest.same_work(store, f"{p['title']}. {p.get('summary') or ''}", 'Taskuary, breaking a part out of another task', skip={int(tid)})):
            reshape.move_part(store, tid, same, p['messages'], p['items'], actor)
            general.to_agent(store, same, f"Moved here from {task_ref(tid)}: {p['title']}" + (f" - {p['summary']}" if p.get('summary') else ''), actor, start=True)
            return {'task': same, 'ref': task_ref(same), 'joined': True, 'said': f"{task_ref(same)} is already that work - moved there, its agent told: {p['title'][:120]}"}
        new = reshape.split_task(store, tid, {'title': p['title'], 'summary': str(p.get('summary') or ''), 'items': p['items']}, None, p['messages'], actor)
        out = {'task': new, 'ref': task_ref(new), 'said': f"{task_ref(new)} is the new task: {p['title'][:120]}"}
    elif a == 'save_routine':
        from . import workflows
        out = workflows.save_script_routine(store, p, actor)
    else:                                   # run_tool
        from .reports import REGISTRY, resolve_cfg
        # the owner approved THIS query, so it may commit - the one road to a write on a read-level SQL card
        cfg = {k: v for k, v in p.items() if k not in ('action', 'flow_run', 'image_path', 'result', 'network')}
        if p.get('image'):
            from . import outputs
            if why := picture_why(tid, p): raise RuntimeError(f'{why} - nothing was posted')
            if p.get('type') in MEDIA: cfg['image_path'] = str(outputs.named(int(tid), p['image']))
            else: cfg.pop('image', None)          # ...a network Taskuary uploads no picture to posts the words; the card said so
        if (bad := unknown_tool(p.get('type'))): raise RuntimeError(f'{bad} - nothing was run')       # ...a card from before the gate refused it
        out = _ran(REGISTRY[p['type']](resolve_cfg(store, {**cfg, '_write': True})))
    return out
