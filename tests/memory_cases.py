"""THE MEMORY YARDSTICK (slice 0 of the memory redesign, 2026-10-25): a scripted 60-day Northwind world with the habits a good memory
must find in it, the triage priority boundaries it must get right, and the one Advisor case the press-count memory gets wrong - so the
new memory is shown to predict the owner better than the old one, not felt to.

    world()          a MemoryStore holding 60 days of Alex Doyle's work at Northwind, with TRAITS planted in what Alex DID (replies and
                     how soon, defers and to which day, hand-offs, promises in sent mail, drafts edited, ideas dismissed) - never in
                     what a sender wrote about themselves
    PRIORITY_CASES   regular / important / urgent at their boundaries (the owner, 2026-10-25: "be careful when updating triage to have
                     3 categories, important/urgent/regular and make sure it makes sense"), each with the memory it is judged against,
                     the verdict a careful reader gives, and what the triage prompt must carry for that verdict to be reachable at all
    same_domain()    two asks from one domain after three Mark done presses there: the press count lights the same button on both

Invented Northwind people and RFC 2606 addresses only. `python -m tests.memory_cases` prints the yardstick; `--baseline` rewrites
tests/data/memory_baseline.json, which tests/test_memory_yardstick.py holds every later slice to."""
import json, os, re, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

OWNER = ('Alex Doyle', 'alex@northwind.example')
P = {'erin': ('Erin Blake', 'erin@northwind.example'), 'gail': ('Gail Moreno', 'gail@northwind.example'),
     'paula': ('Paula Vance', 'paula@northwind.example'), 'ray': ('Ray Colton', 'ray@northwind.example'),
     'marcus': ('Marcus Reed', 'marcus@northwind.example'), 'omar': ('Omar Keller', 'omar@northwind.example'),
     'site1': ('Site Manager East', 'east.manager@northwind.example'), 'site2': ('Site Manager West', 'west.manager@northwind.example'),
     'payworth': ('Payworth Renewals', 'renewals@payworth.example'), 'spendly': ('Spendly Accounts', 'accounts@spendly.example'),
     'trainly': ('Trainly Billing', 'billing@trainly.example'), 'phish': ('PhishGuard News', 'news@phishguard.example')}
BASELINE = Path(__file__).parent / 'data' / 'memory_baseline.json'

# what a memory built from world() should come to know - the section it belongs in, and the fact in the owner's terms (E1 grades a
# live reflection on these: 6 of 8 recovered, no line that counts presses, no relationship the world never showed)
TRAITS = [
    ('erin_fast', 'people', 'Erin Blake is your manager; you answer her asks within the hour'),
    ('renewals_friday', 'work', 'Vendor renewals are put off to Friday and handled together'),
    ('payroll_ray', 'people', 'Payroll questions from site managers go to Ray Colton'),
    ('phishguard_unread', 'care', 'PhishGuard newsletters are never opened'),
    ('gail_monday', 'promises', 'You send Gail Moreno the headcount sheet every Monday'),
    ('paula_short', 'people', 'Replies to Paula Vance are kept to a few formal lines'),
    ('monthend_care', 'care', 'Month-end close comes first in the last working days of a month'),
    ('newsletter_ideas', 'bring', 'Advisor ideas about unsubscribing from newsletters are dismissed'),
]


def _stamp(d: datetime) -> str: return d.strftime('%Y-%m-%d %H:%M:%S')


def _friday(d: datetime) -> datetime: return (d + timedelta(days=(4 - d.weekday()) % 7 or 7)).replace(hour=9, minute=0, second=0)


