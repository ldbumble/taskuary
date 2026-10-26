"""What is FAILING right now - the bell in the top bar. Each item says what broke, the error in its
own words, and where it is fixed. The setup chip covers what is not yet set up; this covers what was
working and is not: a connector whose poll errors (the WhatsApp bridge down, a token expired), the
triage brain not answering, a report whose latest run failed. Quiet when nothing is - the bell is grey.

DISMISSING one is reading it, not fixing it, and the difference matters: a bell that can be emptied
by clicking is a bell nobody believes. So a dismissal is against the exact failure you read - its
text and its timestamp, as a signature - and the moment the same thing fails AGAIN it is a new
signature and the item is back. You can silence what you have decided to live with; you cannot
silence a system that keeps breaking.

A FAILURE IS ONE PER CONNECTION, NOT ONE PER POLL (the owner, 2026-10-26: "errors should be per connection not per
refresh"). A connector re-stamps LastErrorAt on every failing poll, and the dismissal was signed with that stamp,
so a broken chat bridge put down came back thirty seconds later. Now each key's failure is an EPISODE (OPEN): it
opens the first time it is seen and closes when it works again, and a dismissal holds for the whole episode.

ONLY A REAL ONE RINGS (the owner, same day: "the classic whatsapp timeout should not show up. it should just restart
it if it crashes by itself"). A dropped bridge is started again by the poll (wabridge.supervise) and a mailbox that
timed out once reads fine ten minutes later, so a connector's failure shows only once it has lasted GRACE_MINUTES -
and one that healed inside that never rang, so it says no "working again" either. What no retry heals shows at
once: Microsoft signing the owner out, the bridge given up on, a report run that failed or did not go out.

It then stays up for as long as it is true - no clock takes it down. A four-hour cut (2026-10-01) let a report that
failed at 6 am say nothing by 10, and a connector whose poller stopped go quiet while still broken. A failure with
no time at all is from before the stamp existed: old by definition, never shown.

AND IT ANNOUNCES ITS OWN END (`news`), until the owner says Got it (2026-10-26: "once it recovers it still shows
issue and recovery until dismissed"): what failed, from when to when - a quiet line beside the bell, never a red
one, because the worst part of an outage is not knowing whether it is over. Microsoft signing the owner out and
the triage brain going down say theirs in the assistant's own voice: "Back on. 14 came in, 2 need you."
"""
import hashlib
import json
from datetime import datetime, timedelta

GRACE_MINUTES = 10                    # a connector failing for less than this is a retry still at work, not news
NEWS_HOURS = 6                        # a second hand-over of held mail inside this joins the first (held)
NEWS_KEEP = 20                        # news stays until Got it; past this many, the oldest goes

DISMISSED = 'problems_dismissed'      # {key: signature of the failure the owner read}
NEWS = 'problems:news'                # {key: what ended, and when} - the text is worked out when it is read
THINKING = 'problems:thinking'        # {'at': when the brain went down} for as long as the outage lasts
AWAY = 'problems:mail_away:'          # + connector id: {'at', 'seen'} while Microsoft has the owner signed out
OPEN = 'problems:open'                # {key: the failure as last seen, 'from' its start, 'shown' once it rang} while it lasts
OWN_NEWS = ('signed_out', 'thinking')  # these two say their own end (watch_mail, thinking) - no second line for them


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
    """What makes this failure THIS failure: the key and when its episode began. Each failing poll re-stamps `since`
    and may word the error differently; neither is a new failure. Working again, then failing, is."""
    raw = f"{p.get('key')}|{p.get('from') or p.get('since')}"
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:16]


def _fresh(since, cut) -> bool:
    d = _when(since)
    return bool(d and d >= cut)


def _dismissed(store) -> dict: return _load(store.get_setting(DISMISSED))


# ── news: an outage saying that it is over ───────────────────────────────────────────────────────

def _news_put(store, key, entry):
    got = _load(store.get_setting(NEWS))
    got.pop(key, None); got[key] = {**entry, 'at': _now()}
    got = dict(sorted(got.items(), key=lambda kv: str(kv[1].get('at') or ''))[-NEWS_KEEP:])
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
    if kind == 'recovered':
        span = f"Failed {clock(e.get('from'))} to {clock(e.get('to'))}" if e.get('from') else f"Working again since {clock(e.get('to'))}"
        return {'title': e.get('back') or f"{e.get('title')} - working again", 'detail': f"{span}: {e.get('detail')}"[:400] if e.get('detail') else span,
                'where': e.get('where'), 'connector': e.get('connector'), 'report': e.get('report'), 'fix': 'Show me'}
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
    """What ended on its own, said quietly: the bell's calm half. It stays until Got it."""
    out = []
    for k, e in sorted(_load(store.get_setting(NEWS)).items(), key=lambda kv: str(kv[1].get('at') or '')):
        said = _said(store, k, e)
        if said: out.append({'key': k, 'kind': 'news', 'since': e.get('at'), 'connector': None, **said})
    return out


