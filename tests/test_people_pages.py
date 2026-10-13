"""A page per person from the outcome ledger (spec 2026-10-12, build step 4): the numbers are the ledger's, the lines
are the model's, the owner's own lines survive."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import counsel, outcomes, people_pages
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
WHO = 'ray@northwind.example'

def brain_saying(text):
    calls = []
    def llm(system, user, max_tokens=400, images=None, want=None, **kw): calls.append(user); return text
    llm.takes_want = False; llm.calls = calls; return llm

def seed(s, n=3):
    for k in range(n):
        t = s.create_task({'Title': f'thread {k}'}, 'owner'); cid = f'c{k}'
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'thread {k}', 'FromEmail': WHO, 'FromName': 'Ray Colton', 'SentAt': ago(days=12), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'Re: thread {k}', 'FromEmail': WHO, 'SentAt': ago(days=6), 'BodyText': 'a', 'Status': 'filed', 'TaskId': t})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': cid, 'mid': 1, 'verb': 'approve', 'who': WHO, 'cc': [], 'chase': k > 0}, at=ago(days=9))
    outcomes.resolve(s)


class PageTests(unittest.TestCase):
    def test_the_facts_are_the_ledgers_numbers(self):
        s = MemoryStore(); seed(s)
        txt = people_pages.facts_text(s, WHO)
        self.assertIn('3 replies', txt); self.assertIn('answered 3', txt); self.assertIn('median', txt)

    def test_compile_writes_the_doc_inside_the_block_and_the_dossier_reads_it(self):
        s = MemoryStore(); seed(s)
        llm = brain_saying('- Ray answers in about 3 days and needs a second chase [ev: out2, out3]\n- Copy nobody; he answers alone')
        name = people_pages.compile(s, WHO, llm=llm)
        self.assertEqual(name, 'person-ray@northwind.example')
        doc = s.get_doc(name)
        self.assertIn('<!-- ledger:start -->', doc); self.assertIn('needs a second chase', doc); self.assertIn('3 replies', doc)
        self.assertIn('median', llm.calls[0]); self.assertIn('out2', llm.calls[0])                 # the numbers and the evidence reach the model
        self.assertIn('needs a second chase', counsel.dossier(s, {'from_email': WHO, 'subject': 'anything'}, calendar=False))

    def test_the_owners_lines_survive_a_recompile(self):
        s = MemoryStore(); seed(s)
        people_pages.compile(s, WHO, llm=brain_saying('- first'))
        s.save_doc(people_pages.doc_name(WHO), 'Ray runs the data team. Call him, do not mail.\n\n' + s.get_doc(people_pages.doc_name(WHO)), 'owner')
        people_pages.compile(s, WHO, llm=brain_saying('- second'))
        doc = s.get_doc(people_pages.doc_name(WHO))
        self.assertIn('Call him, do not mail.', doc); self.assertIn('- second', doc); self.assertNotIn('- first', doc)
        s.save_doc(people_pages.doc_name(WHO), 'Only my words now.', 'owner')                     # the owner cut the block: it comes back at the end
        people_pages.compile(s, WHO, llm=brain_saying('- third'))
        self.assertTrue(s.get_doc(people_pages.doc_name(WHO)).startswith('Only my words now.'))

    def test_refresh_takes_the_people_with_three_rows_and_silence_writes_nothing(self):
        s = MemoryStore(); seed(s)
        other = 'gail@northwind.example'; t = s.create_task({'Title': 'y'}, 'owner')
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c9', 'mid': 1, 'verb': 'approve', 'who': other, 'cc': [], 'chase': False}, at=ago(days=9)); outcomes.resolve(s)
        self.assertEqual(people_pages.refresh(s, llm=brain_saying('- a line')), [WHO])            # one row is no page
        self.assertEqual(people_pages.pages(s)[0]['who'], WHO)
        self.assertIsNone(people_pages.compile(s, other, llm=brain_saying('')))
        with mock.patch.object(people_pages, 'build_llm', return_value=None): self.assertEqual(people_pages.refresh(s), [])


    def test_refresh_skips_the_owner_and_an_auto_replier(self):
        from taskuary import autoreply
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 'test'); seed(s)
        for who in ('alex@northwind.example', 'noreply@vendor.example'):
            for k in range(3):
                t = s.create_task({'Title': 'z'}, 'owner')
                outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'q{who}{k}', 'mid': 1, 'verb': 'approve', 'who': who, 'cc': [], 'chase': False}, at=ago(days=9))
        s.add_message({'ConversationId': 'auto', 'Channel': 'email', 'Subject': 'Automatic reply', 'FromEmail': 'noreply@vendor.example', 'SentAt': ago(days=1), 'BodyText': 'x', 'Status': autoreply.STATUS})
        outcomes.resolve(s)
        self.assertEqual(people_pages.refresh(s, llm=brain_saying('- a line')), [WHO])
