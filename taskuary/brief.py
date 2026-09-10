"""One task brief for either worker kind (PW-183).

A coding session and the general assistant used to be handed different piles in different orders,
each with the whole of SOUL.md under it. The brief is the one authoritative structure both read:
the task id and title, the objective, the triage checklist, the owner's explicit instruction, the
repository when there is one, the latest complete substantive conversation (the chain as stored,
history included, cleaned and budgeted the way triage reads it), the attachments on the machine -
and the revision of the context it was built from, so a worker's result can be checked against
what it actually read. Rules ride separately: AGENT.md for both kinds, CODER.md on top for coding.
"""
from .store import task_ref


def build(store, tid: int, instruction: str = None, repo: str = None, context_budget: int = None) -> dict:
    """The sections, as data. `render` turns them into prompt text; callers choose what else rides."""
    from . import operations
    from .ingest import exchange_lines
    from .triage import strip_boilerplate
    t = store.get_task(tid) or {}
    msgs = [m for m in store.list_messages(tid) if m.get('Status') not in ('context', 'skipped')]
    last = msgs[-1] if msgs else None
    context = ''
    if last:
        lines = exchange_lines(store, {'conversation_id': last.get('ConversationId'), 'subject': last.get('Subject'),
                                       'sent_at': None}, budget=context_budget)
        context = '\n'.join(lines)
        if not context: context = strip_boilerplate(str(last.get('BodyText') or ''))
    atts = [a for m in msgs for a in store.list_attachments(m['MessageId']) if a.get('Path')]
    return {
        'task': f"{task_ref(tid)} - {t.get('Title') or ''}",
        'objective': str(t.get('Summary') or '').strip(),
        'checklist': store.checklist_markdown(tid) if hasattr(store, 'checklist_markdown') else '',
        'instruction': (instruction or '').strip(),
        'repository': repo or '',
        'context': context,
        'latest': {'from': (last.get('FromName') or last.get('FromEmail') or '') if last else '', 'channel': last.get('Channel') if last else '',
                   'subject': last.get('Subject') if last else '', 'body': strip_boilerplate(str(last.get('BodyText') or '')) if last else ''},
        'attachments': [{'name': a.get('Name'), 'path': a.get('Path')} for a in atts[:8]],
        'message_ids': [m['MessageId'] for m in msgs],
        'revision': operations.context_revision(store, 'task', tid),
    }


def rules(store, doc: str, chars: int) -> str:
    """An operator rules document, flattened for a prompt: headings become plain words, one line."""
    text = str(store.doc(doc) or '')
    keep = [l.strip(' #*-').strip() if l.lstrip().startswith('#') else l.strip() for l in text.splitlines() if l.strip()]
    return ' '.join(' '.join(keep).split())[:chars]
