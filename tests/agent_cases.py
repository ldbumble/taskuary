"""THE GENERAL AGENT'S EVAL (Task 3.2, 2026-11-04): a task in the shape a real one took, built with invented Northwind people, and
the prompt the general agent would get on it checked for what a careful worker needs to reach the right move - the pattern of
tests/advisor_cases.py, at the prompt rather than the answer, because a real model reads the same prompt:

    needs   - what the PROMPT must carry for the right move to be reachable at all
    never   - what must not ride in it (a rule that sends the job back, a worker the task is not)
    LATER   - a need a later task in the plan supplies, kept as a known failure until it lands (pytest xfail, strict)

Used by tests/test_agent_cases.py."""
import json, tempfile
from pathlib import Path


def login_kept_in_a_project(s) -> int:
    """Ray Colton asks Alex for the vendor-portal login so Gail Moreno can upload the payment file. The login sits in the .env of a
    project an agent maps on this machine; the drafter said NEEDS and no agent ever ran (the shape of the 2026-11-04 diagnosis)."""
    s.set_setting('owner_email', 'alex@northwind.example', 't'); s.set_setting('owner_name', 'Alex Doyle', 't')
    d = Path(tempfile.mkdtemp(prefix='tq-ledger-')); (d / '.env').write_text('PORTAL_USER=placeholder\n', encoding='utf-8')
    s.upsert_agent('coding', 'cli', 'claude', json.dumps({'cwd_map': {'northwind/ledger': str(d)}}))
    for n, k in (('assistant', 'general'), ('researcher', 'research')): s.upsert_agent(n, k, 'cli', json.dumps({'kind': k}))   # as an install seeds them
    tid = s.create_task({'Title': 'Ray asks for the vendor-portal login for Gail', 'Kind': 'general', 'Status': 'open',
                         'Summary': 'Ray Colton wants the vendor-portal login sent to Gail Moreno so she can upload the payment file.'}, 'triage')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'ray-1', 'Subject': 'Vendor portal login', 'FromName': 'Ray Colton',
                   'FromEmail': 'ray@northwind.example', 'BodyText': 'Alex - can you send Gail the vendor-portal login? She needs to upload '
                   'the payment file today.', 'Status': 'routed', 'SentAt': '2026-11-04T09:00:00Z'})
    s.cx.execute('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps({
        'asking': 'Ray Colton wants the vendor-portal login for Gail Moreno', 'your_part': 'give Gail the portal login',
        'others': [], 'asks': [], 'aside': [], 'on_you': []}), tid)); s.cx.commit()
    s._case_dir = str(d)
    return tid


# (name, setup(store) -> tid, needs, never). A need may be a callable of the store, for what setup made (a temp folder's path).
CASES = [
    ('login_kept_in_a_project', login_kept_in_a_project,
     [lambda s: s._case_dir, 'PROFILE RULES (the file ASSISTANT.md)', 'Your part: give Gail the portal login',
      'goes only in the reply you draft', 'their Send shares it', 'never in the conversation, your steps or your summary', '.env'],
     ['PROFILE RULES (the file RESEARCHER', 'into the conversation or a draft', 'PORTAL_USER=placeholder']),
]
LATER = {}   # a need a later task supplies: (case, need) -> the task
