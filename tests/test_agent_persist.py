"""THE GENERAL AGENT KEEPS GOING, AND READS MORE (the owner, 2026-11-05: "is there hard coded things in the agent workings? look at open
source assistants online and adapt the best parts to ours").

The brief grows the habits the open-source assistants share - a bounded fallback ladder, work that goes on while a question waits, each
step checked by what came back, done meaning the goal met - and loses the judgements code made for the model: a 24,000-character window,
a draft-quote filter that ate "Thanks, Gail.", a length rule deciding whether the agent's words show. What a long task's brief still
cannot hold is COMPACTED from what the task already keeps (its turn summaries), never a second memory beside LEARNED.md.
"""
import json
from pathlib import Path
from unittest import mock

from taskuary import general, selfclose
from taskuary.store import MemoryStore

TEMPLATES = Path(__file__).resolve().parents[1] / 'taskuary' / 'templates'


def task(s): return s.create_task({'Title': 'Renewal with Northwind', 'Kind': 'general', 'Status': 'open'}, 'owner')


def answered(s, tid, did, on_you=()):
    cid = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'{did} ' + 'detail ' * 400)
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'about': 'the renewal', 'did': did, 'on_you': list(on_you), 'nothing_left': False}))
    return cid


# ── the brief ───────────────────────────────────────────────────────────────────────────────
def test_the_brief_carries_the_ladder_the_work_line_and_the_override():
    s = MemoryStore(); system = general._prompt(s, task(s))[0]
    # the override rides only for an AGENT.md copy that still tells a worker to run --done: the shipped one no longer does (2026-11-09)
    assert general.GENERAL_OVER not in system
    s.save_doc('agent', (s.doc('agent') or '') + '\n- When the work is over, run `taskuary --done "<one sentence>"`.', 'owner')
    system = general._prompt(s, task(s))[0]
    for want in (general.WORK_LINE, general.GENERAL_OVER, 'more than twice', 'three genuinely different ways', 'one line per way you tried',
                 'WHILE A QUESTION WAITS, KEEP WORKING', 'CHECK EACH STEP BEFORE THE NEXT', 'DONE MEANS THE GOAL IS MET AND CHECKED'):
        assert want in system, want
    assert '"answer_is_result"' in selfclose.SUMMARY_LINE and 'true only when the goal is met and you checked it' in selfclose.SUMMARY_LINE


def test_agent_md_no_longer_tells_a_general_agent_to_stop_hunting_wait_or_close():
    text = (TEMPLATES / 'agent.md').read_text(encoding='utf-8')
    for gone in ('Do not go hunting for the task', 'stay at the prompt until the answer comes', 'Do not widen the job'):
        assert gone not in text, gone
    # ...and `--done` is a coding session's alone, so it lives in CODING.md; the general agent hears who closes from owner_closes_line
    assert '--done' not in text and '--done' in (TEMPLATES / 'coding.md').read_text(encoding='utf-8')
    assert 'taskuary --done' in (TEMPLATES / 'coding.md').read_text(encoding='utf-8')      # ...the coding road is unchanged


def test_the_windows_are_large():
    # lean by default, the rest on ask (the owner, 2026-11-05): the brief stays small; answers have room
    assert general.MAX_CONTEXT <= 40_000 and 'reads any mail in full' in general.READ_WHOLE
    assert general.MAX_REPLY_TOKENS >= 8_000 and general.DOCK_REPLY_TOKENS >= 3_000
    assert general.WAIT_TURN is None


