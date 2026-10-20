"""A rule meant for one mailbox stays on that mailbox. "Skip mail from the vendor" written for the board mailbox filed the
same vendor's mail to the work mailbox, where it was an invoice to pay. A rule may name the mailboxes it is for (`Mailbox`);
a rule that names none - every rule written before this - matches every mailbox exactly as it did."""
from taskuary import policy
from taskuary.ingest import ingest_message
from taskuary.policy import apply_retroactively, dropped_unseen, evaluate, matches
from taskuary.store import MemoryStore

NW, CT = 'alex@northwind.example', 'alex@contoso.example'
RULE = {'Name': 'skip vendor', 'Kind': 'sender_domain', 'Pattern': 'vendor.example', 'Action': 'skip', 'Reason': 'board noise',
        'SortOrder': 10, 'Active': 1}
TASK_LLM = lambda sys, usr: '{"intent": "task", "why": "t"}'


def mail(box, xid='m1', who='billing@vendor.example'):
    return {'external_id': xid, 'channel': 'email', 'subject': 'Invoice 42', 'body': 'please pay', 'from_email': who,
            'from_name': 'Billing', 'source_name': box, 'sent_at': '2026-10-19 09:00'}


def test_a_rule_with_no_mailbox_matches_every_mailbox_as_before():
    for box in (NW, CT, None):
        assert matches(RULE, mail(box)) and evaluate(mail(box), [RULE])['action'] == 'skip'


def test_a_rule_naming_a_mailbox_matches_only_that_one():
    board = {**RULE, 'Mailbox': 'Alex@Contoso.example | ops@contoso.example'}
    assert matches(board, mail(CT)) and matches(board, mail('ops@contoso.example'))
    assert not matches(board, mail(NW)) and not matches(board, mail(None))
    assert evaluate(mail(NW), [board])['action'] == 'none'
    assert dropped_unseen(mail(CT), [board]) and not dropped_unseen(mail(NW), [board])


def test_ingest_files_only_the_named_mailboxs_mail():
    s = MemoryStore()
    s.save_policy({**RULE, 'Mailbox': CT}, 't')
    assert ingest_message(s, mail(CT, 'a'), llm=TASK_LLM)['status'] == 'skipped'
    assert ingest_message(s, mail(NW, 'b'), llm=TASK_LLM)['status'] not in ('skipped', 'ignored')


def test_a_scoped_skip_reaches_back_only_into_its_own_mailbox():
    s = MemoryStore()
    for i, box in enumerate((CT, NW, CT)):
        s.add_message({'ExternalId': f'h{i}', 'Channel': 'email', 'Subject': 'Invoice', 'BodyText': 'pay', 'SourceName': box,
                       'FromEmail': 'billing@vendor.example', 'SentAt': '2026-10-18 10:00', 'Status': 'ignored'})
    board = {**RULE, 'Mailbox': CT}
    assert apply_retroactively(s, board) == 2
    assert sorted(m['SourceName'] for m in s.scan_messages(statuses=('skipped',))) == [CT, CT]


def test_the_mailbox_is_saved_and_cleared_with_the_rule():
    s = MemoryStore()
    pid = s.save_policy({**RULE, 'Mailbox': CT}, 't')
    assert s.list_policies()[0]['Mailbox'] == CT
    s.save_policy({'PolicyId': pid, 'Mailbox': ''}, 't')
    assert not s.list_policies()[0]['Mailbox'] and matches(s.list_policies()[0], mail(NW))
    assert 'Mailbox' not in policy.KINDS                                           # a reach, not a kind of match


def test_the_rule_editor_saves_and_clears_the_mailbox_through_the_one_save():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = MemoryStore()
    old, server.store = server.store, s
    try:
        c = TestClient(server.app)
        pid = c.post('/api/policies', json={**RULE, 'Active': True, 'Mailbox': CT}).json()['policyId']
        assert c.get('/api/policies').json()['data'][0]['Mailbox'] == CT
        c.post('/api/policies', json={'PolicyId': pid, 'Mailbox': ''})                 # All mailboxes
        p = c.get('/api/policies').json()['data'][0]
    finally: server.store = old
    assert not p['Mailbox'] and matches(p, mail(NW)) and matches(p, mail(CT))