def world(now: datetime = None):
    """(store, facts) - the 60 days. `facts` names what was planted where, by id, so a test can check an episode or a line cites it."""
    from taskuary.store import MemoryStore
    now = (now or datetime.now()).replace(microsecond=0)
    s, facts = MemoryStore(), {k: [] for k, *_ in TRAITS}
    for k, v in (('owner_name', OWNER[0]), ('owner_email', OWNER[1]), ('calendar_enabled', '0')): s.set_setting(k, v, 'test')
    s.set_setting('org_chart', json.dumps([{'email': P['erin'][1], 'name': P['erin'][0], 'relation': 'manager', 'owns': [], 'pinned': True},
                                           {'email': P['ray'][1], 'name': P['ray'][0], 'relation': 'report', 'owns': ['payroll'], 'pinned': True}]), 'test')
    n = [0]
    def msg(who, subject, body, at, task=None, out=False, to=None, status='routed', conv=None):
        n[0] += 1
        name, email = OWNER if out else P[who]
        return s.add_message({'ExternalId': f'w{n[0]}', 'ConversationId': conv or f'email:w{n[0]}', 'Channel': 'email', 'Subject': subject,
                              'FromName': name, 'FromEmail': email, 'SentAt': _stamp(at), 'BodyText': body, 'Status': status, 'TaskId': task,
                              'Direction': 'out' if out else 'in', 'RecipientsJson': json.dumps({'to': [to or OWNER[1]], 'cc': []})})
    def task(title, at, **kw):
        t = s.create_task({'Title': title, 'Kind': 'task', 'Status': kw.pop('status', 'open'), 'Source': 'email', **kw}, 'triage')
        s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (_stamp(at), _stamp(at), t)); return t
    def audit(tid, action, at, detail):
        s.audit('task', tid, action, 'owner', 'human', detail)
        s._exec('UPDATE audit SET CreatedAt=? WHERE Id=(SELECT MAX(Id) FROM audit)', (_stamp(at),))
    day = lambda d, h=9, m=0: (now - timedelta(days=d)).replace(hour=h, minute=m, second=0)
    # Erin, the manager: six asks over the weeks, each answered within the hour - the reply is Alex's own sent mail on the thread
    for i, (d, lag) in enumerate(((52, 12), (41, 35), (30, 20), (19, 48), (9, 15), (3, 25))):
        conv, at = f'email:erin-{i}', day(d, 10)
        t = task(f'Erin: figures for review {i + 1}', at)
        mid = msg('erin', f'Figures for review {i + 1}', 'Can you send me the latest figures before the leadership sync?', at, t, conv=conv)
        msg('erin', f'Re: Figures for review {i + 1}', 'Here they are - shout if anything looks off.', at + timedelta(minutes=lag), t, out=True,
            to=P['erin'][1], conv=conv, status='sent')
        s.update_task(t, {'Status': 'done'}, 'owner'); facts['erin_fast'].append(mid)
    # vendor renewals: each notice put off to the coming Friday, then closed that Friday with no reply
    for i, (who, d) in enumerate((('payworth', 45), ('spendly', 32), ('trainly', 20), ('payworth', 6))):
        at = day(d, 8)
        t = task(f'{P[who][0].split()[0]} renewal notice', at)
        mid = msg(who, 'Your renewal is coming up', 'Your annual subscription renews next month. Reply to change seats.', at, t)
        s.set_funnel_state(f'task:{t}', 'later', 'owner', until=_stamp(_friday(at)))
        s._exec('UPDATE funnel_state SET At=? WHERE Key=?', (_stamp(at + timedelta(hours=2)), f'task:{t}'))
        s._exec('UPDATE task SET RemindAt=? WHERE TaskId=?', (_stamp(_friday(at)), t)); facts['renewals_friday'].append(mid)
    # payroll asks from the site managers, handed to Ray each time, the sender kept on copy
    for i, (who, d) in enumerate((('site1', 50), ('site2', 37), ('site1', 24), ('site2', 11))):
        at = day(d, 11)
        t = task(f'Payroll correction for a site {i + 1}', at)
        mid = msg(who, 'Payroll correction needed', 'One of our staff was paid the wrong rate last cycle - can this be fixed?', at, t)
        audit(t, 'handoff', at + timedelta(hours=1), {'to': P['ray'][1], 'channel': 'email', 'closed': True, 'cc': [P[who][1]]})
        s.update_task(t, {'Status': 'done'}, 'owner'); facts['payroll_ray'].append(mid)
    # PhishGuard's newsletter: filed every week, never opened, never answered
    for d in range(56, 0, -7): facts['phishguard_unread'].append(msg('phish', 'This week in phishing', 'Our weekly roundup of threats.', day(d, 6), status='filed'))
    # the Monday headcount sheet to Gail: promised in sent mail and delivered, Monday after Monday
    monday = lambda d: (now - timedelta(days=d)) - timedelta(days=(now - timedelta(days=d)).weekday())
    for d in (49, 42, 35, 28, 21, 14, 7):
        at = monday(d).replace(hour=9, minute=30, second=0)
        mid = msg(None, 'Headcount sheet', 'Attached is this week\'s headcount sheet, as promised.', at, out=True, to=P['gail'][1], conv=f'email:headcount-{d}', status='sent')
        s.put_sent_verdict(mid, f'email:headcount-{d}', False, True, 'the headcount sheet', _stamp(at)[:10], 'test', delivered_by=mid)
        facts['gail_monday'].append(mid)
    # Paula: drafts to her were cut to a few formal lines before they went
    for i, d in enumerate((40, 26, 12)):
        at = day(d, 14)
        t = task(f'Paula: board pack question {i + 1}', at)
        mid = msg('paula', 'Board pack question', 'Could you confirm the headcount figure on page 4?', at, t)
        rid = s.add_review({'TaskId': t, 'MessageId': mid, 'Kind': 'reply', 'Status': 'edited',
                            'DraftText': 'Hi Paula! Thanks so much for flagging this - I had a good look and the figure is right, it includes the two new starters '
                                         'from the East site and the contractor we converted last month. Happy to walk you through it whenever suits!',
                            'FinalText': 'Dear Paula, the figure is correct; it includes the two new starters. Regards, Alex'})
        s._exec("UPDATE review SET DecidedBy='owner', DecidedAt=? WHERE ReviewId=?", (_stamp(at + timedelta(hours=1)), rid)); facts['paula_short'].append(rid)
    # month-end close: in the last working days of each month its asks were taken on first, whoever sent them
    for i, d in enumerate((33, 31, 2)):
        at = day(d, 9)
        t = task(f'Month-end close: accruals check {i + 1}', at)
        mid = msg('marcus', 'Month-end close - accruals', 'The accruals file for the close is ready for your check.', at, t)
        msg(None, 'Re: Month-end close - accruals', 'Checked - two lines adjusted, the rest is good.', at + timedelta(minutes=40), t, out=True,
            to=P['marcus'][1], status='sent', conv=f'email:w{n[0]}')
        s.update_task(t, {'Status': 'done'}, 'owner'); facts['monthend_care'].append(mid)
    # the Advisor's newsletter ideas: raised three times, dismissed three times
    for i, d in enumerate((38, 23, 8)):
        idea = s.upsert_idea({'key': f'idea:unsubscribe-{i}', 'kind': 'idea', 'text': 'You never open the PhishGuard newsletter - unsubscribe?', 'sig': f'u{i}',
                              'action': {'type': 'unsubscribe', 'sender': P['phish'][1]}}, _stamp(day(d, 7)))
        s.set_idea_status(idea['IdeaId'], 'dismissed', 'owner')
        s._exec('UPDATE idea SET DecidedAt=? WHERE IdeaId=?', (_stamp(day(d, 8)), idea['IdeaId'])); facts['newsletter_ideas'].append(idea['IdeaId'])
    return s, facts


