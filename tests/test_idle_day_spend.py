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
        if self.job == 'quick_work':                # the figures are looked up: the one call says so and hands on
            up = 'for the figures' in user.split('QUICK WORK:')[0][-300:]
            return json.dumps({'report': 'Tuesday is free.', 'draft': None if up else 'Yes, I am around Tuesday.', 'question': None, 'done': False,
                               'escalate': up, 'why': 'the figures need looking up' if up else ''})
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


# per caller, for the day above: (calls, est. tokens). Triage is one call a mail; an agent turn of ten look-ups is eleven calls; the
# Advisor looks where something moved - once here, since nothing does after the mail
CEILING = {'triage': (20, 320_000), 'quick_work': (16, 130_000), 'general': (8 * 12, 1_500_000), 'advisor': (3, 60_000)}


def test_an_idle_day_calls_the_model_only_for_what_arrived():
    spent = day(store())
    print(NL + 'IDLE DAY (calls, est. tokens):', json.dumps(spent))
    assert set(spent) <= set(CEILING), f'a caller nobody expected on an idle day: {set(spent) - set(CEILING)}'
    for job, (calls, tokens) in spent.items():
        assert calls <= CEILING[job][0] and tokens <= CEILING[job][1], (job, calls, tokens)


class Worst(Model):
    "An agent answering the worst way every time: nothing at all, or the same look-up again and again; a quick look that always hands on."
    def __call__(self, system, user, **kw):
        if self.job != 'quick_work': return super().__call__(system, user, **kw)
        self._count(system, user)
        return json.dumps({'report': '', 'draft': None, 'question': None, 'done': False, 'escalate': True, 'why': 'needs a look'})
    def chat(self, msgs, tools, max_tokens, **kw):
        self._count(msgs, tools)
        if kw.get('tool_choice') == 'none' or len(msgs) % 3: return {'role': 'assistant', 'content': ''}
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{len(msgs)}', 'function': {'name': 'search_mail', 'arguments': '{}'}}]}


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
    assert spent['triage'][0] <= 42 and spent['quick_work'][0] <= 38 and spent['general'][0] <= 19 * 12 and spent.get('advisor', (0,))[0] <= 3, spent
