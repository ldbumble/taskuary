"""Counsel: the private brief - the assistant's own read on a message, written FOR the owner.

Triage answers "is this work?", the responder answers the sender, and until now nothing spoke
to the owner. An info mail was filed and forgotten; a calendar invite was just another email;
a reply was drafted from six thread messages with no memory of what the same person asked
last week. The brief closes that gap with ONE cheap step after the verdict: gather what the
hub already knows (this sender's recent mail, the owner's own replies to them, the same topic
on other threads, open tasks it touches, the calendar around it), hand it to the model with
COUNSEL.md, and store a short opinionated brief on the message - what this is really about,
what I'd do, what to get ahead of, and the task nobody named yet.

The brief is private. SOUL.md's caution ("never commit the owner") governs text that goes OUT;
COUNSEL.md governs this, and asks for the opposite: a position, labelled guesses, the next
step. A suggested task never opens itself - it waits for one click on the panel.
"""
import json, re, threading
from datetime import datetime, timedelta
from loguru import logger


def later(fn, *args):
    """Run the brief off the ingest thread. Its own starter, not ingest._spawn: that one means
    "an agent or a draft was dispatched" and is what the dispatch tests count - a brief is neither."""
    threading.Thread(target=fn, args=args, daemon=True).start()

DAYS = 30                 # how far back the dossier reads
BRIEF_TOKENS = 450
_STRIP = re.compile(r'<!--.*?-->', re.S)
# Outlook and Google subject prefixes on meeting mail, for channels that carry no @odata.type (IMAP)
_INVITE_SUBJ = re.compile(r'^\s*((updated |new )?invitation|accepted|declined|tentative(ly accepted)?|cancel+ed|'
                          r'meeting (request|forward notification))\b', re.I)

CONTRACT = ('\n\nAnswer JSON only: {"read": "<one line: what this really is and what I would do - a position, '
            'not a summary>", "do": "<the single next step, or empty>", "ahead": ["<a thing that bites later '
            'if nobody moves - dated when the message dates it>"], "prep": ["<invites only: what to walk in '
            'knowing, one open item per person, the question worth asking>"], "suggest": {"title": "<a task '
            'the owner may not see, worded so it can be accepted as-is>", "why": "<12 words>"} or null, '
            '"nothing": true|false}. Empty lists and null are fine and expected on a plain notice; "nothing" '
            'true means: file it, there is no brief worth reading. Under 120 words in total.')
PREP = ('\n\nThis is a CALENDAR INVITE (or an update to one). Write the prep note, not a verdict: who is in '
        'the room and what is open with each of them from the history below, what the owner should walk in '
        'knowing, and one question worth asking. If the history says nothing about these people, say so '
        'in a word.')


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


def dossier(store, msg: dict, days: int = DAYS, exclude_mid: int = None, skip_conv: bool = False) -> str:
    """Everything the hub already knows that bears on this message, as prompt text - or '' when
    it knows nothing. Cheap: five local reads, one calendar fetch when a calendar is connected.
    skip_conv leaves out this message's own thread - the responder already has it in full."""
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
    cal = _calendar(store, frm, name_toks, subj_toks)
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


def parse(text: str) -> dict | None:
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return None
    if not isinstance(j, dict) or not str(j.get('read') or '').strip(): return None
    sug = j.get('suggest') if isinstance(j.get('suggest'), dict) and str((j.get('suggest') or {}).get('title') or '').strip() else None
    lst = lambda k: [str(x).strip() for x in (j.get(k) or []) if str(x).strip()][:4] if isinstance(j.get(k), list) else []
    return {'read': str(j['read']).strip()[:400], 'do': str(j.get('do') or '').strip()[:200], 'ahead': lst('ahead'),
            'prep': lst('prep'), 'suggest': {'title': str(sug['title']).strip()[:120], 'why': str(sug.get('why') or '').strip()[:160]} if sug else None,
            'nothing': bool(j.get('nothing')), 'at': datetime.now().isoformat(timespec='minutes')}


