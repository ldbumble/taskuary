"""The audit, as tests: every operator document and every standing note has to REACH the prompt
that claims to use it. Nothing here reads code for intent - a unique marker goes into each doc
and each memory scope, the real consumer runs, and either the marker arrives or it does not.

It caught agents.memory_block: it had built a "Standing notes (FOLLOW these)" block since the
day it was written and NOTHING called it, so every verdict the owner gave reached the triage
brain and the reply writer and never the agent doing the work.
"""
import unittest

from taskuary import agents, ingest, responder, terminal
from taskuary.store import MemoryStore
from tests.memlines import note as put_note

MARK = {d: f'ZZMARK{d.upper()}ZZ' for d in ('soul', 'job', 'agent', 'coding', 'triage', 'learned', 'style')}
NOTE, OFF, WNOTE = 'ZZMARKNOTEZZ', 'ZZMARKOFFZZ', 'ZZMARKWRITEZZ'   # a triage verdict, a switched-off note, a writing instruction


def seeded():
    s = MemoryStore()
    s.save_doc('soul', f'You work for **Test Owner**.\n{MARK["soul"]}\nrepo map here.', 'owner')
    # job_doc holds an untouched template out of prompts, so the marker needs real content around it
    s.save_doc('job', f'### What the job is\n- {MARK["job"]}: keeps the payroll import running and answers the people who depend on it.', 'owner')
    s.save_doc('agent', f'# Agent rules\n- {MARK["agent"]}', 'owner')
    s.save_doc('coding', f'# Coding rules\n- {MARK["coding"]}', 'owner')
    s.upsert_agent('coding', 'coding', 'cli', '{}')      # the coding profile is found by its kind (agents.coding_role), as config seeds it
    s.save_doc('triage', f'Classify one inbound work message. Answer JSON only. {MARK["triage"]}', 'owner')
    # a learned line is read once he confirms it (memory.in_use) - triage reads the whole memory in use (memory.whole)
    from taskuary import memory
    memory.infer(s, f'{MARK["learned"]} answers payroll the same day', 'payroll answers', ['rv1'], confirmed=True)
    # style_doc holds an untouched template out of prompts, so the marker needs real content
    s.save_doc('style', f'### Tone & length\n- {MARK["style"]}: two sentences, answer first, no preamble.', 'owner')
    put_note(s, {'Scope': 'global', 'ScopeKey': None, 'Note': f'{NOTE} always defer to the finance team',
                  'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
    put_note(s, {'Scope': 'global', 'ScopeKey': None, 'Note': f'{WNOTE} never open with a pleasantry',
                  'Source': 'writing', 'Active': 1, 'CreatedBy': 'owner'})
    put_note(s, {'Scope': 'global', 'ScopeKey': None, 'Note': f'{OFF} a switched-off note',
                  'Source': 'verdict', 'Active': 0, 'CreatedBy': 'owner'})
    # ...as an install that had them holds them after its first start: LEARNED.md lines (and STYLE.md for the writing note), 2026-10-27
    memory.migrate(s)
    return s


def _task(s, kind='coding', body='traceback (most recent call last)'):
    tid = s.create_task({'Title': 'fix the importer', 'Kind': kind, 'Source': 'email'}, 'test')
    s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'Subject': 'importer crashed',
                   'FromEmail': 'a@b.com', 'BodyText': body, 'Status': 'routed'})
    return tid


