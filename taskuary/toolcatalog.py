"""Every road the assistant can take, written from the code that runs them.

The chat used to answer with a VERB from a list in prose, and code then guessed the target: which
items a sweep meant, which task a phrase named. That seam is where promises broke - "dismiss all the
tasks that are the category report" became the WORD "report" matched against subject lines, so 13 of
72 were cleared and the answer still said done (the owner, 2026-09-07).

So the model is given the operations themselves - generated from operations.KINDS, which is the same
registry server._run_operation dispatches on, so this catalogue cannot drift from what actually runs -
and it answers with a CALL naming the kind and its parameters, including a SELECTOR when the target is
a description rather than one row.

Nothing here executes. A CALL becomes a proposal exactly as a verb does; the owner's confirmation is
still what runs it (PW-123/124), and the AUTO verbs are still the only things that go straight through.
"""
import json
from . import operations

# What each operation is FOR, in the owner's terms. Kinds absent from here are internal roads the chat
# has no business offering (triage corrections, dispatch plumbing) and are left out of the catalogue.
PURPOSE = {
    'task.create_from_message': 'hand this message to an agent or put it on the list - `kind`: coding | general | task',
    'task.create_from_text':    ('a new job with no message behind it - `kind`: task (a to-do or reminder the owner does '
                                 'themselves, no agent) | general (a regular agent) | coding, and `text`. Never for a task that '
                                 'already exists (a TQ ref): starting an agent on one is dispatch.prepare, and its own last '
                                 'session is agent.continue'),
    'message.file':             "file it - not ours, just this one",
    'message.archive':          'archive it: off the pipe and closed, nothing deleted',
    'preference.exclude_sender': 'teach triage to file this sender or subject from now on - their mail still arrives (`scope`: sender | subject)',
    'preference.sender_rule':   'an exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the Timeline',
    'item.settle':              'put the item down - `verb`: done | later | skip (the item on the table is the target)',
    'task.complete':            'Mark done - the task is finished',
    'task.defer':               ('Remind me: put an open task away until a day and bring it back that morning - `until`: a date '
                                 '(2026-10-09), "2 weeks", "3 days", "monday", or "none" to bring it back now; `ref` names '
                                 'the task (TQ-0123) when it is not the one on the table'),
    'review.approve':           'send the drafted reply as it stands',
    'agent.answer':             'answer the agent that is waiting - `text`; `ref` names its task when it is not the one on the table',
    'agent.stop':               "save and end an agent's session - the one on the table, or the task `ref` names; never a guess at which",
    'report.rerun':             'run that report again',
    'memory.remember':          'keep a fact - `note`',
    'routing.remember':         ('remember how work like this should be ROUTED next time - `field`: kind | profile | system, '
                                 'and `value`. kind: coding (an agent in a checkout) | general (the assistant) | task (the owner, '
                                 'no agent). system: where the work actually lives when no repository here can touch it, named '
                                 'plainly ("ADP"). It teaches triage and moves nothing - say it when the owner tells you a '
                                 'verdict was wrong, or where a kind of job really belongs.'),
    'task.split':               'split one arrival into two jobs - `text`',
    # THE TASK PAGE, as tools (2026-09-25). A task tool acts on the task on the table, or on the one `ref` names
    # (TQ-0123) - never a guess. Each is the page's own button.
    'task.update':              ("change a task's priority, title or owner - any of `priority`: low | normal | high | urgent, "
                                 "`title`, `assignee` ('me', or an agent's role); `ref` when it is not the one on the table"),
    'task.set_kind':            'say what kind of work a task is - `kind`: task (the owner does it) | general (a non-coding agent) | coding; `ref`',
    'task.set_repo':            'put a coding task in the repository it belongs in - `repo` (its name, as the repositories list says it); `ref`',
    'task.check':               'tick a checklist item on a task - `item`: its number (1 is the first) or words from it; `done`: false un-ticks; `ref`',
    'task.comment':             'file a note on a task - `text`; `ref`',
    'task.handoff':             ('hand a task to a PERSON - `who` (a name or address that has written here), `note` optional: '
                                 "writes the forward for the owner's yes, nothing is sent from this card; `ref`"),
    'task.merge':               "fold a task into the one it duplicates - `into`: the survivor's ref (TQ-0123); `ref` is the one folded away",
    'task.clarify':             "prepare a question for the task's sender - `text`: the question; it waits for the owner's yes, never sent from here; `ref`",
    'task.reopen':              'reopen a task that was marked done - `ref`',
    'task.not_a_task':          'delete a task and teach triage it was never work - `ref`',
    'dispatch.prepare':         ('start an agent on an EXISTING task - `kind`: coding | general, `instructions` optional; '
                                 'a coding task asks which repository when it is not clear; `ref`'),
    'agent.continue':           "pick up the agent's own last session on a task where it left off - `ref`",
    'review.reject':            'reject the draft reply waiting on a task - nothing is sent, the task stays open; `ref` names the task',
    'hub.publish':              ('save to the company Hub - `title`: one durable claim, `body`: why it matters and what to do, `topic`, '
                                 '`kind`: new_idea | technical_solve | howto | gotcha | decision | system | people, `why_earned`. Only a '
                                 'reusable discovery reached through real work, or a developed idea with its reasons - never a transcript, '
                                 'a task log or a routine answer. When the owner asks to save something there, or a turn clearly earns it'),
    'pipe.clear':               'clear a SET of items from the pipe at once - takes `select` (below); read, never deleted',
    'task.setup':               'open a walk-through with the assistant, for a set-up that needs digging first - `text`',
    # (the owner, 2026-09-07: "are you adding endpoints for report setup and connector setup and
    # taskuary setup. Include that as well"). Each goes down the same handler the tab's own form
    # uses - report.create through save_source, connection.create through save_connector.
    'report.create':            'create a scheduled report or workflow - `config`; the composer builds it from what the owner asked for',
    'connection.create':        'add a system Taskuary talks to - `type`, `name`; created OFF and never carrying a secret, which the owner gives on the card',
    # THE APP ITSELF, by name. A report is named by `title` (part of its name) or `source_id`; a
    # connection by `name` or `connector_id`; a setting by `key` or `label`. These run AT ONCE
    # (INSTANT below) with an undo in the receipt, except report.delete, which asks first.
    'report.run':               'run a report or workflow now - `title` (or `source_id`); it lands in the pipe when done',
    'report.pause':             'stop a report or workflow running on its clock - `title`',
    'report.resume':            'put a paused report or workflow back on its clock - `title`',
    'report.reach':             'change when a report reaches the owner - `title`, `reach`: always | wrong | rule',
    'report.edit':              'change a report\'s configuration - `title`, `config`: only the keys to change (title, cron, daily_at, every_minutes, deliver, alert...)',
    'report.delete':            'delete a report or workflow for good - `title`; asks first',
    'setting.set':              'change one setting - `setting` (its key, or `label`: part of its name) and `value`; the schema says what it takes',
    'connection.test':          'test a connection now and say what it answered - `name`',
    'connection.pause':         'switch a connection off - `name`; nothing is deleted',
    'connection.resume':        'switch a connection back on - `name`',
    'script.start':             'start a script by its name: walk me through my tasks | set up Taskuary | set up a report',
}

