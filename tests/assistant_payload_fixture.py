"""THE PAYLOAD GATE'S FIXTURE. One store with something in every block, and the payload it produces
with the clock scrubbed out of it.

This module is deliberately written against nothing but `store` and `assistant.inputs/candidates/cfg`
so it runs UNCHANGED on e5a34f53 - the last commit before assistantblocks existed. That is how
tests/data/assistant_payload_golden.txt was generated, and why comparing against it proves the
registry reads what the nine hardcoded calls read, rather than proving inputs() equals itself.

    python -m tests.assistant_payload_fixture > tests/data/assistant_payload_golden.txt

Every timestamp is RELATIVE to the moment the fixture is built, so "3 day(s) ago" is three days ago
whenever the suite runs. What is left of the wall clock - the NOW line, dates, times, weekday names,
hour ages - is scrubbed by `normalise`, because a gate that a minute boundary can fail is a gate
nobody will trust the next time it goes red."""
import json, re, sys
from datetime import datetime, timedelta

ME = 'owner@example.com'


def _ago(**kw) -> str: return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    """Something in every block, and nothing near a window's edge: the offsets are chosen so a run
    at 23:59 sees the same rows as a run at 00:01."""
    from taskuary.store import MemoryStore
    s = MemoryStore()
    s.set_setting('owner_email', ME, 'fixture')
    s.set_setting('calendar_enabled', '0', 'fixture')          # the one live block: never fetched by a test
    s.set_setting('assistant_notes', 'Dana still owes the ledger; Sam is away.', 'fixture')
    s.set_setting('assistant_notes_at', _ago(hours=30), 'fixture')

    def mail(fields):
        return s.add_message({'Channel': 'email', 'Status': 'feed', 'TaskId': None, **fields})

    # a thread whose last word is THEIRS - what people said, and what arrived
    mail({'ExternalId': 'm1', 'ConversationId': 'c-ledger', 'Subject': 'Q3 ledger', 'Direction': 'in',
          'FromName': 'Dana Reed', 'FromEmail': 'dana@vendor.example', 'SentAt': _ago(days=1, hours=5),
          'BodyText': 'Here is the Q3 ledger. Let me know if the reconciliation looks right.'})
    # ...and the owner's own last word on another, which ASKED: a followup candidate
    mail({'ExternalId': 'm2', 'ConversationId': 'c-invoice', 'Subject': 'Invoice 4471', 'Direction': 'in',
          'FromName': 'Priya Shah', 'FromEmail': 'priya@vendor.example', 'SentAt': _ago(days=4, hours=2),
          'BodyText': 'Attaching invoice 4471 for the March work.'})
    mail({'ExternalId': 'm3', 'ConversationId': 'c-invoice', 'Subject': 'Re: Invoice 4471', 'Status': 'context',
          'FromName': 'Me', 'FromEmail': ME, 'SentAt': _ago(days=3, hours=2),
          'BodyText': 'Could you send the signed copy before Friday?'})
    # ...and one where the owner PROMISED
    mail({'ExternalId': 'm4', 'ConversationId': 'c-audit', 'Subject': 'Audit questions', 'Direction': 'in',
          'FromName': 'Sam Okoro', 'FromEmail': 'sam@client.example', 'SentAt': _ago(days=5, hours=3),
          'BodyText': 'Three questions on the audit file when you get a moment.'})
    mail({'ExternalId': 'm5', 'ConversationId': 'c-audit', 'Subject': 'Re: Audit questions', 'Status': 'context',
          'FromName': 'Me', 'FromEmail': ME, 'SentAt': _ago(days=2, hours=4),
          'BodyText': 'I will send you the answers tomorrow.'})
    # an auto-reply: OUT OF OFFICE, and the line that rides on a chase
    mail({'ExternalId': 'm6', 'ConversationId': 'c-ooo', 'Subject': 'Automatic reply: Audit questions', 'Direction': 'in',
          'FromName': 'Sam Okoro', 'FromEmail': 'sam@client.example', 'SentAt': _ago(days=1, hours=2),
          'BodyText': 'I am out of the office until Monday with limited access to email.'})

    # OPEN WORK, DONE THIS WEEK and WORK GONE QUIET
    t1 = s.create_task({'Title': 'Reconcile the Q3 ledger', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    t2 = s.create_task({'Title': 'Draft the audit answers', 'Kind': 'writing', 'Status': 'in_progress'}, 'owner')
    t3 = s.create_task({'Title': 'Ship the invoice importer', 'Kind': 'coding', 'Status': 'done'}, 'owner')
    s.add_comment(t3, 'coder', 'agent', 'CODER REPORT\nSummary: imported the March invoices and closed the run.')
    # the age of a task is what DONE THIS WEEK and WORK GONE QUIET are about, and update_task stamps
    # UpdatedAt with the current moment by design - so the fixture writes the clock it needs
    def aged(tid, when):
        s._exec('UPDATE task SET UpdatedAt=?, CreatedAt=? WHERE TaskId=?', (when, when, tid))
        s._exec('UPDATE comment SET CreatedAt=? WHERE TaskId=?', (when, tid))
    s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(days=2), t3)); aged(t3, _ago(days=2))
    aged(t1, _ago(days=9))                                                  # nothing has touched it: gone quiet
    aged(t2, _ago(days=1))

    # ALREADY SAID
    s.upsert_idea({'key': 'followup:c-invoice', 'kind': 'followup', 'sig': 'x',
                   'text': 'No answer from Priya on the signed copy.', 'action': {}}, _ago(days=1))
    s.upsert_idea({'key': 'idea:weekly-ledger', 'kind': 'idea', 'sig': 'y',
                   'text': 'The ledger reconciliation repeats monthly - worth automating.', 'action': {}}, _ago(days=3))
    return s


def payload() -> str:
    """What a default Assistant run hands the model, for this store: the candidates it finds itself
    and the blocks around them. Two payloads, because the candidate list is half the gate."""
    from taskuary import assistant
    s = store()
    cands = assistant.candidates(s, assistant.cfg(s))
    return assistant.inputs(s, cands) + '\n@@@ NO CANDIDATES @@@\n' + assistant.inputs(s, [])


_CLOCK = ((r'(?m)^NOW: .*$', 'NOW: <now>'),
          (r'\d{4}-\d{2}-\d{2}', '<date>'),
          (r'\b\d{1,2}:\d{2}(:\d{2})?\b', '<time>'),
          (r'\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b ?\d{0,2}', '<day>'),      # _when()[:6] is 'Thu 28': the day of the month rides along
          (r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', '<mon>'),
          (r'\b\d+h\b', '<h>'))


def normalise(text: str) -> str:
    """The payload with the wall clock taken out - and nothing else. Relative ages ("3 day(s) ago"),
    every heading, every subject, every body, the row counts and the ORDER all survive, which is
    what the gate is about."""
    for pat, rep in _CLOCK: text = re.sub(pat, rep, text)
    return text.replace('\r\n', '\n').strip() + '\n'


if __name__ == '__main__':
    # newline='' or Windows writes CRLF into the golden and every later comparison is a lie
    text = normalise(payload())
    if len(sys.argv) > 1: open(sys.argv[1], 'w', encoding='utf-8', newline='').write(text)
    else: sys.stdout.write(text)
