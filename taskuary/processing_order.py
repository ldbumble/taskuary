"""Shared owner-attention bands; presentation lanes and read state are separate."""

PRIORITY_RANK = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}


def priority_rank(value):
    return PRIORITY_RANK.get(str(value or '').strip().lower(), 99)


def attention_band(*, urgent=False, owner_wait=False, working=False, actionable=False):
    if urgent:
        return 1
    if owner_wait:
        return 2
    if working:
        return 5
    return 3 if actionable else 4


def feed_band(row):
    """Rank the already evaluated feed fields without changing eligibility."""
    owner_wait = bool(row.get('AgentWaiting') or row.get('ReviewStatus') == 'pending')
    working = bool(row.get('Working')) and not owner_wait
    actionable = bool(row.get('NeedsYou') or row.get('Channel') == 'report')
    report_work = (row.get('TaskId') and not row.get('ReportFailed')
                   and (row.get('NeedsYou') or row.get('Category') in ('coding', 'todo', 'action')))
    urgent_request = actionable and (row.get('Channel') != 'report' or report_work)
    return attention_band(
        urgent=not owner_wait and not working and urgent_request and priority_rank(row.get('Priority')) == 0,
        owner_wait=owner_wait, working=working, actionable=actionable)
