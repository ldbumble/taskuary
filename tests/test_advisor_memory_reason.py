"""THE MEMORY'S REASON REACHES THE STRIP, AND ONLY WHERE THE ITEM IS ABOUT IT (the live memory A/B, 2026-10-26). The Advisor read LEARNED.md
and used it - "You answer Erin the same day", "Paula takes W-9s now" - and the strip never said it: a model agreeing with the lit button had
its line dropped. A state the rule decided alone never read the memory at all, colleagues tied in the people lines' ranking, and a hand-off
count stood over another verb. Invented Northwind people only (CLAUDE.md)."""
import json
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, learn, learned_cut as lc, rulebook, terminal, usual
from taskuary.testing import Factory
from tests import memory_cases as C

ERIN = C.ERIN_LINE
GAIL_PROMISE = '- You told Gail Moreno (gail@northwind.example) the headcount sheet reaches her every Monday [s:4 | ev: out60, out71 | seen: 2026-10-18 | k: gail monday sheet]'
RAY = '- Ray Colton (ray@northwind.example) runs payroll for you; you hand payroll asks to him [s:5 | ev: out12, out13 | seen: 2026-10-19 | k: ray payroll]'


@pytest.fixture
def w():
    with mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: []), \
         mock.patch.object(advisor, 'notice', lambda *a, **k: None):
        s, facts = C.world(); funnel.invalidate()
        yield s, facts
        funnel.invalidate()


def plant(s, slug, raw):
    s.save_doc('learned', learn._under(s.get_doc('learned') or '', lc.SECTIONS[slug], raw), 'reflect')


def ask(s, who, title, body, hours=0.3):
    f, at = Factory(s), (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    t = f.task(title=title, kind='task')
    f.message(task_id=t, subject=title, body=body, from_name=C.P[who][0], from_email=C.P[who][1], conversation_id=f'email:{title}', sent_at=at)
    funnel.invalidate()
    return t


def judged(s, t, answer: dict) -> tuple:
    """(decision, prompt) - the model's answer through the real judge, then the one decision every surface reads."""
    seen = []
    def brain(system, user, **kw): seen.append(user); return json.dumps(answer)
    advisor.judge(s, advisor.SHOWN, 'task', t, advisor.revision(s, 'task', t), tier=2, llm=brain, key=f'task:{t}')
    return advisor.decide(s, f'task:{t}', preread=False), (seen[-1] if seen else '')


def test_an_agreeing_model_says_its_memory_reason_in_one_line(w):
    s, _ = w
    plant(s, 'people', ERIN)
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    cite = lc.cite_of('erin blake manager answer')
    d, prompt = judged(s, t, {'verb': 'reply', 'line': 'You answer Erin the same morning.', 'evidence': [cite]})
    assert f'(id {cite})' in prompt, 'each memory line the model reads carries the id it cites'
    assert (d['state'], d['verb'], d['by'], d['line']) == ('asked', 'reply', 'model', 'You answer Erin the same morning.'), d
    assert len(d['line']) <= 60 and d['evidence'] == [cite]
    # ...and Why? says what the line rests on in words, never the id
    note = advisor.notes(s, f'task:{t}')[0]
    assert note['evidence'][0]['label'].startswith('Erin Blake (erin@northwind.example) is your manager'), note


def test_an_agreeing_line_on_the_items_own_facts_still_goes(w):
    """Ruling 1 stands: agreeing, a sentence resting on nothing the memory knows is the obvious button explained - it is not said, and
    with no fact left for it the button is not lit either (NO DEFAULT VERB, the owner, 2026-10-28)."""
    s, _ = w
    plant(s, 'people', ERIN)
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Erin wants the agenda checked.', 'evidence': []})
    assert (d['verb'], d['by'], d['line']) == (None, 'rule', ''), d
    # ...while an agreeing line that IS a fact of a kind (late, the same ask, a hand-off...) is the lit button's reason
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Erin asked twice since Monday.', 'evidence': [], 'kind': 'late'})
    assert (d['verb'], d['by'], d['line']) == ('reply', 'model', 'Erin asked twice since Monday.'), d


def test_a_differing_verbs_long_line_is_cut_at_a_word(w):
    """The model's verb over the rule's keeps its line, cut to 64 at a word: "...and is waiting on y" read as a slip (the sweep, 2026-10-27)."""
    s, _ = w
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    long = 'Erin already has the agenda from the planning group and nobody is waiting on you'
    d, _ = judged(s, t, {'verb': 'close', 'line': long, 'evidence': []})
    assert (d['verb'], d['by']) == ('close', 'model'), d
    assert len(d['line']) <= 64 and d['line'].endswith('…') and long.startswith(d['line'][:-1]) and long[len(d['line']) - 1] == ' ', d['line']


def test_a_forgotten_line_rests_on_nothing(w):
    s, _ = w
    plant(s, 'people', ERIN)
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    judged(s, t, {'verb': 'reply', 'line': 'You answer Erin the same morning.', 'evidence': [lc.cite_of('erin blake manager answer')]})
    s.save_doc('learned', s.get_doc('learned').replace(ERIN + '\n', ''), 'owner')
    assert advisor.decide(s, f'task:{t}', preread=False)['line'] == '', 'the line it rested on is gone, so the reason goes with it'


def test_a_counted_usual_already_on_the_strip_keeps_its_place(w):
    """asked_late's line IS the counted usual, with its evidence: the model's agreeing sentence does not replace it."""
    s, facts = w
    t = ask(s, 'erin', 'Q4 headcount forecast', 'Can you send me the Q4 headcount forecast?', hours=3)
    C.reflected(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'She has waited three hours.', 'evidence': [f"msg{facts['erin_fast'][0]}"]})
    assert (d['state'], d['line']) == ('asked_late', 'You usually answer Erin within the hour; this is 3h.'), d