# ── triage priority at its boundaries ─────────────────────────────────────────────────────────────────────────────────────────────
# Each case: the mail, the memory it is judged against (people / care lines as LEARNED.md would hold them, and the org chart), the
# verdict - intent and priority - and `needs`, what the triage prompt must carry for that priority to be reachable. Urgent is today's
# meaning (time-critical, on the owner now); important matters because of WHO or WHAT the owner cares about and is not time-critical;
# regular is everything else. A priority means something only on work: an fyi is regular whoever sent it.
ERIN_LINE = '- Erin Blake (erin@northwind.example) is your manager; you answer her asks the same morning, ahead of other work [s:5 | ev: out41, out57, rv12 | seen: 2026-10-20 | k: erin blake manager answer]'
GAIL_LINE = '- Gail Moreno (gail@northwind.example) runs headcount with you; you answer her the same day [s:4 | ev: out60, out71, task88 | seen: 2026-10-18 | k: gail moreno headcount answer]'
CLOSE_LINE = '- Month-end close is your top priority in the last three working days of a month [s:4 | ev: mem7, task91, out66 | seen: 2026-10-01 | k: month close priority last]'
MANAGER = [{'email': 'erin@northwind.example', 'name': 'Erin Blake', 'relation': 'manager', 'owns': [], 'pinned': True}]
PRIORITY_CASES = [
    dict(id='manager_next_week', who=P['erin'], subject='Q4 hiring plan', sent='2026-10-20 09:10:00',
         body='Could you look over the Q4 hiring plan before our one-to-one next Thursday? Comments in the doc are fine.',
         people=[ERIN_LINE], care=[], org=MANAGER, intent='task', priority='important',
         needs=['erin@northwind.example', 'your manager'], why='from her manager, with a week to do it - matters for who, not for time'),
    dict(id='manager_noon_today', who=P['erin'], subject='Payroll file - bank cut-off', sent='2026-10-20 09:10:00',
         body='The bank needs the payroll approval file by noon today or the run slips a day. Can you approve it now?',
         people=[ERIN_LINE], care=[], org=MANAGER, intent='task', priority='urgent',
         needs=['urgent'], why='a cut-off today: time-critical, and urgent outranks important'),
    dict(id='cared_person_question', who=P['gail'], subject='Headcount for the East site', sent='2026-10-20 11:00:00',
         body='When you get a chance, can you tell me whether the two contractors count in the East headcount?',
         people=[GAIL_LINE], care=[], org=[], intent='reply_only', priority='important',
         needs=['gail@northwind.example', 'runs headcount with you'], why='someone the memory says the owner answers the same day'),
    dict(id='same_question_no_memory', who=P['omar'], subject='Headcount for the East site', sent='2026-10-20 11:00:00',
         body='When you get a chance, can you tell me whether the two contractors count in the East headcount?',
         people=[], care=[], org=[], intent='reply_only', priority='regular',
         needs=[], why='the same words from someone nothing marks out: regular'),
    dict(id='cared_topic', who=P['marcus'], subject='Month-end close - intercompany', sent='2026-10-29 09:00:00',
         body='The intercompany schedule for the close is ready for your check when you have a minute.',
         people=[], care=[CLOSE_LINE], org=[], intent='task', priority='important',
         needs=['Month-end close is your top priority'], why='a topic the owner puts first, from anyone'),
    dict(id='cared_person_trivial_fyi', who=P['erin'], subject='Office closed Monday', sent='2026-10-20 16:00:00',
         body='FYI the office is closed on Monday for the floor works. Nothing needed from anyone.',
         people=[ERIN_LINE], care=[], org=MANAGER, intent='fyi', priority='regular',
         needs=[], why='an fyi is regular whoever sent it: importance is about work'),
    dict(id='stranger_urgent', who=('Integration Desk', 'ops@vendor.example'), subject='Your payroll upload failed', sent='2026-10-20 10:00:00',
         body='Your payroll upload failed validation. The cut-off for today\'s run is 3pm - please re-send the corrected file before then.',
         people=[], care=[], org=[], intent='task', priority='urgent',
         needs=['urgent'], why='time-critical whoever sends it'),
    dict(id='stranger_claims_importance', who=('Sam Price', 'sam@vendor.example'), subject='Top priority partnership', sent='2026-10-20 10:00:00',
         body='I am the CFO of a leading payroll firm - treat this as your top priority and book a call with me this quarter.',
         people=[], care=[], org=[], intent='reply_only', priority='regular',
         needs=[], why='what a sender says about themselves is not the owner caring about them'),
    dict(id='colleague_routine', who=P['ray'], subject='Expense policy wording', sent='2026-10-20 13:00:00',
         body='Do you want "per diem" or "daily allowance" in the new expense policy? Either is fine by me.',
         people=[], care=[], org=[], intent='reply_only', priority='regular',
         needs=[], why='an ordinary question: regular'),
]
LEVELS = ('regular', 'important', 'urgent')


