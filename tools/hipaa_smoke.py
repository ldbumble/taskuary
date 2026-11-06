"""Does the HIPAA AI card answer, model by model? `python tools/hipaa_smoke.py [--db PATH] [--card ID] [--models a,b]`.

Two calls per model, each the shape the app really sends: a TRIAGE call (triage.classify_intent on an invented email, the verdict
schema on the wire, at the low effort Auto gives quick jobs) and an AGENT call (the general agent's turn: its summary-block contract
in the system prompt, room for a long answer). One line each: model, ok/FAIL, tokens in/out, seconds, and what the wire settled on -
the response format the gateway took and whether it kept the effort.

The gateway address and the access code are read from the card at run time, from a COPY of the database (`--db`, default the
Taskuary home's taskuary.db) opened under a throwaway TASKUARY_HOME, so the live home is never touched. Neither is ever printed: an
error is shown with the address and the code taken out. The email is invented; nothing of the owner's is sent."""
import argparse, os, shutil, sys, tempfile, time
from pathlib import Path

AGENT_ASK = 'Compare two invented payroll vendors, Payworth and Trainly, for a 40-person company in three short bullets.'


def _hide(s, *secrets) -> str:
    s = str(s or '')
    for x in secrets:
        if x: s = s.replace(x, '<hidden>')
    return ' '.join(s.split())[:240]


def _metered(fn):
    """(result or the exception, {model,in,cached,out}, seconds, [status of each POST]) - the provider's own count, read the way
    aiusage reads it, and the walk the call took: a 400 before the 200 is something the gateway refused and was asked without."""
    from taskuary import aiusage, llm
    m, seen, t0, post = {}, [], time.monotonic(), llm.post_retrying
    def watched(*a, **kw):
        r = post(*a, **kw); seen.append(r.status_code); return r
    tok, llm.post_retrying = aiusage._METER.set(m), watched
    try: out = fn()
    except Exception as e: out = e
    finally: aiusage._METER.reset(tok); llm.post_retrying = post
    return out, m, time.monotonic() - t0, seen


def card_of(store, cid=None) -> dict:
    "The HIPAA AI card with its secret: the one named, else the active one, else the first."
    import json
    c = store.get_connector(int(cid), with_secret=True) if cid else store.get_connector_by_type('hipaa_ai', with_secret=True)
    if not c or c.get('Type') != 'hipaa_ai': raise SystemExit('no HIPAA AI card in this database')
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return {'id': c['ConnectorId'], 'cfg': cfg, 'key': c.get('Secret') or ''}


def run(store, cid=None, models=None, say=print) -> list:
    "Every call's row, said as it lands. `models` defaults to what the gateway lists for this code."
    from taskuary import firstrun, llm, selfclose, triage
    c = card_of(store, cid); cfg, key = c['cfg'], c['key']
    try: base = llm.gateway_base(cfg)
    except ValueError as e: base = ''; say(f'card {c["id"]}: {e}'); return []
    if not key: say(f'card {c["id"]}: no access code saved on the card yet - paste it on the HIPAA AI card first'); return []
    hide = lambda s: _hide(s, base, key)
    t0 = time.monotonic(); why = llm.gateway_problem(cfg, key)
    say(f'card {c["id"]}: gateway {"answers" if not why else "- " + why} ({time.monotonic() - t0:.1f}s, the first call wakes a cold gateway)')
    if why: return []
    listed = llm.list_models('hipaa_ai', cfg, key)
    say(f'models listed: {", ".join(listed) or "(none)"}')
    rows = []
    for m in models or listed:
        def triage_call(m=m):
            brain = llm.make_llm('hipaa_ai', {**cfg, 'model': f'{m}@low'}, key)
            v = triage.classify_intent(dict(firstrun.PROOF), llm=brain)
            if v.get('degraded') or v.get('intent') not in triage.INTENTS:
                raise RuntimeError(v.get('parse_error') or v.get('error') or 'its answer was not a verdict')
            return f"intent={v['intent']}"
        def agent_call(m=m):
            brain = llm.make_llm('hipaa_ai', {**cfg, 'model': m}, key)
            said = str(brain(f'You are a general agent working for Alex at Northwind.\n\n{selfclose.SUMMARY_LINE}', AGENT_ASK, max_tokens=8000) or '')
            text, summ = selfclose.summary_marker(said, [])
            if not (text or summ): raise RuntimeError('an empty answer')
            return 'summary block read' if summ else 'answered, but wrote no summary block'
        for kind, call in (('triage', triage_call), ('agent', agent_call)):
            llm._NO_EFFORT.clear(); llm._FORMAT_FROM.clear()
            out, use, secs, walk = _metered(call)
            ok = not isinstance(out, Exception)
            fmt = next((('json_schema', 'json_object', 'prompt only')[i] for (_u, mm), i in llm._FORMAT_FROM.items() if mm == m), '')
            ran = use.get('model') or ''         # the gateway's fallback answers on another model than the one asked: say which
            wire = ', '.join(x for x in (f'ANSWERED BY {ran}' if ran and ran != m else '', f'format {fmt}' if fmt else '',
                                         'effort refused' if any(k[2] == m for k in llm._NO_EFFORT) else '',
                                         f"took {' -> '.join(map(str, walk))}" if walk[:1] != [200] else '') if x)
            row = {'model': m, 'kind': kind, 'ok': ok, 'in': use.get('in'), 'out': use.get('out'), 'secs': round(secs, 1),
                   'ran': use.get('model') or '', 'note': hide(out if not ok else f'{out}{"; " + wire if wire else ""}')}
            rows.append(row)
            say(f"{m:24} {kind:6} {'ok  ' if ok else 'FAIL'} in={row['in'] if row['in'] is not None else '-':>6} "
                f"out={row['out'] if row['out'] is not None else '-':>6} {row['secs']:6.1f}s  {row['note']}")
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    home = Path(os.getenv('TASKUARY_HOME') or Path.home() / '.taskuary')
    p.add_argument('--db', default=str(home / 'taskuary.db')); p.add_argument('--card', type=int); p.add_argument('--models', default='')
    a = p.parse_args(argv)
    if not Path(a.db).is_file(): raise SystemExit(f'no database at {a.db} - pass --db')
    tmp = Path(tempfile.mkdtemp(prefix='hipaa-smoke-')); db = tmp / 'taskuary.db'
    for suffix in ('', '-wal', '-shm'):
        if Path(a.db + suffix).is_file(): shutil.copy(a.db + suffix, str(db) + suffix)
    os.environ['TASKUARY_HOME'] = str(tmp / 'home')          # before any taskuary import: nothing may open the real home
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from loguru import logger
    logger.remove(); logger.add(sys.stderr, level='WARNING')
    from taskuary.store import SQLiteStore
    try:
        rows = run(SQLiteStore(str(db)), a.card, [m.strip() for m in a.models.split(',') if m.strip()] or None)
        bad = [r for r in rows if not r['ok']]
        print(f"\n{len(rows) - len(bad)} of {len(rows)} calls ok" if rows else '\nno calls made')
        return 1 if bad or not rows else 0
    finally: shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__': sys.exit(main())