def _episodes(store, failing: list) -> tuple:
    """Open an episode for what is failing and not yet open, close the ones that are not failing any more, and return
    (what rings now, everything failing). Read when the bell is (collect): the failures' own stamps say when, so a bell read an hour later
    still dates them right. Each item leaves with `from`, its episode's start; a closed episode that rang says so in
    `news`, and one that healed inside its grace says nothing at all."""
    was, now, cut = _load(store.get_setting(OPEN)), _now(), datetime.now() - timedelta(minutes=GRACE_MINUTES)
    got, ring = {}, []
    for p in failing:
        e = was.get(p['key']) or {'from': p.get('since') or now}
        p['from'] = e['from']
        shown = bool(p.pop('now', False) or e.get('shown') or not _fresh(e['from'], cut))
        got[p['key']] = {**{k: p.get(k) for k in ('title', 'back', 'detail', 'where', 'connector', 'report', 'kind')}, 'from': e['from'], 'shown': shown}
        if shown: ring.append(p)
    for k, e in was.items():
        if k in got or not e.get('shown') or e.get('kind') in OWN_NEWS: continue
        _news_put(store, f'back:{k}', {**e, 'kind': 'recovered', 'to': now})
    if got != was: store.set_setting(OPEN, json.dumps(got), 'system')
    return ring, failing


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
            out.append({'key': f"connector:{c['ConnectorId']}", 'title': title, 'detail': detail,
                        'since': away_since(store, c['ConnectorId']) or c.get('LastErrorAt') or '', 'where': 'Connections',
                        'connector': str(c['ConnectorId']), 'fix': 'Sign in', 'kind': 'signed_out', 'now': True})
            continue
        # a bridge this machine runs is started again from the bell itself - its error says "Restart bridge starts it"
        from . import wabridge
        restart = c.get('Type') == 'whatsapp' and wabridge.managed(c)
        # ...and the bridge it stopped starting again is past any retry (wabridge.supervise's give-up line)
        gave_up = restart and bool(wabridge._SUP.get('gave_up'))
        out.append({'key': f"connector:{c['ConnectorId']}", 'title': f"{c.get('Name') or c['Type']}: the last poll failed",
                    'back': f"{c.get('Name') or c['Type']} is working again",
                    'detail': err[:400], 'since': c.get('LastErrorAt') or '', 'where': 'Connections', 'connector': str(c['ConnectorId']),
                    'fix': 'Open the card', **({'restart': True} if restart else {}), **({'now': True} if gave_up else {})})
    s = store.get_settings()
    brain = thinking(store)
    if brain:
        pick = str(s.get('triage_ai') or '')
        out.append({'key': 'triage', 'title': brain['title'], 'detail': brain['detail'], 'since': brain['since'], 'error': brain['error'][:400],
                    'now': True, 'where': 'Connections', 'connector': pick[10:] if pick.startswith('connector:') else None,
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
                    'back': f"{name} ran cleanly again",
                    'connector': None, 'report': src['SourceId'], 'fix': 'Open the report', 'now': True})
    # ...and a report that ran but whose send or alert did not go (reports.send_failed)
    from .reports import SEND_FAILED
    for src in store.list_sources():
        if src.get('Channel') != 'report' or not src.get('Active'): continue
        for kind, says in (('send', 'was not sent out'), ('alert', 'alert did not reach you')):
            try: f = json.loads(store.get_setting(f"{SEND_FAILED}{kind}:{src['SourceId']}") or '{}')
            except ValueError: continue
            if not f: continue
            out.append({'key': f"report_{kind}:{src['SourceId']}", 'title': f"{src.get('Address')}: {says}",
                        'back': f"{src.get('Address')}: {'sent out' if kind == 'send' else 'its alert reached you'} again",
                        'detail': f"{f.get('what')}. {f.get('error')}"[:400], 'since': f.get('at') or '', 'where': 'Reports',
                        'connector': None, 'report': src['SourceId'], 'fix': 'Open the report', 'now': True})
    seen, uniq = set(), []
    for p in out:
        if p['key'] in seen or not _when(p['since']): continue
        seen.add(p['key']); uniq.append(p)
    ring, uniq = _episodes(store, uniq)
    if all_of_them: return uniq          # the troubleshooter and the facts see a retry still at work too
    uniq = ring
    # ...minus the ones the owner has read, and only while they are the SAME failure
    put_down = _dismissed(store)
    return [p for p in uniq if put_down.get(p['key']) != signature(p)]