def test_a_hand_off_count_is_never_the_reason_for_another_verb(w):
    s, _ = w
    t = ask(s, 'site1', 'Payroll correction for a site 5', 'One of our staff was paid the wrong rate last cycle - can this be fixed?', hours=1)
    ids = usual.handed_to(s, C.P['site1'][1], skip=t)['evidence']
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Ray handles payroll for you.', 'evidence': ids[:1]})
    assert advisor.rows(s, 'task', t)[0]['Dropped'] == 'a hand-off reason over another verb'
    assert (d['verb'], d['by'], d['line']) == (None, 'rule', ''), d
    # ...over Hand it to a person it is the reason, said
    t2 = ask(s, 'site2', 'Payroll correction for a site 6', 'One of our staff was paid the wrong rate last cycle - can this be fixed?', hours=1)
    d2, _ = judged(s, t2, {'verb': 'forward', 'line': 'Ray handles payroll for you.', 'evidence': usual.handed_to(s, C.P['site2'][1], skip=t2)['evidence'][:1]})
    assert (d2['verb'], d2['line']) == ('forward', 'Ray handles payroll for you.'), d2


def test_the_prompt_says_a_memory_line_counts_only_for_what_is_current(w):
    s, _ = w
    assert 'counts only when something CURRENT in this item is about it' in advisor.SYSTEM
    assert f"is the reason for {advisor.L('forward')} and nothing else" in advisor.SYSTEM