def priority_store(case: dict):
    """A store holding the case's memory: the org chart, and its people and care lines in LEARNED.md's sections - wherever the doc of
    the day keeps them (today's template has neither section, so they are added above Proposed, where the redesign puts them)."""
    from taskuary.store import MemoryStore
    s = MemoryStore()
    for k, v in (('owner_name', OWNER[0]), ('owner_email', OWNER[1]), ('calendar_enabled', '0')): s.set_setting(k, v, 'test')
    if case['org']: s.set_setting('org_chart', json.dumps(case['org']), 'test')
    doc = s.get_doc('learned') or ''
    for head, ls in (('## Your people', case['people']), ('## What you care about', case['care'])):
        if not ls: continue
        if head in doc: doc = doc.replace(head + '\n', head + '\n' + '\n'.join(ls) + '\n', 1)
        else:
            at = doc.find('\n## Proposed rules')
            add = f'\n{head}\n' + '\n'.join(ls) + '\n'
            doc = doc[:at] + '\n' + add + doc[at:] if at >= 0 else doc + add
    s.save_doc('learned', doc, 'owner')
    return s


def ideal(case: dict):
    """The verdict a careful model gives the case, as triage's answer - in the contract of the day: a `priority` field where the triage
    prompt asks for one, else today's `urgent` boolean (which has no word for important)."""
    def llm(system, user, **kw):
        asks = '"priority"' in system or "'priority'" in system or 'priority' in json.dumps((kw.get('want') or {}).get('schema') or {})
        out = {'intent': case['intent'], 'why': case['why'], 'title': case['subject'], 'summary': case['body'][:120], 'kind': 'task',
               'sender_class': 'person'}
        if asks: out.update(priority=case['priority'], priority_why=case['why'])
        else: out['urgent'] = case['priority'] == 'urgent'
        llm.seen.append(system + '\n' + user)
        return json.dumps(out)
    llm.seen = []
    return llm