# THE TIERS (the spec, 2026-09-18). Reads run at once (READS). These WRITES run at once too, because
# each can be put back: the receipt carries the undo. Everything else waits for the owner's yes -
# deleting, sending to a person, spending, stopping an agent mid-run.
INSTANT = frozenset({'report.run', 'report.pause', 'report.resume', 'report.reach', 'report.edit', 'setting.set', 'task.defer',
                     'connection.test', 'connection.pause', 'connection.resume', 'script.start'})


def is_instant(kind: str) -> bool: return kind in INSTANT

# A set of items, described rather than listed. This is the part the verb vocabulary never had: it is
# how "all the reports" or "everything from that sender" is said in a way code can carry out exactly.
# The vocabularies are read off the PILE ITSELF where a store is at hand, for the same reason the
# operations are read off the registry: a hand-written list drifts, and a category the model names
# that triage never emits is a promise that cannot be kept.
FALLBACK_CATEGORIES = ('report', 'info', 'idea', 'todo', 'coding', 'review', 'promo',
                       'automated', 'error', 'assistant', 'filed', 'ignored', 'yours')


def vocabularies(store=None) -> dict:
    """{category, kind, lane} -> the values actually in the PIPE right now.

    The same set concierge.select_items searches, and that is the whole point. This read
    keep_surfaced=True - the whole timeline, all-time - while the selector only ever filtered the
    live pipe, so five categories were advertised that could not possibly match: assistant,
    automated, error, filed, yours. The model asked to clear `category: assistant` because the app
    told it that was a legal value, got nothing, and the answer blamed the pipe: "nothing matches,
    so there is nothing to clear" - about eleven rows the owner was looking at (2026-09-10).

    select_items already carries the same lesson for itself ("it offered to clear 72 when seven were
    actually waiting", 2026-09-07); the menu was left reading the wide set. A value offered here has
    to be a value that can be found there."""
    out = {'category': list(FALLBACK_CATEGORIES), 'kind': [], 'lane': []}
    from . import funnel
    out['lane'] = list(funnel.LANES)
    if store is None: return out
    try:
        items = funnel.build(store)['items']
    except Exception:
        return out
    seen = lambda f: sorted({str(i.get(f) or '') for i in items} - {''})
    return {'category': seen('category') or list(FALLBACK_CATEGORIES),
            'kind': seen('kind'), 'lane': seen('lane') or list(funnel.LANES)}


