"""The default end-of-day checkup.

This is deliberately a scheduled report, not another always-on Assistant producer. It runs once
at the end of the local workday, reads a short rolling window of WHATEVER is connected - mail, chat,
task trackers - and the owner's own Taskuary tasks and agent runs, and files one durable brief on the
Timeline. Its instruction remains editable on the Reports tab.

Email is not a requirement (the owner, 2026-10-21): a home may be monday.com only, chat only, or
nothing but its own tasks. What is connected is read off the poller's own list at run time
(sources), a connection that cannot be read is named on the run rather than read as "nothing came
in", and a home with truly nothing to report on is a skipped run with the reason, never a brief over
nothing (brief).
"""
import json, sqlite3
from datetime import datetime, timedelta

from .categories import category_of, team_domains_of
from .counsel import is_invite


HOURS = 8

# The brief says only what the data bears out. The old text named "top 3" in two headings and asked for a closing
# line "acknowledging progress", so a quiet day with one open item read "top 3 priorities: 1) ..." and "Good
# progress today" (2026-09-29). A count is the data's to give, and praise needs something completed.
PROMPT = (
    'Give me an executive and concise end-of-day brief over the last 8 hours: what came in and what I did '
    'across every source in the data, and my own Taskuary tasks and agent work.\n\n'
    'Start with exactly two one-sentence roll-ups:\n'
    'Done today: the main themes completed today, and the number of meeting invites handled when there were any.\n'
    'Tomorrow: the most urgent and important open items, at most three.\n\n'
    'Then use these groups in this order, omitting a group entirely when its data has no items:\n'
    'What I accomplished today\n'
    'Focus for tomorrow\n\n'
    'One bullet per item the data supports - at most five for today and three for tomorrow, never padded. '
    'Never state a number of items the data does not show. Use exactly this bullet shape: '
    '[Who or where] — Subject — one-line gist. Begin completed items with ✅, priorities with 🔍, and meeting '
    'invites with 📅 (an invite may use 📅 with ✅ or 🔍). Rank tomorrow by urgency and importance.\n\n'
    'Exclude bulk and marketing mail, system notifications, receipts, and anything suppressed by a blocked '
    'sender or keyword rule. Include meeting invites and flagged messages when the supplied data identifies them. '
    'Do not infer that an item was completed, flagged, deleted, archived, or still open unless the data says so. '
    'Do not mention excluded items or missing groups. When the data says a source could not be read, say so in '
    'one short line first and never say nothing came in from it. '
    'End with one short, plain closing sentence that the data bears out: speak of progress only when something '
    'was completed; on a quiet day, say what is left instead. No preamble, table, or extra sections.'
)

# shipped instructions an unedited report still runs - store.py moves it to PROMPT; an owner-edited one is never touched
OLD_PROMPTS = (
    # the Inbox-and-Sent-only instruction until 2026-10-21: it read nothing but email
    'Give me an executive and concise evening Inbox Brief for emails in my Inbox (Focused and Other) '
    'and Sent from the last 8 hours only.\n\n'
    'Start with exactly two one-sentence roll-ups:\n'
    'Done today: the main themes completed today and the number of meeting invites handled.\n'
    'Tomorrow: the most urgent and important open items, at most three.\n\n'
    'Then use these groups in this order, omitting a group entirely when its data has no items:\n'
    'What I accomplished today\n'
    'Focus for tomorrow\n\n'
    'One bullet per item the data supports - at most five for today and three for tomorrow, never padded. '
    'Never state a number of items the data does not show. Use exactly this bullet shape: '
    '[Sender] — Subject — one-line gist. Begin completed items with ✅, priorities with 🔍, and meeting '
    'invites with 📅 (an invite may use 📅 with ✅ or 🔍). Rank tomorrow by urgency and importance.\n\n'
    'Exclude every other folder or channel, bulk and marketing mail, system notifications, receipts, and '
    'anything suppressed by a blocked sender or keyword rule. Include meeting invites and flagged messages '
    'when the supplied data identifies them. Do not infer that an item was completed, flagged, deleted, '
    'archived, or still open unless the data says so. Do not mention excluded items or missing groups. '
    'End with one short, plain closing sentence that the data bears out: speak of progress only when something '
    'was completed; on a quiet day, say what is left instead. No preamble, table, or extra sections.',
    'Give me an executive and concise evening Inbox Brief for emails in my Inbox (Focused and Other) '
    'and Sent from the last 8 hours only.\n\n'
    'Start with exactly two one-sentence roll-ups:\n'
    'Summary of accomplishments: the main themes completed today and the number of meeting invites handled.\n'
    'Summary of top 3 priorities for tomorrow: the three most urgent and important open items.\n\n'
    'Then use these groups in this order, omitting a group entirely when its data has no items:\n'
    'What I accomplished today\n'
    'Top 3 things to focus on tomorrow\n\n'
    'Give each group 3-5 bullets. Use exactly this bullet shape: '
    '[Sender] — Subject — one-line gist. Begin completed items with ✅, priorities with 🔍, and meeting '
    'invites with 📅 (an invite may use 📅 with ✅ or 🔍). Rank tomorrow by urgency and importance.\n\n'
    'Exclude every other folder or channel, bulk and marketing mail, system notifications, receipts, and '
    'anything suppressed by a blocked sender or keyword rule. Include meeting invites and flagged messages '
    'when the supplied data identifies them. Do not infer that an item was completed, flagged, deleted, '
    'archived, or still open unless the data says so. Do not mention excluded items or missing groups. '
    'End with one short motivational sentence acknowledging progress, such as “Great progress today—tomorrow’s '
    'priorities are clear!” No preamble, table, or extra sections.',
)


