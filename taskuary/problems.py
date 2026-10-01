"""What is FAILING right now - the bell in the top bar. Each item says what broke, the error in its
own words, and where it is fixed. The setup chip covers what is not yet set up; this covers what was
working and is not: a connector whose poll errors (the WhatsApp bridge down, a token expired), the
triage brain not answering, a report whose latest run failed. Quiet when nothing is - the bell is grey.

DISMISSING one is reading it, not fixing it, and the difference matters: a bell that can be emptied
by clicking is a bell nobody believes. So a dismissal is against the exact failure you read - its
text and its timestamp, as a signature - and the moment the same thing fails AGAIN it is a new
signature and the item is back. You can silence what you have decided to live with; you cannot
silence a system that keeps breaking.

A failure ALSO puts itself down with time: one that has not happened again for STALE_HOURS is
yesterday's news (the owner, 2026-10-01: an error from the day before, already fixed, still rang
the bell). Something that keeps failing re-stamps `since` on every try, so it stays. A failure
with no time at all is one from before the stamp existed - old by definition.
"""
import hashlib
import json
from datetime import datetime, timedelta

STALE_HOURS = 4

DISMISSED = 'problems_dismissed'      # {key: signature of the failure the owner read}


def signature(p: dict) -> str:
    """What makes this failure THIS failure. `since` is in it deliberately: the same connector
    failing the same way an hour later is news again."""
    raw = f"{p.get('key')}|{p.get('detail')}|{p.get('since')}"
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:16]


def _fresh(since, cut) -> bool:
    try: return datetime.fromisoformat(str(since).replace('T', ' ')[:19]) >= cut
    except ValueError: return False


def _dismissed(store) -> dict:
    try: return json.loads(store.get_setting(DISMISSED) or '{}') or {}
    except (TypeError, ValueError): return {}


def dismiss(store, key: str, actor: str = 'owner') -> dict:
    """Put this one down. Unknown key = nothing to dismiss, said plainly rather than silently."""
    live = {p['key']: p for p in collect(store, all_of_them=True)}
    p = live.get(key)
    if not p: raise ValueError(f'nothing failing under {key!r} - it may have already cleared')
    keep = {k: v for k, v in _dismissed(store).items() if k in live}      # forget what has gone away
    keep[key] = signature(p)
    store.set_setting(DISMISSED, json.dumps(keep), actor)
    store.audit('problem', 0, 'dismissed', actor, detail={'key': key, 'title': p.get('title')})
    return {'ok': True, 'key': key, 'remaining': len(collect(store))}


def collect(store, all_of_them: bool = False) -> list:
    out = []
    for c in store.list_connectors():
        err = str(c.get('LastError') or '').strip()
        if c.get('Active') and err:
            out.append({'key': f"connector:{c['ConnectorId']}", 'title': f"{c.get('Name') or c['Type']}: the last poll failed",
                        'detail': err[:400], 'since': c.get('LastErrorAt') or '', 'where': 'Connections', 'connector': str(c['ConnectorId']),
                        'fix': 'Open the card'})
    s = store.get_settings()
    if str(s.get('triage_last_error') or '').strip():
        pick = str(s.get('triage_ai') or '')
        out.append({'key': 'triage', 'title': 'The triage brain is not answering', 'detail': s['triage_last_error'][:400], 'since': s.get('triage_last_error_at') or '',
                    'where': 'Connections', 'connector': pick[10:] if pick.startswith('connector:') else None, 'fix': 'Check the AI card'})
    # A REPORT'S FAILURE LIVES HERE AND NOWHERE ELSE (the owner, 2026-09-28): a failed run files no row, so
    # this reads each report's latest run - failed, or run without one of its sources - and clears itself
    # the moment a run works again
    from .reports import failed_sources
    for src in store.list_sources():
        if src.get('Channel') != 'report' or not src.get('Active'): continue
        last = (store.report_runs(src['SourceId'], 1) or [None])[0]
        if not last: continue
        name, gone = last.get('title') or src.get('Address'), [] if last.get('failed') else failed_sources(last.get('subject'))
        if not (last.get('failed') or gone): continue
        out.append({'key': f"report:{src['SourceId']}", 'title': f"Report failed: {name}" if last.get('failed') else f"{name} ran without {', '.join(gone)}",
                    'detail': str(last.get('error') or last.get('subject') or '')[:400], 'since': last.get('at') or '', 'where': 'Reports',
                    'connector': None, 'report': src['SourceId'], 'fix': 'Open the report'})
    # ...and a report that ran but whose send or alert did not go (reports.send_failed)
    from .reports import SEND_FAILED
    for src in store.list_sources():
        if src.get('Channel') != 'report' or not src.get('Active'): continue
        for kind, says in (('send', 'was not sent out'), ('alert', 'alert did not reach you')):
            try: f = json.loads(store.get_setting(f"{SEND_FAILED}{kind}:{src['SourceId']}") or '{}')
            except ValueError: continue
            if not f: continue
            out.append({'key': f"report_{kind}:{src['SourceId']}", 'title': f"{src.get('Address')}: {says}",
                        'detail': f"{f.get('what')}. {f.get('error')}"[:400], 'since': f.get('at') or '', 'where': 'Reports',
                        'connector': None, 'report': src['SourceId'], 'fix': 'Open the report'})
    cut, seen, uniq = datetime.now() - timedelta(hours=STALE_HOURS), set(), []
    for p in out:
        if p['key'] in seen or not _fresh(p['since'], cut): continue
        seen.add(p['key']); uniq.append(p)
    if all_of_them: return uniq
    # ...minus the ones the owner has read, and only while they are the SAME failure
    put_down = _dismissed(store)
    return [p for p in uniq if put_down.get(p['key']) != signature(p)]