def render(b: dict) -> str:
    """The brief as one chat line or a digest row: the read, the step, what is ahead."""
    if not b: return ''
    out = [b['read']] + ([f"→ {b['do']}"] if b.get('do') else []) + [f"⏳ {a}" for a in b.get('ahead') or []] \
          + [f"📝 {p}" for p in b.get('prep') or []] + ([f"💡 Task? {b['suggest']['title']}"] if b.get('suggest') else [])
    return '\n'.join(out)


def brief(store, msg: dict, mid: int, intent: str = 'fyi', llm=None, invite: bool = False) -> dict | None:
    """Write and store the brief for one message. Returns it, or None when the model had nothing
    to say (a plain notice) or could not be read - a brief nobody can trust is not stored."""
    from .llm import build_llm
    from .triage import strip_boilerplate
    llm = llm or build_llm(store)
    if not llm: return None
    doc = _STRIP.sub('', store.doc('counsel') or '').strip()
    soul = store.doc('soul') or ''
    system = (doc + CONTRACT + (PREP if invite else '')
              + f"\n\nTriage already called this '{intent}'" + (' - it is a task on the list; brief the owner on what to watch around it.' if intent == 'task'
                                                                else ' - a reply is being drafted; brief the owner on what the reply should know.' if intent == 'reply_only'
                                                                else ' - no work was opened; if you see work the owner should know about, say so.')
              + (f"\n\nWho the owner is and what they are responsible for (from their own document; the reply rules in it are for text sent to OTHERS, not for this brief):\n{soul[:2000]}" if soul else ''))
    dos = dossier(store, msg, exclude_mid=mid)
    user = (f"Subject: {msg.get('subject') or ''}\nFrom: {msg.get('from_name') or ''} <{msg.get('from_email') or ''}>\n"
            f"Channel: {msg.get('channel') or ''}" + (f"\nTo: {len(msg.get('to') or [])} · Cc: {len(msg.get('cc') or [])}" if msg.get('to') or msg.get('cc') else '')
            + f"\n\n{strip_boilerplate(str(msg.get('body') or ''))[:3000]}"
            + (f"\n\n--- WHAT YOU ALREADY KNOW\n{dos[:5000]}" if dos else '\n\n--- WHAT YOU ALREADY KNOW\n(nothing on file about this sender or topic - the brief rests on the message alone)'))
    out = parse(llm(system, user, max_tokens=BRIEF_TOKENS))
    if not out: return None
    out['history'] = bool(dos)
    store.set_brief(mid, json.dumps(out))
    return out


def after_triage(store, msg: dict, mid: int, tid, intent: str, llm=None, invite: bool = False) -> None:
    """The one entry ingest calls, in a thread. Gated by the switch; never raises. A brief with
    something to get ahead of (or a task to suggest) is also pushed to the notify channels - a
    filed message otherwise makes no sound, and that silence is exactly what this fixes."""
    try:
        if store.get_settings().get('counsel_enabled', '1') != '1': return
        b = brief(store, msg, mid, intent, llm, invite)
        if not b or b.get('nothing'): return
        if tid: store.add_comment(tid, 'counsel', 'agent', 'ASSISTANT BRIEF\n' + render(b))
        if intent != 'task' and (b.get('ahead') or b.get('suggest') or invite) and store.get_settings().get('notify_level', 'needs_me') != 'off':
            from .outbound import notify
            head = 'Prep note' if invite else 'Heads-up'
            notify(store, f"{head} · {msg.get('subject') or '(no subject)'}\n{render(b)}",
                   about={'Channel': msg.get('channel'), 'ConversationId': msg.get('conversation_id')})
    except Exception as e:
        logger.warning(f'counsel failed for message {mid}: {e}')


def msg_of(row: dict) -> dict:
    """A stored message row back into the dict shape the funnel passes around."""
    rec = json.loads(row.get('RecipientsJson') or 'null') or {}
    return {'external_id': row.get('ExternalId'), 'channel': row.get('Channel'), 'conversation_id': row.get('ConversationId'),
            'subject': row.get('Subject'), 'from_name': row.get('FromName'), 'from_email': row.get('FromEmail'),
            'sent_at': row.get('SentAt'), 'body': row.get('BodyText'), 'source_name': row.get('SourceName'),
            'to': rec.get('to'), 'cc': rec.get('cc')}
