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

...EXCEPT what is still costing the owner something. Two failures are said in the assistant's own voice and
stay up for as long as they are true, whatever the clock says (`live`): Microsoft signing the owner out (no
mail is read, so no answer is watched for) and the triage brain down while mail it could not sort is still
being held. Each one ANNOUNCES ITS OWN END (`news`): "Back on. 14 came in, 2 need you." - a quiet line beside
the bell, never a red one, because the worst part of an outage is not knowing whether it is over.
"""
import hashlib
import json
from datetime import datetime, timedelta

STALE_HOURS = 4
NEWS_HOURS = 6                        # how long "I'm back" stays beside the bell unless it is put down

DISMISSED = 'problems_dismissed'      # {key: signature of the failure the owner read}
NEWS = 'problems:news'                # {key: what ended, and when} - the text is worked out when it is read
THINKING = 'problems:thinking'        # {'at': when the brain went down} for as long as the outage lasts
AWAY = 'problems:mail_away:'          # + connector id: {'at', 'seen'} while Microsoft has the owner signed out


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _load(raw) -> dict:
    try: return json.loads(raw or '{}') or {}
    except (TypeError, ValueError): return {}


def _when(stamp) -> datetime | None:
    try: return datetime.fromisoformat(str(stamp).replace('T', ' ')[:19])
    except ValueError: return None


def clock(stamp) -> str:
    """'2 pm', '2:05 pm', 'Mon 9 am' - the way a person says when, not an ISO stamp."""
    d = _when(stamp)
    if not d: return ''
    t = f"{d.hour % 12 or 12}{f':{d.minute:02d}' if d.minute else ''} {'am' if d.hour < 12 else 'pm'}"
    return t if d.date() == datetime.now().date() else f"{d:%a} {t}"


def _minus(stamp, **kw) -> str:
    d = _when(stamp)
    return (d - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S') if d else ''


def _plural(n, one, many): return one if n == 1 else many


def signature(p: dict) -> str:
    """What makes this failure THIS failure. `since` is in it deliberately: the same connector
    failing the same way an hour later is news again."""
    raw = f"{p.get('key')}|{p.get('detail')}|{p.get('since')}"
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:16]


def _fresh(since, cut) -> bool:
    d = _when(since)
    return bool(d and d >= cut)


def _dismissed(store) -> dict: return _load(store.get_setting(DISMISSED))


# ── news: an outage saying that it is over ───────────────────────────────────────────────────────

def _news_put(store, key, entry):
    got = _load(store.get_setting(NEWS))
    got[key] = {**entry, 'at': _now()}
    store.set_setting(NEWS, json.dumps(got), 'system')


def _needs_you(store, mids) -> tuple:
    """(how many of these need the owner, how many are still being sorted) - the feed's own band, so this
    agrees with the rail about what "needs you" means."""
    if not mids: return 0, 0
    from .processing_order import feed_band
    rows = store.feed(limit=len(mids) + 10, days=3650, ids=list(mids))
    return sum(1 for r in rows if feed_band(r) <= 2), sum(1 for r in rows if r.get('MsgStatus') == 'triaging')


def _who(store, mids) -> list:
    names = []
    for mid in mids:
        m = store.get_message(mid) or {}
        n = str(m.get('FromName') or m.get('FromEmail') or '').strip()
        if n and n not in names: names.append(n)
    return names


def _said(store, key, e) -> dict | None:
    """One news entry in words. Counted now rather than when it ended: mail that came back in is still
    being sorted at that moment, and "2 need you" is only true once it has been."""
    kind = e.get('kind')
    if kind == 'mail':
        seen = [s['Address'] for s in store.list_sources(active_only=False)
                if s.get('Channel') == 'email' and str(s.get('ConnectorId')) == str(e.get('cid'))]
        mids = [r['MessageId'] for r in store._rows(
            f"SELECT MessageId FROM message WHERE Channel='email' AND IFNULL(Direction,'in')<>'out' AND SentAt >= ? AND SentAt <= ? "
            f"AND Status NOT IN ('context','history','skipped') AND SourceName IN ({','.join('?' * len(seen)) or 'NULL'})",
            (e.get('seen') or e.get('out') or '', e.get('at') or '') + tuple(seen))]   # what came in while away - not since
        need, sorting = _needs_you(store, mids)
        n = len(mids)
        text = ("Back on, and your mail is connected again. Nothing new came in while you were signed out." if not n
                else f"Back on. {n} came in while you were signed out - I'm sorting {_plural(n, 'it', 'them')} now." if sorting
                else f"Back on. {n} came in, {need or 'none'} {_plural(need, 'needs', 'need')} you.")
        return {'title': text, 'detail': 'I read everything that arrived while you were signed out.', 'where': 'Timeline', 'fix': 'Show me'}
    if kind == 'thinking':
        mids = [r['MessageId'] for r in store._rows(
            "SELECT DISTINCT MessageId FROM route WHERE ParseError IS NOT NULL AND CreatedAt >= ? AND CreatedAt <= ?",
            (_minus(e.get('out'), minutes=2), e.get('at') or ''))]
        need, _ = _needs_you(store, mids)
        n = len(mids)
        text = ("I'm back. Nothing was waiting on me." if not n
                else f"I'm back. The message I was holding is sorted - {'it needs you' if need else 'nothing for you'}." if n == 1
                else f"I'm back. All {n} sorted, {need or 'none'} {_plural(need, 'needs', 'need')} you.")
        return {'title': text, 'detail': 'Everything that came in while I was stuck has been read.', 'where': 'Timeline', 'fix': 'Show me'}
    if kind == 'held':
        mids = e.get('mids') or []
        n, names = len(mids), _who(store, mids)
        if not n: return None
        who = ', '.join(names[:5]) + (f' and {len(names) - 5} more' if len(names) > 5 else '')
        return {'title': f"I couldn't make sense of {n} {_plural(n, 'message', 'messages')}, so I put {_plural(n, 'it', 'them')} "
                         f"on your list to be safe.",
                'detail': f"Here's who {_plural(n, 'it is', 'they are')} from: {who}." if who else f"{_plural(n, 'It is', 'They are')} on your list now.",
                'where': 'Timeline', 'fix': 'Show me', 'mids': mids}
    return None


def news(store) -> list:
    """What ended on its own, said once and quietly: the bell's calm half. Gone after NEWS_HOURS or a dismiss."""
    got, cut, out = _load(store.get_setting(NEWS)), datetime.now() - timedelta(hours=NEWS_HOURS), []
    keep = {k: e for k, e in got.items() if _fresh(e.get('at'), cut)}
    if keep != got: store.set_setting(NEWS, json.dumps(keep), 'system')
    for k, e in sorted(keep.items(), key=lambda kv: str(kv[1].get('at') or '')):
        said = _said(store, k, e)
        if said: out.append({'key': k, 'kind': 'news', 'since': e.get('at'), 'connector': None, **said})
    return out


