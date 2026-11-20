"""THE SAME EVERYDAY ASKS AGAINST ANY AGENT ROAD - a manual check, never collected by pytest (its name has no test_ prefix), never in CI.

    python tests/agent_sweep.py <REAL_OUT> [--only make,web] [--asks 1,5,9] [--wait 300] [--tag hydrogen]

It drives a scratch app that website/browser/real-run.mjs keeps up (its REAL_OUT/info.json), over the app's own HTTP doors - New's start
(/api/start), a task's line (/api/tasks/{id}/assistant/messages) - so whatever brain the app's agents run on is what is judged: an AI card's
agent today (EVAL_BRAIN=gateway, EVAL_AI_MODEL=...), a CLI road tomorrow (EVAL_BRAIN=cli / codex). Nothing here knows which.

Per ask it logs the tool calls in order (as the chat records them: conversation `steps`), when each was first seen (polled each second, so a
call's seconds are to the next call's start), the turn's total seconds, the answer's head and the files the task's outputs folder holds.
It FLAGS a turn for a person to look at - it judges nothing about meaning: a class of tool the ask should not need (a web search to make a
file, the browser for a lookup), none of the classes it needs, more calls or more seconds than the ask's budget, an answer that ends on a
question where the tools could have found the answer, or no file where a file was asked. The table goes to REAL_OUT/sweep-<tag>.md, every
turn whole to REAL_OUT/sweep-<tag>.jsonl. Every person, mail and file in it is invented (the repo's stand-ins)."""
import argparse, json, os, sys, time, urllib.request
from pathlib import Path

# a tool's class, by its name on either road (an AI card's own tools, a CLI's): one table, so a road is judged by what it did, not by its words
CLASS = {'make': ('file_write', 'file_edit', 'write', 'edit', 'notebookedit', 'apply_patch'), 'cmd': ('run_command', 'bash', 'powershell', 'exec_command', 'shell'),
         'read': ('file_read', 'files_list', 'read', 'glob', 'grep', 'ls'), 'web': ('web_search', 'websearch', 'web_fetch', 'webfetch'),
         'browser': ('browser_',), 'mail': ('search_messages', 'read_message', 'mail'), 'tasks': ('search_tasks', 'my_task', 'task'),
         'calendar': ('free_times', 'calendar', 'meeting'), 'show': ('show',), 'reply': ('propose_reply', 'reply')}
def classes(name: str) -> set:
    n = str(name or '').lower().split('__')[-1]
    return {c for c, ks in CLASS.items() if any(n == k or n.startswith(k) for k in ks)}