def waiting_on_gail(s) -> dict:
    t = s.create_task({'Title': 'Headcount sheet sign-off', 'Status': 'waiting', 'WaitingOn': 'person:gail@northwind.example'}, 'owner')
    s.add_message({'ConversationId': 'email:sheet', 'Channel': 'email', 'Subject': 'Headcount sheet sign-off', 'FromEmail': C.OWNER[1], 'FromName': C.OWNER[0],
                   'Direction': 'out', 'Status': 'sent', 'TaskId': t, 'BodyText': 'Can you sign the sheet off?', 'RecipientsJson': json.dumps({'to': ['gail@northwind.example']}),
                   'SentAt': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')})
    # ...Gail has written before, on another thread: her name is known by her address
    s.add_message({'ConversationId': 'email:rota', 'Channel': 'email', 'Subject': 'Rota', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                   'Status': 'filed', 'BodyText': 'The rota is up.', 'SentAt': (datetime.now() - timedelta(days=9)).strftime('%Y-%m-%d %H:%M:%S')})
    return {'key': f'task:{t}', 'tid': t, 'lane': 'theirs', 'kind': 'task', 'title': 'Headcount sheet sign-off'}


def test_a_rule_state_asks_the_model_only_where_a_memory_line_names_someone_on_it(w):
    s, _ = w
    it = waiting_on_gail(s)
    verbs = [{'verb': 'defer'}, {'verb': 'chase'}]
    r = rulebook.decide(s, it, verbs)
    assert (r['state'], r['ask'], r.get('memory')) == ('waiting', False, None), 'no line about Gail: the rule alone, no model call'
    plant(s, 'people', RAY)
    assert rulebook.decide(s, it, verbs)['ask'] is False, 'a line about someone else is no reason to ask'
    plant(s, 'promises', GAIL_PROMISE)
    r = rulebook.decide(s, it, verbs)
    assert (r['state'], r['verb'], r['ask'], r['memory']) == ('waiting', None, True, ['gail monday sheet']), r
    # ...and by full name, where the line carries no address
    s.save_doc('learned', s.get_doc('learned').replace(' (gail@northwind.example)', ''), 'owner')
    assert rulebook.decide(s, it, verbs)['memory'] == ['gail monday sheet']


def test_people_lines_rank_by_who_is_on_the_item_then_its_subject():
    ls = [(RAY, 'ray payroll'), (C.ERIN_LINE, 'erin blake manager answer'), (GAIL_PROMISE, 'gail monday sheet')]
    one = max(len(r) for r, _ in ls) + 1
    # every colleague shares the domain: by domain alone, the document's first line won the budget
    assert lc.cut(ls, one, {'domain': 'northwind.example'})[0] == [RAY]
    assert lc.cut(ls, one, {'domain': 'northwind.example', 'people': ['gail@northwind.example']})[0] == [GAIL_PROMISE]
    assert lc.cut(ls, one, {'domain': 'northwind.example', 'people': ['erin blake']})[0] == [C.ERIN_LINE]
    assert lc.cut(ls, one, {'topic': 'Weekly headcount sheet for Monday'})[0] == [GAIL_PROMISE]
    assert lc.cut(ls, one, {'sender_name': 'erin blake', 'people': ['gail@northwind.example']})[0] == [C.ERIN_LINE], 'the sender first'


def test_a_state_asked_for_its_memory_changes_only_on_that_memory(w):
    """Asked because a line names the person, the model's other verb stands only when it rests on a memory line: the live A/B's model,
    asked about a late step for its holder's line, swapped the rule's move for another on the age alone."""
    s, _ = w
    it = waiting_on_gail(s); funnel.invalidate()
    plant(s, 'promises', GAIL_PROMISE)
    key, t = it['key'], it['tid']
    r = advisor.decide(s, key, preread=False)
    assert r['ask'] and r['state'] in rulebook.MEMORY_ASKS and not rulebook.asks(r['state']), r
    other = next(v['verb'] for v in advisor.offered(s, advisor._item(s, 'task', t, key)) if v['verb'] not in (r['verb'], 'next'))
    d, _ = judged(s, t, {'verb': other, 'line': 'It has waited a day.', 'evidence': []})
    assert (d['verb'], d['by']) == (r['verb'], 'rule'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': other, 'line': 'Her sheet is due Monday.', 'evidence': [lc.cite_of('gail monday sheet')]})
    assert (d['verb'], d['by'], d['line']) == (other, 'model', 'Her sheet is due Monday.'), d
