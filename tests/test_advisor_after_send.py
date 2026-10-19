"""THE ADVISOR SEES WHAT AN ACT LEFT (2026-10-19): a reply went - the close-out read "Sent" and "What was sent" - and the line still
said the sender was waiting for an answer, with Reply lit. Its revision did not cover a draft decided with no delivery receipt, and
its prompt never said a reply had gone, so the sender's ask in the preview was all it had. Now every act on the item moves the
revision, the prompt carries what was sent as evidence, and each reason for having no line is a sentence the strip can say."""
import json
from datetime import datetime, timedelta
from taskuary import advisor, demo, words
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail, brain_saying

def _at(h=0): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


class AfterSendTests(_Rail):
    def _asked(self, s):
        """Erin Blake asked a question on a task; a reply is drafted for her."""
        t = s.create_task({'Title': 'August close numbers', 'Status': 'open'}, 'owner')
        m = s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'August close', 'FromEmail': 'erin@northwind.example',
                           'FromName': 'Erin Blake', 'SentAt': _at(2), 'BodyText': 'Can you confirm the August numbers before Thursday?',
                           'Status': 'routed', 'TaskId': t})
        rv = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Confirmed - the numbers stand.', 'Status': 'pending'})
        return t, m, rv

    def test_a_sent_reply_moves_the_revision_even_with_no_delivery_receipt(self):
        s = MemoryStore(); t, m, rv = self._asked(s)
        before = advisor.revision(s, 'task', t)
        s._exec("UPDATE review SET Status='approved', DecidedAt=? WHERE ReviewId=?", (_at(), rv))        # DeliveryState stays NULL
        sent = advisor.revision(s, 'task', t)
        self.assertNotEqual(before, sent, 'a decided draft is an act: the line judged before it is not read back over it')
        s._exec("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rv,))
        self.assertNotEqual(sent, advisor.revision(s, 'task', t))

    def test_an_act_that_ran_moves_it_and_a_proposal_waiting_for_its_yes_does_not(self):
        s = MemoryStore(); t, m, rv = self._asked(s)
        a = advisor.revision(s, 'task', t)
        s._exec("INSERT INTO operation (OpId, Kind, TargetKind, TargetId, Status, CreatedAt) VALUES ('op1','task.defer','task',?,'proposed',?)", (t, _at()))
        self.assertEqual(a, advisor.revision(s, 'task', t), 'a proposal is not an act yet')
        s._exec("UPDATE operation SET Status='done' WHERE OpId='op1'")
        self.assertNotEqual(a, advisor.revision(s, 'task', t))

    def test_the_prompt_says_what_was_sent_and_whether_anything_came_since(self):
        s = MemoryStore(); t, m, rv = self._asked(s)
        s._exec("UPDATE review SET Status='approved', DeliveryState='sent', FinalText='Confirmed - the numbers stand.', DecidedAt=? WHERE ReviewId=?", (_at(1), rv))
        line = advisor.sent_line(s, 'task', t)
        self.assertIn('A REPLY WAS ALREADY SENT', line); self.assertIn('Erin Blake', line); self.assertIn('the numbers stand', line)
        self.assertIn('NOTHING HAS COME IN SINCE IT WENT', line)
        llm = brain_saying({'verb': None, 'line': '', 'evidence': []})
        advisor.notice(s, advisor.SHOWN, 'task', t, wait=True, llm=llm)
        self.assertIn('A REPLY WAS ALREADY SENT', llm.calls[0][1], 'the model is given the send as evidence')
        # ...and a word from her after it is the evidence that something is owed again - the model reads which
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Re: August close', 'FromEmail': 'erin@northwind.example',
                       'FromName': 'Erin Blake', 'SentAt': _at(0), 'BodyText': 'And September?', 'Status': 'routed', 'TaskId': t})
        later = advisor.sent_line(s, 'task', t)
        self.assertIn('WRITTEN TO THE OWNER SINCE', later); self.assertIn('And September?', later)
        self.assertEqual(advisor.sent_line(s, 'task', s.create_task({'Title': 'nothing sent'}, 'owner')), '')

    def test_the_demo_advisor_closes_a_reply_that_went_instead_of_answering_it_again(self):
        ask = lambda extra: json.loads(demo.brain()('Answer with JSON only', f'EVENT: item.shown\n\nVERBS OFFERED: reply (Reply), close (Mark done){extra}'))
        self.assertEqual(ask('')['verb'], 'reply')
        self.assertEqual(ask('\n\nA REPLY WAS ALREADY SENT (today) to Erin Blake: "Done."\nNOTHING HAS COME IN SINCE IT WENT.')['verb'], 'close')
        self.assertEqual(ask('\n\nA REPLY WAS ALREADY SENT (today) to Erin Blake: "Done."\nWRITTEN TO THE OWNER SINCE: Erin: more?')['verb'], 'reply')


def test_every_reason_for_no_line_is_a_sentence_with_one_move():
    """advisor.status answers {none: why}; the strip says each as words.json's sentence and lights its move - none goes blank."""
    for why in advisor.REASONS:
        said = words.ADVICE_NONE.get(why)
        assert said and said['line'].strip() and said['move'] in ('next', 'ai'), why
        assert not words.jargon_in(said['line']), (why, said['line'])