# ── 1. signed out of Microsoft ───────────────────────────────────────────────────────────────────

def signed_out(c: dict) -> bool:
    """An Outlook card whose sign-in Microsoft has let lapse: the token is still stored, so "signed in"
    alone said yes while no mail had been read for hours."""
    if (c or {}).get('Type') != 'outlook' or not c.get('Active'): return False
    from .msauth import lapsed
    return lapsed(c.get('LastError'))


def away_since(store, cid):
    return _load(store.get_setting(f'{AWAY}{cid}')).get('at') or ''


def signed_out_line(store, c) -> tuple:
    """(title, detail) - the one thing to say about it, on the bell and on the rail alike."""
    at = clock(away_since(store, c['ConnectorId']) or c.get('LastErrorAt'))
    return (f"Microsoft signed you out{f' at {at}' if at else ''}",
            "I can't see your mail, so I can't watch for answers. Sign in here and I'll catch up.")


def watch_mail(store, c: dict, err=None):
    """After every Outlook poll: remember when the sign-in lapsed, and say so when it is back."""
    if (c or {}).get('Type') != 'outlook': return
    from .msauth import lapsed
    key = f"{AWAY}{c['ConnectorId']}"
    was = _load(store.get_setting(key))
    if err and lapsed(err):
        if not was: store.set_setting(key, json.dumps({'at': _now(), 'seen': c.get('LastSyncAt') or ''}), 'system')
    elif not err and was:
        store.set_setting(key, '', 'system')
        _news_put(store, f"back:mail:{c['ConnectorId']}", {'kind': 'mail', 'cid': c['ConnectorId'], 'out': was.get('at'), 'seen': was.get('seen')})


# ── 4. the brain is down, and nothing waits ──────────────────────────────────────────────────────