CONTRACT = (
    '\n\nYOU ARE WRITING THE END OF DAY BRIEF. Follow the report instruction exactly. Plain text '
    'only: the two named roll-ups, then the named groups and bullets, then one short closing sentence. '
    'Never claim more items, or more progress, than the rows show. '
    'The supplied rows are the complete eligible Taskuary slice for the stated window - every connected source, '
    'and the owner\'s own tasks and agent runs - unless a block explicitly says it was capped. A source the data '
    'says could not be read is unknown, not quiet. Never promote an excluded row into the brief, never call an '
    'automatic filing a user accomplishment, and never invent flags or actions that are not present in the data.'
)


# A receipt is a system's mail, and the verdict already says so (sender_class "automated" -> the category dropped
# below). A word list over subject and body used to drop "receipts", and with them a person's "your payment is
# overdue - please call me" (2026-10-11, the owner: "everything should be ai").


def system(store) -> str:
    """Use Taskuary's normal assistant voice while enforcing the evening brief shape."""
    from . import counsel
    voice = counsel.for_brief(store)
    soul = store.doc('soul') or ''
    return (voice + CONTRACT
            + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}"
               if soul else ''))


def _one_line(value, limit=220) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _invite(row: dict) -> bool:
    return is_invite(row)          # the stored invite mark (MailMetaJson), never the words of the route reason


