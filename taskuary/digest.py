"""The morning brief: the ASSISTANT's summary of the window, delivered as the Morning digest REPORT.

The digest used to be its own once-a-day machinery writing only the DIGEST.md doc, which nobody
opened. It became a REPORT (reports.run_digest, seeded on first run): the summary lands on the
Timeline where mornings actually start, the prompt below is edited like any report's on the
Reports tab, deleting the source turns the whole thing off - and the same run keeps DIGEST.md fresh
for the Docs tab.

Then it was a brief of COUNTS - the window by tag, who wrote how often - and the owner
(2026-08-30): "useless... more like a summary assistant, not just stats but what's going on, what
we missed". So the digest now READS what the assistant reads (assistant.py: the words of every
human thread, who is out of office, the calendar, the machines' mail with each failure's cause,
open work with its state) plus what only a morning brief needs - the asks that slipped
(assistant.unanswered), the owner's own open loops (followups, promises, cold work), the pending
reviews, the verdicts given - and it SPEAKS in the assistant's voice (system(): COUNSEL.md, the
same document the Timeline assistant speaks from). It also knows what the assistant already
raised in the window, so the brief consolidates instead of rediscovering.
"""
import math, re
from datetime import datetime, timedelta

DAYS = 1                 # the window the synthesis reads: all of yesterday, plus today so far (gather starts at midnight)