# (group, ask, needs any of, never, max calls, max seconds, wants a file) - `{dir}` is the sweep's own folder of invented files
ASKS = [
    ('make', 'Make me an image (SVG) of a simple logo for Northwind: a sail over two waves, navy and sky blue.', {'make', 'cmd'}, {'web', 'browser'}, 4, 90, True),
    ('make', 'Make a bar chart image of Q3 revenue by month: July 120k, August 135k, September 150k.', {'make', 'cmd'}, {'web', 'browser'}, 5, 120, True),
    ('make', 'Make a one-page PDF summarising our Q3: revenue 405k, up 12%, two new customers (Payworth, Trainly). Include a small chart.', {'make', 'cmd'}, {'web', 'browser'}, 5, 120, True),
    ('make', 'Make a spreadsheet of our three vendors (Payworth 1200/mo, Trainly 300/mo, Spendly 450/mo) with a total row that is a formula.', {'make', 'cmd'}, {'web', 'browser'}, 4, 90, True),
    ('make', 'Make a 5-slide deck introducing Northwind to a new hire: who we are, teams, tools, first week, who to ask.', {'make', 'cmd'}, {'web', 'browser'}, 5, 150, True),
    ('make', 'Make a simple HTML page announcing the Northwind summer picnic on July 18 at noon, with a map placeholder and an RSVP button.', {'make', 'cmd'}, {'web', 'browser'}, 4, 90, True),
    ('make', 'Write a Word document with a short policy on expense reports: who approves, limits, and deadlines.', {'make', 'cmd'}, {'web', 'browser'}, 4, 90, True),
    ('local', 'In {dir}\\vendors.xlsx, what does Trainly cost per month?', {'read', 'cmd'}, {'web', 'browser'}, 3, 45, False),
    ('local', 'Which file in {dir} mentions the rooftop parking change?', {'read', 'cmd'}, {'web', 'browser'}, 4, 60, False),
    ('local', 'Summarise {dir}\\handbook.pdf in three bullets.', {'read', 'cmd'}, {'web', 'browser'}, 3, 60, False),
    ('local', 'Compare {dir}\\plan-a.txt and {dir}\\plan-b.txt: what changed?', {'read', 'cmd'}, {'web', 'browser'}, 4, 60, False),
    ('local', "In {dir}\\vendors.xlsx change Spendly's monthly cost to 500 and keep the total right.", {'make', 'cmd'}, {'web', 'browser'}, 5, 90, False),
    ('local', 'How many rows are in {dir}\\orders.csv, and what is the largest order?', {'read', 'cmd'}, {'web', 'browser'}, 3, 45, False),
    ('web', 'What year was the Eiffel Tower finished?', {'web'}, {'browser', 'make'}, 2, 30, False),
    ('web', 'What does a Raspberry Pi 5 with 8 GB cost right now?', {'web'}, {'make'}, 3, 45, False),
    ('web', "What's in the news today about electric vehicles? Three headlines with sources.", {'web'}, {'make'}, 3, 60, False),
    ('web', 'Read https://example.com and tell me what it says.', {'web', 'browser'}, {'make'}, 2, 30, False),
    ('web', 'What is the current population of Iceland?', {'web'}, {'browser', 'make'}, 2, 30, False),
    ('web', 'Find two well-reviewed project management tools for a 10-person team and compare their prices in a short table.', {'web'}, {'browser'}, 5, 90, False),
    ('mail', 'Draft a reply to Erin Blake thanking her for the Q3 numbers and asking for the October forecast by Friday.', {'reply', 'mail'}, {'web', 'browser'}, 4, 60, False),
    ('mail', 'What did Erin ask me last week?', {'mail', 'tasks'}, {'web', 'browser'}, 4, 45, False),
    ('mail', 'Find a free hour for me next Tuesday afternoon for a call with Gail Moreno.', {'calendar'}, {'web', 'browser'}, 4, 45, False),
    ('mail', 'Remind me on Friday to check whether Ray Colton signed the Payworth contract.', set(), {'web', 'browser', 'make'}, 3, 30, False),
    ('mail', 'Write a short note to the team that the office is closed Monday for the holiday.', set(), {'web', 'browser'}, 3, 45, False),
    ('browser', 'Open https://example.com in the browser and follow its "More information" link; tell me where it lands.', {'browser'}, {'make'}, 6, 90, False),
    ('browser', 'Sign me up for a free trial on http://127.0.0.1:18791/ with made-up details.', {'browser'}, {'make'}, 12, 240, False),
    ('code', 'Run the script {dir}\\add.py and tell me what it prints.', {'cmd'}, {'web', 'browser'}, 3, 45, False),
    ('code', 'The function in {dir}\\repo\\price.py rounds wrong for 2.675 - fix it so it rounds half up to cents, and run its test.', {'cmd', 'make'}, {'web', 'browser'}, 8, 180, False),
    ('chat', 'Explain in two sentences what a 401(k) match is.', set(), {'web', 'browser', 'make', 'cmd'}, 1, 20, False),
    ('chat', 'Rewrite this to sound friendlier: "Send me the report by 5pm. No excuses."', set(), {'web', 'browser', 'make', 'cmd'}, 1, 20, False),
    ('chat', 'Give me a 3-item agenda for a 30-minute vendor review with Payworth.', set(), {'web', 'browser', 'cmd'}, 2, 30, False),
    ('chat', 'Turn these into a checklist: book room, order lunch, send invites, print badges.', set(), {'web', 'browser', 'cmd'}, 2, 30, False),
    ('chat', 'What is 17.5% of 2,340?', set(), {'web', 'browser'}, 1, 20, False),
    ('chat', 'Translate "Thanks for your patience, the shipment leaves tomorrow" into Spanish.', set(), {'web', 'browser', 'make', 'cmd'}, 1, 20, False),
    ('make', 'Make a CSV of the twelve months of 2027 with a column for the first Monday of each.', {'make', 'cmd'}, {'web', 'browser'}, 4, 60, True),
    ('make', 'Draw a simple org chart image: Alex Doyle at the top, Erin Blake and Gail Moreno under him, Paula Vance under Erin.', {'make', 'cmd'}, {'web', 'browser'}, 5, 120, True),
    ('make', 'Make a QR-code-free event poster image for a book club, Thursday 6pm, room 4B.', {'make', 'cmd'}, {'web', 'browser'}, 5, 120, True),
    ('local', 'List the files in {dir} and say what each one is for.', {'read', 'cmd'}, {'web', 'browser'}, 4, 45, False),
    ('web', 'Look up the opening hours of the Louvre today.', {'web'}, {'make'}, 3, 45, False),
    ('code', 'Write a small Python script in {dir} that renames every .txt file there to lower case, and run it on a copy first.', {'cmd', 'make'}, {'web', 'browser'}, 8, 150, False),
]


