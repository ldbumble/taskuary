"""A realistic invented month for the Advisor's job-ideas run (lookout.py) - Alex Doyle at Northwind (CLAUDE.md's stand-ins, nobody real).

`busy()`: ~300 messages over 60 days across a mailbox, a chat and two monitors, with what the owner asked the Advisor to find in it -
two expense tools billing for one job (Spendly and Payworth Expenses), a price rise (Spendly $1,450 -> $1,600), the same PhishGuard
invoice charged twice in five days, a Trainly renewal for 25 seats with 11 in use, the AP aging sheet he builds by hand every Monday,
a nightly export failing the same way, and a thread that drags - under newsletters, notices and ordinary chatter.
`quiet()`: a fortnight of ordinary mail with nothing in it worth his time."""
import json
from datetime import datetime, timedelta
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ALEX, ERIN, GAIL, PAULA, RAY = (f'{n}@northwind.example' for n in ('alex', 'erin', 'gail', 'paula', 'ray'))
JOB = ("## The job\n- I run finance systems at Northwind: invoice approvals, the vendor master, the AP aging and the month-end reports.\n"
       "- Erin Blake and Gail Moreno in AP depend on my weekly numbers.")
def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')


TOPICS = ('vendor onboarding', 'credit memo', 'tax form', 'GL mapping', 'cost centre', 'PO match', 'freight charge', 'bank file', 'audit sample',
          'accrual', 'card statement', 'travel claim', 'budget line', 'FX rate', 'payment run', 'remittance', 'contract scan', 'SOX control')
# ...the owner's documents at the length a real home has them, and a month of what the Advisor raised before
SOUL = '\n'.join(f'- I prefer {t} questions answered in one line, with the number first.' for t in TOPICS) * 2
LEARNED = '\n'.join(f'- [memory:m{i}] {t}: Erin owns it; Gail approves above $5,000.' for i, t in enumerate(TOPICS))


def _base(full=True):
    s = MemoryStore()
    job = JOB + ('\n' + '\n'.join(f'- I keep the {t} process running.' for t in TOPICS) * 3 if full else '')
    s.set_setting('owner_email', ALEX, 'test'); s.save_doc('job', job, 'test')
    if full:
        s.save_doc('soul', SOUL, 'test'); s.save_doc('learned', LEARNED, 'test')
        for i, t in enumerate(TOPICS):
            s.upsert_idea({'key': f'idea:old-{i}', 'kind': 'pitch', 'text': f'The {t} step waits on one approver most weeks', 'action': {'type': 'note'}}, ago(days=20 + i))
    return s, Factory(s)