# ── compaction ──────────────────────────────────────────────────────────────────────────────
def test_a_long_task_is_compacted_and_still_names_its_earlier_decisions():
    s = MemoryStore(); tid = task(s)
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Go with the three-year term, not the two.')
    answered(s, tid, 'Drafted the three-year terms to C:/tasks/renewal/terms.docx', on_you=['confirm the 6% uplift with Erin Blake'])
    for i in range(30):
        s.add_comment(tid, 'owner', general.USER_TYPE, f'question {i}'); answered(s, tid, f'answer {i}')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Where did we land?')
    before = len(s.list_comments(tid, internal=True))
    with mock.patch.object(general, 'MAX_CONTEXT', 30_000), mock.patch('taskuary.learn.learn_from') as lf:
        user = general._prompt(s, tid)[1]
    assert 'EARLIER IN THIS CONVERSATION, COMPACTED' in user
    assert 'Go with the three-year term, not the two.' in user                                  # the owner's decision
    assert 'C:/tasks/renewal/terms.docx' in user and 'confirm the 6% uplift with Erin Blake' in user      # ...what was done, what was left
    assert user.rstrip().endswith('Do not repeat the task context.') and 'Where did we land?' in user
    assert len(user) <= 30_000 + 200
    # ...nothing new is stored, and nothing goes around LEARNED.md: the chat keeps every turn, compaction is only what the model reads
    assert len(s.list_comments(tid, internal=True)) == before and len(general.chat_rows(s, tid)) == 63
    lf.assert_not_called()
    assert not [n for n in s.doc_names() if n not in ('soul', 'job', 'agent', 'coding', 'digest', 'learned', 'triage', 'style', 'counsel',
                                                      'researcher', 'analyst', 'coordinator', 'marketer', 'trader', 'assistant')]


def test_a_short_task_is_not_compacted():
    s = MemoryStore(); tid = task(s)
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Go with the three-year term.'); answered(s, tid, 'Drafted it')
    assert 'COMPACTED' not in general._prompt(s, tid)[1]


def test_older_mail_is_compacted_by_id():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); tid = task(s)
    ids = [s.add_message({'ExternalId': f'x{i}', 'TaskId': tid, 'Channel': 'email', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                          'Subject': 'renewal', 'BodyText': f'mail {i} body', 'SentAt': f'2026-11-0{i + 1} 09:00:00'}) for i in range(4)]
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Sum it up')
    with mock.patch.object(general, 'SOURCE_MAILS', 2): user = general._prompt(s, tid)[1]
    assert 'EARLIER MAIL ON THIS TASK, COMPACTED - 2 older messages' in user and f'[m{ids[0]}] Gail Moreno' in user and general.READ_WHOLE in user
    assert f'[m{ids[3]}] · email\nmail 3 body' in user


def test_the_thread_a_task_was_built_from_is_in_its_material():
    """The agent walk, 2026-11-10: a reply task held the one mail that asked for the figures, and the two earlier mails that HELD them -
    same conversation, kept as `history` on no task when the thread was completed - were not in what the agent was handed. It searched
    the mailbox for what triage, the drafter and the task page had all read. They ride as the task's mail, oldest first, each as what
    its sender wrote; another conversation's history does not, and a stranger's session is handed its own task's rows as before."""
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); tid = task(s)
    row = lambda ext, who, at, body, conv='<pay-root@northwind.example>', **kw: s.add_message({
        'ExternalId': ext, 'TaskId': None, 'Status': 'history', 'Channel': 'email', 'ConversationId': conv, 'Subject': 'Payroll figures',
        'FromName': who, 'FromEmail': f'{who.split()[0].lower()}@northwind.example', 'SentAt': at, 'BodyText': body, **kw})
    first = 'The October run came to 48,210.55 across 212 staff.'
    g1 = row('h1', 'Gail Moreno', '2026-11-02 09:00:00', first)
    g2 = row('h2', 'Gail Moreno', '2026-11-03 09:00:00', 'Corrected: the adjustment file adds 1,904.00, so 50,114.55 in all.\n\n'
             f'From: Gail Moreno <gail@northwind.example>\nSent: Monday, November 2, 2026 9:00 AM\nTo: Erin Blake\nSubject: Payroll figures\n\n{first}')
    other = row('h3', 'Paula Vance', '2026-11-03 10:00:00', 'The Trainly seats renew in March.', conv='<seats@northwind.example>')
    ask = row('a1', 'Erin Blake', '2026-11-04 09:00:00', 'Alex - can you confirm the final October figure to Payworth?', TaskId=tid, Status='sent')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Answer her')
    user = general._prompt(s, tid)[1]
    src = user[user.index('SOURCE MATERIAL'):user.index('CONVERSATION\n')]
    assert f'[m{g1}]' in src and '48,210.55' in src and f'[m{g2}]' in src and '50,114.55' in src           # the figures are in the material...
    assert src.index(f'[m{g1}]') < src.index(f'[m{g2}]') < src.index(f'[m{ask}]')                          # ...in the order they were written
    assert src.count('48,210.55') == 1                                                                 # each mail's own words, once
    assert f'[m{other}]' not in user and 'Trainly' not in user
    with mock.patch.object(general, 'SOURCE_MAILS', 1): few = general._prompt(s, tid)[1]                  # one window: the oldest are the lines
    assert 'COMPACTED - 2 older messages' in few and f'- [m{g1}] Gail Moreno' in few and f'[m{ask}]' in few
    with mock.patch('taskuary.origin.of_task', return_value=('stranger', '')), mock.patch('taskuary.origin.stranger_file', return_value='f.md') as wrote:
        general._prompt(s, tid)
    assert '50,114.55' not in '\n'.join(wrote.call_args[0][2])