def unsorted(store) -> int:
    """Mail triage FAILED on that the sweep will still try - what "I'm holding it" is about. A row it gave up
    on is on the owner's list instead (ingest.give_up), and is not held any more."""
    from . import ingest
    try: after = int(store.get_setting('triage_recovered_route') or 0)
    except (TypeError, ValueError): after = 0
    since = (datetime.now() - timedelta(hours=ingest.RETRY_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    return len(store.stranded_triage_failures(1000, since=since, tries_after=after, tries=ingest.RETRY_TRIES, failed_only=True))


def thinking(store) -> dict | None:
    """The brain's state in one place: None when it is fine, else the line to say. Opening and closing the outage
    happen here too, so the bell, the Timeline caption and the sweep all see one story."""
    s = store.get_settings()
    err, n = str(s.get('triage_last_error') or '').strip(), unsorted(store)
    out = _load(s.get(THINKING))
    if not (err or n):
        if out.get('at'):
            store.set_setting(THINKING, '', 'system')
            _news_put(store, 'back:thinking', {'kind': 'thinking', 'out': out['at']})
        return None
    if not out.get('at'):
        out = {'at': s.get('triage_last_error_at') or _now()}
        store.set_setting(THINKING, json.dumps(out), 'system')
    held = f" {n} {_plural(n, 'is', 'are')} waiting for me so far." if n else ''
    if err: return {'title': "I'm having trouble thinking for a few minutes",
                    'detail': f"Mail is still coming in and I'm holding all of it.{held} Nothing is lost.", 'since': out['at'], 'error': err, 'held': n}
    return {'title': "I'm catching up", 'detail': f"I'm sorting the {n} {_plural(n, 'message', 'messages')} I was holding. Nothing is lost.",
            'since': out['at'], 'error': '', 'held': n}


# ── 5. nothing lost when the retry gives up ──────────────────────────────────────────────────────

def held(store, mids):
    """The sweep handed these to the owner (ingest.give_up). One line for all of them: a second hand-over while the
    first is still on show joins it, so the bell never says "3" and "2" side by side."""
    was = _load(store.get_setting(NEWS)).get('held') or {}
    fresh = _fresh(was.get('at'), datetime.now() - timedelta(hours=NEWS_HOURS))
    _news_put(store, 'held', {'kind': 'held', 'mids': list(dict.fromkeys(((was.get('mids') or []) if fresh else []) + list(mids)))})


# ── the bell ─────────────────────────────────────────────────────────────────────────────────────

def dismiss(store, key: str, actor: str = 'owner') -> dict:
    """Put this one down. Unknown key = nothing to dismiss, said plainly rather than silently."""
    got = _load(store.get_setting(NEWS))
    if key in got:                                                           # news is read once and gone
        got.pop(key); store.set_setting(NEWS, json.dumps(got), actor)
        return {'ok': True, 'key': key, 'remaining': len(collect(store))}
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
        if not (c.get('Active') and err): continue
        if signed_out(c):
            title, detail = signed_out_line(store, c)
            out.append({'key': f"connector:{c['ConnectorId']}", 'title': title, 'detail': detail, 'live': True,
                        'since': away_since(store, c['ConnectorId']) or c.get('LastErrorAt') or '', 'where': 'Connections',
                        'connector': str(c['ConnectorId']), 'fix': 'Sign in', 'kind': 'signed_out'})
            continue
        out.append({'key': f"connector:{c['ConnectorId']}", 'title': f"{c.get('Name') or c['Type']}: the last poll failed",
                    'detail': err[:400], 'since': c.get('LastErrorAt') or '', 'where': 'Connections', 'connector': str(c['ConnectorId']),
                    'fix': 'Open the card'})
    s = store.get_settings()
    brain = thinking(store)
    if brain:
        pick = str(s.get('triage_ai') or '')
        out.append({'key': 'triage', 'title': brain['title'], 'detail': brain['detail'], 'since': brain['since'], 'error': brain['error'][:400],
                    # held mail keeps it up whatever its age; a bare error with nothing held ages out like any other
                    'live': brain['held'] > 0, 'where': 'Connections', 'connector': pick[10:] if pick.startswith('connector:') else None,
                    'fix': 'Check my setup', 'kind': 'thinking'})
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
        if p['key'] in seen or not (p.pop('live', False) or _fresh(p['since'], cut)): continue
        seen.add(p['key']); uniq.append(p)
    if all_of_them: return uniq
    # ...minus the ones the owner has read, and only while they are the SAME failure
    put_down = _dismissed(store)
    return [p for p in uniq if put_down.get(p['key']) != signature(p)]
