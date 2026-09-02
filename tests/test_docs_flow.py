"""The audit, as tests: every operator document and every standing note has to REACH the prompt
that claims to use it. Nothing here reads code for intent - a unique marker goes into each doc
and each memory scope, the real consumer runs, and either the marker arrives or it does not.

It caught agents.memory_block: it had built a "Standing notes (FOLLOW these)" block since the
day it was written and NOTHING called it, so every verdict the owner gave reached the triage
brain and the reply writer and never the agent doing the work.
"""
import unittest

from taskuary import agents, ingest, outbound, responder, terminal
from taskuary.store import MemoryStore

MARK = {d: f'ZZMARK{d.upper()}ZZ' for d in ('soul', 'coder', 'triage', 'learned', 'style')}
NOTE, OFF = 'ZZMARKNOTEZZ', 'ZZMARKOFFZZ'


def seeded():
    s = MemoryStore()
    s.save_doc('soul', f'You work for **Test Owner**.\n{MARK["soul"]}\nrepo map here.', 'owner')
    s.save_doc('coder', f'# Coder rules\n- {MARK["coder"]}', 'owner')
    s.save_doc('triage', f'Classify one inbound work message. Answer JSON only. {MARK["triage"]}', 'owner')
    # LEARNED.md injects its ACTIVE sections only, so the marker has to live inside one
    s.save_doc('learned', f'## Active\n- {MARK["learned"]} [s:3 | ev: rv1 | seen: 2026-08-01]', 'owner')
    # style_doc holds an untouched template out of prompts, so the marker needs real content
    s.save_doc('style', f'### Tone & length\n- {MARK["style"]}: two sentences, answer first, no preamble.', 'owner')
    s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Note': f'{NOTE} always defer to the finance team',
                  'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
    s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Note': f'{OFF} a switched-off note',
                  'Source': 'verdict', 'Active': 0, 'CreatedBy': 'owner'})
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
        self.assertFlows(seen['p'], [MARK['triage'], MARK['soul'], MARK['learned'], NOTE],
                         forbid=[MARK['coder'], MARK['style']])

    def test_both_reply_paths_get_soul_style_learned_and_the_notes(self):
        s = seeded()
        tid = _task(s, 'reply', 'Can you confirm the date?')
        seen = {}
        responder.draft_reply(s, tid, llm=lambda sysm, usr, **k: (seen.update(p=sysm + usr), 'ok')[1])
        self.assertFlows(seen['p'], [MARK['soul'], MARK['style'], MARK['learned'], NOTE], forbid=[MARK['coder']])
        mid = s.add_message({'ExternalId': 'r2', 'Channel': 'email', 'Subject': 'quick question',
                             'FromEmail': 'a@b.com', 'BodyText': 'Can you confirm the date?', 'Status': 'filed'})
        rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        seen2 = {}
        responder.draft_for_message(s, s.get_message(mid), rid,
                                    llm=lambda sysm, usr, **k: (seen2.update(p=sysm + usr), 'ok')[1])
        self.assertFlows(seen2['p'], [MARK['soul'], MARK['style'], MARK['learned'], NOTE], forbid=[MARK['coder']])

    def test_the_coding_agent_gets_soul_coder_and_the_notes(self):
        """The notes are the part that was missing: an agent was handed the operator rules and
        the coder rules, and none of the verdicts the owner had actually given."""
        s = seeded()
        self.assertFlows(terminal.seed_text(s, _task(s)), [MARK['soul'], MARK['coder'], NOTE])

    def test_task_context_and_the_handoff_writer_carry_them_too(self):
        s = seeded()
        tid = _task(s)
        self.assertFlows(agents.task_context(s, tid), [NOTE])
        seen = {}
        outbound.draft_handoff(s, tid, 'x@y.com', None,
                               llm=lambda sysm, usr, **k: (seen.update(p=sysm + usr), 'ok')[1])
        self.assertFlows(seen['p'], [MARK['soul'], NOTE])

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
        s.add_memory({'Scope': scope, 'ScopeKey': key, 'Note': f'{NOTE} {scope} rule',
                      'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
        return s

    MSG = {'from_email': 'dana@vendor.com', 'subject': 'Resident Refund Request - PAYNE, MICHAEL',
           'body': 'history attached', 'source_name': 'devteam-logs@corp.example'}

    def test_all_five_scopes_match_what_they_claim_to(self):
        for scope, key in (('global', None), ('sender', 'dana@vendor.com'), ('sender_domain', 'vendor.com'),
                           ('subject', 'resident refund request'), ('source', 'devteam-logs@corp.example')):
            with self.subTest(scope=scope):
                self.assertTrue(ingest.notes_for(self._note(scope, key), self.MSG),
                                f'a {scope}-scoped note matched nothing')

    def test_and_none_of_them_matches_an_unrelated_message(self):
        other = {'from_email': 'someone@elsewhere.com', 'subject': 'Directors meeting',
                 'body': 'agenda', 'source_name': 'dana@corp.example'}
        for scope, key in (('sender', 'dana@vendor.com'), ('sender_domain', 'vendor.com'),
                           ('subject', 'resident refund request'), ('source', 'devteam-logs@corp.example')):
            with self.subTest(scope=scope):
                self.assertEqual(ingest.notes_for(self._note(scope, key), other), [])


if __name__ == '__main__':
    unittest.main()


class BlankDocsHeal(unittest.TestCase):
    """CODER.md went blank on a live install and every session ran with no rules. An empty operator
    document carries no intent worth keeping: reading it, saving it blank, or restarting all put
    the shipped default back."""

    def test_a_blank_document_is_the_template_again_on_read(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        server.store.save_doc('coder', '   ', 'owner')
        r = c.get('/api/doc/coder')
        self.assertIn('CODER.md', r.json()['content'])
        self.assertEqual(server.store.doc_owner('coder'), 'template')

    def test_saving_blank_means_give_me_the_default_back(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        r = c.put('/api/doc/coder', json={'content': ''})
        self.assertTrue(r.json().get('restored'))
        self.assertIn('CODER.md', server.store.get_doc('coder'))