# ── the draft filter takes only the draft ───────────────────────────────────────────────────
LETTER = 'Hi Gail,\n\nThe three-year term works for us at a 6% uplift. I will send the signed copy on Friday.\n\nThanks, Gail.'

def test_a_short_line_that_is_also_in_the_draft_stays():
    said = 'I read the thread.\n\nThanks, Gail.'
    assert selfclose.without_draft(said, LETTER) == said


def test_the_draft_written_out_whole_goes():
    said = f'I drafted your yes.\n\n---\n\n{LETTER}\n\n---\n\nSend it when ready.'
    assert selfclose.without_draft(said, LETTER) == 'I drafted your yes.\n\nSend it when ready.'
    assert selfclose.without_draft(LETTER, LETTER) == ''


# ── the agent says whether its words are the result ─────────────────────────────────────────
def test_answer_is_result_rides_the_summary_only_when_said():
    block = lambda **kw: f"{selfclose.SUMMARY_OPEN}{json.dumps({'about': 'a', 'did': 'b', **kw})}{selfclose.SUMMARY_CLOSE}"
    assert selfclose.summary_marker(f'The list.\n{block(answer_is_result=True)}')[1]['answer_is_result'] is True
    assert selfclose.summary_marker(f'The list.\n{block(answer_is_result=False)}')[1]['answer_is_result'] is False
    assert 'answer_is_result' not in selfclose.summary_marker(f'The list.\n{block(answer_is_result="yes")}')[1]
    assert 'answer_is_result' not in selfclose.summary_marker(f'The list.\n{block()}')[1]


# ── a nothing-new turn is one line (the owner, 2026-11-06) ────────────────────────────────────
def test_a_one_line_turn_files_its_line_alone_and_the_agent_is_told_it_may():
    said = f"Ray thanked you.\n{selfclose.SUMMARY_OPEN}{json.dumps({'did': 'Ray thanked you.', 'about': '', 'on_you': []})}{selfclose.SUMMARY_CLOSE}"
    rest, out = selfclose.summary_marker(said)
    assert rest == 'Ray thanked you.' and out['did'] == 'Ray thanked you.' and out['about'] == '' and out['on_you'] == []
    # ...the model judges it: the instructions say ONE line and no draft, and never hand it a list of words to match
    from taskuary import ingest
    for words in (selfclose.SUMMARY_LINE, ingest.REPLAN):
        assert 'ONE' in words and 'no draft' in words


# ── a refusal says why, and what to do next ─────────────────────────────────────────────────
def test_a_refused_proposal_tells_the_agent_why_and_the_next_move():
    from taskuary import proposals
    s = MemoryStore(); tid = task(s); miss = []
    assert proposals.queue(s, tid, {'action': 'no_such_act', 'why': 'try'}, refused=miss) is None and miss
    said = proposals.refusal_line(miss[0])
    assert miss[0] in said and 'Fix that and propose it again' in said and 'on the task' not in said