def selector(store=None) -> str:
    v = vocabularies(store)
    lines = ['SELECT (for pipe.clear, and anywhere a set is meant) - every field is optional and they AND together:',
             '  category   one of these, exactly: ' + ', '.join(v['category'])]
    if v['kind']: lines.append('  kind       ' + ' | '.join(v['kind']))
    lines.append('  lane       ' + ' | '.join(v['lane']))
    lines += ['  sender     an address or a name, matched on the sender only',
              '  contains   words that must appear in the subject',
              '  older_than_hours  a number',
              'Use SELECT when the owner describes a SET ("all the reports", "everything from Marketing").',
              'Naming a category is not the same as the word appearing in a subject - say category: report,',
              'never contains: report.']
    return '\n'.join(lines)


def block(store=None) -> str:
    """How the model acts, then WHERE THINGS ARE, then the tools in buckets - progressive disclosure (the owner,
    2026-09-25: "tell the assistant where it can find things with examples, then tools disclosed in buckets, then
    individual tools. It should be an exhaustive list to figure out everything but it doesn't need that up front").
    Every tool is reachable (tools.list per bucket, tools.describe per tool); only the index rides every turn."""
    lines = [
        'HOW YOU ACT (code reads your last line)',
        'Answer in plain words. To look something up or to do anything, end with ONE line:',
        '  CALL: {"kind": "<tool>", "params": {...}}',
        'A look-up runs at once and its answer comes back to you. Anything that changes something becomes a card the',
        'owner confirms - a few that can be undone run at once, with the undo on the receipt. When two different',
        'things fit and you cannot tell which, ask one short question and end with OPTIONS: first | second instead.',
        'Never both, never a tool that is not listed. A task the owner names goes in params.ref ("TQ-0123"); otherwise',
        'the item on the table is the target. A decision about a DIFFERENT item than the one on the table puts the',
        'words that name it in params.on. A SET of items goes in params.select (SELECT below).',
        '',
        'WHERE THINGS ARE - look before you guess, and before you say you do not know or offer to look:',
    ]
    for said, kind, params in WHERE:
        lines.append(f'  {said} -> CALL: {{"kind": "{kind}", "params": {json.dumps(params)}}}')
    lines += ['', 'TOOLS, IN BUCKETS. CALL tools.list with {"bucket": "<name>"} to see each tool in a bucket and what it needs,',
              'or tools.describe with {"kind": "<tool>"}. When you already know a tool and what it needs, CALL it directly.']
    for name, what, kinds in BUCKETS:
        lines.append(f'  {name} - {what}: {", ".join(signature(k) for k in kinds)}')
    lines += ['', selector(store), '',
        'WHICH ONE, in this order:',
        '  1. the owner means one of the action words under your line - do that (bucket table).',
        '  2. they want detail, history or a summary - LOOK IT UP and answer with what you read. Search the period',
        '     THEY mean: six months ago means days: 200, not the last week.',
        '  3. they want something DONE and it says what - CALL it now; the card is their confirmation. A reminder or',
        '     a to-do they will do themselves is task.create_from_text kind task; a task that exists is never a new',
        '     one - change it with the task bucket.',
        '  4. it is not clear which - LOOK first; then, if two different things still fit, ASK one short question',
        '     naming both. A question about this app itself - its settings, reports, connections, agents - is',
        '     answered from the look-ups, never handed to an agent.']
    return '\n'.join(lines)


