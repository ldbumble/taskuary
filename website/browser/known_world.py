"""A SCRATCH HOME THAT ALREADY KNOWS THE SYSTEM A NEW ASK IS ABOUT (real-known.mjs; not a test - nothing here runs in CI). The live shape of
2026-11-16 with invented people: an internal app's record for a new hire looks incomplete; the Hub holds notes on that app among better-voted
notes on other things, closed tasks from another colleague settled the same kind of case in the app's repository, the repository map names
the repository only as an "operations platform", the live data sits beside a stale archive copy, and semantic search is off.

    TASKUARY_HOME=<the walk's home> PYTHONPATH=<checkout> python known_world.py   ->  prints {"taskId": ...}
"""
import json, os, sqlite3, subprocess, sys
from pathlib import Path

from taskuary import config, handbook, wrapup
from taskuary.store import SQLiteStore

home = Path(os.environ['TASKUARY_HOME'])
s = SQLiteStore(config.db_path())
code, data = home / 'code', home / 'data'
code.mkdir(exist_ok=True); data.mkdir(exist_ok=True)


def repo(name: str, files: dict) -> str:
    p = code / name.split('/')[-1]; p.mkdir(exist_ok=True)
    for f, text in files.items(): (p / f).parent.mkdir(parents=True, exist_ok=True); (p / f).write_text(text, encoding='utf-8')
    git = lambda *a: subprocess.run(['git', '-C', str(p), *a], check=True, capture_output=True)
    git('init', '-q'); git('config', 'user.name', 'Alex Doyle'); git('config', 'user.email', 'alex@northwind.example')
    subprocess.run(['git', '-C', str(p), 'remote', 'add', 'origin', f'https://github.com/{name}.git'], capture_output=True)
    git('add', '.'); git('commit', '-qm', 'start', '--allow-empty')
    return str(p)


LIVE, OLD = data / 'ledger.db', data / 'keycard_2023.db'
paths = {
    'northwind/portal': repo('northwind/portal', {
        'README.md': 'Northwind operations platform: APIs, reports, schedulers and web tools.\n',
        'src/keycard/provision.py': f'"""KeyCard logins for new hires - runs at 06:00."""\nimport sqlite3\nLIVE = r"{LIVE}"\n\n'
                                    'def run():\n    cx = sqlite3.connect(LIVE)\n'
                                    '    for emp, job in cx.execute("SELECT emp_id, job_code FROM pay_people WHERE status=\'active\'"):\n'
                                    '        if not job: continue          # no job code yet: no logins - the record shows blank until payroll sets it\n'
                                    '        cx.execute("INSERT OR IGNORE INTO keycard_logins (emp_id, windows_user, email_user) VALUES (?,?,?)", (emp, f"u{emp}", f"u{emp}@northwind.example"))\n'
                                    '    cx.commit()\n',
        'src/reports/aging.py': 'def aging(rows):\n    return sorted(rows, key=lambda r: r["days"])\n',
        'src/api/health.py': 'def health():\n    return {"ok": True}\n'}),
    'northwind/ledger': repo('northwind/ledger', {'totals.py': 'def total(a, tax):\n    return a + tax\n'}),
    'northwind/warehouse': repo('northwind/warehouse', {'jobs/nightly.sql': 'SELECT 1;\n'}),
}
for f in (LIVE, OLD): f.unlink(missing_ok=True)
cx = sqlite3.connect(LIVE)
cx.executescript("CREATE TABLE pay_people (emp_id INTEGER PRIMARY KEY, name TEXT, site TEXT, job_code TEXT, status TEXT, hired TEXT);"
                 "CREATE TABLE keycard_logins (emp_id INTEGER PRIMARY KEY, windows_user TEXT, email_user TEXT);")
cx.executemany('INSERT INTO pay_people VALUES (?,?,?,?,?,?)', [(1001, 'Sam Ortiz', 'Riverside', 'RN', 'active', '2026-10-02'),
               (1002, 'Dana Fox', 'Lakeside', 'LPN', 'active', '2026-10-20'), (1003, 'Jordan Lee', 'Riverside', None, 'active', '2026-11-13')])
cx.executemany('INSERT INTO keycard_logins VALUES (?,?,?)', [(1001, 'u1001', 'u1001@northwind.example'), (1002, 'u1002', 'u1002@northwind.example')])
cx.commit(); cx.close()
cx = sqlite3.connect(OLD)
cx.executescript("CREATE TABLE employees (EmplID INTEGER, EmpName TEXT, Fac TEXT, JobCode TEXT, DateImported TEXT);"
                 "INSERT INTO employees VALUES (1001, 'Sam Ortiz', 'Riverside', 'RN', '2023-06-01');")
