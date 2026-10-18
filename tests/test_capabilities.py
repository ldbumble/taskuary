"""WHAT THIS INSTALL CAN DO, from one function (capabilities.py) - and the Advisor offered only what the item can really do:
no Send on a draft that cannot leave, the failed send's fix under its own name, advice read back only for its item."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import advisor, agents, capabilities, concierge
from taskuary.store import MemoryStore


def brain_saying(answer: dict):
    def llm(system, prompt, **kw): llm.calls.append(prompt); return json.dumps(answer)
    llm.calls = []; return llm


def draft(s, channel='email', deliver=None):
    """A task with a drafted reply waiting for the owner's yes, on `channel` - and the item the rail would show for it."""
    tid = s.create_task({'Title': 'Vendor invoice question', 'Status': 'open'}, 'test')
    mid = s.add_message({'Channel': channel, 'FromEmail': 'erin.blake@northwind.example', 'FromName': 'Erin Blake',
                         'Subject': 'Invoice', 'BodyText': 'Can you approve it by Friday?', 'TaskId': tid, 'Status': 'task'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'DraftText': 'Approved - thanks, Erin.', 'Status': 'pending',
                        'Deliver': json.dumps(deliver) if deliver else None})
    return {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'rid': rid, 'tid': tid, 'mid': mid, 'channel': channel,
            'draft': 'Approved - thanks, Erin.', 'ref': f'TQ-{tid}', 'title': 'Vendor invoice question'}


class CapabilitiesTests(unittest.TestCase):
    def test_one_answer_with_every_field(self):
        s = MemoryStore()
        with mock.patch.object(agents, 'coding_ready', return_value=False):
            c = capabilities.capabilities(s)
        self.assertEqual(set(c), {'coding', 'ai', 'mail', 'send'})
        self.assertIs(c['coding'], False); self.assertIs(c['mail'], False)
        # email can deliver; a Teams chat is read here and never posted into
        self.assertIs(c['send']['email'], True); self.assertIs(c['send']['teams'], False)
        with mock.patch.object(agents, 'coding_ready', return_value=True): self.assertIs(capabilities.capabilities(s)['coding'], True)

    def test_the_page_reads_the_same_answer(self):
        from taskuary import server
        s = MemoryStore()
        with mock.patch.object(server, 'store', s), mock.patch.object(agents, 'coding_ready', return_value=False):
            self.assertEqual(TestClient(server.app).get('/api/capabilities').json(), capabilities.capabilities(s))

    def test_a_probe_that_fails_answers_no_for_itself_only(self):
        s = MemoryStore()
        with mock.patch.object(agents, 'coding_ready', side_effect=OSError('gone')):
            c = capabilities.capabilities(s)
        self.assertIs(c['coding'], False); self.assertIs(c['send']['email'], True)

    def test_the_offers_ask_it(self):
        """The chips, the assistant's coding lines and setup read capabilities - patched there, every one follows."""
        from taskuary import counsel, firstrun
        s = MemoryStore()
        with mock.patch.object(capabilities, 'can_code', return_value=False):
            self.assertTrue(concierge.cannot({'ref': 'TQ-1'}, 'coding_agent', s))
            self.assertEqual(counsel.for_chat(s), counsel.without_coding(counsel.load(s)))
        with mock.patch.object(capabilities, 'ai_brain', return_value={'ready': False, 'why': 'none'}):
            self.assertEqual(firstrun.state(s)['step'], 'ai')

    def test_a_refused_send_says_why_not_where_to_click_in_general(self):
        s = MemoryStore()
        self.assertEqual(capabilities.send_refusal(s, 'email'), '')
        self.assertIn('Teams does not let an app post', capabilities.send_refusal(s, 'teams'))


