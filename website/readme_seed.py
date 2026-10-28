"""The README's one request, written into a browser harness's demo home (capture-readme-app.mjs): Ruth's ask for the August vendor spend,
then the analyst's finished run on it - its report, the workbook it left and the reply drafted for the owner. Invented people only.
python website/readme_seed.py ask            -> prints the new task's id
python website/readme_seed.py done <task id> -> the agent finished, the workbook made, the reply drafted"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskuary import config, demo, outputs, terminal
from taskuary.store import SQLiteStore
from taskuary.testing import Factory

ASK = ('Can you send me the latest August vendor spend numbers before the operations review? '
       'Please include the total, the change from July, and a breakdown by category.')
ROWS = [('Supplies', 78400, 71900), ('Services', 64200, 59300), ('Software', 50000, 47200)]
ANSWER = ('August vendor spend was **$192,600**, up **$14,200 (8.0%)** from July\'s $178,400.\n\n'
          '| Category | July | August |\n|---|---:|---:|\n'
          + ''.join(f'| {c} | ${j:,} | ${a:,} |\n' for c, a, j in ROWS)
          + '| **Total** | **$178,400** | **$192,600** |\n\n'
          'The three categories add up to the total. Posted invoices through August 31; open purchase orders are excluded. '
          'The reply to Ruth is drafted on the task - nothing has been sent.')
DRAFT = ('Hi Ruth,\n\nAugust vendor spend was $192,600, up $14,200 (8.0%) from July\'s $178,400.\n\n'
         + ''.join(f'- {c}: ${a:,}\n' for c, a, _ in ROWS)
         + '\nThe three categories reconcile to the total. These are posted invoices through August 31; open purchase orders are excluded.'
           '\n\nAlex')

s = SQLiteStore(str(config.home() / 'taskuary.db'))
f = Factory(s); f.actor = 'triage'
ruth = demo.PEOPLE[3]
if sys.argv[1] == 'ask':
    tid = f.task(title='Prepare the latest vendor spend numbers', status='open', kind='general', source='email',
                 Summary='Ruth needs the August vendor spend before the 11:30 operations review: the total, the change from July and a category breakdown.')
    mid = f.message(task_id=tid, subject='Latest vendor spend numbers?', body=ASK, from_name=ruth[0], from_email=ruth[1],
                    sent_at=f.ago(minutes=25), conversation_id='email:readme-vendor-spend')
    f.route(mid, tid, 'create', 'a request for current internal numbers: an agent can prepare the analysis and draft the reply for review')
    print(tid)
else:
    tid = int(sys.argv[2])
    s._exec("UPDATE task SET Status='in_progress', Assignee='agent:general', Tags=? WHERE TaskId=?", (terminal.SAVED, tid))
    s.add_transcript(tid, f'readme-{tid}', 'Reading the posted-invoice report for July and August.\nChecking the category totals against the ledger.',
                     agent='general', cwd=str(config.home()), brain='claude')
    s.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: August vendor spend is $192,600, up $14,200 (8.0%) from July.\n'
                  'Actions: Read the posted vendor invoices for July and August; totalled them by category; checked the categories add up.\n'
                  'Summary: The August vendor spend is ready for review, with the change from July and a category breakdown.\n\n'
                  'LAST MESSAGE\n' + ANSWER)
    out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = 'August'
    for r in (['Category', 'July', 'August'], *[[c, j, a] for c, a, j in ROWS], ['Total', 178400, 192600]): ws.append(r)
    wb.save(out / 'August vendor spend.xlsx')
    mid = s.list_messages(tid)[0]['MessageId']
    f.review(tid, mid, draft=DRAFT, reason='needs a reply: Ruth asks for the numbers')
