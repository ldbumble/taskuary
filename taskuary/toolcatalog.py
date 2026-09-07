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
    'task.create_from_text':    'start an agent from a brief when there is no message behind it - `kind`, `text`',
    'message.file':             "file it - not ours, just this one",
    'message.archive':          'archive it: off the pipe and closed, nothing deleted',
    'preference.exclude_sender': 'teach triage to file this sender or subject from now on - their mail still arrives (`scope`: sender | subject)',
    'preference.sender_rule':   'an exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the Timeline',
    'item.settle':              'put the item down - `verb`: done | later | skip (the item on the table is the target)',
    'task.complete':            'close the task',
    'review.approve':           'send the drafted reply as it stands',
    'agent.answer':             'answer the agent that is waiting - `text`',
    'agent.stop':               'stop the running agent',
    'report.rerun':             'run that report again',
    'memory.remember':          'keep a fact - `note`',
    'task.split':               'split one arrival into two jobs - `text`',
    'pipe.clear':               'clear a SET of items from the pipe at once - takes `select` (below); read, never deleted',
    'task.setup':               'open a walk-through with the assistant - `text`',
}

# A set of items, described rather than listed. This is the part the verb vocabulary never had: it is
# how "all the reports" or "everything from that sender" is said in a way code can carry out exactly.
# A set of items, described rather than listed. This is the part the verb vocabulary never had: it is
# how "all the reports" or "everything from that sender" is said in a way code can carry out exactly.
# The vocabularies are read off the PILE ITSELF where a store is at hand, for the same reason the
# operations are read off the registry: a hand-written list drifts, and a category the model names
# that triage never emits is a promise that cannot be kept.
FALLBACK_CATEGORIES = ('report', 'info', 'idea', 'todo', 'coding', 'review', 'promo',
                       'automated', 'error', 'assistant', 'filed', 'ignored', 'yours')


def vocabularies(store=None) -> dict:
    """{category, kind, lane} -> the values actually in the pile right now."""
    out = {'category': list(FALLBACK_CATEGORIES), 'kind': [], 'lane': []}
    from . import funnel
    out['lane'] = list(funnel.LANES)
    if store is None: return out
    try:
        items = funnel.build(store, keep_surfaced=True)['items']
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
    """The catalogue as the model sees it: one line per operation, then the selector."""
    lines = ['THE OPERATIONS YOU CAN ASK FOR (this is the whole surface - there is nothing else)']
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
        'the operation has no verb. Never both in one answer, and never invent a kind.')
    return '\n'.join(lines)


# Parameters the CHAT supplies from what is on the table, never the model: it has no way to know a
# pile key, and an operation listed under a header that says "this is the whole surface" has to be
# genuinely callable or the catalogue is lying.
CONTEXT_FILLED = frozenset({'key'})


def valid(kind: str, params: dict) -> str:
    """'' when this CALL is one the registry actually runs, otherwise why not."""
    if kind not in operations.KINDS: return f'{kind} is not an operation this app has'
    if kind not in PURPOSE: return f'{kind} is not something the chat may ask for'
    missing = [p for p in operations.KINDS[kind][1]
               if p not in CONTEXT_FILLED and not str((params or {}).get(p) or '').strip()]
    if missing: return f"{kind} needs {', '.join(missing)}"
    return ''
