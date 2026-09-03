"""A day's worth of arrivals through the front door of the scratch server, with the real triage brain."""
import sys, json, time
sys.path.insert(0, r'C:\Users\UNUSSB~1\AppData\Local\Temp\claude\C--Users-unussbaum-Documents-General-Testing-taskhub\4ed300c8-8b52-4c88-8747-64a79ae5215a\scratchpad')
from tq import call
from datetime import datetime, timedelta
def ago(h=0, m=0): return (datetime.now() - timedelta(hours=h, minutes=m)).strftime('%Y-%m-%d %H:%M:%S')
MSGS = [
 dict(tag='coding-colleague', channel='email', subject='Nightly export drops inter-company rows', from_name='Chana Klein', from_email='chana@ours.com', conversation_id='c:export',
      body='Hi - the nightly export in export.py is missing every inter-company row again. Can you fix the filter so those rows come through? Thanks, Chana', sent_at=ago(0, 50)),
 dict(tag='question-stranger', channel='email', subject='Are you around Tuesday?', from_name='Craig Neiswanger', from_email='craig@vendor.com', conversation_id='c:tuesday',
      body='Quick 15 min call Tuesday afternoon about the renewal? Let me know what time works.', sent_at=ago(1, 10)),
 dict(tag='fyi-1', channel='email', subject='FYI - Rebecca is back Tuesday', from_name='Chana Klein', from_email='chana@ours.com', conversation_id='c:fyi1',
      body='Just so you know, Rebecca is back from leave on Tuesday. Nothing needed.', sent_at=ago(2)),
 dict(tag='fyi-2', channel='email', subject='Lunch moved to Thursday', from_name='Dovid Roth', from_email='dovid@ours.com', conversation_id='c:fyi2',
      body='Heads up, the team lunch is Thursday now, same place.', sent_at=ago(2, 30)),
 dict(tag='promo', channel='email', subject='September newsletter: 5 ways to streamline AP', from_name='BillFlow Marketing', from_email='news@billflow.io', conversation_id='c:promo',
      body='Discover how leading finance teams automate approvals... Unsubscribe here.', sent_at=ago(3)),
 dict(tag='general-ask', channel='email', subject='Which vendor should we pick for the badge printers?', from_name='Dovid Roth', from_email='dovid@ours.com', conversation_id='c:vendor',
      body='Two quotes attached in spirit: Zebra at $2,400 and Brady at $1,900 with a slower turnaround. Which would you go with, and why?', sent_at=ago(3, 20)),
 dict(tag='urgent-outage', channel='teams', subject='', from_name='Miriam Schwartz', from_email='miriam@ours.com', conversation_id='t:ops',
      body='the payroll portal is down for everyone in Roanoke since 8am, people cannot clock in - who can look at this??', sent_at=ago(0, 20)),
 dict(tag='ooo', channel='email', subject='Automatic reply: Nightly export drops inter-company rows', from_name='Kishan Patel', from_email='kishan@vendor.com', conversation_id='c:ooo',
      body='I am out of the office until Monday with limited access to email.', sent_at=ago(0, 40)),
 dict(tag='two-asks', channel='email', subject='Two things before Friday', from_name='Chana Klein', from_email='chana@ours.com', conversation_id='c:two',
      body='1) Please add Priya to the payroll distribution list. 2) Also the T&E report still shows the Bulk Approve button - can that be removed like we discussed?', sent_at=ago(4)),
 dict(tag='followup-on-export', channel='email', subject='RE: Nightly export drops inter-company rows', from_name='Chana Klein', from_email='chana@ours.com', conversation_id='c:export',
      body='Also - when you fix it, can you make sure the amounts keep two decimals? Last time they were rounded.', sent_at=ago(0, 30)),
 dict(tag='chat-burst-1', channel='whatsapp', subject='', from_name='Yosef Adler', from_email='', conversation_id='w:yosef', body='hey', sent_at=ago(0, 15)),
 dict(tag='chat-burst-2', channel='whatsapp', subject='', from_name='Yosef Adler', from_email='', conversation_id='w:yosef', body='did the invoice for Oak Ridge go out?', sent_at=ago(0, 14)),
 dict(tag='chat-burst-3', channel='whatsapp', subject='', from_name='Yosef Adler', from_email='', conversation_id='w:yosef', body='they are asking', sent_at=ago(0, 13)),
]
out = []
for m in MSGS:
    tag = m.pop('tag'); m['external_id'] = f'probe:{tag}'; m['source_name'] = 'probe@ours.com'
    t0 = time.time(); st, r = call('POST', '/api/ingest/push', m)
    row = {'tag': tag, 'status': st, 'secs': round(time.time() - t0, 1), 'out': r}; out.append(row)
    print(json.dumps(row, default=str)[:300], flush=True)
json.dump(out, open(r'C:\Users\UNUSSB~1\AppData\Local\Temp\claude\C--Users-unussbaum-Documents-General-Testing-taskhub\4ed300c8-8b52-4c88-8747-64a79ae5215a\scratchpad\push_out.json', 'w'), indent=1, default=str)
