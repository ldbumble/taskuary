"""One task brief for either worker kind (PW-183).

A coding session and the general assistant used to be handed different piles in different orders,
each with the whole of SOUL.md under it. The brief is the one authoritative structure both read:
the task id and title, the objective, the triage checklist, the owner's explicit instruction, the
repository when there is one, the latest complete substantive conversation (the chain as stored,
history included, cleaned and budgeted the way triage reads it), the attachments on the machine -
and the revision of the context it was built from, so a worker's result can be checked against
what it actually read. Rules ride separately: AGENT.md for both kinds, CODING.md on top for coding.
"""
from .store import task_ref


def build(store, tid: int, instruction: str = None, repo: str = None, context_budget: int = None) -> dict:
    """The sections, as data. `render` turns them into prompt text; callers choose what else rides."""
    from . import operations
    from .ingest import exchange_lines
    from .triage import own_words
    t = store.get_task(tid) or {}
    msgs = [m for m in store.list_messages(tid) if m.get('Status') not in ('context', 'skipped')]
    last = msgs[-1] if msgs else None
    context = ''
    if last:
        lines = exchange_lines(store, {'conversation_id': last.get('ConversationId'), 'subject': last.get('Subject'),
                                       'sent_at': None}, budget=context_budget)
        context = '\n'.join(lines)
        if not context: context = own_words(str(last.get('BodyText') or ''))
    atts = [a for m in msgs for a in store.list_attachments(m['MessageId']) if a.get('Path')]
    return {
        'task': f"{task_ref(tid)} - {t.get('Title') or ''}",
        'objective': str(t.get('Summary') or '').strip(),
        'checklist': store.checklist_markdown(tid, ids=True) if hasattr(store, 'checklist_markdown') else '',   # ids: the agent ticks its own (--tick)
        'instruction': (instruction or '').strip(),
        'repository': repo or '',
        'context': context,
        'latest': {'from': (last.get('FromName') or last.get('FromEmail') or '') if last else '', 'channel': last.get('Channel') if last else '',
                   'subject': last.get('Subject') if last else '', 'body': own_words(str(last.get('BodyText') or '')) if last else ''},
        'attachments': [{'name': a.get('Name'), 'path': a.get('Path')} for a in atts[:8]],
        'message_ids': [m['MessageId'] for m in msgs],
        'revision': operations.context_revision(store, 'task', tid),
    }


# THE OWNER, before any rules (the owner, 2026-10-14: "I would do soul/job which is about the person, then specific profile for
# agent"). PW-184 had taken SOUL.md out of every worker and JOB.md never reached one, so an agent knew its rules and not whom it
# worked for - the people, the systems, the repos, what the job is. Every worker now reads both, whole, as background; the one
# part left out is SOUL.md's "What counts as a task", which is triage's sorting rules, not something an agent does.
BACKGROUND_DOCS = (('soul', 'SOUL.md - who the owner is, their people, systems and repositories'),
                   ('job', "JOB.md - the owner's job: what they own, who they serve, what matters"))
TRIAGE_ONLY = ('what counts as a task',)


def background(store, chars: int = 9_000) -> str:
    """SOUL.md and JOB.md as one background block, comments stripped and triage's own section dropped. '' when both are empty."""
    import re
    out = []
    for name, what in BACKGROUND_DOCS:
        text = re.sub(r'<!--.*?-->', '', str(store.doc(name) or ''), flags=re.S)
        keep, skip = [], False
        for line in text.splitlines():
            if re.match(r'^#{1,3} ', line): skip = line.strip('# ').strip().lower() in TRIAGE_ONLY
            if not skip: keep.append(line)
        body = re.sub(r'\n{3,}', '\n\n', '\n'.join(keep)).strip()
        if body: out.append(f'## {what}\n{body[:chars]}')
    # ...and what About you saved, which no doc carries: an agent asked for the job title the owner had typed in (the email walk, 2026-10-29)
    saved = [f'{k}: {v}' for k, n in (('Name', 'owner_name'), ('Job title', 'owner_title'), ('Company', 'owner_company'))
             if (v := ' '.join(str(store.get_setting(n) or '').split()))]
    if saved: out.insert(0, '## Saved in About you\n' + '\n'.join(saved))
    return ('ABOUT THE OWNER (background for everything below - facts about whom you work for, not tasks to do)\n\n'
            + '\n\n'.join(out)) if out else ''


def rules(store, doc: str, chars: int) -> str:
    """An operator rules document, flattened for a prompt: headings become plain words, one line."""
    text = str(store.doc(doc) or '')
    keep = [l.strip(' #*-').strip() if l.lstrip().startswith('#') else l.strip() for l in text.splitlines() if l.strip()]
    return ' '.join(' '.join(keep).split())[:chars]
