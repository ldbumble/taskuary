"""THE IDLE DAY: what calls the model when nobody uses the app (the owner, 2026-11-10: "client claims he barely used it. are we leaking
tokens? this is really bad bug"). One day of an install on an AI card, its mailbox taking a realistic drip - newsletters, notices, a few
colleagues' questions, one in two of them needing a look-up - and the owner pressing nothing, with the Advisor's clock run as often as the
day runs it. A counting stand-in answers every call. Each automatic caller has a ceiling on calls and estimated tokens (characters / 4)
for the day, so a new road that calls the model on a clock, or a follow-up that wakes an agent again and again, fails here."""
import json, threading, time
from unittest import mock

from taskuary import agenttools, aiusage, apiagent, assistant, general, ingest, llm, senders
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'
PEOPLE = [('Erin Blake', 'erin@northwind.example'), ('Gail Moreno', 'gail@northwind.example'), ('Ray Colton', 'ray@northwind.example')]
NL = chr(10)


def drip(n=120, every=8):
    "The day's mail: one in eight a colleague's question (every other one needing a look-up), the rest newsletters - each its own thread."
    for i in range(n):
        q = i % every == 0
        who, at = PEOPLE[i % 3] if q else ('Payworth', 'news@vendor.example'), f'2026-11-10 {7 + i * 12 // n:02d}:{i % 60:02d}'
        body = (f'Hi Alex, are you around on Tuesday for the rota? ({i})' + (' And can you send me the figures from last month?' if i % (2 * every) == 0 else '')
                if q else f'This week at Payworth: release notes {i}. ' * 30)
        yield {'external_id': f'idle-{i}', 'channel': 'email', 'conversation_id': f'conv-{i}', 'source_name': ME, 'sent_at': at,
               'subject': f'Quick question {i}' if q else f'Payworth news {i}', 'from_email': who[1], 'from_name': who[0], 'body': body,
               **({} if q else {'sender_class': 'bulk'})}            # a list's own headers say so (categories.header_class)


# what a card agent's tools typically answer: a mail search of ten hits, a message read whole, a 20 KB file (cut at apiagent.CAP)
TOOLS = ('search_mail', 'read_message', 'file_read')
ANSWERS = {'search_mail': lambda k: NL.join(f'[m{k}-{i}] Erin Blake <erin@northwind.example> 2026-11-0{i % 9 + 1} - rota for Tuesday: '
                                            + 'the cover plan ' * 16 for i in range(10)),
           'read_message': lambda k: f'FROM Erin Blake (m{k}){NL}' + f'Line {k} of the rota thread, what was agreed and who covers which shift. ' * 55,
           'file_read': lambda k: f'rota-{k}.csv{NL}' + f'{k},Tuesday,early,Erin Blake,confirmed{NL}' * 600}


class Model:
    "The stand-in model, one per brain built: counts each call by its job and answers the cheapest way that keeps the day going."
    spent, steps = {}, 10
    def __init__(self, job): self.job = job
    def _count(self, *parts):
        c = Model.spent.setdefault(self.job, [0, 0]); c[0] += 1; c[1] += aiusage.est(*parts)
    def __call__(self, system, user, **kw):
        self._count(system, user)
        if self.job == 'triage':
            body = json.loads(user).get('body') or ''          # this mail's own words, never the thread around it
            q, hard = 'are you around' in body, 'the figures' in body
            return json.dumps({'intent': 'reply_only' if q else 'fyi', 'kind': 'task', 'why': 'w', 'title': 'Erin asks about Tuesday' if q else 'Payworth news',
                               'summary': 'Erin asks for the figures' if hard else 'Erin asks about Tuesday', 'checklist': [], 'asks_owner': q, 'sender_class': 'person' if q else 'bulk',
                               'difficulty': 'hard' if hard else 'easy'})
        return json.dumps({'lines': [], 'notes': ''})
    def chat(self, msgs, tools, max_tokens, **kw):
        self._count(msgs, tools)
        n = sum(m.get('role') == 'tool' for m in msgs[[i for i, m in enumerate(msgs) if m.get('role') == 'user'][-1]:])
        if kw.get('tool_choice') == 'none' or n >= Model.steps: return {'role': 'assistant', 'content': 'Tuesday is free; the reply is set up for your Send.'}
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{len(msgs)}', 'function': {'name': TOOLS[n % 3], 'arguments': json.dumps({'query': f'tuesday {n}'})}}]}