# THE DECISIONS about the item on the table, as tools like any other (2026-09-25). The model named tools on
# DECIDE lines and verbs on CALL lines; there is one line now, and concierge turns a CALL to one of these into
# the decision road the card's buttons take. Each takes `on` for an item other than the one on the table.
DECISIONS = {
    'reply':           "write a reply to the sender - `text`: the gist, in the owner's words. Nothing is sent",
    'approve':         'send the drafted reply as it stands',
    'redraft':         'write the draft again - `text`: the change',
    'mine':            "make it a task on the owner's own list - no agent",
    'regular_agent':   'send it to a non-coding agent - `text`: the job; `as`: a profile from agents.list, only when one fits',
    'coder':           ('send it to a coding agent - `text`: what is wanted; `as`: the repository (repos.list), only when sure. '
                        'Not sure which repository is no reason to ask - CALL it, and its card offers every repository to pick'),
    'not_ours':        'file it, just this once - its card asks whether from now on, or as a rule',
    'not_ours_sender': 'file everything from this sender from now on - their mail still arrives and stays readable',
    'block_sender':    'an exclusion rule in Settings: the sender never reaches triage again - only when they ask for a rule',
    'close':           'Mark done - the task behind the item is finished',
    'done':            'the owner handled it - Mark done on a task; on an idea, a report or an fyi it is read and settled',
    'next':            'move on to the next thing',
    'answer_agent':    'answer the agent waiting on the owner - `text`',
    'stop_agent':      "save and end the agent's session on the item",
    'rerun':           'run the report on the table again',
    'remember':        'keep a fact - `text`',
    'setup':           'build a report, a connection to another system or an automation - `text`: the request. Never a to-do',
    'clear':           'clear these from the pipe - `text`: which',
    'confirm':         "the owner's yes to the card already waiting - only when one is",
    'cancel':          "the owner's no to it",
}

# WHERE THINGS ARE: the owner's question, and the look-up that answers it - an example CALL each.
WHERE = (
    ('what is waiting on the owner', 'pipe.list', {}),
    ("a task's story - its messages, notes, agent and draft", 'task.read', {'ref': 'TQ-0123'}),
    ('mail or chat about something, however old', 'timeline.search', {'contains': 'invoice', 'days': 60}),
    ('one message in full', 'message.read', {'mid': 4321}),
    ('a person - how often they write, their open tasks', 'sender.read', {'who': 'Erin'}),
    ('open work', 'tasks.list', {'contains': 'export'}),
    ('how something is done here - a policy, a system, a site', 'knowledge.search', {'query': 'PO approval limit'}),
    ('how Taskuary itself works', 'docs.search', {'query': 'remind me'}),
    ('reports and workflows', 'reports.list', {}),
    ('a setting', 'setting.read', {'label': 'auto-drafts'}),
    ('connections', 'connections.list', {}),
    ('agents, profiles and which brain does what', 'agents.list', {}),
    ('the repositories a coding agent can work in', 'repos.list', {}),
    ("the owner's meetings", 'calendar.read', {'from': 'tomorrow'}),
    ('what is failing, or failed', 'errors.list', {}),
    ('what you remember about the owner', 'memory.list', {}),
)

# THE BUCKETS. Every tool is in one (a test holds it to that), so the index is exhaustive though no tool's
# detail rides the turn.
BUCKETS = (
    ('table', 'decide about the item on the table', tuple(DECISIONS)),
    ('task', 'change any task - the one on the table or one named with ref',
     ('task.update', 'task.set_kind', 'task.set_repo', 'task.check', 'task.comment', 'task.split', 'task.merge', 'task.reopen',
      'task.not_a_task', 'task.complete', 'task.defer', 'task.handoff', 'task.clarify', 'review.approve', 'review.reject')),
    ('agents', 'start, continue, answer or stop the agent on a task, and teach where work belongs',
     ('dispatch.prepare', 'agent.continue', 'agent.answer', 'agent.stop', 'routing.remember')),
    ('new', 'new work with no task yet', ('task.create_from_text', 'task.create_from_message', 'task.setup')),
    ('pipe', 'the walk and sets of items, and filing mail', ('pipe.clear', 'item.settle', 'message.file', 'message.archive',
                                                            'preference.exclude_sender', 'preference.sender_rule')),
    ('reports', 'reports and workflows', ('report.create', 'report.run', 'report.rerun', 'report.pause', 'report.resume',
                                          'report.reach', 'report.edit', 'report.delete')),
    ('app', 'settings, connections, scripts and kept facts', ('setting.set', 'connection.create', 'connection.test', 'connection.pause',
                                                             'connection.resume', 'script.start', 'memory.remember', 'hub.publish')),
)