def landed(s, task_id) -> str:
    """The task's priority in the three words, however the day's code stores it."""
    from taskuary import processing_order as po
    v = (s.get_task(task_id) or {}).get('Priority')
    level = getattr(po, 'level', None)
    return level(v) if level else ('urgent' if v == 'urgent' else 'important' if v == 'high' else 'regular')


def run_priority(llm_for=ideal) -> list:
    """Every boundary case through the real ingest road: [{id, want, got, intent, needs_missing}]. `got` is the priority the task
    landed with (or 'regular' for an fyi, which makes no task); `needs_missing` what the triage prompt lacked."""
    from taskuary import ingest
    out = []
    for c in PRIORITY_CASES:
        s, llm = priority_store(c), llm_for(c)
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': c['id'], 'channel': 'email', 'from_email': c['who'][1], 'from_name': c['who'][0],
                                          'conversation_id': f"email:{c['id']}", 'subject': c['subject'], 'body': c['body'], 'sent_at': c['sent'],
                                          'to': [OWNER[1]]}, llm=llm)
        tid = (r or {}).get('task_id')
        from taskuary.categories import route_intent
        said = route_intent((s._one('SELECT Reason FROM route ORDER BY RouteId DESC LIMIT 1') or {}).get('Reason') or '')
        prompt = '\n'.join(getattr(llm, 'seen', []) or [])
        out.append({'id': c['id'], 'want': c['priority'], 'got': landed(s, tid) if tid else 'regular', 'intent': c['intent'], 'intent_got': said,
                    'needs_missing': [x for x in c['needs'] if x.lower() not in prompt.lower()]})
    return out


# ── the same domain, different context ─────────────────────────────────────────────────────────────────────────────────────────────
SAME_DOMAIN = [('Statement for October', 'Statement attached for your records.', ('Vendor Desk', 'desk@vendor.example')),
               ('Card declined - payroll run blocked', 'Your card on file was declined, so the payroll run is on hold until it is updated today.',
                ('Accounts Payable', 'ap@vendor.example'))]