def _post(url, json=None, headers=None, timeout=None):
    r = mock.Mock(status_code=200); r.json.return_value = agenttools.rpc(json, lambda n, a: '', ()); return r


def _settle(base, wait=60):
    "Every thread the day set going has finished: a follow-up that wakes an agent again shows up as more calls, never as a hang."
    end = time.monotonic() + wait
    while threading.active_count() > base and time.monotonic() < end: time.sleep(0.05)


def day(s, n=120, looks=48, model=Model, every=8) -> dict:
    "{job: (calls, est. tokens)} for one idle day of `n` mails and `looks` Advisor looks."
    Model.spent = {}
    base, k = threading.active_count(), iter(range(10**6))
    # the suite's guard lets only an owner's start through; the day's starts are the router's, run here as the app runs them
    owners, toolbox = general.start_session, apiagent.taskuary_tools
    with mock.patch.object(llm, 'build_llm', side_effect=lambda store, *a, job=None, **kw: model(job or 'triage')), \
         mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'start_session', side_effect=lambda store, tid, *a, actor='owner', **kw: owners(store, tid, *a, actor='owner', **kw)), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'connector:1', 'type': 'hipaa_ai', 'label': 'HIPAA AI', 'model': ''}]), \
         mock.patch.object(general, '_selected', return_value=('connector:1', 'HIPAA AI', '')), \
         mock.patch.object(apiagent, 'taskuary_tools', side_effect=lambda tid, sid, stranger=False, post=None: toolbox(tid, sid, stranger, _post)), \
         mock.patch.object(apiagent, 'run_tool', side_effect=lambda store, tid, sid, name, a: apiagent._cut(ANSWERS.get(name, ANSWERS['search_mail'])(next(k)))):
        for m in drip(n, every):
            ingest.ingest_message(s, m, llm=model('triage')); _settle(base)
        for _ in range(looks):                       # the Advisor's report, every thirty minutes of the day
            assistant.run(s); _settle(base)
    return {j: tuple(v) for j, v in Model.spent.items()}


def store():
    s = MemoryStore()
    s.set_setting('owner_email', ME, 't'); s.set_setting('owner_name', 'Alex Doyle', 't')
    return s


# per caller, for the day above: (calls, est. tokens). Triage is one call a mail; an agent turn of ten look-ups is eleven calls - the warm
# agent's too, since it has the tools (the owner, 2026-11-13: "they should have tools"), so a quick question costs a turn, not one call;
# hard work starts the full agent. The Advisor looks where something moved - once here, since nothing does after the mail
CEILING = {'triage': (20, 320_000), 'quick_work': (8 * 12, 1_500_000), 'general': (8 * 12, 1_500_000), 'advisor': (3, 60_000)}


def test_an_idle_day_calls_the_model_only_for_what_arrived():
    spent = day(store())
    print(NL + 'IDLE DAY (calls, est. tokens):', json.dumps(spent))
    assert set(spent) <= set(CEILING), f'a caller nobody expected on an idle day: {set(spent) - set(CEILING)}'
    for job, (calls, tokens) in spent.items():
        assert calls <= CEILING[job][0] and tokens <= CEILING[job][1], (job, calls, tokens)


class Worst(Model):
    "An agent answering the worst way every time - the warm one and the full one alike: nothing at all, or the same look-up again and again."
    def chat(self, msgs, tools, max_tokens, **kw):
        self._count(msgs, tools)
        if kw.get('tool_choice') == 'none' or len(msgs) % 3: return {'role': 'assistant', 'content': ''}
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{len(msgs)}', 'function': {'name': 'search_mail', 'arguments': '{}'}}]}


