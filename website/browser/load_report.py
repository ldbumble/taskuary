"""The tables of a load run (load-burst.mjs): `python load_report.py <run.json> [...]` prints markdown - every timed call and button
against its budget, the lock/CPU timeline, and what was lost or silent. Not a test."""
import json, sys
from collections import defaultdict

BUDGET = [('press', 300), ('typed line', 300), ('rail', 500), ('pile', 500), ('conversation', 1000), ('open a rail row', 1000), ('Next', 300), ('Back', 300)]
def budget(k): return next((b for w, b in BUDGET if w.lower() in k.lower()), 3000)
def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None
def row(k, xs, b=None):
    b = b or budget(k); p50, p95, mx = pct(xs, 50), pct(xs, 95), pct(xs, 100)
    over = sum(1 for x in xs if x is not None and x > b)
    flag = 'BREACH' if p95 is not None and p95 > b else ('some over' if over else 'ok')
    f = lambda v: '-' if v is None else f'{v:.0f}'
    return f'| {k} | {len(xs)} | {f(p50)} | {f(p95)} | {f(mx)} | {b} | {over} | {flag} |'
HEAD = '| call / button | n | p50 ms | p95 ms | max ms | budget ms | over | verdict |\n|---|---|---|---|---|---|---|---|'


def report(d):
    out = [f"## Run `{d['TAG']}`: {d['MAILS']} mails, {d['LINES']} typed lines, {d['PRESSES']} presses" + (f", a {d['BIG']}-line task" if d.get('BIG') else '')
           + f" - burst + drain {d['drainS']} s", '']
    out += ['### From outside (probe and presses, node:http: full response)', HEAD]
    for k, v in sorted(d['timings'].items()): out.append(row(k, [x['ms'] for x in v]))
    out += ['', '### TTFB of the same calls', HEAD]
    for k, v in sorted(d['timings'].items()): out.append(row(k, [x['ttfb'] for x in v]))
    ui = d['ui']
    out += ['', '### The page, clicked (click -> first change / -> screen settled)', HEAD]
    for w in sorted({u['what'] for u in ui}):
        us = [u for u in ui if u['what'] == w and not u.get('missing')]
        out.append(row(f'{w}: first change', [u.get('first') for u in us], budget(w)))
        out.append(row(f'{w}: settled', [u.get('ms') for u in us], 1000))
    miss = [u['what'] for u in ui if u.get('missing')]; dead = [u for u in ui if not u.get('missing') and not u.get('moved')]
    out += ['', f"Buttons not found on screen when wanted: {len(miss)} ({', '.join(sorted(set(miss)))}); clicks that changed nothing within 2 s: {len(dead)}; "
            f"blank-beat samples: {d.get('uiBlank', 0)}; frames recorded: {d.get('frames')}; page errors: {len(d.get('errs') or [])}"]
    gaps = d['page']['gaps']; out.append(f"Page main-thread stalls (rAF gap > 250 ms): {len(gaps)}, > 1 s: {sum(1 for g in gaps if g[1] > 1000)}, worst {max([g[1] for g in gaps] or [0])} ms")
    # the page's own requests, by route, as Chrome timed them (headers received)
    by = defaultdict(list)
    for n in d['net']: by[n['key']].append(n['ms'])
    out += ['', '### Every request the page made (Chrome: request -> headers)', HEAD]
    for k, v in sorted(by.items(), key=lambda kv: -(pct(kv[1], 95) or 0))[:25]: out.append(row(k, v))
    s = d['stats']
    sb = defaultdict(list)
    for t, k, ms in s['reqs']: sb[k].append(ms)
    out += ['', '### Server time per route (middleware), slowest p95 first', HEAD]
    for k, v in sorted(sb.items(), key=lambda kv: -(pct(kv[1], 95) or 0))[:25]: out.append(row(k, v))
    allr = [ms for _, _, ms in s['reqs']]
    out.append(f"\nRequests over 3 s: {sum(1 for x in allr if x > 3000)} of {len(allr)}; worst {max(allr or [0]):.0f} ms")
    # the lock
    holds, waits = s['holds'], s['waits']
    out += ['', '### Writer lock', f"Holds > 50 ms: {len(holds)}; > 500 ms: {sum(1 for h in holds if h[1] > .5)}; longest {max([h[1] for h in holds] or [0]) * 1000:.0f} ms. "
            f"Waits > 50 ms: {len(waits)}; longest {max([w[1] for w in waits] or [0]) * 1000:.0f} ms.", '',
            '| holder site | holds > 50 ms | total s | longest ms |', '|---|---|---|---|']
    site = defaultdict(list)
    for h in holds: site[h[2]].append(h[1])
    for k, v in sorted(site.items(), key=lambda kv: -max(kv[1]))[:15]: out.append(f'| `{k}` | {len(v)} | {sum(v):.1f} | {max(v) * 1000:.0f} |')
    # timeline, 30 s buckets
    out += ['', '### Timeline (30 s buckets)', '| t s | cpu % max | rss MB | threads | triage backlog | queued agents | working | sessions | loop lag max ms | pool borrowed max | lock hold max ms | requests | worst request ms |',
            '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    B = defaultdict(lambda: defaultdict(list))
    for x in s['samples']:
        if 'cpu' in x:
            b = B[int(x['t'] // 30)]
            for k in ('cpu', 'rss_mb', 'threads', 'triage_backlog', 'queued_agents', 'working_agents', 'sessions'): b[k].append(x[k] or 0)
    for t, ms, *pool in s['lag']: B[int(t // 30)]['lag'].append(ms); B[int(t // 30)]['pool'].append(pool[0] or 0)
    for h in holds: B[int(h[0] // 30)]['hold'].append(h[1] * 1000)
    for t, k, ms in s['reqs']: B[int(t // 30)]['req'].append(ms)
    mx = lambda b, k: f"{max(b[k]):.0f}" if b[k] else '-'
    for i in sorted(B):
        b = B[i]
        if not b['cpu']: continue
        out.append(f"| {i * 30} | {mx(b, 'cpu')} | {mx(b, 'rss_mb')} | {mx(b, 'threads')} | {mx(b, 'triage_backlog')} | {mx(b, 'queued_agents')} | {mx(b, 'working_agents')} | "
                   f"{mx(b, 'sessions')} | {mx(b, 'lag')} | {mx(b, 'pool')} | {mx(b, 'hold')} | {len(b['req'])} | {mx(b, 'req')} |")
    # lost and silent
    o, mails = d['outcomes']['out'], d['mails']
    end = defaultdict(int); notdone = []
    for m in mails:
        x = o.get(m['ext'])
        st = 'missing' if not x else ('task' if x.get('task') else x.get('status'))
        end[f"{m['kind']} -> {st}" + (f" ({x.get('kind')})" if x and x.get('task') else '')] += 1
        if not x or x.get('status') in ('triaging', 'error', 'pending'): notdone.append((m['id'], m['kind'], x and x.get('status'), x and (x.get('route') or {}).get('Reason')))
    out += ['', '### Where every mail ended', '| kind -> end | n |', '|---|---|'] + [f'| {k} | {v} |' for k, v in sorted(end.items())]
    out.append(f"\nNot judged / failed: {len(notdone)} {notdone[:10]}")
    out.append(f"Agent starts still queued at the end: {len(d['outcomes'].get('dispatchq') or [])} {[(q['TaskId'], q['Reason']) for q in (d['outcomes'].get('dispatchq') or [])][:10]}")
    tk = d['outcomes'].get('tasks') or {}
    if tk:
        q = {t: v for t, v in tk.items() if v['queuedSaid']}
        out.append(f"Tasks whose agent was queued (said 'Waiting its turn'): {len(q)}; of them with a run/transcript after: {sum(1 for v in q.values() if v['runs'] or v['transcripts'])}")
    # typed lines heard
    heard = defaultdict(int)
    for t in d['turns']:
        for n in t['lines']: heard[n] += 1
    sent = d['sent']
    out.append(f"Typed lines: {len(sent)} sent, answers {dict((s_['status'], sum(1 for y in sent if y['status'] == s_['status'])) for s_ in sent)}; heard by an agent once: "
               f"{sum(1 for s_ in sent if heard.get(s_['n']) == 1)}, twice+: {[n for n, c in heard.items() if c > 1]}, never: {[s_['n'] for s_ in sent if not heard.get(s_['n'])]}")
    p = d['pressed']
    out.append(f"Presses: {len(p)}; statuses {dict((x['status'], sum(1 for y in p if y['status'] == x['status'])) for x in p)}; Send presses {sum(1 for x in p if 'Send' in x['k'])} -> outbox lines {d['outbox']}")
    out.append(f"Agent turns answered: {len([t for t in d['turns'] if not t['triage']])}; triage prompts that reached the director: {len([t for t in d['turns'] if t['triage']])}; "
               f"longest prompt {max([t['chars'] for t in d['turns']] or [0])} chars")
    if d.get('bigOpen'): out.append(f"Opening the {d['BIG']}-line task in the page: {d['bigOpen']}")
    return '\n'.join(out)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for f in sys.argv[1:]: print(report(json.load(open(f, encoding='utf-8')))); print()