def busy(noise: int = 1):
    "`noise`: how many times over the colleagues' daily chatter comes - 1 is ~550 messages, 6 is a mailbox the size a live home holds."
    s, f = _base()
    ids = {}
    m = lambda **k: f.message(source_name=k.pop('src', 'Outlook'), **k)
    ids['spendly'] = [m(from_email='billing@spendly.example', from_name='Spendly', subject='Your Spendly receipt',
                        body=f'Spendly Team plan, 40 seats. Amount charged: ${a} for the month. Thank you.', sent_at=ago(days=d))
                      for d, a in ((58, '1,450.00'), (28, '1,600.00'))]
    ids['payworth'] = [m(from_email='billing@payworth.example', from_name='Payworth', subject='Payworth Expenses invoice',
                         body='Payworth Expenses, 40 seats, expense reports and receipts. Total due: $1,450.00. Renews on the 1st.', sent_at=ago(days=d))
                       for d in (55, 25)]
    ids['phish'] = [m(from_email='ar@phishguard.example', from_name='PhishGuard', subject='Invoice INV-2207',
                      body='PhishGuard awareness training, invoice INV-2207. Amount due: $380.00', sent_at=ago(days=d)) for d in (14, 9)]
    ids['trainly'] = m(from_email='renewals@trainly.example', from_name='Trainly', subject='Your Trainly renewal is coming up',
                       body='Your Trainly plan renews on the 15th: 25 seats at $16 per seat per month, $4,800 for the year.', sent_at=ago(days=6))
    ids['trainly_use'] = m(from_email='reports@trainly.example', from_name='Trainly', src='Trainly', channel='report', subject='Trainly monthly usage',
                           body='Active learners this month: 11 of 25 seats. Courses completed: 14.', sent_at=ago(days=4))
    # ...the sheet he builds by hand every Monday, and what AP writes back
    ids['aging'] = [m(direction='out', status='context', subject='AP aging - this week', body='Attached is this week\'s AP aging, pulled from the ledger and the vendor master by hand.',
                      RecipientsJson=json.dumps({'to': [ERIN, GAIL]}), sent_at=ago(days=7 * w + 1, hours=2)) for w in range(8)]
    for w in range(0, 8, 2):
        m(from_email=ERIN, from_name='Erin Blake', subject='Re: AP aging - this week', body='Thanks - can you add the vendor column again? It was missing.',
          sent_at=ago(days=7 * w + 1))
    ids['fail'] = [m(from_email='jobs@northwind.example', from_name='Ledger jobs', src='Ledger monitor', channel='report', subject='Nightly ledger export failed',
                     body='HTTP 403: the service account password expired', sent_at=ago(days=d, hours=3)) for d in range(1, 7)]
    ids['drag'] = [m(from_email=a if a != ALEX else None, from_name=n, direction='out' if a == ALEX else 'in', status='context' if a == ALEX else 'routed',
                     subject='Vendor master clean-up', conversation_id='vm', body=f'{n}: still waiting on the duplicate vendor list.', sent_at=ago(days=d),
                     **({'RecipientsJson': json.dumps({'to': [RAY]})} if a == ALEX else {}))
                   for d, a, n in ((26, RAY, 'Ray Colton'), (22, ALEX, 'Alex Doyle'), (18, RAY, 'Ray Colton'), (14, PAULA, 'Paula Vance'),
                                   (10, ALEX, 'Alex Doyle'), (6, RAY, 'Ray Colton'), (2, RAY, 'Ray Colton'))]
    # ...and the month around it: newsletters, notices, chatter
    for d in range(60):
        m(from_email='news@vendor.example', from_name='Finance Weekly', subject=f'Finance Weekly #{d}', body='Five things in finance this week. Read more.', sent_at=ago(days=d, hours=5))
        if d % 2 == 0: m(from_email='noreply@northwind.example', from_name='IT Notices', subject=f'Maintenance window {d}', body='Planned maintenance tonight 22:00-23:00.',
                         sent_at=ago(days=d, hours=7))
        m(from_email=PAULA, from_name='Paula Vance', channel='teams', src='Teams', subject='', body=f'Lunch at noon? ({d})', sent_at=ago(days=d, hours=4))
        if d % 3 == 0: m(from_email=GAIL, from_name='Gail Moreno', subject=f'Approval {d}', body=f'Please approve invoice {1000 + d} when you can.', sent_at=ago(days=d, hours=6))
        if d % 5 == 0: m(from_email='marcus@northwind.example', from_name='Marcus Reed', subject=f'Re: Q{d % 4 + 1} plan', body='Looks fine to me.', sent_at=ago(days=d, hours=1))
        for k, (a, n) in enumerate(((ERIN, 'Erin Blake'), (GAIL, 'Gail Moreno'), (RAY, 'Ray Colton'), ('omar@northwind.example', 'Omar Keller')) * noise):
            t = TOPICS[(d * 4 + k) % len(TOPICS)] + (f' {k // 4}' if k >= 4 else '')
            m(from_email=a, from_name=n, subject=f'{t} for {n.split()[0]}', body=f'Quick one on the {t}: can you check line {d + k} against the ledger? '
              'The usual numbers look a little off this time and I want to be sure before we close.', sent_at=ago(days=d, hours=2 + k))
            if (d + k) % 3 == 0: m(direction='out', status='context', subject=f'Re: {t} for {n.split()[0]}', body=f'Checked - line {d + k} is right.',
                                   RecipientsJson=json.dumps({'to': [a]}), sent_at=ago(days=d, hours=1 + k))
    return s, ids


def quiet():
    s, f = _base(full=False)
    for d in range(14):
        f.message(from_email='news@vendor.example', from_name='Finance Weekly', subject=f'Finance Weekly #{d}', body='Five things in finance this week.', sent_at=ago(days=d, hours=5))
    return s