def _mail_meta(row: dict) -> dict:
    try:
        value = json.loads(row.get('MailMetaJson') or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _row_line(row: dict, state: str) -> str:
    who = 'You' if state == 'sent' else (row.get('FromName') or row.get('FromEmail') or 'Unknown sender')
    bits = [
        f"state={state}",
        f"sender={_one_line(who, 80)}",
        f"subject={_one_line(row.get('Subject') or '(no subject)', 140)}",
        f"at={str(row.get('SentAt') or '')[:16]}",
    ]
    if row.get('Channel') and row['Channel'] != 'email': bits.append(f"where={row['Channel']}")
    if _invite(row): bits.append('invite=yes')
    meta = _mail_meta(row)
    if str(meta.get('flag') or '').lower() == 'flagged': bits.append('flagged=yes')
    if meta.get('focus'): bits.append(f"inbox_lane={meta['focus']}")
    if row.get('Priority'): bits.append(f"priority={row['Priority']}")
    if row.get('TaskStatus'): bits.append(f"task_status={row['TaskStatus']}")
    if row.get('ReviewStatus'): bits.append(f"reply_status={row['ReviewStatus']}")
    if row.get('RouteReason'): bits.append(f"triage={_one_line(row['RouteReason'], 160)}")
    gist = _one_line(row.get('BodyText'), 320)
    if gist: bits.append(f"gist={gist}")
    return ' | '.join(bits)


def sources(store) -> list:
    """[{label, channel, ok, why}] - every connection the poller reads, and whether it can be read right now. The
    poller's own list (channels._poll_jobs) says what is connected, so no channel is named here and a card added
    later is covered without a word; its health is the card's own state (Microsoft's sign-in, the last poll's error)."""
    from . import channels, connectorcatalog, problems
    out = []
    for c, _ in channels._poll_jobs(store):
        err = str(c.get('LastError') or '').strip()
        why = ('signed out - sign in again under Connections' if problems.signed_out(c)
               else channels.plain_error_text(err)[:200] if err else '')
        label = (c.get('Name') or '').strip() or (connectorcatalog.by_type(c['Type']) or {}).get('title') or c['Type']
        out.append({'label': label, 'channel': channels.CH2SRC[c['Type']], 'ok': not why, 'why': why})
    return out


def _and(xs): return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + f' and {xs[-1]}'


def collect(store, hours: int = HOURS) -> dict:
    """The window's evidence: the connected channels' rows sorted into done and open, and the owner's own tasks and
    agent runs. Every channel a connection lands in is read (channels.CH2SRC), not email alone. New Outlook rows
    retain Inbox/Sent, Focused/Other and flag state; rows from before that metadata are treated as Inbox."""
    from .channels import CH2SRC
    hours = max(1, min(int(hours or HOURS), 48))
    since = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    chans = sorted(set(CH2SRC.values()))
    # newest route/review by index per row, never a GROUP BY over the whole table (the store.feed fix)
    rows = store._rows(
        f"""SELECT m.*, t.Status TaskStatus, t.Priority,
                  rt.Decision, rt.Reason RouteReason, rt.RoutedBy,
                  rv.Status ReviewStatus
             FROM message m
             LEFT JOIN task t ON t.TaskId=m.TaskId
             LEFT JOIN route rt ON rt.RouteId=(SELECT MAX(RouteId) FROM route WHERE MessageId=m.MessageId)
             LEFT JOIN review rv ON rv.ReviewId=(SELECT MAX(ReviewId) FROM review WHERE MessageId=m.MessageId)
            WHERE m.Channel IN ({','.join('?' * len(chans))}) AND m.SentAt>=?
            ORDER BY m.SentAt DESC, m.MessageId DESC
            LIMIT 500""",
        (*chans, since),
    )
    team = team_domains_of(store.get_settings())
    eligible, sent, archived = [], [], []
    for row in rows:
        meta = _mail_meta(row)
        mine = row.get('Status') == 'context' or row.get('Direction') == 'out'
        if mine:
            sent.append(row)
            continue
        # Graph source cards may also watch custom folders. Only a mailbox's Inbox belongs in this brief;
        # rows from before folder metadata shipped are Inbox by the historical default.
        if meta.get('folder') and str(meta['folder']).lower() != 'inbox':
            continue
        if row.get('Status') == 'ignored' and row.get('RoutedBy') == 'owner':
            archived.append(row)
            continue
        category = category_of({**row, 'MsgStatus': row.get('Status')}, team)
        # Policy suppression is excluded, as are the two categories specifically meant to keep
        # bulk/system traffic (receipts among it) out of a human brief. Owner filing above is a completed action.
        if row.get('Status') in ('skipped', 'ignored', 'withdrawn') or category in ('promo', 'automated'):
            continue
        eligible.append(row)

    accomplished = []
    accomplished.extend(_row_line(r, 'sent') for r in sent)
    accomplished.extend(_row_line(r, 'archived') for r in archived)
    for row in eligible:
        review = str(row.get('ReviewStatus') or '').lower()
        if review in ('approved', 'edited', 'sent'):
            accomplished.append(_row_line(row, 'replied'))
        elif row.get('TaskStatus') == 'done':
            accomplished.append(_row_line(row, 'completed'))
        elif _invite(row):
            # Ingest has positively identified and triaged this as a calendar invite. It is safe
            # to call handled; a plain auto-filed FYI is intentionally not treated the same way.
            accomplished.append(_row_line(row, 'invite handled'))

    priorities = []
    for row in eligible:
        review = str(row.get('ReviewStatus') or '').lower()
        flagged = str(_mail_meta(row).get('flag') or '').lower() == 'flagged'
        if flagged or review == 'pending' or row.get('TaskStatus') in ('open', 'in_progress', 'waiting'):
            priorities.append(_row_line(row, 'open priority'))

    from .store import task_ref
    done = store._rows("SELECT TaskId, Title, Priority FROM task WHERE Status='done' AND ClosedAt>=? "
                       "ORDER BY ClosedAt DESC LIMIT 80", (since,))
    open_ = store._rows("SELECT TaskId, Title, Priority, Status FROM task WHERE Status IN ('open','in_progress','waiting') "
                        "ORDER BY CASE Priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, COALESCE(UpdatedAt, CreatedAt) DESC "
                        "LIMIT 40", ())
    runs = store._rows("SELECT r.AgentName, r.Status, r.LastError, r.TaskId, t.Title FROM run r LEFT JOIN task t ON t.TaskId=r.TaskId "
                       "WHERE COALESCE(r.FinishedAt, r.UpdatedAt, r.StartedAt)>=? ORDER BY r.RunId DESC LIMIT 80", (since,))
    def task_line(t, state):
        return f"state={state} | task={task_ref(t['TaskId'])} | title={_one_line(t.get('Title'), 140)} | priority={t.get('Priority') or 'normal'}"
    def run_line(r):
        bits = [f"agent={_one_line(r.get('AgentName'), 60)}", f"status={r.get('Status') or 'running'}"]
        if r.get('TaskId'): bits.append(f"task={task_ref(r['TaskId'])} {_one_line(r.get('Title'), 120)}")
        if r.get('LastError'): bits.append(f"error={_one_line(r['LastError'], 160)}")
        return ' | '.join(bits)
    return {'hours': hours, 'since': since, 'accomplished': accomplished, 'priorities': priorities,
            'done': [task_line(t, 'closed') for t in done], 'open': [task_line(t, t.get('Status') or 'open') for t in open_],
            'runs': [run_line(r) for r in runs]}


def has_any(ev: dict) -> bool: return any(ev[k] for k in ('accomplished', 'priorities', 'done', 'open', 'runs'))


def gather(store, hours: int = HOURS, read=(), unread=()) -> str:
    """The evidence as the model reads it. `read` names the connections read, `unread` the (label, why) of those that
    could not be (sources): one that could not is said at the top, so its silence is never read as a quiet day."""
    return _text(collect(store, hours), read, unread)


def _text(ev: dict, read=(), unread=()) -> str:
    since, hours, accomplished, priorities = ev['since'], ev['hours'], ev['accomplished'], ev['priorities']
    out = [
        f"WINDOW: {since[:16]} through {datetime.now().strftime('%Y-%m-%d %H:%M')} ({hours} rolling hours)",
        f"SCOPE: {_and([*read, 'Taskuary tasks and agent runs'])}; of a mailbox, its Inbox (Focused and Other together) and Sent copies only.",
        *([f"COULD NOT READ THIS RUN: {'; '.join(f'{l} ({w})' for l, w in unread)}. Its rows below are only what Taskuary "
           'already held - never say nothing came in from it.'] if unread else []),
        'EXCLUSIONS APPLIED: blocked/ignored/withdrawn, bulk/marketing, system notifications, and receipts.',
        '',
        f"ACCOMPLISHED EVIDENCE ({len(accomplished)} rows; newest first):",
        *(accomplished[:80] or ['(none)']),
        '',
        f"OPEN PRIORITY EVIDENCE ({len(priorities)} rows; newest first):",
        *(priorities[:80] or ['(none)']),
        '',
        f"TASKUARY TASKS CLOSED IN THE WINDOW ({len(ev['done'])}):",
        *(ev['done'] or ['(none)']),
        '',
        f"TASKUARY AGENT RUNS IN THE WINDOW ({len(ev['runs'])}):",
        *(ev['runs'] or ['(none)']),
        '',
        f"TASKUARY TASKS STILL OPEN ({len(ev['open'])}, most urgent first):",
        *(ev['open'] or ['(none)']),
    ]
    if len(accomplished) > 80 or len(priorities) > 80:
        out += ['', 'CAP NOTICE: one or more evidence blocks were capped at 80 rows.']
    return '\n'.join(out)


def brief(store, hours: int = HOURS, unread: list = None) -> tuple:
    """(head, evidence) for one run. Skipped, loudly, when the only connections there are cannot be read and Taskuary
    holds no work; NothingToReport, quietly, when nothing is connected at all and Taskuary holds no work in the window
    or open - an empty home is not a fault (the owner, 2026-10-21). A connection that cannot be
    read is named on the run (`unread` collects (label, why) for run_report_source) and the run goes on over the rest;
    a connected source with nothing in the window is a normal, quiet run - zero items is a result."""
    from .reports import NothingToReport, Skipped
    srcs = sources(store)
    try: ev = collect(store, hours)
    except sqlite3.Error as e: raise Skipped(f"Skipped: Taskuary's own data could not be read - {e}") from e
    good, bad = [x for x in srcs if x['ok']], [x for x in srcs if not x['ok']]
    if not good and not has_any(ev):
        if bad: raise Skipped('Skipped: ' + '; '.join(f"{x['label']} could not be read ({x['why']})" for x in bad))
        # nothing connected and nothing done is not a failure to tell anyone about (the owner, 2026-10-21): a quiet skip
        raise NothingToReport(f"Nothing to report on: nothing is connected and Taskuary has no work in the last {ev['hours']} hours or still open")
    if unread is not None: unread += [(x['label'], x['why']) for x in bad]
    read = list(dict.fromkeys(x['label'] for x in good))
    head = f"the last {ev['hours']} hours of {_and([*read, 'your Taskuary work'])}" + ''.join(f" · {x['label']}: FAILED" for x in bad)
    return head, _text(ev, read, [(x['label'], x['why']) for x in bad])
