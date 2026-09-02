"""The default end-of-day inbox checkup.

This is deliberately a scheduled report, not another always-on Assistant producer. It runs once
at the end of the local workday, reads only email activity from a short rolling window, and files
one durable brief on the Timeline. Its instruction remains editable on the Reports tab.
"""
import json
import re
from datetime import datetime, timedelta

from .categories import category_of, team_domains_of
from .counsel import is_invite


HOURS = 8

PROMPT = (
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
    'priorities are clear!” No preamble, table, or extra sections.'
)


CONTRACT = (
    '\n\nYOU ARE WRITING THE EVENING INBOX BRIEF. Follow the report instruction exactly. Plain text '
    'only: the two named roll-ups, then the named groups and bullets, then one short closing sentence. '
    'The supplied rows are the complete eligible Taskuary email slice for the stated window unless a block '
    'explicitly says it was capped. Never promote an excluded row into the brief, never call an automatic '
    'filing a user accomplishment, and never invent mailbox flags or actions that are not present in the data.'
)


_RECEIPT = re.compile(
    r'\b(receipt|order confirmation|payment confirmation|invoice paid|your payment|purchase confirmation)\b',
    re.I,
)


def system(store) -> str:
    """Use Taskuary's normal assistant voice while enforcing the evening brief shape."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    soul = store.doc('soul') or ''
    return (doc + CONTRACT
            + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}"
               if soul else ''))


def _one_line(value, limit=220) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _invite(row: dict) -> bool:
    return (_mail_meta(row).get('invite') is True
            or 'calendar invite' in str(row.get('RouteReason') or '').lower()
            or is_invite(row))


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


def gather(store, hours: int = HOURS) -> str:
    """Return only eligible Inbox/Sent evidence in the exact rolling window.

    New Outlook rows retain Inbox/Sent, Focused/Other and flag state. Rows ingested by older
    versions predate that metadata and are treated as Inbox because Inbox was the default source.
    """
    hours = max(1, min(int(hours or HOURS), 48))
    start = datetime.now() - timedelta(hours=hours)
    since = start.strftime('%Y-%m-%d %H:%M:%S')
    rows = store._rows(
        """SELECT m.*, t.Status TaskStatus, t.Priority,
                  rt.Decision, rt.Reason RouteReason, rt.RoutedBy,
                  rv.Status ReviewStatus
             FROM message m
             LEFT JOIN task t ON t.TaskId=m.TaskId
             LEFT JOIN (SELECT MessageId, Decision, Reason, RoutedBy FROM route
                        WHERE RouteId IN (SELECT MAX(RouteId) FROM route GROUP BY MessageId)) rt
                    ON rt.MessageId=m.MessageId
             LEFT JOIN (SELECT MessageId, Status FROM review
                        WHERE ReviewId IN (SELECT MAX(ReviewId) FROM review GROUP BY MessageId)) rv
                    ON rv.MessageId=m.MessageId
            WHERE m.Channel='email' AND m.SentAt>=?
            ORDER BY m.SentAt DESC, m.MessageId DESC
            LIMIT 500""",
        (since,),
    )
    team = team_domains_of(store.get_settings())
    eligible, sent, archived = [], [], []
    for row in rows:
        meta = _mail_meta(row)
        mine = row.get('Status') == 'context' or row.get('Direction') == 'out'
        if mine:
            sent.append(row)
            continue
        # Graph source cards may also watch custom folders. Only Inbox belongs in this brief;
        # rows from before folder metadata shipped are Inbox by the historical default.
        if meta.get('folder') and str(meta['folder']).lower() != 'inbox':
            continue
        if row.get('Status') == 'ignored' and row.get('RoutedBy') == 'owner':
            archived.append(row)
            continue
        category = category_of({**row, 'MsgStatus': row.get('Status'), 'Preview': row.get('BodyText')}, team)
        # Policy suppression is excluded, as are the two categories specifically meant to keep
        # bulk/system traffic out of a human brief. Owner filing above is a completed action.
        if row.get('Status') in ('skipped', 'ignored', 'withdrawn') or category in ('promo', 'automated'):
            continue
        if _RECEIPT.search(f"{row.get('Subject') or ''} {row.get('BodyText') or ''}"):
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

    out = [
        f"WINDOW: {since[:16]} through {datetime.now().strftime('%Y-%m-%d %H:%M')} ({hours} rolling hours)",
        'SCOPE: email Inbox (Focused and Other together) and Sent copies retained by Taskuary only.',
        'EXCLUSIONS APPLIED: blocked/ignored/withdrawn, bulk/marketing, system notifications, and receipts.',
        '',
        f"ACCOMPLISHED EVIDENCE ({len(accomplished)} rows; newest first):",
        *(accomplished[:80] or ['(none)']),
        '',
        f"OPEN PRIORITY EVIDENCE ({len(priorities)} rows; newest first):",
        *(priorities[:80] or ['(none)']),
    ]
    if len(accomplished) > 80 or len(priorities) > 80:
        out += ['', 'CAP NOTICE: one or more evidence blocks were capped at 80 rows.']
    return '\n'.join(out)