class OfferedTests(unittest.TestCase):
    def test_a_draft_that_cannot_send_is_offered_no_send(self):
        s = MemoryStore()
        teams, email = draft(s, 'teams'), draft(s, 'email')
        self.assertNotIn('approve', [v['verb'] for v in advisor.offered(s, teams)])
        self.assertIn('approve', [v['verb'] for v in advisor.offered(s, email)])
        # ...and the chat's own buttons agree: the same gate (concierge.cannot), so the Advisor and the chips never differ
        self.assertNotIn('approve', [c['verb'] for c in concierge.chips_for(s, teams)])
        self.assertIn('cannot be sent from here', concierge.cannot(teams, 'approve', s))

    def test_a_failed_send_with_a_fix_offers_the_fix_by_its_own_name(self):
        s = MemoryStore()
        fix = {'label': 'Connect a mailbox', 'href': '#connections=Email'}
        it = draft(s, 'email', deliver={'kind': 'reply', 'delivery': 'failed', 'fix': fix})
        verbs = advisor.offered(s, it)
        self.assertEqual((verbs[0]['verb'], verbs[0]['label'], verbs[0]['href']), ('fix', 'Connect a mailbox', '#connections=Email'))
        # the Advisor may pick it, and its line keeps the fix's own name - never the generic button word
        with mock.patch.object(advisor, '_item', return_value=it):
            rev = advisor.revision(s, 'task', it['tid'])
            advisor.judge(s, advisor.SHOWN, 'task', it['tid'], rev, 2,
                          brain_saying({'verb': 'fix', 'line': 'The send failed because no mailbox is connected.', 'evidence': []}), key=it['key'])
            got = advisor.for_key(s, it['key'])
        # ...and its place, so a page with no '<rid>:fix' on the row still opens it rather than proposing a verb nobody runs
        self.assertEqual((got['verb'], got['label'], got['href']), ('fix', 'Connect a mailbox', '#connections=Email'))

    def test_a_failed_act_names_its_fix_too(self):
        s = MemoryStore(); it = draft(s, 'email')
        s.add_operation({'OpId': 'op1', 'Kind': 'review.approve', 'TargetKind': 'task', 'TargetId': it['tid'], 'Status': 'error',
                         'OutcomeJson': json.dumps({'fix': {'label': 'Turn replies on', 'href': '#settings=config&group=Replies'}})})
        self.assertEqual(advisor.delivery_fix(s, it), {'label': 'Turn replies on', 'href': '#settings=config&group=Replies'})
        s.add_operation({'OpId': 'op2', 'Kind': 'review.approve', 'TargetKind': 'task', 'TargetId': it['tid'], 'Status': 'done'})
        self.assertIsNone(advisor.delivery_fix(s, it), 'a later act that worked: nothing is left to fix')

    def test_no_failure_no_fix(self):
        s = MemoryStore()
        self.assertNotIn('fix', [v['verb'] for v in advisor.offered(s, draft(s, 'email'))])


class KeyedTests(unittest.TestCase):
    def test_advice_is_read_back_only_for_the_item_it_was_written_for(self):
        """One task, two cards: its draft (review:N) and its agent (agent:T). A line judged for the agent's card names a verb only
        that card carries - read over the draft, it pointed at a button the draft does not have."""
        s = MemoryStore(); it = draft(s, 'email'); tid = it['tid']
        agent = {'key': f'agent:{tid}', 'kind': 'agent', 'lane': 'blocked', 'tid': tid, 'ref': it['ref']}
        rev = advisor.revision(s, 'task', tid)
        advisor._write(s, target_kind='task', target_id=tid, key=agent['key'], event='agent.asked', revision=rev, tier=2,
                       line='The agent is asking you something.', verb='answer_agent', label='Answer it')
        cards = {it['key']: it, agent['key']: agent}
        with mock.patch.object(advisor, '_item', side_effect=lambda st, k, i, key=None: cards.get(key) or agent), \
             mock.patch.object(advisor, 'notice') as n:
            self.assertEqual(advisor.for_key(s, agent['key'])['verb'], 'answer_agent')
            self.assertEqual(advisor.for_key(s, it['key']), {})                  # not the agent card's line
        self.assertEqual(n.call_args.kwargs.get('key'), it['key'])                 # ...the draft is judged as itself

    def test_a_judgement_is_written_under_the_item_it_judged(self):
        s = MemoryStore(); it = draft(s, 'email')
        with mock.patch.object(advisor, '_item', return_value=it):
            rid = advisor.judge(s, advisor.SHOWN, 'task', it['tid'], advisor.revision(s, 'task', it['tid']), 2,
                                brain_saying({'verb': 'approve', 'line': 'Erin is waiting on this answer.', 'evidence': []}), key=it['key'])
        self.assertEqual(s._one('SELECT Key FROM advice WHERE Id=?', (rid,))['Key'], it['key'])

    def test_a_review_key_names_its_task(self):
        s = MemoryStore(); it = draft(s, 'email')
        self.assertEqual(advisor.target_of(s, it['key']), ('task', it['tid']))
        self.assertIsNone(advisor.target_of(s, 'review:99999'))


if __name__ == '__main__':
    unittest.main()
