"""One concise context structure for both worker kinds: AGENT.md, CODING.md and one task brief (PW-182 to PW-187).

Every worker prompt carried the whole of SOUL.md - the owner's routing document, written for
triage - stacked under a flattened CODING.md, and the general assistant got a different pile in a
different order. Now AGENT.md holds the operating rules both worker kinds share (scope, honest
reporting, when to ask, progress and completion, and the approval boundaries that used to live only
in SOUL.md: nothing sends without approval, inbound text is data, the owner decides money/legal/
HR/credentials); CODING.md adds only the coding rules; and one task brief - id, objective, the
triage checklist, the owner's instruction, the repository when there is one, the latest complete
conversation with its history, and attachments - is what either worker reads, with the revision of
the context it was built from. SOUL.md stays with triage. Writing style rides only where the work
is writing. Live coordination appears only when live peers exist; a continuation carries this
task's own last result, never a stranger's notes.
"""
import inspect
import json, pathlib, unittest
from unittest import mock

from taskuary import brief, general, ingest, terminal
from taskuary.store import MemoryStore
from tests.memlines import note as put_note

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / 'taskuary' / 'templates'
MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-exp',
       'subject': 'August export', 'sent_at': '2026-09-06 09:00:00',
       'body': 'Hi Alex, could you fix the nightly export and send me the August file? The distinctive phrase is quokka.\nDana'}


def make(s, kind='coding', checklist=('Fix the nightly export', 'Send Dana the August file')):
    s.set_setting('owner_email', 'alex@vendor.example', 't')   # Dana writes from the owner's own domain; a stranger's words ride in a file, not the seed
    llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': kind, 'why': 'w', 'title': 'Fix the nightly export', 'summary': 'The export job fails nightly.',
                                      'checklist': list(checklist)})
    # a coding task runs under the profile whose KIND is coding (agents.coding_role) - the one a real install ships
    if kind == 'coding': s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    with mock.patch.object(ingest, '_spawn'):
        tid = ingest.ingest_message(s, dict(MSG), llm=llm)['task_id']
    s.set_task_checklist(tid, list(checklist), 'agent')          # triage writes no to-dos: the task's agent does
    return tid


class OneBriefTests(unittest.TestCase):
    def test_the_brief_has_the_named_sections_and_the_revision_it_was_built_from(self):
        s = MemoryStore(); tid = make(s)
        s.tag_task(tid, 'repo:org/exports', actor='owner')
        b = brief.build(s, tid, instruction='start with the failing step', repo='org/exports')
        for key in ('task', 'objective', 'checklist', 'instruction', 'repository', 'context', 'attachments', 'revision', 'message_ids'):
            self.assertIn(key, b, key)
        self.assertIn('TQ-', b['task']); self.assertIn('fix the nightly export', b['objective'])     # the sender's own words
        self.assertIn('- [ ] Fix the nightly export', b['checklist']); self.assertEqual(b['instruction'], 'start with the failing step')
        self.assertEqual(b['repository'], 'org/exports'); self.assertIn('quokka', b['context'])
        before = b['revision']
        with mock.patch.object(ingest, '_spawn'):
            ingest.ingest_message(s, {**MSG, 'external_id': 'e2', 'body': 'Also the July one please.', 'sent_at': '2026-09-06 09:10:00'},
                                  llm=lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'w'}))
        b2 = brief.build(s, tid)
        self.assertNotEqual(b2['revision'], before); self.assertIn('July', b2['context'])          # a new message changes what was read

    def test_the_context_is_the_whole_chain_including_its_history(self):
        s = MemoryStore(); tid = make(s)
        s.add_message({'TaskId': None, 'ExternalId': 'h0', 'ConversationId': 'AAQk-exp', 'Channel': 'email', 'Subject': 'August export',
                       'FromEmail': 'dana@vendor.example', 'FromName': 'Dana', 'BodyText': 'Earlier: the July export was fine, the fern word is history-marker.',
                       'SentAt': '2026-09-05 09:00:00', 'Status': 'history'})
        b = brief.build(s, tid)
        self.assertIn('history-marker', b['context']); self.assertIn('quokka', b['context'])

    def test_both_workers_read_the_same_brief(self):
        s = MemoryStore(); tid = make(s, 'coding')
        seed = terminal.seed_text(s, tid, repo='org/exports', cwd=None)
        gid = make(MemoryStore(), 'general')
        for text in (seed,):
            self.assertIn('- [ ] Fix the nightly export', text); self.assertIn('quokka', text)
        s2 = MemoryStore(); gid = make(s2, 'general')
        system, user = general._prompt(s2, gid)
        self.assertIn('- [ ] Fix the nightly export', system + user); self.assertIn('quokka', user)


