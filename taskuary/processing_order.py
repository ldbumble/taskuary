"""Shared owner-attention bands; presentation lanes and read state are separate."""

PRIORITY_RANK = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}


def priority_rank(value):
    return PRIORITY_RANK.get(str(value or '').strip().lower(), 99)


def attention_band(*, urgent=False, owner_wait=False, working=False, actionable=False, result=False):
    """The five levels, and they are TRIAGE's verdict rather than a second opinion on top of it
    (the owner, 2026-09-07: "Sort should just take what the triage does instead of adding more").

    1 urgent - a meeting inside fifteen minutes, or a sender on the owner's escalate list.
    2 your task - what triage called work, whoever is waiting: an open task with no agent, a reply
      drafted and waiting for a yes, an agent parked on a question, a hand-off that never started,
      a check that failed. Owner-input and actionable were two levels for a split triage never
      made, and nothing needed the difference: inside a level the oldest comes first.
    3 reports - a report landed, or an agent finished. A result is not work.
    4 fyi - what triage called fyi, and anything it has not judged yet.
    5 agents working - an agent has it; nothing here is for the owner until it stops or asks."""
    if urgent:
        return 1
    if owner_wait:                     # a question or a draft waiting on the owner outranks a session
        return 2
    if working:
        return 5
    if actionable:                     # ...and everything else the owner has to do is the same level
        return 2
    return 3 if result else 4


def feed_band(row):
    """Rank the already evaluated feed fields without changing eligibility."""
    owner_wait = bool(row.get('AgentWaiting') or row.get('ReviewStatus') == 'pending')
    working = bool(row.get('Working')) and not owner_wait
    report = row.get('Channel') == 'report'
    failed = bool(row.get('ReportFailed'))
    # a report the owner made work of - or one that could not run - is work; the rest are results
    report_work = (row.get('TaskId') and not failed
                   and (row.get('NeedsYou') or row.get('Category') in ('coding', 'todo', 'action')))
    work = bool(row.get('NeedsYou')) or failed or (report and bool(report_work))
    # a report row is never an urgent REQUEST unless the owner made work of it: a failed check on an
    # urgent task is a failed check, and feed_band must say what funnel._band says about it
    urgent_request = work and (not report or bool(report_work))
    return attention_band(
        urgent=not owner_wait and not working and urgent_request and priority_rank(row.get('Priority')) == 0,
        owner_wait=owner_wait, working=working, actionable=work, result=report and not work)