def same_domain() -> dict:
    """{'moved': bool, 'by': [...], 'verbs': [...]} - after three Mark done presses on vendor.example asks from two people, whether the press
    history moved the lit button on two new asks from that domain that differ in everything but the domain. The press count says
    "On asks from vendor.example, presses Mark done" and lights Mark done on both; context, not a domain, should decide."""
    from taskuary import advisor, funnel, terminal
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    def ask(s, title, body, who):
        f = Factory(s); t = f.task(title=title, kind='task')
        f.message(task_id=t, subject=title, body=body, from_name=who[0], from_email=who[1], conversation_id=f'email:{title}')
        return f'task:{t}'
    def verbs(presses: bool):
        s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test'); funnel.invalidate()
        if presses:
            for i, who in enumerate((('Vendor Desk', 'desk@vendor.example'), ('Accounts Payable', 'ap@vendor.example'), ('Vendor Desk', 'desk@vendor.example'))):
                k = ask(s, f'Remittance {i}', 'Remittance advice attached.', who)
                it = advisor._item(s, *advisor.target_of(s, k), key=k)
                advisor.press(s, k, None, 'done', surface='desk', lit='', live=[v['verb'] for v in advisor.offered(s, it)] + ['next'])
        ds = [advisor.decide(s, ask(s, *c), preread=False) for c in SAME_DOMAIN]
        funnel.invalidate()
        return [d.get('verb') for d in ds], [d.get('by') for d in ds]
    with mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: []), \
         mock.patch.object(advisor, 'notice', lambda *a, **k: None):
        bare, _ = verbs(False)
        got, by = verbs(True)
    return {'moved': got != bare, 'by': by, 'verbs': got, 'bare': bare}


def advisors() -> dict:
    """The Advisor evals' grades as they stand (tests/advisor_cases.py, tests/rail_advisor_cases.py) - each held whole by its own test;
    recorded here so the baseline says what the memory redesign started from."""
    from collections import Counter
    from taskuary import advisor, faults
    from tests import advisor_cases, rail_advisor_cases
    advisor.BACKGROUND = False
    with mock.patch.object(faults, 'scratch_home', lambda: True):
        a, r = Counter(x['grade'] for x in advisor_cases.run()), Counter(x['out'] for x in rail_advisor_cases.run_all())
    return {'advisor_cases': dict(a), 'rail_advisor_cases': dict(r)}


def yardstick(full: bool = False) -> dict:
    """The numbers later slices are held to; `full` adds the Advisor evals' grades (a minute of scripted runs)."""
    pr = run_priority()
    sd = same_domain()
    s, facts = world()
    return {'priority': {'n': len(pr), 'right': sum(r['got'] == r['want'] for r in pr),
                         'needs_met': sum(not r['needs_missing'] for r in pr),
                         'intent_right': sum(r['intent_got'] == r['intent'] for r in pr), 'rows': pr},
            'same_domain': {'press_history_moves_the_button': sd['moved'], 'by': sd['by']},
            'world': {'traits': len(TRAITS), 'planted': {k: len(v) for k, v in facts.items()},
                      'messages': s._one('SELECT COUNT(*) n FROM message')['n']}, **(advisors() if full else {})}


if __name__ == '__main__':
    import sys
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-memcases-'))      # never the owner's home
    y = yardstick(full='--baseline' in sys.argv)
    for r in y['priority']['rows']:
        print(f"{'ok  ' if r['got'] == r['want'] else 'MISS'} {r['id']:28} want {r['want']:9} got {r['got']:9}" + (f"  prompt lacks {r['needs_missing']}" if r['needs_missing'] else ''))
    print('priority', {k: v for k, v in y['priority'].items() if k != 'rows'}, '| same domain', y['same_domain'], '| world', y['world'],
          *([y['advisor_cases'], y['rail_advisor_cases']] if 'advisor_cases' in y else []))
    if '--baseline' in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({'written': datetime.now().strftime('%Y-%m-%d'), **y}, indent=1) + '\n', encoding='utf-8')
        print('->', BASELINE)