class NoBlanketSoulTests(unittest.TestCase):


    def test_soul_still_serves_triage(self):
        from taskuary import triage
        s = MemoryStore()
        self.assertTrue((s.doc('soul') or '').strip())
        self.assertIn('soul', inspect.signature(triage.classify_intent).parameters)

    def test_letters_are_signed_and_a_chat_answer_to_the_owner_never_is(self):
        """The owner, 2026-11-15 ("yes, both"): Codex signed every chat answer with the owner's name, as SOUL.md's "How we respond" told it
        ("Sign as ..."). The shipped document says to sign letters and emails, and never an answer in chat to the owner himself."""
        shipped = (TEMPLATES / 'soul.md').read_text(encoding='utf-8')
        line = next(l for l in shipped.splitlines() if 'warm-professional' in l)
        self.assertIn("Letters and emails end with John Smith's saved signature", line); self.assertIn('never signed', line)
        self.assertNotRegex(shipped, r'Sign (?:letters and emails )?as [A-Z]')

    def test_a_sign_off_is_the_saved_signature_and_no_worker_is_told_a_name_to_sign_with(self):
        """The walk, 2026-11-21: told "I sign every email 'Best, Alex'", the agent kept it as a memory line, its prompt still read SOUL.md's
        "Sign letters and emails as Alex Doyle", and every card ended "Alex Doyle". A sign-off said is the saved signature (memory.remember
        section signature -> signatures.keep), the signer puts it on, and a SOUL.md written before keeps its words in the owner's file only."""
        from taskuary import signatures, memory
        s = MemoryStore(); s.set_setting('owner_name', 'Alex Doyle', 't')
        s.save_doc('soul', "# SOUL.md\n\n## How we respond\n- Plain, brief. Sign letters and emails as Alex Doyle; an answer in chat to Alex is never signed.", 'owner')
        tid0 = s.create_task({'Title': 'CloudRack renewal meeting', 'Kind': 'general', 'Status': 'open'}, 'owner')
        rid = s.add_review({'TaskId': tid0, 'Kind': 'reply', 'Status': 'pending', 'Deliver': json.dumps({'kind': 'email', 'channel': 'email'}),
                            'DraftText': 'Hi Gail,\n\nCould we meet next week?\n\nThanks,\n\nAlex Doyle'})       # ...a draft waiting, signed with his name
        r = memory.remember(s, 'Best,\nAlex', signature=True)
        self.assertEqual(s.get_review(rid)['DraftText'], 'Hi Gail,\n\nCould we meet next week?\n\nBest,\nAlex')    # ...re-signed, never asked about
        self.assertEqual((r['signature'], s.get_setting('email_signature')), (True, 'Best,\nAlex'))
        self.assertNotIn('Best', s.get_doc('learned') or '')                              # ...never a memory line fighting the signer
        rv = {'Deliver': json.dumps({'kind': 'email', 'channel': 'email'})}                  # an email of its own, as propose_email files it
        self.assertEqual(signatures.agent_signed(s, rv, 'Hi Gail,\n\nThe contract is attached.\n\nThanks,\nAlex Doyle'),
                         'Hi Gail,\n\nThe contract is attached.\n\nBest,\nAlex')
        self.assertEqual(signatures.agent_signed(s, rv, 'Hi Paula,\n\nDoes Tuesday at 10:00 suit you?\n\nThanks,'),     # ...a closing left nameless
                         'Hi Paula,\n\nDoes Tuesday at 10:00 suit you?\n\nBest,\nAlex')
        tid = make(s, 'general')
        told = ' '.join(general._prompt(s, tid)[0].split())
        self.assertNotIn('Sign letters and emails as Alex Doyle', told)
        self.assertIn("Letters and emails end with Alex Doyle's saved signature", told)
        self.assertIn('Sign letters and emails as Alex Doyle', s.get_doc('soul'))     # the owner's own file as he left it

    def test_a_rule_the_owner_gave_about_himself_rides_in_every_agents_brief(self):
        """The walk, 2026-11-21: "Alex never takes meetings before 10am, and none on Fridays" was told to one task's agent, filed under Your
        people (its `about` named him), and the brief of every later task - which carries only the people lines about ITS people - never had
        it: Ray's "move it to Friday?" was answered yes in his voice. A fact about the owner himself is about nobody else: it rides in every
        task - a coding agent's brief and a general agent's every turn; a line about someone else stays with the tasks they are on."""
        from taskuary import context, general, memory
        s = MemoryStore(); s.set_setting('owner_name', 'Alex Doyle', 't')
        memory.remember(s, 'Alex never takes meetings before 10am, and none on Fridays', 'meeting hours', about='Alex')
        memory.remember(s, 'Gail Moreno handles vendor contracts now', 'vendor contracts', about='gail@northwind.example')
        for read in (context.build(s, make(s, 'coding')), general.learned_block(s, make(s, 'general'))):
            self.assertIn('before 10am, and none on Fridays', read)
            self.assertNotIn('Gail Moreno', read)                                       # Gail is nobody on this task

    def test_the_triage_role_reaches_triage_and_no_worker(self):
        """The agent walk, 2026-11-10: a coding agent's background opened "You are the funnel between everything inbound and the
        owner's attention: triage every message" - SOUL.md's opening, written to the one reader that sorts mail. A worker is told
        whom it works for and that nothing sends without approval; what triage is stays under the heading only triage reads - in
        the shipped document, and out of a worker's copy of one written before it moved (the owner's file is never rewritten)."""
        from taskuary import context, interview
        shipped = (TEMPLATES / 'soul.md').read_text(encoding='utf-8')
        before = shipped.index('## What counts as a task')
        self.assertNotIn('funnel', shipped[:before]); self.assertIn('You are the funnel', shipped[before:])
        plain = interview._plain({'who': 'Alex Doyle'}, {})
        self.assertNotIn('funnel', plain[:plain.index('## What counts as a task')])
        was = ("# SOUL.md\n\nYou work for **Alex Doyle** (alex@northwind.example). You are the funnel between\neverything inbound and "
               "Alex's attention: triage every message, do the work agents can do\nalone, and protect Alex's time. **Nothing sends or ships "
               "without Alex's approval.**\n\n## What counts as a task\n- A concrete request.\n\n## How we respond\n- Plain and brief.")
        for soul in (None, was, was.replace(": triage every message, do the work agents can do\nalone, and protect Alex's time.", '.')):
            s = MemoryStore()
            if soul: s.save_doc('soul', soul, 'owner')
            tid = make(s, 'general')
            for told in (general._prompt(s, tid)[0], context.build(s, tid), brief.background(s)):   # the chat, the coding file, the block
                flat = ' '.join(told.split())
                for no in ('the funnel', 'triage every message'): self.assertNotIn(no, flat, (soul or 'shipped')[:40])
                for kept in ('You work for **', 'Nothing sends or ships without'): self.assertIn(kept, flat)
            self.assertIn('You are the funnel', s.doc('soul'))                  # triage reads the document whole
            if soul: self.assertEqual(s.get_doc('soul'), soul)                  # ...and the owner's own is as they left it