def _clock(at):
    import datetime as dt
    class Clock(dt.datetime): now = classmethod(lambda cls, tz=None: cls.fromisoformat(f'2026-11-12T{at}:00'))
    return Clock


def test_the_advisor_on_its_half_hour_clock_asks_on_its_facts_not_its_clock():
    """The live shape (2026-11-12): the Advisor report on its half-hour schedule, a candidate standing, nothing arriving all night - the
    whole payload, ~50K tokens, went to the model at 00:15, 00:45 ... 07:15, each payload a few tokens off the last ("4h since anything
    happened" read "5h since"), and the scheduler's own force switched every guard off. Ages moving: no call. One new mail: one short
    call with only what changed, the last answer standing on its NO CHANGE. Run now: the whole payload, asked."""
    from taskuary import reports
    from taskuary.testing import Factory
    s, seen = store(), []
    f = Factory(s); f.task('Reconcile the August accruals', status='in_progress', UpdatedAt='2026-11-11 20:10:00')
    def brain(system, user, **k):
        if 'YOUR INSTRUCTION' not in system: return '{"verdicts": []}'           # the sent-words judge, not the look
        seen.append(user); return 'NO CHANGE' if user.startswith('YOUR LAST ANSWER') else '{"lines": [], "notes": "watching the accruals"}'
    src = assistant.source(s)
    half_hour = src['cfg'] | {'every_minutes': 30, 'cron': None}       # a half-hour clock the owner set: its guards stay
    s._exec('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(half_hour), src['SourceId']))
    cand = [{'key': 'cold:1', 'kind': 'cold', 'facts': 'Gail Moreno asked for the accruals and nothing has moved'}]
    def run(at, trigger='schedule'):
        with mock.patch.object(assistant, 'datetime', _clock(at)), mock.patch.object(assistant, 'candidates', return_value=cand):
            reports.run_one(s, s.get_source(src['SourceId']), brain, trigger)
        return json.loads(s.get_setting(reports.LAST_RUN + str(src['SourceId'])))['summary']
    with mock.patch.object(assistant, 'datetime', _clock('00:15')): before = assistant.inputs(s, cand)
    with mock.patch.object(assistant, 'datetime', _clock('00:45')): assert assistant.inputs(s, cand) != before, 'the bytes move with the clock'
    assert run('00:15') == 'Model: asked.' and len(seen) == 1 and ' since anything happened' in seen[0]
    # the first look's own note, and the weekly counts it read once, are the next look's only news: a short check, not the whole payload
    assert run('00:45') == 'Model: checked 10 changed facts - no change.' and 'watching the accruals' in seen[1] and len(seen) == 2
    assert [run(f'0{h}:{m}') for h, m in ((1, 15), (1, 45), (2, '05'))] == ['Model: nothing changed.'] * 3 and len(seen) == 2
    f.message(subject='Accruals - the August file', from_email='gail@northwind.example', from_name='Gail Moreno', body='Here it is, sorry for the wait.',
              sent_at='2026-11-12 02:05:00')
    assert run('02:15').endswith('changed facts - no change.') and len(seen) == 3
    assert seen[2].startswith('YOUR LAST ANSWER') and 'Accruals - the August file' in seen[2] and len(seen[2]) < len(seen[0]) / 4, seen[2]
    assert run('02:45') == 'Model: nothing changed.' and len(seen) == 3
    assert run('02:45', 'manual') == 'Model: asked.' and len(seen) == 4 and not seen[3].startswith('YOUR LAST ANSWER'), 'Run now asks whole'


def _at(stamp):
    import datetime as dt
    class Clock(dt.datetime): now = classmethod(lambda cls, tz=None: cls.fromisoformat(stamp))
    return Clock


def test_the_advisor_runs_twice_a_day_at_the_start_and_the_end_of_the_working_day_and_nothing_in_between():
    """The owner, 2026-11-12: "let's run the advisor twice a day in AM and PM ... that will save a bunch of tokens". Measured on his install
    that morning: six looks in under four hours at ~50K each. A day of the report clock's minute ticks, 07:00 to 20:00, last run the evening
    before: the seeded Advisor is due at 07:30 and 16:30 and at no other minute - and its card says so."""
    from datetime import datetime, timedelta
    from taskuary import reports
    s = store(); cfg = assistant.source(s)['cfg']
    last, ran, t = '2026-11-11 16:30:00', [], datetime(2026, 11, 12, 7, 0)
    while t <= datetime(2026, 11, 12, 20, 0):
        with mock.patch.object(reports, 'datetime', _at(t.isoformat())):
            if reports.is_due(cfg, last): ran.append(f'{t:%H:%M}'); last = f'{t:%Y-%m-%d %H:%M:%S}'
        t += timedelta(minutes=1)
    assert ran == ['07:30', '16:30'], ran
    assert reports.schedule_words(cfg) == 'twice a day: 7:30 and 16:30' and reports.runs_per_day(cfg) == 2
    # a morning the app was shut through: the 07:30 look runs once when it opens, never twice
    with mock.patch.object(reports, 'datetime', _at('2026-11-12T09:10:00')): assert reports.is_due(cfg, '2026-11-11 16:30:00')
    with mock.patch.object(reports, 'datetime', _at('2026-11-12T09:11:00')): assert not reports.is_due(cfg, '2026-11-12 09:10:00')


def test_both_looks_read_whole_even_when_nothing_changed_and_the_days_job_ideas_land_before_the_morning_one(monkeypatch):
    """"make sure the full advisor run happens though with the pain points etc." - the two booked looks are the full run: never "nothing
    changed", never a short check (llm.standing), whatever moved. The day's job-ideas pass (lookout: pain points, money, early warnings,
    credit) runs before the morning look - an app opened at 09:00 fires the missed 07:30 look before the Advisor's own clock ticks - and
    still once a calendar day: the afternoon look does not run it again, the next morning does."""
    from taskuary import lookout, reports
    s, order = store(), []
    src = assistant.source(s)
    def brain(system, user, **k):
        if 'YOUR INSTRUCTION' not in system: return '{"verdicts": []}'
        order.append('look'); return '{"lines": [], "notes": "watching the accruals"}'
    monkeypatch.setattr(lookout, 'CLOCK', True)
    monkeypatch.setattr(lookout, 'brain', lambda st: brain)
    monkeypatch.setattr(lookout, 'window', lambda st: ('', set()))
    monkeypatch.setattr(lookout, 'propose', lambda st, llm, user, shown: order.append('job ideas') or [])
    cand = [{'key': 'cold:1', 'kind': 'cold', 'facts': 'Gail Moreno asked for the accruals and nothing has moved'}]
    def run(stamp):
        clock = _at(stamp)
        with mock.patch.object(assistant, 'datetime', clock), mock.patch.object(lookout, '_now', clock.now), \
             mock.patch.object(assistant, 'candidates', return_value=cand):
            reports.run_one(s, s.get_source(src['SourceId']), brain, 'schedule')
        return json.loads(s.get_setting(reports.LAST_RUN + str(src['SourceId'])))['summary']
    assert run('2026-11-12T09:00:00') == 'Model: asked.' and order == ['job ideas', 'look']
    assert run('2026-11-12T16:30:00') == 'Model: asked.' and order == ['job ideas', 'look', 'look'], 'nothing moved, and it read whole'
    assert run('2026-11-13T07:30:00') == 'Model: asked.' and order[3:] == ['job ideas', 'look']


def test_a_clocked_question_is_asked_whole_only_when_much_changed_and_never_drifts():
    "llm.standing's three cases on one key: same facts, a few, many - and small checks stacked, a new day, a changed instruction, no answer."
    s, asked = store(), []
    def ask(u): asked.append(u); return 'NO CHANGE' if u.startswith('YOUR LAST ANSWER') else f'answer {len(asked)}'
    rows = [f'- TQ-{i:04d} [open] item {i} - {i}h since anything happened' for i in range(40)]
    from datetime import datetime
    go = lambda rs, at='2026-11-12 01:00', sys='S': llm.standing(s, 'k', sys, 'NOW: x\n' + '\n'.join(rs), ask, now=datetime.fromisoformat(at))
    assert go(rows) == ('answer 1', 'asked')
    assert go([r.replace(f' {i}h', f' {i + 1}h') for i, r in enumerate(rows)]) == ('answer 1', 'nothing changed')
    assert go(rows + ['- TQ-0099 [open] a new one']) == ('answer 1', 'checked 1 changed facts - no change') and len(asked) == 2
    assert 'new: - TQ-0099 [open] a new one' in asked[-1] and 'item 3 ' not in asked[-1], 'only what changed is sent'
    assert go(rows + ['- TQ-0099 [open] a new one'])[1] == 'nothing changed' and len(asked) == 2
    new = ['- TQ-0099 [open] a new one']
    assert go(rows + new + ['b'])[1].startswith('checked 1') and go(rows + new + ['b', 'c'])[1].startswith('checked 1')
    assert go(rows + ['- TQ-0099 [open] a new one', 'b', 'c', 'd']) == ('answer 5', 'rebuilt: 1 facts changed'), 'three small checks stacked: whole'
    assert go(rows[13:])[1] == 'rebuilt: 17 facts changed', 'many changed: whole'
    assert go(rows[13:], at='2026-11-13 00:15')[1] == 'rebuilt: a new day'
    assert go(rows[13:], at='2026-11-13 00:15', sys='T')[1] == 'rebuilt: its instruction changed'
    n = len(asked); none = lambda u: asked.append(u)
    assert llm.standing(s, 'k', 'T', 'other', none, now=datetime.fromisoformat('2026-11-13 00:45')) == (None, 'rebuilt: 28 facts changed')
    assert go(rows[13:], at='2026-11-13 00:15', sys='T')[1] == 'nothing changed' and len(asked) == n + 1, 'no answer is never kept'


def test_follow_ups_that_wake_an_agent_end_however_badly_it_answers():
    """A turn that said nothing is woken once, a quick look hands on to the agent, a reply owed is asked for at a run's end: none of them
    may wake another, whatever the agent does - here it answers nothing, or calls the same search, every time."""
    spent = day(store(), n=9, looks=2, model=Worst)
    print(NL + 'WORST AGENT (calls, est. tokens):', json.dumps(spent))
    assert spent['general'][0] <= 2 * 12, spent        # the two questions: a turn and its one wake each, every turn bounded


def test_past_the_days_ceiling_nothing_starts_by_itself_the_bell_says_why_and_the_owner_still_runs():
    "A leak can never again run unseen for a day: past `auto_ai_daily_calls`, automatic starts wait, the bell says so, the owner's own run."
    from taskuary import brainroute, problems
    s = store(); s.set_setting(brainroute.AUTO_CAP_KEY, '500', 't')
    s.add_brain_route({'At': time.strftime('%Y-%m-%d %H:%M:%S'), 'Job': 'general', 'Pick': 'connector:1', 'Tier': 'standard', 'Calls': 500})
    spent = day(s, n=17, looks=3)
    assert 'general' not in spent and 'quick_work' not in spent and 0 < spent['triage'][0] <= 17, spent      # mail is still read; nobody started
    assert 'advisor' not in spent and assistant.run(s, force=True)['ran'], 'the clock waits; Run now is the owner asking'
    bell = [p for p in problems.collect(s) if p['key'] == 'auto_ai_cap']
    assert len(bell) == 1 and '500' in bell[0]['detail'] and 'what you ask for still runs' in bell[0]['detail']
    assert any('daily limit' in c['Body'] for t in s.list_tasks() for c in s.list_comments(t['TaskId'])), 'the task says why no agent started'
    assert 'daily limit' not in str(ingest.auto_start_ok(s, {}, None, 'general', own=True)[1]) and assistant.run(s)['held']


def test_a_notice_like_the_last_three_is_filed_as_they_were_without_a_call_and_a_correction_hands_it_back():
    "Rung one of the ladder (the owner, 2026-11-10: \"the ai limits as much as possible to use ai\"): nothing cheaper answers? then the model."
    s = store()
    spent = day(s, n=24, looks=0)
    assert spent['triage'][0] == 3 + 3, spent           # three questions; three of the newsletter, then its verdict is reused
    rows = s._rows("SELECT VerdictJson FROM route WHERE VerdictJson LIKE '%reused%'")
    assert len(rows) == 18 and all('no AI call' in json.loads(r['VerdictJson'])['why'] for r in rows)
    s._exec("INSERT INTO correction (MessageId, Sender, Verdict, Change, CreatedAt) VALUES (1, 'news@vendor.example', 'fyi', 'task', ?)",
            (time.strftime('%Y-%m-%d %H:%M:%S'),))
    m = {**next(drip(2)), 'external_id': 'later', 'from_email': 'news@vendor.example', 'subject': 'Payworth news 99', 'sender_class': 'bulk'}
    assert ingest.reused_verdict(s, m) is None, 'the owner pressed otherwise: the model reads it again'
    assert ingest.reused_verdict(s, {**m, 'sender_class': None}) is None, 'a person writing is never filed by its look'


def test_a_notice_is_reused_only_when_its_words_are_the_same_as_the_last_three_numbers_aside():
    """The owner, 2026-11-10: "dangerous like who decides it's the same". A system that says "finished" three nights and "FAILED" on the
    fourth - in the body, under the same subject - has the failure read by the model; the next "finished" is filed as before."""
    s, calls = store(), []
    def model(system, user, **kw):
        calls.append(json.loads(user).get('body')); return json.dumps({'intent': 'fyi', 'kind': 'task', 'why': 'w', 'title': 't', 'summary': 's'})
    def mail(i, body, **kw):
        return ingest.ingest_message(s, {'external_id': f'run-{i}', 'channel': 'email', 'conversation_id': f'run-{i}', 'source_name': ME,
                                         'sent_at': f'2026-11-0{i} 02:00', 'subject': f'Nightly export 2026-11-0{i}', 'from_email': 'jobs@vendor.example',
                                         'from_name': 'Export bot', 'body': body, 'sender_class': 'automated', **kw}, llm=model)
    with mock.patch.object(senders, 'wrote_to', return_value=True):
        for i, n in ((1, 120), (2, 118), (3, 121)): mail(i, f'Nightly export finished at 02:0{i} on Tuesday, {n} rows.')
        assert len(calls) == 3
        mail(4, 'Nightly export FAILED at 02:04 on Tuesday, 0 rows.')
        assert len(calls) == 4, 'one word differs: the model reads it'
        mail(5, 'Nightly export finished at 02:05 on Thursday, 133 rows.')
        assert len(calls) == 4, 'the same words as the last three, numbers and days aside: filed as they were'
        mail(6, 'Nightly export finished at 02:06 on Friday, 140 rows.', mail_meta={'atts': 1})
        assert len(calls) == 5, 'a file rides on it: the model reads it'
        s._exec("INSERT INTO correction (MessageId, Sender, Verdict, Change, CreatedAt) VALUES (1, 'jobs@vendor.example', 'fyi', 'task', ?)",
                (time.strftime('%Y-%m-%d %H:%M:%S'),))
        mail(7, 'Nightly export finished at 02:07 on Friday, 141 rows.')
        assert len(calls) == 6, 'the owner corrected one: the model reads them again'
    assert ingest.notice_template('Re: Export 12', 'declined on Dec 3') != ingest.notice_template('Export 12', 'marked on Dec 3')


def test_a_busy_day_stays_one_judgement_per_new_kind_of_mail_and_one_look_or_turn_per_question():
    "150 mails, one in four a question, half of those needing a look-up: what the day costs, held under its own ceiling."
    spent = day(store(), n=150, looks=48, every=4)
    print(NL + 'BUSY DAY (calls, est. tokens):', json.dumps(spent))
    assert spent['triage'][0] <= 42 and spent['quick_work'][0] <= 19 * 12 and spent['general'][0] <= 19 * 12 and spent.get('advisor', (0,))[0] <= 3, spent
