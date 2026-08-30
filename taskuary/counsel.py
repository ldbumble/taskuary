"""What the hub already knows about a message - the dossier - and what a calendar invite is.

Every voice that speaks for or to the owner reads the same history: the reply drafter (responder.history_block),
the assistant's post (assistant.prep) and the coder's context file (context.build) all call dossier() -
this sender's recent mail, what the owner last wrote them, the same topic on other threads, open tasks it
touches, the calendar around it. Cheap: five local reads and one calendar fetch.

A per-message private brief used to live here too (the owner, 2026-08-29: "not sure we need that") - one AI
call on every judged message, a box above every mail, a ping on every warning. The assistant now speaks on
its own clock instead (assistant.py), reading this same dossier; COUNSEL.md is that voice's document.
"""
import json, re
from datetime import datetime, timedelta
from loguru import logger


DAYS = 30                 # how far back the dossier reads
# Outlook and Google subject prefixes on meeting mail, for channels that carry no @odata.type (IMAP)
_INVITE_SUBJ = re.compile(r'^\s*((updated |new )?invitation|accepted|declined|tentative(ly accepted)?|cancel+ed|'
                          r'meeting (request|forward notification))\b', re.I)

def is_invite(m: dict) -> bool:
    """Graph marks meeting mail with @odata.type eventMessage (and a meetingMessageType); anything
    else is judged by the subject prefix Outlook/Google put on invites."""
    if str(m.get('@odata.type') or '').lower().endswith('eventmessage') or m.get('meetingMessageType'): return True
    return bool(_INVITE_SUBJ.match(str(m.get('subject') or m.get('Subject') or '')))


def _since(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _first(s, n): return ' '.join(str(s or '').split())[:n]


def _line(r) -> str:
    from .triage import strip_boilerplate
    when = str(r.get('SentAt') or '')[:10]
    who = 'you' if r.get('Status') == 'context' else (r.get('FromName') or r.get('FromEmail') or '?')
    tag = f" · TQ-{r['TaskId']:04d}" if r.get('TaskId') else ''
    return f"- {when} {who}: \"{_first(r.get('Subject'), 80)}\"{tag} - {_first(strip_boilerplate(str(r.get('BodyText') or '')), 160)}"


def dossier(store, msg: dict, days: int = DAYS, exclude_mid: int = None, skip_conv: bool = False, calendar: bool = True) -> str:
    """Everything the hub already knows that bears on this message, as prompt text - or '' when
    it knows nothing. Cheap: five local reads, one calendar fetch when a calendar is connected.
    skip_conv leaves out this message's own thread - the responder already has it in full;
    calendar=False skips the fetch for a caller that already holds the agenda (assistant.prep)."""
    from .routing import tokens
    frm = (msg.get('from_email') or '').lower()
    subj_toks = set(tokens(msg.get('subject') or ''))
    conv = msg.get('conversation_id')
    since, parts = _since(days), []
    if frm:
        theirs = [r for r in store.messages_from(frm, since, 8) if r['MessageId'] != exclude_mid and not (skip_conv and conv and r.get('ConversationId') == conv)]
        if theirs: parts.append(f'FROM THIS SENDER, last {days} days:\n' + '\n'.join(_line(r) for r in theirs))
        yours = store.own_replies_to(frm, since, 5)
        if yours: parts.append('WHAT YOU LAST WROTE TO THEM:\n' + '\n'.join(_line(r) for r in yours))
    if len(subj_toks) >= 2:
        # the same topic on OTHER threads - two shared subject words is the same matter, one is noise
        rows = [r for r in store.recent_messages(since, 300)
                if r['MessageId'] != exclude_mid and (r.get('FromEmail') or '').lower() != frm and (not conv or r.get('ConversationId') != conv)
                and len(subj_toks & set(tokens(r.get('Subject') or ''))) >= 2][:6]
        if rows: parts.append('SAME TOPIC ELSEWHERE:\n' + '\n'.join(_line(r) for r in rows))
    name_toks = set(tokens(msg.get('from_name') or '')) | ({frm.split('@')[0]} if frm else set())
    open_ = [t for t in store.list_tasks(active_only=True)
             if (subj_toks and len(subj_toks & set(tokens(t.get('Title') or ''))) >= 2)
             or (name_toks and name_toks & set(tokens(f"{t.get('Title') or ''} {t.get('Summary') or ''}")))][:5]
    if open_: parts.append('OPEN TASKS THAT TOUCH IT:\n' + '\n'.join(f"- TQ-{t['TaskId']:04d} {t.get('Status')}: {_first(t.get('Title'), 90)}" for t in open_))
    cal = _calendar(store, frm, name_toks, subj_toks) if calendar else ''
    if cal: parts.append(cal)
    return '\n\n'.join(parts)


def _calendar(store, frm: str, name_toks: set, subj_toks: set) -> str:
    """Meetings a week back and two ahead that involve this sender or this subject."""
    if store.get_settings().get('calendar_enabled', '1') != '1': return ''
    try:
        from . import calendar as cal
        ag = cal.agenda(store, days=21, start=datetime.now(cal.tz_of(store)).replace(second=0, microsecond=0) - timedelta(days=7))
    except Exception as e:
        logger.debug(f'counsel: calendar skipped - {e}'); return ''
    from .routing import tokens
    hits = []
    for e in ag.get('events') or []:
        people = ' '.join([e.get('organizer') or ''] + list(e.get('who') or [])).lower()
        if (frm and frm in people) or (name_toks and name_toks & set(tokens(people))) \
           or (len(subj_toks) >= 2 and len(subj_toks & set(tokens(e.get('subject') or ''))) >= 2):
            hits.append(f"- {e['start'][:16]} \"{e['subject']}\"" + (f" with {', '.join(e['who'][:5])}" if e.get('who') else '')
                        + (f" - {e['about']}" if e.get('about') else ''))
    return 'CALENDAR, a week back and two ahead, involving them or this subject:\n' + '\n'.join(hits[:8]) if hits else ''


def msg_of(row: dict) -> dict:
    """A stored message row back into the dict shape the funnel passes around."""
    rec = json.loads(row.get('RecipientsJson') or 'null') or {}
    return {'external_id': row.get('ExternalId'), 'channel': row.get('Channel'), 'conversation_id': row.get('ConversationId'),
            'subject': row.get('Subject'), 'from_name': row.get('FromName'), 'from_email': row.get('FromEmail'),
            'sent_at': row.get('SentAt'), 'body': row.get('BodyText'), 'source_name': row.get('SourceName'),
            'to': rec.get('to'), 'cc': rec.get('cc')}
