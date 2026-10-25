"""Shared owner-attention bands; presentation lanes and read state are separate."""

# THREE PRIORITIES (the owner, 2026-10-25: "be careful when updating triage to have 3 categories, important/urgent/regular and make
# sure it makes sense"). Urgent is time-critical and on the owner now - today's meaning, and the only one that shades a row or bands
# it. Important matters because of WHO or WHAT (people and topics the owner cares about) but can wait: a mark in the row's own place,
# never a move. Regular is everything else. The old four read in them: low and normal are regular, high is important.
LEVELS = ('regular', 'important', 'urgent')
LEGACY = {'low': 'regular', 'normal': 'regular', 'medium': 'regular', 'high': 'important'}
PRIORITY_RANK = {'urgent': 0, 'important': 1, 'regular': 2}


def level(value) -> str:
    """Any priority word, old or new, as one of the three - 'regular' for none or one nobody knows."""
    v = str(value or '').strip().lower()
    return v if v in PRIORITY_RANK else LEGACY.get(v, 'regular')


def known(value) -> bool: return str(value or '').strip().lower() in PRIORITY_RANK or str(value or '').strip().lower() in LEGACY


def priority_rank(value):
    return PRIORITY_RANK[level(value)] if known(value) else 99


def attention_band(*, urgent=False, owner_wait=False, working=False, actionable=False, result=False):
    """The four levels, and they are TRIAGE's verdict rather than a second opinion on top of it
    (the owner, 2026-09-07: "Sort should just take what the triage does instead of adding more").

    1 urgent - a meeting inside fifteen minutes, or a sender on the owner's escalate list.
    2 tasks - what triage called work, whoever is on it: an open task with no agent, one an agent is WORKING, a reply
      drafted and waiting for a yes, an agent parked on a question, a hand-off that never started,
      a check that failed, a task an agent finished and closed (until it is read). Owner-input and actionable were two levels for a split triage never
      made, and nothing needed the difference: inside a level the oldest comes first.
    3 reports - a report you set up landed. Information, never a task.
    4 fyi - what triage called fyi, and anything it has not judged yet - while it is still being retried. A row
      the retry GAVE UP on is level 2 (gave_up): nobody will judge it now, so it is the owner's.
    A working agent's task was a fifth level below fyi, and the row jumped between sections each time its agent started,
    asked or stopped (the owner, 2026-10-21): it is a task like the rest now, in the same place whatever its agent does."""
    if urgent:
        return 1
    if owner_wait or working or actionable:
        return 2
    return 3 if result else 4


def gave_up(row) -> bool:
    """Unjudged, and the automatic retry has stopped on it (store.HELD, written by ingest.give_up)."""
    return row.get('MsgStatus') == 'error' and row.get('Decision') == 'held'


def feed_band(row):
    """Rank the already evaluated feed fields without changing eligibility."""
    owner_wait = bool(row.get('AgentWaiting') or row.get('ReviewStatus') == 'pending')
    working = bool(row.get('Working')) and not owner_wait
    report = row.get('Channel') == 'report'
    failed = bool(row.get('ReportFailed'))
    # a report the owner made work of - or one that could not run - is work; the rest are results
    report_work = (row.get('TaskId') and not failed
                   and (row.get('NeedsYou') or row.get('Category') in ('coding', 'todo', 'action')))
    work = bool(row.get('NeedsYou')) or failed or (report and bool(report_work)) or gave_up(row)
    # a report row is never an urgent REQUEST unless the owner made work of it: a failed check on an
    # urgent task is a failed check, and feed_band must say what funnel._band says about it
    urgent_request = work and (not report or bool(report_work))
    return attention_band(
        urgent=not owner_wait and not working and urgent_request and priority_rank(row.get('Priority')) == 0,
        owner_wait=owner_wait, working=working, actionable=work, result=report and not work)
