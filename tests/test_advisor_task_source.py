"""A task the Advisor raised shows the mail it was about (2026-10-28). Triage filed Erin's mail as fyi; the Advisor read her follow-up
and said the reconciliation was still owed; the task that idea opened carried only the Advisor's own line - "Advisor · Advisor", its
words with "whose move: the owner the Advisor's suggestion: ..." run into them - and never Erin's mail or her follow-up. The idea's
mail(s) now ride on the task it opens, an older task finds them from the idea, and the idea is said in one line, not as a message."""
import json
from datetime import datetime, timedelta

from taskuary import assistant
from taskuary.store import MemoryStore

STAMP = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
TEXT = "Erin's follow-up shows the year-end reconciliation is still owed - I'd send it today."


def _mails(s):
    add = lambda i, **m: s.add_message({'ExternalId': f'rec-{i}', 'ConversationId': 'email:rec', 'Channel': 'email', 'Direction': 'in',
                                        'FromName': 'Erin Blake', 'FromEmail': 'erin@vendor.example', 'Subject': 'Year-end reconciliation', **m})
    first = add(1, SentAt=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), BodyText='Could you send the year-end reconciliation?')
    again = add(2, SentAt=(datetime.now() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S'), BodyText='Following up - still need it for Friday.')
    return first, again


def _idea(s, first, again):
    return s.upsert_idea({'key': 'idea:reconciliation-owed', 'kind': 'idea', 'text': TEXT, 'sig': TEXT[:40],
                          'action': {'type': 'message', 'mid': first, 'whose': 'the owner', 'suggest': 'Send the reconciliation and the summary.',
                                     'why': f'Erin Blake mid {first} asked; her follow-up mid {again} says Friday; triage filed it as fyi.'}}, STAMP)


SEEN = []
def _brain(system, user, **k): SEEN.append(user); return json.dumps({'intent': 'task', 'kind': 'general', 'why': 'the Advisor says the owner owes Erin a reply',
                                                  'title': 'Send Erin the year-end reconciliation'})


def test_the_idea_line_carries_no_format_text_and_triage_still_reads_it():
    s = MemoryStore(); first, again = _mails(s); i = _idea(s, first, again)
    msg, _, _ = assistant._idea_message(s, i, json.loads(i['ActionJson']))
    assert msg['body'] == TEXT
    assert not any(w in msg['body'] for w in ('whose move', "Advisor's suggestion", 'why:'))
    ctx = msg['idea_context']
    assert (ctx['whose'], ctx['suggest']) == ('the owner', 'Send the reconciliation and the summary.') and f'mid {again}' in ctx['why']


def test_a_task_an_idea_opens_carries_the_mails_it_was_about():
    s = MemoryStore(); first, again = _mails(s); i = _idea(s, first, again)
    assistant.triage_ideas(s, [i], _brain)
    tid = json.loads(s.get_idea(i['IdeaId'])['ActionJson'])['tid']
    assert 'the owner' in SEEN[-1] and 'Send the reconciliation and the summary.' in SEEN[-1]    # triage still reads them
    ms = s.list_messages(tid)
    assert {m['MessageId'] for m in ms if m['Channel'] == 'email'} == {first, again}       # both of Erin's mails, moved onto it
    [line] = [m for m in ms if m['Channel'] == 'assistant']
    assert 'whose move' not in line['BodyText']
    assert assistant.raised_by(s, s.get_task(tid), ms) == {'by': 'Advisor', 'text': TEXT}


def test_a_mail_another_task_holds_stays_there_and_shows_from_the_idea():
    s = MemoryStore(); first, again = _mails(s)
    other = s.create_task({'Title': 'Year-end close', 'Kind': 'task', 'Status': 'done'}, 'owner')
    s.attach_message(first, other)
    i = _idea(s, first, again)
    tid = s.create_task({'Title': 'Send Erin the reconciliation', 'Kind': 'task', 'Source': 'assistant',
                         'SourceRef': f"assistant:idea:{i['IdeaId']}"}, 'assistant')
    assistant.attach_sources(s, i, tid)
    assert s.get_message(first)['TaskId'] == other and s.get_message(again)['TaskId'] == tid
    assert [m['MessageId'] for m in s.made_from(s.get_task(tid))] == [first, again]


def test_an_older_task_finds_its_mail_from_the_idea_not_the_advisor_post():
    """idea.MessageId is the Advisor post that SAID the idea - made_from read it before the idea's own mid, found the Advisor's channel
    and showed nothing at all."""
    s = MemoryStore(); first, again = _mails(s); i = _idea(s, first, again)
    post = s.add_message({'ExternalId': 'assistant:post', 'Channel': 'assistant', 'FromName': 'Advisor', 'SourceName': 'Advisor',
                          'SentAt': STAMP, 'BodyText': 'The day so far.'})
    s.set_ideas_message([i['IdeaId']], post)
    tid = s.create_task({'Title': 'Send Erin the reconciliation', 'Kind': 'task', 'Source': 'assistant',
                         'SourceRef': f"assistant:idea:{i['IdeaId']}"}, 'assistant')
    # the line as an older build stored it, the format text in its body
    s.add_message({'TaskId': tid, 'ExternalId': f"idea:{i['IdeaId']}", 'Channel': 'assistant', 'FromName': 'Advisor', 'SourceName': 'Advisor',
                   'SentAt': STAMP, 'BodyText': TEXT + "\n\nwhose move: the owner\nthe Advisor's suggestion: Send it."})
    assert [m['MessageId'] for m in s.made_from(s.get_task(tid))] == [first, again]
    assert assistant.raised_by(s, s.get_task(tid), s.list_messages(tid))['text'] == TEXT
    s.cx.execute('DELETE FROM idea')                                   # the idea gone, the line's own words before the format text
    assert assistant.raised_by(s, s.get_task(tid), s.list_messages(tid)) == {'by': 'Advisor', 'text': TEXT}


def test_a_task_nobody_raised_says_nothing():
    s = MemoryStore()
    assert assistant.raised_by(s, s.get_task(s.create_task({'Title': 'Typed by hand', 'Kind': 'task'}, 'owner')), []) is None