# what a tool takes, when its registry entry cannot say it: a tool that needs one of several, or takes its words as `text`
HINTS = {'hub.publish': 'title, body, topic?, kind?, why_earned?', 'task.update': 'priority|title|assignee', 'reply': 'text', 'redraft': 'text', 'regular_agent': 'text, as?', 'coder': 'text, as?',
         'answer_agent': 'text', 'remember': 'text', 'setup': 'text', 'clear': 'text', 'task.handoff': 'who, note?',
         'dispatch.prepare': 'kind, instructions?', 'task.check': 'item, done?', 'task.defer': 'until'}


def signature(kind: str) -> str:
    """`task.handoff(who, note?)` - the name and what it needs, so a call does not guess its parameter names."""
    if kind in HINTS: return f'{kind}({HINTS[kind]})'
    if kind in operations.KINDS:
        asks = [r for r in operations.KINDS[kind][1] if r not in CONTEXT_FILLED]
        if asks: return f"{kind}({', '.join(asks)})"
    return kind


def describe(kind: str) -> str:
    """One tool in full: what it does, what it needs, and whether it waits for the owner's yes."""
    if kind in DECISIONS:
        return f'{kind} (bucket table) - {DECISIONS[kind]}. Takes `on` for another item than the one on the table.'
    if kind in READS: return f'{kind} (a look-up - runs at once, changes nothing) - {READS[kind]}'
    if kind in PURPOSE:
        target, required, _ = operations.KINDS[kind]
        asks = [r for r in required if r not in CONTEXT_FILLED]
        runs = 'runs at once, with an undo' if kind in INSTANT else 'a card the owner confirms'
        return f"{kind} (on a {target}; {runs}){' - needs ' + ', '.join(asks) if asks else ''} - {PURPOSE[kind]}"
    return f'There is no tool {kind!r}. The buckets: ' + ', '.join(n for n, _, _ in BUCKETS) + ', look.'


def bucket_list(name: str) -> str:
    """tools.list: each tool in one bucket, described - or the buckets, when the name is not one."""
    name = str(name or '').strip().lower()
    if name in ('look', 'looks', 'look-ups', 'lookups', 'read', 'reads'):
        return 'LOOK-UPS (run at once, change nothing):\n' + '\n'.join(f'  {describe(k)}' for k in READS)
    hit = next((b for b in BUCKETS if b[0] == name), None)
    if not hit:
        return 'The buckets: ' + '; '.join(f'{n} ({w})' for n, w, _ in BUCKETS) + '; look (every look-up).'
    return f'{hit[0].upper()} - {hit[1]}:\n' + '\n'.join(f'  {describe(k)}' for k in hit[2])