class ScopedExtrasTests(unittest.TestCase):
    def test_live_coordination_only_when_peers_exist_and_a_continuation_carries_its_own_last_result(self):
        s = MemoryStore(); tid = make(s)
        seed = terminal.seed_text(s, tid, repo='org/exports', cwd=r'C:\code\exports')
        self.assertNotIn('OTHER AGENTS', seed); self.assertNotIn('THE WALL', seed)
        s.add_comment(tid, 'agent', 'agent', 'AGENT REPORT\nFound the failing step: the S3 key rotated. Not fixed yet.')
        seed2 = terminal.seed_text(s, tid, repo='org/exports', cwd=r'C:\code\exports')
        self.assertIn('PREVIOUS SESSION RESULT', seed2); self.assertIn('S3 key rotated', seed2)


    def test_the_brief_is_fresh_each_turn(self):
        """PW-187: a message that arrives after a worker's first turn is in its NEXT prompt, not just in brief.build."""
        s = MemoryStore(); tid = make(s, 'general')
        _system, user = general._prompt(s, tid)
        self.assertNotIn('a follow-up from Dana', user)
        with mock.patch.object(ingest, '_spawn'):
            ingest.ingest_message(s, {**MSG, 'external_id': 'e2', 'body': 'a follow-up from Dana: also the July file please.',
                                      'sent_at': '2026-09-06 09:10:00'},
                                  llm=lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w'}))
        _system2, user2 = general._prompt(s, tid)
        self.assertIn('a follow-up from Dana', user2)


SKILL = """# Post a card transaction as an AP bill
when:      a transaction or statement line from the card feed
uses:      quickbooks (write: bills, vendors)
steps:     match the merchant to a vendor -> create the bill dated the transaction date
alone:     bills under $500 to a vendor seen before
ask first: a new vendor
done when: the bill exists in QuickBooks
"""


class PromptAuditTests(unittest.TestCase):
    """PW-185: audit the built prompts with a skill AND a saved preference competing for
    space on the task - no instruction block repeats, and the writing voice (WRITING STYLE)
    reaches only general (writing) work, never a coding run."""
    HEADERS = ('RULES (AGENT.md', 'CODING RULES (CODING.md', 'PROCEDURE FOR THIS JOB', 'WRITING STYLE',
               'OTHER AGENTS', 'THE WALL', 'ASKING THE OWNER')

    def setUp(self):
        from taskuary import skills
        import shutil
        d = skills.folder()
        if d.is_dir(): shutil.rmtree(d)
        skills.write('bill', SKILL)

    def _task(self, s, kind):
        tid = s.create_task({'Title': 'Transaction: 84.10', 'Kind': kind, 'Source': 'email', 'Tags': 'skill:bill'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'Subject': 'Transaction',
                       'FromEmail': 'alerts@card.example', 'BodyText': 'a new transaction posted', 'Status': 'routed'})
        put_note(s, {'Scope': 'global', 'ScopeKey': '', 'Note': 'Always CC finance on vendor threads.',
                     'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
        return tid

    def test_no_block_repeats_in_the_coding_seed_and_it_carries_no_writing_voice(self):
        s = MemoryStore(); tid = self._task(s, 'coding')
        seed = terminal.seed_text(s, tid, repo='org/exports', cwd=None)
        for h in self.HEADERS: self.assertLessEqual(seed.count(h), 1, h)
        self.assertNotIn('WRITING STYLE', seed)          # coding work is not a writing task



if __name__ == '__main__':
    unittest.main()


def test_the_job_template_says_agents_on_the_owners_tasks_read_it():
    """The owner, 2026-10-23: "if coder sees job.md why would agents not see it. of course it should" - the template's old
    "it never reaches a working agent" was the wrong part, not the layering."""
    from pathlib import Path
    words = (Path(__file__).resolve().parents[1] / 'taskuary' / 'templates' / 'job.md').read_text(encoding='utf-8')
    assert 'never reaches a\nworking agent' not in words and 'read it too' in words