cx.commit(); cx.close()

s.save_doc('soul', (s.doc('soul') or '').rstrip() + '\n\n## Repo map\n'
           '- **northwind/portal**: Northwind\'s internal operations platform - APIs, reports, schedulers and web tools\n'
           '- **northwind/ledger**: the finance backend - totals and exports\n'
           '- **northwind/warehouse**: the reporting warehouse\'s nightly jobs\n', 'owner')
s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': paths}))
s.set_setting('code_folders', str(code), 'owner')
s.set_setting('owner_name', 'Alex Doyle', 'owner'); s.set_setting('owner_email', 'alex@northwind.example', 'owner')

for i, (t, b, topic) in enumerate([('Month-end close posts accruals before the ledger close', 'Run the accrual job first.', 'ledger'),
                                   ('Warehouse nightly jobs restart from the last good partition', 'Never from the start.', 'warehouse'),
                                   ('Payworth invoices go to Gail Moreno for approval', 'Not to AP directly.', 'payables'),
                                   ('Trainly renewals are decided in the January budget', 'Hold quotes until then.', 'vendors')]):
    p = handbook.post(s, t, b, topic, 'howto', 'agent')
    for who in ('owner', 'agent', 'codex'): s.lore_vote(p['LoreId'], 1, who)
handbook.post(s, 'KeyCard logins are made by the portal provisioning job from ledger.db pay_people',
              f'northwind/portal src/keycard/provision.py runs at 06:00: an active pay_people row in {LIVE} WITH a job_code gets its logins in '
              'keycard_logins. No job code, no logins - the KeyCard record shows blank until payroll sets it.', 'portal', 'system', 'agent')
handbook.post(s, 'keycard_2023.db is a stale 2023 archive of KeyCard, never the live data',
              f'{OLD} stopped updating in 2023; the live rows are in {LIVE}.', 'portal', 'gotcha', 'agent')


def closed(title, report, frm=('Gail Moreno', 'gail@northwind.example'), tags=None):
    tid = s.create_task({'Title': title, 'Kind': 'general', 'Status': 'done', 'Tags': tags}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': f'kw-{tid}', 'Channel': 'email', 'FromName': frm[0], 'FromEmail': frm[1], 'ToEmail': 'alex@northwind.example',
                   'Subject': title, 'SentAt': '2026-11-02 09:00:00', 'BodyText': 'Could you look at this?', 'Status': 'routed'})
    s.add_comment(tid, 'agent', 'agent', f'{wrapup.REPORT}\n{report}')
    s._exec("UPDATE task SET ClosedAt='2026-11-03 10:00:00', Tags=? WHERE TaskId=?", (tags, tid))
closed('Check blank KeyCard logins for Sam Ortiz', "Determination: Sam's pay_people row had no job_code when the 06:00 provisioning ran; payroll set "
       'it and the next run made his logins. Blank logins on a new hire = no job_code yet in ledger.db pay_people.', tags='agent-repo:northwind/portal')
closed('Ledger close ran late on the 3rd', 'Actions: moved the close job to 06:00.', frm=('Ray Colton', 'ray@northwind.example'))
closed('Warehouse export missing a day', 'Actions: reran the nightly job from the last good partition.', frm=('Ray Colton', 'ray@northwind.example'))

tid = s.create_task({'Title': 'Check incomplete KeyCard record for Jordan Lee', 'Kind': 'general', 'Status': 'open',
                     'Summary': 'Paula Vance asks why new hire Jordan Lee shows an incomplete KeyCard record with blank logins'}, 'owner')
s.add_message({'TaskId': tid, 'ExternalId': f'kw-{tid}', 'Channel': 'teams', 'FromName': 'Paula Vance', 'FromEmail': 'paula@northwind.example',
               'ToEmail': 'alex@northwind.example', 'Subject': 'KeyCard help', 'SentAt': '2026-11-16 09:00:00', 'Status': 'routed',
               'BodyText': 'Hi Alex, Jordan Lee (new hire at Riverside, started Friday) shows an incomplete record in KeyCard - the logins are blank. '
                           'Can you check why? Thanks, Paula'})
print(json.dumps({'taskId': tid}))