# READS. Everything above CHANGES something and waits for the owner's yes; these change nothing, so
# they run at once and their result comes straight back to the model, which then answers with it
# (the owner, 2026-09-07: "read should be immediate, yes it can take time since it's searching").
# A read never moves what is on the table: asking about another task must not hijack the walk.
READS = {
    'task.read':        'everything on one task - its summary, status, the messages on it, what agents said and did. `ref`: TQ-0401 (or `id`)',
    'timeline.search':  ('find messages anywhere in the history, however old - takes the same SELECT fields below, plus `limit`; here '
                         '`contains` matches the subject, the sender AND the body, best match first. Returns m-numbers, refs, senders, '
                         'subjects and dates; open one with message.read or its task with task.read'),
    # OPEN WORK, ONE MESSAGE, ONE PERSON, THE DOCS (lookups.py). "What's open", "what did that mail
    # actually say", "what do we have with her", "how do I set up X" had no read at all (2026-09-24).
    'tasks.list':       'the tasks - `status`: open (the default: open, in progress or waiting) | done | all; `contains`: words; `limit`',
    'message.read':     'one message in full - who, when, its task and the whole text. `mid`: the m-number timeline.search printed',
    'sender.read':      ('one person at a glance - how often they write, their recent messages, their open tasks, when you last '
                         'wrote back and what the owner told you to remember about them. `who`: a name or an address'),
    'docs.search':      ("how Taskuary works and how to set it up (the help pages), and the owner's own docs (SOUL, TRIAGE, "
                         'COUNSEL...). `query`: the words. Use it for any "how do I", "what does X do" or "why did it" about the app'),
    # THE APP AT WORK (lookups.py, 2026-09-24): which agent is on what, what waits on a yes, the
    # calendar past today, what happened, and every place a failure is written down.
    'agents.now':       'every agent session running now - its task, which CLI, and whether it is working, idle, stuck or asking the owner something',
    'approvals.list':   'everything waiting for the owner\'s yes: drafted replies and the actions agents proposed, with their tasks',
    'pipe.list':        ('everything waiting on the owner, lane by lane - replies, asks, approvals, stopped agents, reports: the whole '
                         'work rail. Use it for "what\'s waiting", "what\'s left", "what do I have"'),
    'calendar.read':   ('the owner\'s meetings - `from`: today (the default) | tomorrow | YYYY-MM-DD; `days`: how many (7 by default). '
                         'Reads the calendar live, so it takes a moment'),
    'activity.list':    ('what happened, from the audit trail: counts by kind and the latest entries. `days` (1 by default); '
                         '`who`: you | agents | all'),
    'errors.list':      ('what is failing and what failed: the bell (dismissed ones marked), failed agent runs, report runs, '
                         'drafts, triage and actions over `days` (3 by default), and the last errors in the log. Use it for any '
                         '"what broke", "why did X not happen", "is anything wrong"'),
    'memory.list':      ('everything kept about the owner: the saved notes (from "remember this", their verdicts, Settings) '
                         'and what LEARNED.md has learned from their verdicts. `about`: words to narrow it (a sender, a topic). '
                         'Use it for "what do you remember", "what do you know about me"'),
    'rules.list':       ('the standing filters on the owner\'s mail - queue mutes set with a reason, and the policy rules '
                         '(skip, ignore, escalate...) that decide before any model reads it. `about`: words to narrow it. '
                         'Use it for "why did I never see X", "what am I filtering"'),
    'report.read':      'a report or workflow and its last runs - what it said, whether it failed and why, and its source_id. `title`: part of its name (or `source_id`)',
    # THE APP ITSELF, by name (appfacts). Asked from a chat to "run me the AR report" the assistant had
    # no list of reports at all; "is Teams connected" had no answer but a guess (the owner, 2026-09-18).
    'reports.list':     'every report and workflow: name, source_id, clock, how it reaches the owner, last outcome',
    'settings.list':    'the settings in one `group` (or, with no group, the groups themselves and how many knobs each has)',
    'setting.read':     'one setting, its value in words and what it does. `key` (or `label`: part of its name)',
    'connections.list': 'every live connection: name, type, whether it has a key, last sync, last error - and how many catalogue cards are off',
    'connection.read':  'one connection in full. `name`: part of its name (or `connector_id`)',
    'agents.list':      'the agents and profiles, and which brain answers which job',
    'repos.list':       'the repositories a coding agent can work in, and what each one is for',
    'tools.list':       'every tool in one `bucket` (table, task, agents, new, pipe, reports, app, look) - what each does and needs',
    'tools.describe':   'one tool in full - `kind`: its name',
    # WHAT WE KNOW. "What is our PO limit", "who handles AP": the answer offered to "look it up in the
    # Hub" and then searched the mail, because no read reached the Hub, the documents or the kept facts.
    'knowledge.search': ('what the company knows - the Hub, the indexed documents and the facts the owner asked to keep. '
                         '`query`: the words to look for. Call it FIRST whenever the owner asks about a person, a site, a '
                         'policy, a system or how something is done here - never offer to look it up instead of looking'),
}

# Parameters the CHAT supplies from what is on the table, never the model: it has no way to know a
# pile key, and an operation listed under a header that says "this is the whole surface" has to be
# genuinely callable or the catalogue is lying.
CONTEXT_FILLED = frozenset({'key'})


def is_read(kind: str) -> bool: return kind in READS


