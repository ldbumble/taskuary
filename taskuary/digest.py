"""The morning brief's raw material - and the Morning digest REPORT that delivers it.

The digest used to be its own once-a-day machinery writing only the DIGEST.md doc, which
nobody opened: a brief nobody reads is not a brief. It is a REPORT now (reports.run_digest,
seeded on first run): the summary lands on the Timeline where mornings actually start, the
prompt below is edited like any report's on the Reports tab, deleting the source turns the
whole thing off - and the same run keeps DIGEST.md fresh for the Docs tab.
"""
from datetime import datetime, timedelta

DAYS = 3                 # the window the synthesis reads - matches the startup catch-up

# The seeded report's editable instruction - "configure what goes in there" IS this text,
# on the Reports tab. reports.AI_SYSTEM wraps it; this is only the ask.
#
# The two rules at the end are not decoration. A digest once announced "TQ-0032 pending
# review: approve/send draft 'Re: Resident Refund Request'" when TQ-0032 was a Docker issue
# and NOTHING was pending: it took a mail subject out of the verdicts block (a "not our
# task" the owner had already given) and pinned it to a TQ-ref from the open-work list.
# A brief that invents work waiting on you is worse than no brief, so a ref must arrive
# wearing the title the data gave it, and an empty section must stay empty.
PROMPT = (
    'Write what the owner, half awake, should hold in mind TODAY, under 400 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f3f7\ufe0f By the tags — the window in numbers: one bullet per tag from THE WINDOW BY TAG '
    '(coding, to do, review, info, automated, promo, ignored…) with its count and a few words on what '
    'that bucket was; then one bullet for open tasks by kind\n'
    '\U0001f680 In flight — what is being worked and who is waiting on whom\n'
    '⏳ Waiting on you — questions still unanswered, replies still unapproved\n'
    '\U0001f4ac Info from people — what colleagues told you (the info rows: sender and the gist, one bullet each, '
    'nothing to do)\n'
    '\U0001f4cc Keep honoring — verdicts you gave recently that should keep applying\n'
    '\U0001f4c8 Patterns — heads-ups (a sender getting louder, the same system failing twice)\n'
    'Every TQ-ref you write must appear in the data, described with the SAME title it has there - '
    'never restate a task under another subject, and never carry a subject across from one block '
    'to another. A block whose data reads "(none)" has nothing to say: omit its section entirely '
    'rather than filling it.\n'
    'Every TQ-ref keeps the link that follows it in the data, written right after the ref in the '
    'same bullet, so the reader clicks straight into the task. Lead with what needs the owner NOW.\n'
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.')

# every prompt ever SHIPPED, so store.__init__ can tell "still the stock text" (upgrade it)
# from "the owner wrote this" (never touch) - same deal the template docs get
OLD_PROMPTS = (
    (
    'Write what the owner, half awake, should hold in mind TODAY, under 350 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f680 In flight — what is being worked and who is waiting on whom\n'
    '⏳ Waiting on you — questions still unanswered, replies still unapproved\n'
    '\U0001f4cc Keep honoring — verdicts you gave recently that should keep applying\n'
    '\U0001f4c8 Patterns — heads-ups (a sender getting louder, the same system failing twice)\n'
    'Every TQ-ref you write must appear in the data, described with the SAME title it has there - '
    'never restate a task under another subject, and never carry a subject across from one block '
    'to another. A block whose data reads "(none)" has nothing to say: omit its section entirely '
    'rather than filling it.\n'
    'Every TQ-ref keeps the link that follows it in the data, written right after the ref in the '
    'same bullet, so the reader clicks straight into the task. Lead with what needs the owner NOW.\n'
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.'),
    'Write what the owner, half awake, should hold in mind TODAY, under 350 words, grouped into sections. Each section is its emoji header on its own line, then tight "- " bullets under it (one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these sections in this order, and OMIT any with nothing to say:\n🚀 In flight — what is being worked and who is waiting on whom\n⏳ Waiting on you — questions still unanswered, replies still unapproved\n📌 Keep honoring — verdicts you gave recently that should keep applying\n📈 Patterns — heads-ups (a sender getting louder, the same system failing twice)\nEvery TQ-ref you write must appear in the data, described with the SAME title it has there - never restate a task under another subject, and never carry a subject across from one block to another. A block whose data reads "(none)" has nothing to say: omit its section entirely rather than filling it.\nNever invent facts; no preamble, no sign-off, nothing outside the sections.',

    'Write what the owner, half awake, should hold in mind TODAY, in plain bullets under 350 words:\n'
    '- what is in flight and who is waiting on whom (name tasks by their TQ-refs)\n'
    '- questions still unanswered, replies still unapproved\n'
    '- verdicts the owner gave recently that should keep being honored\n'
    '- patterns worth a heads-up (a sender getting louder, the same system failing twice)\n'
    'Never invent facts; omit sections with nothing to say; no preamble, no sign-off.',

    'Write what the owner, half awake, should hold in mind TODAY, under 350 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f680 In flight — what is being worked and who is waiting on whom\n'
    '⏳ Waiting on you — questions still unanswered, replies still unapproved\n'
    '\U0001f4cc Keep honoring — verdicts you gave recently that should keep applying\n'
    '\U0001f4c8 Patterns — heads-ups (a sender getting louder, the same system failing twice)\n'
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.',
)

HEADER = ('# DIGEST.md — your morning brief\n\n'
          '_Written by the Morning digest report (Reports tab - its prompt decides what goes in\n'
          "here; deleting the report turns it off). For YOUR eyes - agents get their task's own\n"
          'context instead. Durable rules belong in Agent memory (Settings) or SOUL.md._\n\n')


def _block(out, head, lines):
    """A header with NOTHING under it is an invitation to fill the silence - the model reads
    the next block's lines as if they belonged to this one. Say "(none)" out loud instead."""
    out.append(head)
    out += list(lines) or ['  (none)']


def task_link(tid: int) -> str:
    """The URL that opens this task in the app - the digest carries one per task so the brief
    is a set of doors, not a reading. The UI honours #task=<id> on load (TaskHubPage)."""
    from . import config
    try: srv = config.load().get('server') or {}
    except Exception: srv = {}
    host = srv.get('host') or '127.0.0.1'
    if host in ('0.0.0.0', '::', ''): host = '127.0.0.1'
    return f"http://{host}:{srv.get('port') or 7787}/#task={int(tid)}"


def gather(store, days: int = DAYS) -> str:
    """The raw material, compact enough to hand an AI whole."""
    since = (datetime.now() - timedelta(days=days)).isoformat(sep=' ', timespec='seconds')
    out = []
    tasks = store.list_tasks()
    live = [t for t in tasks if t.get('Status') in ('open', 'in_progress', 'waiting')]
    # waiting-on-you first, then in progress, then open: the order the owner should read in
    rank = {'waiting': 0, 'in_progress': 1, 'open': 2}
    live.sort(key=lambda t: (rank.get(t.get('Status'), 3), -(t.get('TaskId') or 0)))
    _block(out, 'OPEN WORK (most urgent first; each line ends with the link that opens the task):',
           (f"  TQ-{t['TaskId']:04d} [{t['Status']}] {t.get('Title') or ''} "
            f"(kind {t.get('Kind')}, created {t.get('CreatedAt')}) {task_link(t['TaskId'])}" for t in live[:25]))
    done = [t for t in tasks if t.get('Status') == 'done' and str(t.get('UpdatedAt') or '') >= since]
    _block(out, 'FINISHED THIS WINDOW:', (f"  TQ-{t['TaskId']:04d} {t.get('Title') or ''}" for t in done[:20]))
    # the ref carries its task's TITLE here too (list_reviews already joins it): a line
    # holding only the attached MAIL SUBJECT let the subject and the ref drift apart, and a
    # brief that renames a task is a lie in the one place the owner trusts by default
    _block(out, 'WAITING ON THE OWNER (pending reviews):',
           (f"  TQ-{r['TaskId']:04d} ({(r.get('Title') or '?')[:60]}) {r.get('Kind')} "
            f"on mail: {(r.get('Subject') or '(no subject)')[:90]} {task_link(r['TaskId'])}" for r in store.list_reviews('pending')[:15]))
    notes = [m for m in store.list_memories() if str(m.get('CreatedAt') or '') >= since]
    # these quote mail subjects, which is exactly what got recycled into a fake pending
    # review once - the header says plainly that nothing here is live work
    _block(out, 'VERDICTS GIVEN THIS WINDOW (already durable in memory - standing rules, NOT open work,\n'
                'and the mail they quote is already decided):',
           (f"  [{m.get('Scope')}:{m.get('ScopeKey') or '*'}] {(m.get('Note') or '')[:110]}" for m in notes[:12]))
    feed = store.feed(limit=500, days=days)
    # the same one-word tags the Timeline wears (categories.py), counted - the brief opens with
    # them so "what was the last three days" is a glance, not a reading
    LABEL = {'coding': 'coding (sent to the agent)', 'todo': 'to do (yours, not code)', 'review': 'review (a reply drafted for you)',
             'info': 'info (a person told you something)', 'automated': 'automated (a system told you something)',
             'promo': 'promo (newsletters, marketing)', 'filed': 'filed', 'ignored': 'ignored', 'report': 'report',
             'feed': 'feed', 'yours': 'your replies', 'triaging': 'still triaging'}
    counts = {}
    for m in feed: counts[m.get('Category') or 'filed'] = counts.get(m.get('Category') or 'filed', 0) + 1
    _block(out, 'THE WINDOW BY TAG (every inbound item, tagged the way the Timeline shows it):',
           (f"  {LABEL.get(k, k)}: {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])))
    kinds = {}
    for t in live: kinds[t.get('Kind') or 'general'] = kinds.get(t.get('Kind') or 'general', 0) + 1
    _block(out, 'OPEN TASKS BY KIND:', (f"  {k}: {n}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])))
    _block(out, 'INFO FROM PEOPLE (colleagues told you something; nothing to do - the gist, newest first):',
           (f"  {m.get('FromName') or m.get('FromEmail') or '?'}: {(m.get('Subject') or '(no subject)')[:70]} - "
            f"{' '.join(str(m.get('Preview') or '').split())[:110]}" for m in [x for x in feed if x.get('Category') == 'info'][:15]))
    senders = {}
    for m in feed[:120]:
        who = m.get('FromName') or m.get('FromEmail') or m.get('SourceName') or '?'
        senders[who] = senders.get(who, 0) + 1
    loud = sorted(senders.items(), key=lambda kv: -kv[1])[:8]
    _block(out, 'WHO WROTE, HOW OFTEN:', (f'  {who}: {n}' for who, n in loud))
    return '\n'.join(out)


# build_digest / refresh_if_stale used to live here - their whole job (schedule, AI pass,
# no-AI fallback, filing) is what the reports pipeline already does, so the Morning digest
# report replaced them: reports.run_digest is the executor, run_report_source keeps the doc.