def fixtures(d: Path):
    "The sweep's own folder of invented files the local asks read."
    d.mkdir(parents=True, exist_ok=True); (d / 'repo').mkdir(exist_ok=True)
    (d / 'plan-a.txt').write_text('Launch: May 4\nBudget: 40k\nOwner: Erin Blake\nVenue: hall B\n', encoding='utf-8')
    (d / 'plan-b.txt').write_text('Launch: May 18\nBudget: 46k\nOwner: Erin Blake\nVenue: rooftop\n', encoding='utf-8')
    (d / 'memo-facilities.txt').write_text('From Omar Keller: from June, rooftop parking moves to level 3 while the deck is resurfaced.\n', encoding='utf-8')
    (d / 'memo-lunch.txt').write_text('Lunch-and-learn moves to Thursdays.\n', encoding='utf-8')
    (d / 'orders.csv').write_text('id,customer,amount\n1,Payworth,1200\n2,Trainly,300\n3,Spendly,4500\n4,Payworth,800\n', encoding='utf-8')
    (d / 'add.py').write_text('print(sum(range(1, 11)))\n', encoding='utf-8')
    (d / 'repo' / 'price.py').write_text('def cents(x):\n    return round(x, 2)\n', encoding='utf-8')
    (d / 'repo' / 'test_price.py').write_text('from price import cents\n\ndef test_half_up():\n    assert cents(2.675) == 2.68\n', encoding='utf-8')
    try:
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.append(['Vendor', 'Monthly'])
        for r in (('Payworth', 1200), ('Trainly', 300), ('Spendly', 450)): ws.append(r)
        ws.append(['Total', '=SUM(B2:B4)']); wb.save(d / 'vendors.xlsx')
    except ImportError: print('openpyxl is not here - vendors.xlsx skipped')
    if not (d / 'handbook.pdf').exists(): (d / 'handbook.pdf').write_bytes(_pdf(['Northwind handbook', 'Hours: 9 to 5, Fridays to 3.',
                                                                                     'Expenses: file within 30 days.', 'Security: badges on at all times.']))


def _pdf(lines) -> bytes:
    "A one-page PDF of `lines`, written by hand: no library needed."
    body = 'BT /F1 14 Tf 72 740 Td ' + ' '.join(f'({l}) Tj 0 -22 Td' for l in lines) + ' ET'
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
            f'<< /Length {len(body)} >>\nstream\n{body}\nendstream', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, at = b'%PDF-1.4\n', []
    for i, o in enumerate(objs, 1): at.append(len(out)); out += f'{i} 0 obj\n{o}\nendobj\n'.encode()
    x = len(out)
    out += f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode() + b''.join(f'{a:010d} 00000 n \n'.encode() for a in at)
    return out + f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n'.encode()


class App:
    def __init__(self, out: Path):
        i = json.loads((out / 'info.json').read_text(encoding='utf-8')); self.base, self.tok = i['api'], i['token']
    def call(self, p, body=None, timeout=60):
        r = urllib.request.Request(self.base + p, data=None if body is None else json.dumps(body).encode(), method='POST' if body is not None else 'GET',
                                   headers={'Content-Type': 'application/json', 'X-Taskuary-Token': self.tok})
        return json.load(urllib.request.urlopen(r, timeout=timeout))


