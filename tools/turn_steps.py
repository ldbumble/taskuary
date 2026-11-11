"""What an agent's turns on an AI card did, step by step: `python tools/turn_steps.py --db PATH [--days 14] [--each]`.

Reads a COPY of PATH (a read such as origin.of_task writes a cache) with TASKUARY_HOME pointed at a fresh temp dir, so the real home is never
opened; the turns' steps are read from the `artifacts` folder beside PATH (sessionrecord.keep_turn), or --artifacts, and never written.
There is no default for --db. Prints keys and counts only - tool names (Taskuary's own), numbers - never a title, a name, an address or any
text. Per turn: its steps, the tool-name sequence, calls that repeated an identical earlier call of the turn (as far as the kept step shows
its arguments), reads of what the opening prompt already carried (the task's brief, its own mails and their files, its senders), and the
tokens its calls took in and how many of those the provider served from its cache. Tokens are kept per turn, not per step (brainroute adds
each call to its turn's row): `in/call` is the turn's average."""
import argparse, json, os, re, shutil, sys, tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


def _num(s) -> int | None:
    m = re.fullmatch(r'\s*(?:m|attachment\s*)?(\d+)\s*', str(s or ''), re.I)
    return int(m.group(1)) if m else None


def carried(store, tid: int):
    "What the opening prompt of a turn on task `tid` already holds (general.prompt_parts): its mails by id, their files by id, their senders."
    ms = store.list_messages(tid)
    files = {a['AttachmentId'] for m in ms for a in store.list_attachments(m['MessageId'])}
    who = {str(x).strip().lower() for m in ms for x in (m.get('FromName'), m.get('FromEmail')) if x}
    def had(step) -> bool:
        n, t = step.get('name'), step.get('text')
        return (n == 'my_task' or (n == 'read_message' and _num(t) in {m['MessageId'] for m in ms})
                or (n == 'read_attachment' and _num(t) in files) or (n == 'person' and str(t or '').strip().lower() in who))
    return had


def turns(store, arts: Path, days: int = 14, now: datetime = None) -> list:
    "One dict of counts per kept general turn on an AI card in the last `days` - its steps, repeats, reads of the prompt, tokens."
    since = ((now or datetime.now()) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for f in sorted(arts.glob('*/general-steps.jsonl'), key=lambda p: p.parent.name):
        if not f.parent.name.isdigit(): continue
        tid, had = int(f.parent.name), None
        routes = store._rows("SELECT At, Pick, Calls, TokensIn, Cached FROM brainroute WHERE TaskId=? AND Job IN ('general','coding') ORDER BY Id", (tid,))
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            try: rec = json.loads(line)
            except ValueError: continue
            c = store._one('SELECT CreatedAt FROM comment WHERE CommentId=?', (rec.get('reply'),)) if rec.get('reply') else None
            at = str((c or {}).get('CreatedAt') or '')
            if not at or at < since: continue
            # ...the turn's own route: the newest written before its reply (one per turn - general.send_prompt builds its brain each turn)
            r = next((r for r in reversed(routes) if str(r['At'] or '').replace('T', ' ') <= at), None)
            if not r or not str(r['Pick'] or '').startswith('connector:'): continue
            had = had or carried(store, tid)
            steps = [s for s in rec.get('steps') or [] if s.get('k') == 'tool']
            keys = [(s.get('name'), s.get('text'), json.dumps(s.get('args') or {}, sort_keys=True)) for s in steps]
            calls, tin = int(r['Calls'] or 0), int(r['TokensIn'] or 0)
            out.append({'steps': len(steps), 'tools': [s.get('name') or '?' for s in steps], 'repeats': len(keys) - len(set(keys)),
                        'prompt_had': sum(map(had, steps)), 'calls': calls, 'in': tin, 'cached': int(r['Cached'] or 0),
                        'in_per_call': tin // calls if calls else 0})
    return out


def summary(ts: list) -> dict:
    "Totals over the turns, keys and counts only."
    n, tin = len(ts), sum(t['in'] for t in ts)
    first = Counter(t['tools'][0] for t in ts if t['tools'])
    return {'turns': n, 'steps': sum(t['steps'] for t in ts), 'calls': sum(t['calls'] for t in ts),
            'repeats': sum(t['repeats'] for t in ts), 'turns_with_repeats': sum(t['repeats'] > 0 for t in ts),
            'prompt_had': sum(t['prompt_had'] for t in ts), 'turns_reading_the_prompt_again': sum(t['prompt_had'] > 0 for t in ts),
            'tokens_in': tin, 'cached': sum(t['cached'] for t in ts), 'cached_pct': round(100 * sum(t['cached'] for t in ts) / tin) if tin else 0,
            'steps_per_turn_max': max((t['steps'] for t in ts), default=0),
            **{f'first:{k}': v for k, v in first.most_common(8)},
            **{f'tool:{k}': v for k, v in Counter(x for t in ts for x in t['tools']).most_common(15)}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True); p.add_argument('--artifacts'); p.add_argument('--days', type=int, default=14)
    p.add_argument('--each', action='store_true', help='also one line per turn')
    a = p.parse_args(argv)
    arts = Path(a.artifacts) if a.artifacts else Path(a.db).resolve().parent / 'artifacts'
    tmp = Path(tempfile.mkdtemp(prefix='turn-steps-')); db = tmp / 'taskuary.db'
    for x in ('', '-wal', '-shm'):                           # ...with what a live database has not yet written into its file
        if Path(a.db + x).is_file(): shutil.copy(a.db + x, str(db) + x)
    from taskuary.store import SQLiteStore
    try:
        ts = turns(SQLiteStore(db), arts, a.days)
        if a.each:
            for i, t in enumerate(ts, 1):
                print(f"turn {i}: steps {t['steps']} | {'>'.join(t['tools']) or '-'} | repeats {t['repeats']} | prompt_had {t['prompt_had']} | "
                      f"calls {t['calls']} | in {t['in']} | cached {t['cached']} | in/call {t['in_per_call']}")
        for k, v in summary(ts).items(): print(f'{k}: {v}')
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='turn-steps-home-')     # before any taskuary import: nothing may open the real home
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from loguru import logger; logger.remove(); logger.add(sys.stderr, level='WARNING')
    try: sys.exit(main())
    finally: shutil.rmtree(os.environ['TASKUARY_HOME'], ignore_errors=True)
