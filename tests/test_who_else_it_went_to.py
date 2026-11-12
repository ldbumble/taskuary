"""A mail to the owner AND a colleague is not the owner's just for having them on it (2026-11-03). An ask to change someone's role in
an app went to the owner and one colleague who always takes those; triage made it the owner's coding task, and Came from showed only
who sent it. No gate decides it (the owner: "no hard-coded rules: the model sees everything") - these pin the EVIDENCE triage is
handed (who else it went to, who answered the like of it before), the guide's words, and the names Came from shows."""
import json
from unittest import mock

import pytest

from taskuary import ingest, triage
from taskuary.store import MemoryStore

ME, GAIL, RAY, PAULA = 'alex@northwind.example', 'gail@northwind.example', 'ray@northwind.example', 'paula@northwind.example'


@pytest.fixture
def s():
    value = MemoryStore()
    value.set_setting('owner_email', ME, 'test')
    yield value
    value.close()


def say(s, conv, frm, name, at, to=(ME,), cc=(), subject='Access', direction='in', status='routed'):
    return s.add_message({'ExternalId': f'graph:{conv}-{at}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': subject,
                          'FromEmail': frm, 'FromName': name, 'BodyText': 'words', 'SentAt': at, 'Status': status, 'Direction': direction,
                          'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)})})


def history(s):
    # Paula asked the owner and Gail twice before; Gail answered both. Ray wrote once, so his name is known store-wide.
    say(s, 'a1', PAULA, 'Paula Vance', '2026-09-01 09:00:00', to=(ME, GAIL), subject='Role change in the app')
    say(s, 'a1', GAIL, 'Gail Moreno', '2026-09-01 10:00:00', to=(PAULA,), cc=(ME,), subject='RE: Role change in the app')
    say(s, 'a2', PAULA, 'Paula Vance', '2026-10-01 09:00:00', to=(ME, GAIL), subject='Access to reports')
    say(s, 'a2', GAIL, 'Gail Moreno', '2026-10-01 09:30:00', to=(PAULA,), cc=(ME,), subject='RE: Access to reports')
    say(s, 'r1', RAY, 'Ray Colton', '2026-10-02 09:00:00', subject='Lunch')


def mail(to=(ME, GAIL), cc=(RAY,)):
    return {'from_email': PAULA, 'from_name': 'Paula Vance', 'channel': 'email', 'subject': 'Finance access', 'conversation_id': 'now',
            'body': 'Kindly adjust my role in the app so I have access to budgets.', 'source_name': ME, 'to': list(to), 'cc': list(cc),
            'sent_at': '2026-11-03 09:00:00'}


def thread_of(s, msg):
    seen = {}
    def judge(m, **kw): seen.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
    with mock.patch.object(ingest, 'classify_intent', side_effect=judge): ingest.judge(s, msg, llm=lambda *a, **k: '{}', mine={ME}, me={ME})
    return seen


def test_triage_is_told_who_answered_the_like_of_it_before(s):
    history(s)
    t = thread_of(s, mail())
    assert t['addressed_to'] == ['you', 'Gail Moreno'] and t['copied'] == ['Ray Colton']   # Ray never wrote on this thread: known by his own mail
    ab = t['answered_before']
    assert [a['subject'] for a in ab] == ['Access to reports', 'Role change in the app']   # this sender's, newest first
    assert all(a['answered_by'] == 'Gail Moreno' and a['from'] == 'Paula Vance' and a['with'] == ['Gail Moreno'] for a in ab)
    assert not any(x in json.dumps(ab) for x in (ME, GAIL, RAY, PAULA))                   # names, never an address


def test_the_owner_answering_before_says_you_and_no_reply_says_null(s):
    say(s, 'b1', PAULA, 'Paula Vance', '2026-10-01 09:00:00', to=(ME, GAIL), subject='Budget sheet')
    say(s, 'b1', ME, 'Alex Doyle', '2026-10-01 11:00:00', to=(PAULA,), direction='out', status='context', subject='RE: Budget sheet')
    say(s, 'b2', PAULA, 'Paula Vance', '2026-10-05 09:00:00', to=(ME, GAIL), subject='Old ask')
    by = {a['subject']: a['answered_by'] for a in thread_of(s, mail(cc=()))['answered_before']}
    assert by == {'Budget sheet': 'you', 'Old ask': None}


def test_nothing_before_or_the_owner_alone_hands_over_nothing(s):
    assert 'answered_before' not in thread_of(s, mail())
    history(s)
    assert 'answered_before' not in thread_of(s, mail(to=(ME,), cc=()))


def test_the_classifier_and_the_guide_carry_it(s):
    history(s)
    seen = {}
    def llm(system, user, **kw): seen.update(sys=system, usr=json.loads(user)); return '{"intent": "fyi", "why": "Gail takes these"}'
    msg = mail()
    triage.classify_intent(msg, llm=llm, system='Judge it.', mine={ME}, thread=thread_of(s, msg))
    assert seen['usr']['answered_before'][0]['answered_by'] == 'Gail Moreno'
    assert triage.FIELDS['answered_before'] in seen['sys']                                 # a doc that never names it is told what it is
    guide = (ingest.__file__.rsplit('ingest.py', 1)[0] + 'templates/triage.md')
    text = open(guide, encoding='utf-8').read()
    assert '`answered_before`' in text and 'When the owner shares the To line and nothing turns to them, ask who takes this' in text


def test_came_from_gets_the_lines_by_name_and_nothing_for_the_owner_alone(s):
    history(s)
    m = s.get_message(say(s, 'now', PAULA, 'Paula Vance', '2026-11-03 09:00:00', to=(ME, GAIL), cc=(RAY, 'omar@vendor.example')))
    rc = ingest.row_recipients(s, m)
    assert rc == {'to': ['you', 'Gail Moreno'], 'cc': ['Ray Colton', 'someone at vendor.example'], 'n': 4}
    assert ingest.recipients_said(rc) == 'to you, Gail Moreno · cc Ray Colton, someone at vendor.example'
    assert ingest.row_recipients(s, s.get_message(say(s, 'solo', PAULA, 'Paula Vance', '2026-11-03 10:00:00'))) == {}
    assert ingest.row_recipients(s, {'Channel': 'whatsapp', 'RecipientsJson': None}) == {}


def test_the_task_page_carries_each_mails_lines(s, monkeypatch):
    from taskuary import server, terminal
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kw: [])
    history(s)
    tid = s.create_task({'Title': 'Finance access', 'Kind': 'task', 'Status': 'open', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': 'graph:now', 'ConversationId': 'now', 'Channel': 'email', 'SourceName': ME, 'Subject': 'Finance access',
                   'FromEmail': PAULA, 'FromName': 'Paula Vance', 'BodyText': 'words', 'SentAt': '2026-11-03 09:00:00', 'Status': 'routed',
                   'Direction': 'in', 'RecipientsJson': json.dumps({'to': [ME, GAIL], 'cc': [RAY]})})
    m, = server.task_detail(tid)['messages']
    assert m['Recipients'] == {'to': ['you', 'Gail Moreno'], 'cc': ['Ray Colton'], 'n': 3}
