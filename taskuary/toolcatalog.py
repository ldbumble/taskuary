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
from . import operations

# What each operation is FOR, in the owner's terms. Kinds absent from here are internal roads the chat
# has no business offering (triage corrections, dispatch plumbing) and are left out of the catalogue.
PURPOSE = {
    'task.create_from_message': 'hand this message to an agent or put it on the list - `kind`: coding | general | task',
    'task.create_from_text':    ('a new job with no message behind it - `kind`: task (a to-do or reminder the owner does '
                                 'themselves, no agent) | general (a regular agent) | coding, and `text`'),
    'message.file':             "file it - not ours, just this one",
    'message.archive':          'archive it: off the pipe and closed, nothing deleted',
    'preference.exclude_sender': 'teach triage to file this sender or subject from now on - their mail still arrives (`scope`: sender | subject)',
    'preference.sender_rule':   'an exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the Timeline',
    'item.settle':              'put the item down - `verb`: done | later | skip (the item on the table is the target)',
    'task.complete':            'Mark done - the task is finished',
    'review.approve':           'send the drafted reply as it stands',
    'agent.answer':             'answer the agent that is waiting - `text`',
    'agent.stop':               'stop the running agent',
    'report.rerun':             'run that report again',
    'memory.remember':          'keep a fact - `note`',
    'routing.remember':         ('remember how work like this should be ROUTED next time - `field`: kind | profile | system, '
                                 'and `value`. kind: coding (an agent in a checkout) | general (the assistant) | task (the owner, '
                                 'no agent). system: where the work actually lives when no repository here can touch it, named '
                                 'plainly ("ADP"). It teaches triage and moves nothing - say it when the owner tells you a '
                                 'verdict was wrong, or where a kind of job really belongs.'),
    'task.split':               'split one arrival into two jobs - `text`',
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
INSTANT = frozenset({'report.run', 'report.pause', 'report.resume', 'report.reach', 'report.edit', 'setting.set',
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
    """The catalogue as the model sees it: what it can READ, what it can DO, then the selector."""
    lines = ['WHAT YOU CAN LOOK UP (these run at once and change nothing - use them before you guess,',
             'and before you say you do not know. They do not move what is on the table.)']
    for kind, purpose in READS.items():
        lines.append(f'  {kind} - {purpose}')
    lines += ['', 'WHAT YOU CAN ASK TO HAPPEN (each becomes a card the owner confirms - nothing runs on its own)']
    for kind, (target, required, _correction) in operations.KINDS.items():
        purpose = PURPOSE.get(kind)
        if not purpose: continue
        asks = [r for r in required if r not in CONTEXT_FILLED]
        need = f" needs {', '.join(asks)}" if asks else ''
        lines.append(f'  {kind} (on a {target}){need} - {purpose}')
    lines.append('')
    lines.append(selector(store))
    lines.append('')
    lines.append(
        'To ask for one, end your answer with a single line:\n'
        '  CALL: {"kind": "<one of the above>", "params": {...}}\n'
        'The item on the table is the target unless you say otherwise; for a SET put the selector in\n'
        'params.select. Nothing runs on a CALL - it becomes a card the owner confirms, exactly like a\n'
        'DECIDE. Use DECIDE for the ordinary one-item verbs; use CALL when the target is a SET, or when\n'
        'the operation has no verb. Never both in one answer, and never invent a kind.'
        '\n\nWHICH ONE, in this order:\n'
        '  1. the owner means one of the ACTION WORDS under your line - do that. It is what the\n'
        '     buttons run, and it is instant.\n'
        '  2. they want detail, history or a summary of a task or a message - LOOK IT UP first and\n'
        '     answer with what you read. Never say you cannot see something you could have read,\n'
        '     and search the period THEY mean: six months ago means days: 200, not the last week.\n'
        '  3. they want something DONE and it says what - propose it now. A reminder or a to-do they\n'
        '     will do themselves is task.create_from_text kind task, with the day in the text; a\n'
        '     setting changes with setting.set on the key a look-up found (settings.list, setting.read);\n'
        '     a report is report.create; a system is connection.create; work for an agent is\n'
        '     task.create_from_text kind general or coding. task.setup only for a set-up that needs\n'
        '     digging before anything can be configured - never for a plain reminder.\n'
        '  4. it is not clear which - LOOK first (the setting, the report, the task it might mean);\n'
        '     then, if two different things still fit, ASK one short question naming both. A CALL\n'
        '     is only a card the owner confirms, so a clear ask gets the card, not a question about\n'
        '     details the card lets them change. A question about this app itself - its settings,\n'
        '     reports, connections, agents - is answered from these look-ups, never handed to an agent.')
    return '\n'.join(lines)


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
                'calendar.read': (), 'activity.list': (), 'errors.list': (), 'memory.list': (), 'rules.list': ()}[kind]
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