def run(app: App, ask: str, wait: float) -> dict:
    "One ask on New: the task it made, its turn's calls as first seen, the seconds, the answer and the files."
    t0 = time.time(); tid = app.call('/api/start', {'text': ask, 'images': []})['taskId']
    seen, c = [], {}
    while time.time() - t0 < wait:
        try: c = app.call(f'/api/tasks/{tid}/conversation?level=everything')
        except Exception: time.sleep(2); continue
        turns = [x for x in c.get('items', []) if x.get('kind') == 'turn']
        steps = [s for t in turns for s in t.get('steps') or [] if s.get('k') == 'tool']
        for s in steps[len(seen):]: seen.append({'name': s.get('name') or s.get('title') or '?', 'at': round(time.time() - t0, 1),
                                                 'what': str(s.get('text') or s.get('args') or s.get('summary') or '')[:160]})
        if turns and not c.get('working') and turns[-1].get('state') not in ('working', 'starting') and time.time() - t0 > 5: break
        time.sleep(1)
    total = round(time.time() - t0, 1)
    for a, b in zip(seen, seen[1:] + [{'at': total}]): a['secs'] = round(b['at'] - a['at'], 1)
    turns = [x for x in c.get('items', []) if x.get('kind') == 'turn']
    try: files = [f.get('name') for f in app.call(f'/api/task-outputs/{tid}').get('data') or []]
    except Exception: files = []
    return {'task': tid, 'calls': seen, 'secs': total, 'answer': str((turns[-1] if turns else {}).get('text') or '')[:600],
            'state': (turns[-1] if turns else {}).get('state'), 'files': files, 'timed_out': total >= wait}


def flags(r: dict, need: set, never: set, most: int, secs: float, wants_file: bool) -> list:
    did = [classes(x['name']) for x in r['calls']]
    out = [f"{x['name']} ({'/'.join(sorted(k & never))})" for x, k in zip(r['calls'], did) if k & never]
    if need and not any(k & need for k in did): out.append(f"none of {'/'.join(sorted(need))}")
    if len(r['calls']) > most: out.append(f"{len(r['calls'])} calls > {most}")
    if r['secs'] > secs: out.append(f"{r['secs']} s > {secs}")
    if wants_file and not r['files']: out.append('no file made')
    if r['answer'].rstrip().endswith('?'): out.append('ends on a question')
    if r['timed_out']: out.append('still working at the wait')
    if r['state'] == 'failed': out.append('turn failed')
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--only', default=''); ap.add_argument('--asks', default='')
    ap.add_argument('--wait', type=float, default=300); ap.add_argument('--tag', default='sweep')
    a = ap.parse_args()
    out = Path(a.out); app = App(out); d = out / 'sweep-files'; fixtures(d)
    pick = [(i, x) for i, x in enumerate(ASKS, 1) if (not a.only or x[0] in a.only.split(',')) and (not a.asks or str(i) in a.asks.split(','))]
    rows, log = [], (out / f'sweep-{a.tag}.jsonl').open('a', encoding='utf-8')
    for i, (group, ask, need, never, most, secs, wants_file) in pick:
        ask = ask.replace('{dir}', str(d))
        try: r = run(app, ask, a.wait)
        except Exception as e: r = {'task': None, 'calls': [], 'secs': 0, 'answer': f'(could not start: {e})', 'state': 'failed', 'files': [], 'timed_out': False}
        f = flags(r, need, never, most, secs, wants_file)
        log.write(json.dumps({'n': i, 'group': group, 'ask': ask, **r, 'flags': f}, ensure_ascii=False) + '\n'); log.flush()
        line = f"| {i} | {group} | {ask[:60]} | {'WRONG' if f else 'right'} | {len(r['calls'])} | {r['secs']} | {' -> '.join(x['name'] for x in r['calls'])[:120]} | {'; '.join(f)} |"
        rows.append(line); print(line, flush=True)
    (out / f'sweep-{a.tag}.md').write_text('| # | group | ask | verdict | calls | s | tools | why |\n|---|---|---|---|---|---|---|---|\n' + '\n'.join(rows) + '\n', encoding='utf-8')


if __name__ == '__main__': sys.exit(main())
