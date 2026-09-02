"""What is FAILING right now - the bell in the top bar. Each item says what broke, the error in its
own words, and where it is fixed. The setup chip covers what is not yet set up; this covers what was
working and is not: a connector whose poll errors (the WhatsApp bridge down, a token expired), the
triage brain not answering, a report run that failed today. Quiet when nothing is - the bell is grey.

DISMISSING one is reading it, not fixing it, and the difference matters: a bell that can be emptied
by clicking is a bell nobody believes. So a dismissal is against the exact failure you read - its
text and its timestamp, as a signature - and the moment the same thing fails AGAIN it is a new
signature and the item is back. You can silence what you have decided to live with; you cannot
silence a system that keeps breaking.
"""
import hashlib
import json

DISMISSED = 'problems_dismissed'      # {key: signature of the failure the owner read}


def signature(p: dict) -> str:
    """What makes this failure THIS failure. `since` is in it deliberately: the same connector
    failing the same way an hour later is news again."""
    raw = f"{p.get('key')}|{p.get('detail')}|{p.get('since')}"
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:16]


def _dismissed(store) -> dict:
    try: return json.loads(store.get_settings().get(DISMISSED) or '{}') or {}
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
                        'detail': err[:400], 'since': c.get('LastSyncAt') or '', 'where': 'Connections', 'connector': str(c['ConnectorId']),
                        'fix': 'Open the card'})
    s = store.get_settings()
    if str(s.get('triage_last_error') or '').strip():
        pick = str(s.get('triage_ai') or '')
        out.append({'key': 'triage', 'title': 'The triage brain is not answering', 'detail': s['triage_last_error'][:400], 'since': '',
                    'where': 'Connections', 'connector': pick[10:] if pick.startswith('connector:') else None, 'fix': 'Check the AI card'})
    for r in store.feed(limit=60, days=1, channel='report'):
        if str(r.get('Subject') or '').endswith('FAILED'):
            out.append({'key': f"report:{r.get('SourceName') or r.get('Subject')}", 'title': f"Report failed: {r.get('SourceName') or r.get('Subject')}",
                        'detail': str(r.get('Preview') or '')[:400], 'since': r.get('SentAt') or '', 'where': 'Reports', 'connector': None,
                        'fix': 'Open Reports'})
    seen, uniq = set(), []
    for p in out:
        if p['key'] in seen: continue
        seen.add(p['key']); uniq.append(p)
    if all_of_them: return uniq
    # ...minus the ones the owner has read, and only while they are the SAME failure
    put_down = _dismissed(store)
    return [p for p in uniq if put_down.get(p['key']) != signature(p)]