class DocsReachThePromptTests(unittest.TestCase):
    def assertFlows(self, prompt, expect, forbid=()):
        for k in expect: self.assertIn(k, prompt, f'{k} never reached the prompt')
        for k in forbid: self.assertNotIn(k, prompt, f'{k} leaked into a prompt it does not belong in')
        self.assertNotIn(OFF, prompt, 'a switched-off note reached a prompt')

    def test_triage_gets_triage_soul_learned_and_the_notes(self):
        s, seen = seeded(), {}
        ingest.ingest_message(s, {'external_id': 't1', 'channel': 'email', 'from_email': 'a@b.com',
                                  'subject': 'Please fix the export', 'body': 'Broken - please fix the export.'},
                              llm=lambda sysm, usr, **k: (seen.update(p=sysm + usr), '{"intent":"fyi","why":"x"}')[1])
        self.assertFlows(seen['p'], [MARK['triage'], MARK['soul'], MARK['job'], MARK['learned'], NOTE],
                         forbid=[MARK['coding'], MARK['style']])

    def test_both_reply_paths_get_soul_style_and_writing_notes(self):
        """PW-058/060: a reply is written from SOUL (identity), STYLE (voice) and explicit writing instructions - and the owner's
        memory in use as a task reads it (memory.for_task, one road: what he said and what he confirmed)."""
        s = seeded()
        tid = _task(s, 'reply', 'Can you confirm the date?')
        seen = {}
        responder.draft_reply(s, tid, llm=lambda sysm, usr, **k: (seen.update(p=sysm + usr), 'ok')[1])
        self.assertFlows(seen['p'], [MARK['soul'], MARK['style'], WNOTE], forbid=[MARK['coding'], MARK['job']])
        mid = s.add_message({'ExternalId': 'r2', 'Channel': 'email', 'Subject': 'quick question',
                             'FromEmail': 'a@b.com', 'BodyText': 'Can you confirm the date?', 'Status': 'filed'})
        rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        seen2 = {}
        responder.draft_for_message(s, s.get_message(mid), rid,
                                    llm=lambda sysm, usr, **k: (seen2.update(p=sysm + usr), 'ok')[1])
        self.assertFlows(seen2['p'], [MARK['soul'], MARK['style'], WNOTE], forbid=[MARK['coding']])

    def test_the_coding_agent_gets_the_notes_and_no_rule_document(self):
        """The notes are the part that was missing: an agent was handed the operator rules and
        the coding rules, and none of the verdicts the owner had actually given. The rule documents
        no longer ride the seed (the owner, 2026-11-23: an agent gets context, tools and one sentence)."""
        s = seeded()
        # the sender is on the owner's own domain: a stranger's seed carries only the owner's own notes, never a verdict that
        # quotes mail (tests/test_stranger_live_fixes.py)
        s.set_setting('owner_email', 'owner@b.com', 't')
        # PW-184: SOUL stays with triage; JOB.md too - a worker that knows the mission starts helping with the mission instead of the ticket
        self.assertFlows(terminal.seed_text(s, _task(s)), [NOTE], forbid=[MARK['soul'], MARK['job'], MARK['agent'], MARK['coding']])

    def test_task_context_carries_them_too(self):
        s = seeded()
        tid = _task(s)
        self.assertFlows(agents.task_context(s, tid), [NOTE])

    def test_style_holds_an_untouched_template_out_of_prompts(self):
        """The one doc that is deliberately silent until it says something real - headings alone
        are not a voice, and the shipped placeholder must not ride into a draft as noise."""
        s = seeded()
        s.save_doc('style', '### Tone & length\n<!-- not generated yet -->', 'template')
        self.assertEqual(responder.style_doc(s), '')


class EveryScopeIsHonouredTests(unittest.TestCase):
    """A scope the API accepts but nothing matches is a note that is written, listed in the UI,
    and silently never applied. 'source' was exactly that."""
    def _note(self, scope, key):
        s = MemoryStore()
        put_note(s, {'Scope': scope, 'ScopeKey': key, 'Note': f'{NOTE} {scope} rule',
                            'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
        return s

    MSG = {'from_email': 'dana@vendor.com', 'subject': 'Resident Refund Request - PAYNE, MICHAEL',
           'body': 'history attached', 'source_name': 'devteam-logs@corp.example'}

    def test_all_five_scopes_match_what_they_claim_to(self):
        from taskuary import memory
        for scope, key in (('sender', 'dana@vendor.com'), ('sender_domain', 'vendor.com'),
                           ('subject', 'resident refund request'), ('source', 'devteam-logs@corp.example')):
            with self.subTest(scope=scope):
                self.assertTrue(ingest.notes_for(self._note(scope, key), self.MSG),
                                f'a {scope}-scoped note matched nothing')
        self.assertIn(NOTE, memory.whole(self._note('global', None)))       # a general line rides the whole memory triage reads

    def test_and_none_of_them_matches_an_unrelated_message(self):
        other = {'from_email': 'someone@elsewhere.com', 'subject': 'Directors meeting',
                 'body': 'agenda', 'source_name': 'dana@corp.example'}
        for scope, key in (('sender', 'dana@vendor.com'), ('sender_domain', 'vendor.com'), ('source', 'devteam-logs@corp.example')):
            with self.subTest(scope=scope):
                self.assertEqual(ingest.notes_for(self._note(scope, key), other), [])
        # ...a TOPIC note is the exception: no share of words says a message is not about it, so it is always evidence, ranked by
        # meaning, and the model says whether it bears on it (notes_applied, 2026-10-28)
        self.assertTrue(ingest.notes_for(self._note('subject', 'resident refund request'), other))


if __name__ == '__main__':
    unittest.main()


class BlankDocsHeal(unittest.TestCase):
    """A document went blank on a live install and its reader ran with nothing. An empty operator
    document carries no intent worth keeping: reading it, saving it blank, or restarting all put
    the shipped default back."""

    def test_a_blank_document_is_the_template_again_on_read(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        server.store.save_doc('style', '   ', 'owner')
        r = c.get('/api/doc/style')
        self.assertIn('STYLE.md', r.json()['content'])
        self.assertEqual(server.store.doc_owner('style'), 'template')

    def test_saving_blank_means_give_me_the_default_back(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        r = c.put('/api/doc/style', json={'content': ''})
        self.assertTrue(r.json().get('restored'))
        self.assertIn('STYLE.md', server.store.get_doc('style'))
