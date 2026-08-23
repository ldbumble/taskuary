"""What should you automate next? A weekly report that mines the funnel's OWN history for
repeated toil - the same sender asking the same shape of thing, drafts you always approve
untouched, noise you keep ignoring by hand - and proposes the concrete Taskuary object
that kills each one: a skip policy, an auto-answer rule, a standing prompt, a scheduled
report. Ships seeded like the Morning digest: lands on the Timeline, prompt editable on
the Reports tab, delete the source to turn it off.
"""
from datetime import datetime, timedelta

PROMPT = (
    'You are looking at one operator\'s inbound-work statistics. Propose AT MOST five '
    'automations, ranked by minutes saved per week. Each proposal is 2-3 lines: the pattern '
    '(with its numbers), the concrete fix IN THIS APP (a skip policy on a sender/domain, an '
    'auto_answer policy, a standing prompt on a connector, a scheduled report, flipping '
    'auto-dispatch or auto-draft on), and what to watch out for. Only propose what the '
    'numbers actually support - several episodes, more than one week. If nothing repeats '
    'enough to automate, say so in one line instead of inventing work. Skip anything the '
    'EXISTING POLICIES section already covers.')


def gather(store, days: int = 30) -> str:
    """The evidence, compact: per-sender traffic with outcome mix, drafts approved
    untouched, and the policies that already exist (never propose those again)."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    by = {}
    for m in store.scan_messages():
        if str(m.get('SentAt') or '') < since or m.get('Status') == 'context': continue
        who = (m.get('FromEmail') or '?').lower()
        d = by.setdefault(who, {'n': 0, 'ignored': 0, 'filed': 0, 'tasks': 0, 'subjects': []})
        d['n'] += 1
        if m['Status'] in ('ignored', 'skipped'): d['ignored'] += 1
        elif m['Status'] == 'filed': d['filed'] += 1
        elif m.get('TaskId'): d['tasks'] += 1
        if len(d['subjects']) < 3 and (m.get('Subject') or '').strip(): d['subjects'].append(m['Subject'][:60])
    # drafts sent unchanged = the reply the machine already writes right - per sender
    approved = {}
    for r in store.list_reviews('approved'):
        if str(r.get('DecidedAt') or '') < since: continue
        who = (r.get('FromEmail') or '?').lower()
        approved[who] = approved.get(who, 0) + 1
    out = [f'INBOUND BY SENDER (last {days} days; senders with 3+ messages):']
    for who, d in sorted(by.items(), key=lambda x: -x[1]['n']):
        if d['n'] < 3: continue
        out.append(f"  {who}: {d['n']} msgs - {d['tasks']} became tasks, {d['ignored']} ignored, "
                   f"{d['filed']} filed" + (f", {approved[who]} drafts approved UNTOUCHED" if approved.get(who) else '')
                   + (f" · e.g. {' | '.join(d['subjects'])}" if d['subjects'] else ''))
    if len(out) == 1: out.append('  (nothing repeated 3+ times)')
    hot = [f'  {who}: {n} drafts sent unchanged' for who, n in sorted(approved.items(), key=lambda x: -x[1]) if n >= 3]
    if hot: out += ['DRAFTS YOU ALWAYS APPROVE UNTOUCHED (auto_answer candidates):'] + hot
    pols = store.list_policies(active_only=True)
    out.append('EXISTING POLICIES (already automated - never propose these again):')
    out += [f"  [{p['Action']}] {p['Kind']}: {str(p.get('Pattern') or '')[:60]}" for p in pols[:25]] or ['  (none)']
    settings = store.get_settings()
    out.append(f"CURRENT SWITCHES: auto-dispatch={'on' if settings.get('coder_auto_enabled') == '1' else 'off'}, "
               f"auto-draft={'on' if settings.get('auto_draft_enabled') == '1' else 'off'}, "
               f"phone approvals={'on' if settings.get('phone_approvals') == '1' else 'off'}")
    return '\n'.join(out)