# The seeded report's editable instruction - "configure what goes in there" IS this text,
# on the Reports tab. digest.system() wraps it; this is only the ask.
#
# The honesty rules at the end are not decoration. A digest once announced "TQ-0032 pending
# review: approve/send draft 'Re: Resident Refund Request'" when TQ-0032 was a Docker issue
# and NOTHING was pending: it took a mail subject out of the verdicts block (a "not our
# task" the owner had already given) and pinned it to a TQ-ref from the open-work list.
# A brief that invents work waiting on you is worse than no brief, so a ref must arrive
# wearing the title the data gave it, and an empty section must stay empty.
_PROMPT_WITHOUT_STANDING_MEMORY = (
    'Write my morning brief - what I, half awake, should hold in mind TODAY. Not a report of counts: '
    'a sharp assistant who has read everything telling me what is going on, what slipped, and what the '
    'day needs. Under 450 words, grouped into sections. Each section is its emoji header on its own line, '
    'then tight "- " bullets under it (one fact per bullet; first person is fine - "I\'d chase this"), then '
    'a blank line. Use exactly these sections in this order, and OMIT any with nothing to say:\n'
    '❗ What slipped — asks from people I have not answered (THEIR ASKS YOU HAVE NOT ANSWERED), promises I '
    'made and have not kept, replies waiting for my approval (WAITING ON THE OWNER), things I asked for that '
    'never came back (MY OPEN LOOPS): who, what, since when, what covers it, and what I would do - check OUT '
    'OF OFFICE before suggesting a chase, and say when they are back instead\n'
    '\U0001f4c5 Today — one bullet per meeting from MEETINGS TODAY, in time order: the time, the title, who is '
    'in it (first names, never me), what it is about in the invite\'s own words (the "about:" text; never '
    'guess a purpose from a title), and what in WHAT PEOPLE SAID bears on it\n'
    '\U0001f50e What happened — the story of the window from WHAT PEOPLE SAID and WHAT ARRIVED: who said what '
    'and what it means for me, decisions made, information worth holding, a machine\'s failure with its cause - '
    'the words, never the counts\n'
    '\U0001f680 In flight — from OPEN WORK and FINISHED THIS WINDOW: what an agent is on, what closed and what '
    'it shipped, what has gone quiet (push it or drop it - say which)\n'
    '\U0001f916 The assistant said — what it raised in the window that is still open (WHAT THE ASSISTANT ALREADY '
    'RAISED), one line each, and whether it still stands given the rest of the data\n'
    '\U0001f4cc Keep honoring — verdicts I gave in the window that should keep applying\n'
    '\U0001f4c8 Heads-up — patterns: a sender getting louder, the same system failing twice, a report whose '
    'every run says nothing\n'
    'Every TQ-ref you write must appear in the data, described with the SAME title it has there - never '
    'restate a task under another subject, and never carry a subject across from one block to another. A '
    'block whose data reads "(none)" has nothing to say: omit its section entirely rather than filling it. '
    'Every TQ-ref keeps the link that follows it in the data, written right after the ref in the same bullet, '
    'so I click straight into the task. Name people, dates and quoted phrases; use a number only where it '
    'carries meaning (THE WINDOW IN NUMBERS is one line at most, or nothing). Lead with what needs me NOW. '
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.')

# A stock prompt already stored in an existing install must be recognisable below so store.py
# can advance it without touching an owner-edited report. The digest used to receive only the
# verdicts CREATED in this window; those are news about what the owner decided, not the standing
# memory that decides whether today's material deserves their attention at all.
PROMPT = _PROMPT_WITHOUT_STANDING_MEMORY.replace(
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.',
    'WHAT THE OWNER HAS ALREADY DECIDED governs every section: do not surface, summarize, chase, '
    'or suggest action on anything those standing verdicts rule out. They are instructions about '
    'relevance, not events to repeat as news. Never invent facts; no preamble, no sign-off, nothing '
    'outside the sections.')

# every prompt ever SHIPPED, so store.__init__ can tell "still the stock text" (upgrade it)
# from "the owner wrote this" (never touch) - same deal the template docs get
OLD_PROMPTS = (
    _PROMPT_WITHOUT_STANDING_MEMORY,
    (
    'Write what the owner, half awake, should hold in mind TODAY, under 450 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f4c5 Today\'s meetings — one bullet per meeting from MEETINGS TODAY, in time order: the time, '
    'the title, who is in it (first names, never the owner), and what it is about in a few words when the '
    'invite says (the "about:" text) - never guess a purpose from a title alone\n'
    '\U0001f3f7️ By the tags — the window in numbers: one bullet per tag from THE WINDOW BY TAG '
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
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.'),
    (
    'Write what the owner, half awake, should hold in mind TODAY, under 400 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f3f7️ By the tags — the window in numbers: one bullet per tag from THE WINDOW BY TAG '
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
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.'),
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

# what the assistant's voice document does NOT settle for a brief: the shape of the answer
CONTRACT = ('\n\nYOU ARE WRITING THE MORNING BRIEF, not a Timeline post: the instruction in the user message decides the '
            'sections and the length. Plain text with the emoji headers it names - no JSON, no markdown headings, no '
            'tables. Facts only from the data you are given; a TQ-ref keeps the title and the link the data gave it; a '
            'block reading "(none)" has nothing to say. The data may be a CAPPED slice (a block says so when it is cut) - '
            'never describe a cut block as complete, and say plainly when something the instruction asks about is not '
            'in what you got.')


def system(store) -> str:
    """The brief's system prompt: COUNSEL.md - how the assistant speaks to the owner - then the shape of
    a brief, then who the owner is. The same voice as the assistant's Timeline post (assistant.think),
    so the two never sound like different people."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    soul = store.doc('soul') or ''
    return (doc + CONTRACT
            + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else ''))


def _block(out, head, lines):
    """A header with NOTHING under it is an invitation to fill the silence - the model reads
    the next block's lines as if they belonged to this one. Say "(none)" out loud instead."""
    out.append(head)
    body = list(lines) if not isinstance(lines, str) else ([lines] if lines and not lines.startswith('(') else [])
    out += body or ['  (none)']
    out.append('')


def task_link(tid: int) -> str:
    """The URL that opens this task in the app - the digest carries one per task so the brief
    is a set of doors, not a reading. The UI honours #task=<id> on load (TaskHubPage)."""
    from . import config
    try: srv = config.load().get('server') or {}
    except Exception: srv = {}
    host = srv.get('host') or '127.0.0.1'
    if host in ('0.0.0.0', '::', ''): host = '127.0.0.1'
    return f"http://{host}:{srv.get('port') or 7787}/#task={int(tid)}"


_REF = re.compile(r'\bTQ-(\d{4})\b')
def _linked(text: str) -> str:
    """Every line naming a task ends with the door into it (the assistant's blocks carry refs
    without links; the brief promises one after every ref)."""
    def one(line):
        m = _REF.search(line)
        return f"{line} {task_link(int(m.group(1)))}" if m and 'http' not in line else line
    return '\n'.join(one(l) for l in text.split('\n'))


def _midnight_since(days: int) -> datetime:
    """The window starts at MIDNIGHT `days` days back, not `days`*24h ago: a morning digest with
    days=1 is "all of yesterday, plus today so far" - run at 07:26 it used to start at yesterday
    07:26 and lose yesterday's morning."""
    return (datetime.now() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)


def gather(store, days: int = DAYS) -> str:
    """The raw material, compact enough to hand the model whole: what the Timeline assistant reads
    (assistant.py), plus what only a morning brief needs. Block headers are what PROMPT names."""
    from . import assistant as A
    start = _midnight_since(days)
    since = start.isoformat(sep=' ', timespec='seconds')
    span = max(0.5, (datetime.now() - start).total_seconds() / 86400)     # the fractional window the assistant's readers take
    out = [f"NOW: {datetime.now().strftime('%A %d %B %Y %H:%M')} - the window is since {since[:16]}", '']
    # the day's meetings lead: who the owner will sit with and what each is about (calendar.today
    # reads every card that can reach a calendar; an unreadable one says so instead of vanishing)
    try:
        from . import calendar as cal
        t = cal.today(store)
        lines = cal.render_today(t) + [f'  COULD NOT READ: {e}' for e in t.get('errors') or []]
    except Exception as e:
        lines = [f'  COULD NOT READ: {str(e)[:160]}']
    _block(out, "MEETINGS TODAY (in order; 'with' = the other people, 'about' = the invite's own words):", lines)
    # what slipped: their ask, nobody answered - the one block a brief of counts never had
    state = {i['Key']: i for i in store.list_ideas()}
    def said(c):
        i = state.get(c.get('key') or '')
        if not i: return ''
        s = i.get('Status')
        return f" [the assistant raised this {A._when(i.get('LastSaid') or i.get('FirstSeen'))}" + (f"; you marked it {s}" if s in ('dismissed', 'done', 'snoozed') else '') + ']'
    try: asked = A.unanswered(store, span + 1)
    except Exception as e: asked = [{'facts': f'COULD NOT READ: {str(e)[:120]}'}]
    _block(out, 'THEIR ASKS YOU HAVE NOT ANSWERED (their last word wants something from you; what covers it, if anything):',
           (f"  {c['facts']}{said(c)}" for c in asked[:15]))
    # the owner's own open loops: what they asked for and never got, what they promised, what went cold
    c = A.cfg(store)
    try: loops = A.candidates(store, c | {'producers': {'followup', 'promise', 'cold'}})
    except Exception as e: loops = [{'kind': 'followup', 'facts': f'COULD NOT READ: {str(e)[:120]}', 'key': ''}]
    _block(out, 'MY OPEN LOOPS (I asked and nothing came back; I promised; work gone quiet):',
           (f"  [{c_['kind']}] {_linked(c_['facts'].split(chr(10), 1)[0])}{said(c_)}" for c_ in loops[:20]))
    # the ref carries its task's TITLE here too (list_reviews already joins it): a line
    # holding only the attached MAIL SUBJECT let the subject and the ref drift apart, and a
    # brief that renames a task is a lie in the one place the owner trusts by default
    _block(out, 'WAITING ON THE OWNER (pending reviews):',
           (f"  TQ-{r['TaskId']:04d} ({(r.get('Title') or '?')[:60]}) {r.get('Kind')} "
            f"on mail: {(r.get('Subject') or '(no subject)')[:90]} {task_link(r['TaskId'])}" for r in store.list_reviews('pending')[:15]))
    people = A._people(store, span)
    _block(out, 'WHAT PEOPLE SAID (the window, by thread, newest first; the last lines of each, oldest first; "you" = the owner):',
           people)
    away = A.ooo(store)
    _block(out, 'OUT OF OFFICE (from their auto-replies):', (f'  {k}: {v}' for k, v in away.items()))
    recent = A._recent(store, span)
    _block(out, 'WHAT ARRIVED (xN = that many alike; a report carries its schedule, a failure its cause):', recent)
    # The digest reads the same applicable standing verdicts as triage and the Timeline assistant.
    # Match against the source material's real subjects and senders, not a model's paraphrase of
    # them: that is how "Resident Refund Request - Doe" keeps matching the owner's resident-refund
    # ruling even when the summary uses different words. Unrelated scoped memory stays out.
    verdicts = A._verdicts_block(store, [], f'{people}\n{recent}')
    if verdicts:
        out += [verdicts.strip(), '']
    _block(out, 'OPEN WORK (each line ends with the link that opens the task):', _linked(A._open(store)))
    _block(out, 'FINISHED THIS WINDOW (with the agent\'s own summary where there is one):', _linked(A._done(store, span)))
    notes = [m for m in store.list_memories() if str(m.get('CreatedAt') or '') >= since]
    # these quote mail subjects, which is exactly what got recycled into a fake pending
    # review once - the header says plainly that nothing here is live work
    _block(out, 'VERDICTS GIVEN THIS WINDOW (already durable in memory - standing rules, NOT open work,\n'
                'and the mail they quote is already decided):',
           (f"  [{m.get('Scope')}:{m.get('ScopeKey') or '*'}] {(m.get('Note') or '')[:110]}" for m in notes[:12]))
    _block(out, 'WHAT THE ASSISTANT ALREADY RAISED (its Timeline posts in the window, with their state and your replies):',
           A.raised(store, span))
    n, at = A.notes(store)
    _block(out, "THE ASSISTANT'S NOTES TO ITSELF (its facts and timings from its last check" + (f", {A._ts(at)}" if at else '') + '):', n or '(none)')
    # the counts, ONE line: the brief is not a report of numbers, but "43 things arrived, 30 of them
    # machines" is a fact worth a glance
    feed = [m for m in store.feed(limit=500, days=math.ceil(span)) if A._ts(m.get('SentAt')) >= since]
    LABEL = {'coding': 'coding (sent to the agent)', 'todo': 'to do (yours, not code)', 'review': 'review (a reply drafted for you)',
             'info': 'info (a person told you something)', 'automated': 'automated (a system told you something)',
             'promo': 'promo (newsletters, marketing)', 'filed': 'filed', 'ignored': 'ignored', 'report': 'report',
             'feed': 'feed', 'yours': 'your replies', 'triaging': 'still triaging', 'assistant': 'assistant (its own posts)'}
    counts = {}
    for m in feed: counts[m.get('Category') or 'filed'] = counts.get(m.get('Category') or 'filed', 0) + 1
    live = [t for t in store.list_tasks() if t.get('Status') in ('open', 'in_progress', 'waiting')]
    kinds = {}
    for t in live: kinds[t.get('Kind') or 'general'] = kinds.get(t.get('Kind') or 'general', 0) + 1
    _block(out, 'THE WINDOW IN NUMBERS (one line, for a glance):',
           [f"  {len(feed)} inbound items - " + ', '.join(f"{n_} {LABEL.get(k, k)}" for k, n_ in sorted(counts.items(), key=lambda kv: -kv[1]))
            + f"; open tasks: " + (', '.join(f"{n_} {k}" for k, n_ in sorted(kinds.items(), key=lambda kv: -kv[1])) or 'none')] if feed or live else [])
    return '\n'.join(out).rstrip() + '\n'


# build_digest / refresh_if_stale used to live here - their whole job (schedule, AI pass,
# no-AI fallback, filing) is what the reports pipeline already does, so the Morning digest
# report replaced them: reports.run_digest is the executor, run_report_source keeps the doc.
