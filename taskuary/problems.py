"""What is FAILING right now - the bell in the top bar. Each item says what broke, the error in its
own words, and where it is fixed. The setup chip covers what is not yet set up; this covers what was
working and is not: a connector whose poll errors (the WhatsApp bridge down, a token expired), the
triage brain not answering, a report run that failed today. Quiet when nothing is - the bell is grey."""


def collect(store) -> list:
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
    return uniq