def valid(kind: str, params: dict) -> str:
    """'' when this CALL is one the registry actually runs, otherwise why not."""
    if kind in READS:
        need = {'task.read': ('ref', 'id'), 'report.read': ('title', 'source_id'), 'timeline.search': (),
                'reports.list': (), 'settings.list': (), 'setting.read': ('key', 'label'),
                'connections.list': (), 'connection.read': ('name', 'connector_id'), 'agents.list': (),
                'knowledge.search': ('query',), 'tasks.list': (), 'message.read': ('mid', 'id'),
                'sender.read': ('who', 'sender'), 'docs.search': ('query',), 'agents.now': (), 'approvals.list': (), 'pipe.list': (),
                'calendar.read': (), 'activity.list': (), 'errors.list': (), 'memory.list': (), 'rules.list': (),
                'repos.list': (), 'tools.list': (), 'tools.describe': ('kind',)}[kind]
        if need and not any(str((params or {}).get(n) or '').strip() for n in need):
            return f"{kind} needs {' or '.join(need)}"
        return ''
    if kind not in operations.KINDS: return f'{kind} is not an operation this app has'
    if kind not in PURPOSE: return f'{kind} is not something the chat may ask for'
    # a setting may be named by its label instead of its key; concierge.call_turn resolves either
    alt = {'setting': ('label', 'key')}
    missing = [p for p in operations.KINDS[kind][1]
               if p not in CONTEXT_FILLED and not str((params or {}).get(p) or '').strip()
               and not any(str((params or {}).get(a) or '').strip() for a in alt.get(p, ()))]
    if missing: return f"{kind} needs {', '.join(missing)}"
    return ''


# ── the docs site's page (docs/site/assistant-tools.md), written from this file so it cannot drift ─────────────
# `python -m taskuary.toolcatalog` rewrites it; tests/test_task_tools.py fails when the page and the catalogue differ.
DOCS_PAGE = 'docs/site/assistant-tools.md'
# the decisions that do not wait for a card (concierge.AUTO, and the two that only ever write a draft)
DECISION_RUNS = {'next': 'at once', 'close': 'at once', 'done': 'at once', 'stop_agent': 'at once', 'confirm': 'at once',
                 'cancel': 'at once', 'reply': 'at once - a draft, nothing sent', 'redraft': 'at once - a draft, nothing sent'}


def _cell(s: str) -> str: return str(s).replace('|', '/').replace('`', '').replace('\n', ' ').strip()


def docs_markdown() -> str:
    """Two tables, what the Assistant sees: the buckets (every turn) and every tool in full (on demand)."""
    lines = ['<!-- Written by `python -m taskuary.toolcatalog` from taskuary/toolcatalog.py - edit the catalogue, not this page. -->',
             '',
             'What the Assistant is told about its tools. It gets the **summary** on every turn: the buckets, and',
             'each tool\'s name and what it needs. It asks for the **detail** of a bucket (`tools.list`) or a tool',
             '(`tools.describe`) only when a turn needs it. Everything it can change becomes a card you confirm,',
             'except the few that can be undone, which run at once with an undo on the receipt.',
             '',
             '## The summary, sent every turn',
             '',
             '| Bucket | What it is for | Tools, and what each needs |',
             '|---|---|---|']
    for name, what, kinds in BUCKETS:
        lines.append(f'| **{name}** | {_cell(what)} | {_cell(", ".join(signature(k) for k in kinds))} |')
    lines.append(f'| **look** | look-ups - they run at once and change nothing | {_cell(", ".join(READS))} |')
    lines += ['', 'A task you name goes in `ref` ("TQ-0123"); otherwise the tool acts on what is on the table.',
              '', '## Every tool, in detail', '',
              '| Tool | Bucket | Needs | What it does | Runs |',
              '|---|---|---|---|---|']
    for name, _what, kinds in BUCKETS:
        for k in kinds:
            text = DECISIONS.get(k) or PURPOSE.get(k) or ''
            needs = HINTS.get(k) or ', '.join(r for r in (operations.KINDS.get(k, ('', (), None))[1]) if r not in CONTEXT_FILLED) or '-'
            runs = DECISION_RUNS.get(k) or ('at once, with an undo' if k in INSTANT else 'you confirm')
            lines.append(f'| `{k}` | {name} | {_cell(needs)} | {_cell(text)} | {runs} |')
    for k, text in READS.items():
        lines.append(f'| `{k}` | look | - | {_cell(text)} | at once |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    from pathlib import Path
    out = Path(__file__).resolve().parent.parent / DOCS_PAGE
    out.write_text(docs_markdown(), encoding='utf-8', newline='\n')
    print(f'{DOCS_PAGE}: {len(BUCKETS)} buckets, {sum(len(k) for _, _, k in BUCKETS) + len(READS)} tools')
